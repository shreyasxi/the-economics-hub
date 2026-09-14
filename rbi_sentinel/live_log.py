"""
rbi_sentinel/live_log.py

The live test of whether Resolution tone lines up with the 10-year G-sec on
decision day.

Every historical meeting predates the scoring model's training cutoff, so its
score may carry hindsight about how markets reacted. Meetings from October
2026 are scored as they happen. For each one this log records the Resolution's
tone change and the time it was scored, and the automated workflow commits
that row to git before the bond market closes — the commit time is a public
record that the score existed before the day's move was known. The 10-year
close is added afterwards.

Files (both tracked in git):
  data/rbi_live_log.csv      one row per live meeting, written by the pipeline
  data/rbi_live_market.csv   10-year closes supplied by hand when no automatic
                             source returns them: decision_date,previous_close,close,source
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from rbi_sentinel.cleaners.policy_facts import extract_policy_facts
from rbi_sentinel.config import DATA_DIR
from rbi_sentinel.db import manager as db

log = logging.getLogger("rbi_sentinel.live_log")

LIVE_TEST_START = "2026-10-01"          # first meeting after the model's training cutoff
LOG_PATH = DATA_DIR / "rbi_live_log.csv"
MARKET_FEED_PATH = DATA_DIR / "rbi_live_market.csv"
IST = timezone(timedelta(hours=5, minutes=30))
GSEC_CLOSE_IST = (17, 0)                # G-sec market closes 17:00 IST
# Written when a close is missing, so the workflow can open a GitHub issue.
NEEDS_INPUT_PATH = Path(os.environ.get("RBI_NEEDS_INPUT_FILE", DATA_DIR.parent / "output" / "rbi_needs_input.md"))

COLUMNS = [
    "policy_cycle", "decision_date", "resolution_url",
    "resolution_scored_at_utc", "scored_at_ist", "scored_before_close",
    "tone", "previous_tone", "tone_change",
    "rate_action", "rate_change_bps", "stated_stance", "previous_stated_stance",
    "y10_previous_close", "y10_close", "y10_change_bps", "y10_source",
    "logged_at_utc",
]


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write(rows: list[dict]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def record_decision_day_tone() -> bool:
    """
    Log the newest cycle's Resolution tone once it has been scored. Returns True
    if a row was added. Cycles before LIVE_TEST_START are never logged.
    """
    latest = db.get_live_resolution_scores()
    if not latest or latest["policy_cycle"] < LIVE_TEST_START:
        return False
    rows = _read(LOG_PATH)
    if any(r["policy_cycle"] == latest["policy_cycle"] for r in rows):
        return False

    scored_utc = datetime.strptime(latest["scored_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    scored_ist = scored_utc.astimezone(IST)
    close_ist = datetime.combine(date.fromisoformat(latest["policy_cycle"]),
                                 datetime.min.time().replace(hour=GSEC_CLOSE_IST[0], minute=GSEC_CLOSE_IST[1]), IST)
    before_close = scored_ist < close_ist

    prev_tone = latest.get("previous_score")
    stance = extract_policy_facts(latest["resolution_text"])["stated_stance"]
    prev_stance = extract_policy_facts(latest["previous_resolution_text"])["stated_stance"] \
        if latest.get("previous_resolution_text") else None
    rows.append({
        "policy_cycle": latest["policy_cycle"],
        "decision_date": latest["policy_cycle"],
        "resolution_url": latest["source_url"],
        "resolution_scored_at_utc": scored_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "scored_at_ist": scored_ist.strftime("%Y-%m-%d %H:%M"),
        "scored_before_close": "yes" if before_close else "no",
        "tone": f"{latest['score']:.4f}",
        "previous_tone": f"{prev_tone:.4f}" if prev_tone is not None else "",
        "tone_change": f"{latest['score'] - prev_tone:+.4f}" if prev_tone is not None else "",
        "rate_action": latest.get("rate_action") or "",
        "rate_change_bps": "" if latest.get("rate_change_bps") is None else str(latest["rate_change_bps"]),
        "stated_stance": stance or "",
        "previous_stated_stance": prev_stance or "",
        "logged_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write(rows)
    log.info(
        "Live log: %s tone %+.3f (change %s), scored %s IST — %s the 17:00 close",
        latest["policy_cycle"], latest["score"],
        rows[-1]["tone_change"] or "n/a", rows[-1]["scored_at_ist"],
        "before" if before_close else "AFTER",
    )
    if not before_close:
        log.warning("Scored after the close: this meeting cannot count as a clean live test")
    return True


def fetch_ten_year_close(decision_date: str) -> Optional[tuple[float, float, str]]:
    """
    (previous_close, close, source) for the benchmark 10-year G-sec on the
    decision date, from an automatic source.

    No sanctioned programmatic source is wired in yet: FBIL and CCIL publish the
    data only through interactive web pages. Returning None routes the request
    to data/rbi_live_market.csv and a GitHub issue asking for the figure.
    """
    return None


def _from_market_feed(decision_date: str) -> Optional[tuple[float, float, str]]:
    for r in _read(MARKET_FEED_PATH):
        if r.get("decision_date") == decision_date and r.get("close") and r.get("previous_close"):
            return float(r["previous_close"]), float(r["close"]), r.get("source") or "manual"
    return None


def record_market_closes(today: Optional[date] = None) -> list[str]:
    """
    Fill the 10-year close for logged meetings whose decision day has ended.
    Returns the decision dates still waiting for a figure.
    """
    today = today or datetime.now(IST).date()
    rows = _read(LOG_PATH)
    waiting, changed = [], False
    for r in rows:
        if r.get("y10_close"):
            continue
        d = r["decision_date"]
        close_time = datetime.combine(date.fromisoformat(d), datetime.min.time().replace(hour=17, minute=30), IST)
        if datetime.now(IST) < close_time and date.fromisoformat(d) >= today:
            continue                              # market has not closed yet
        got = fetch_ten_year_close(d) or _from_market_feed(d)
        if not got:
            waiting.append(d)
            continue
        prev_close, close, source = got
        r.update({
            "y10_previous_close": f"{prev_close:.4f}", "y10_close": f"{close:.4f}",
            "y10_change_bps": f"{(close - prev_close) * 100:+.1f}", "y10_source": source,
        })
        changed = True
        log.info("Live log: %s 10-year %.3f → %.3f (%s bps, %s)", d, prev_close, close, r["y10_change_bps"], source)
    if changed:
        _write(rows)

    if waiting:
        NEEDS_INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        NEEDS_INPUT_PATH.write_text(
            "The RBI Sentinel live test needs the benchmark 10-year G-sec closing yield for:\n\n"
            + "".join(f"- **{d}** — and the close on the previous trading day\n" for d in waiting)
            + "\nAdd one line per date to `data/rbi_live_market.csv` and commit it:\n\n"
            "```\ndecision_date,previous_close,close,source\n"
            + "".join(f"{d},<previous day close>,<decision day close>,<where it came from>\n" for d in waiting)
            + "```\n\nThe next scheduled run fills the log and closes this issue.\n",
            encoding="utf-8",
        )
        log.warning("Live log: 10-year close needed for %s — see %s", ", ".join(waiting), NEEDS_INPUT_PATH)
    elif NEEDS_INPUT_PATH.exists():
        NEEDS_INPUT_PATH.unlink()
    return waiting
