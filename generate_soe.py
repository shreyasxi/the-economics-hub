"""
Economics Hub — RBI Bulletin, State of the Economy (India tab)

Reads the RBI's monthly article and produces the two things the India tab uses:

  soe.json                    the opening summary and concluding assessment,
                              written into an India edition folder and published
                              with that edition's charts, exactly as
                              generate_news.py does for the weekly headlines;
  data/rbi_transmission.csv   Table IV.3 across editions: how much of each
                              policy rate move has reached bank deposit and
                              lending rates. Tracked in git, one row per
                              edition and cycle, and read by generate_india.py.

Usage:
  python generate_soe.py                         # latest edition -> newest India edition folder + history
  python generate_soe.py --out output/india/2026-09
  python generate_soe.py --month 2026-07         # one past edition
  python generate_soe.py --history               # rebuild the transmission history, no soe.json
  python generate_soe.py --no-cache              # ignore the local page cache

The briefing never blocks the India charts: a fetch that fails leaves the
edition without soe.json, and the tab simply shows no briefing. The transmission
history is different — a table that is present but unreadable stops the run,
because a misread column would put wrong basis points on a chart.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.soe_settings import (
    BRIEFING_FILENAME, MAX_EDITION_AGE_DAYS, PAUSE_SECONDS, PROJECT_ROOT, TRANSMISSION_CSV,
)
from data.rbi_soe import Edition, SoeError, build_session, fetch_article, find_latest, find_month, \
    parse_briefing, parse_transmission

INDIA_OUTPUT = PROJECT_ROOT / "output" / "india"
SENTINEL_DB = PROJECT_ROOT / "data" / "rbi_sentinel.db"

CSV_COLUMNS = [
    "month", "published", "cycle_type", "cycle_start", "cycle_end",
    "repo_bps", "wadtdr_fresh_bps", "wadtdr_outstanding_bps", "eblr_bps",
    "mclr_bps", "walr_fresh_bps", "walr_outstanding_bps", "overall_bps", "url",
]


# ═══════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════

def _rel(path: Path) -> str:
    """A path as the project sees it, for printing; absolute when it sits outside."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def latest_edition_folder(base: Path = INDIA_OUTPUT) -> Path | None:
    """
    The newest India edition folder that already holds charts.

    Same rule as the weekly headlines: never create a folder, because an edition
    folder without charts would hide the published ones from the dashboard.
    """
    if not base.exists():
        return None
    folders = sorted((p for p in base.iterdir() if p.is_dir() and any(p.glob("*.png"))),
                     key=lambda p: p.name)
    return folders[-1] if folders else None


def month_range(start: str, end: str) -> list[str]:
    """Every month from start to end inclusive, as "YYYY-MM"."""
    out, (year, mon) = [], (int(start[:4]), int(start[5:]))
    while f"{year:04d}-{mon:02d}" <= end:
        out.append(f"{year:04d}-{mon:02d}")
        year, mon = (year + 1, 1) if mon == 12 else (year, mon + 1)
    return out


def read_history(path: Path = TRANSMISSION_CSV) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    missing = [c for c in CSV_COLUMNS if rows and c not in rows[0]]
    if missing:
        raise SoeError(f"{path.name} is missing columns {missing}; it was not written by this script")
    return rows


def write_history(rows: list[dict], path: Path = TRANSMISSION_CSV) -> None:
    """One row per edition and cycle, oldest first, so the file diffs cleanly."""
    rows = sorted(rows, key=lambda r: (r["month"], r["cycle_start"], r["cycle_type"]))
    with path.open("w", newline="", encoding="utf-8") as fh:
        # Unix line endings: the file is tracked, and csv's default \r\n would
        # rewrite every line on a machine that checks out LF.
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in CSV_COLUMNS})


def history_rows(edition: Edition, briefing: dict, transmission: dict) -> list[dict]:
    return [
        {
            "month": edition.month,
            "published": briefing["published"],
            "url": edition.url,
            **{c: cycle.get(c, "") for c in CSV_COLUMNS
               if c not in {"month", "published", "url"}},
        }
        for cycle in transmission["cycles"]
    ]


# ── Cross-check: RBI's repo column against the Sentinel's own rate history ──

def repo_change_bps(cycle_start: str, cycle_end: str, db: Path = SENTINEL_DB) -> int | None:
    """
    The repo rate change over a cycle, from data/rbi_sentinel.db.

    The Sentinel records the repo rate at every MPC cycle, so RBI's own repo
    column in the transmission table can be checked against it. Returns None when
    the database cannot answer (no file, or no rate before the cycle started).
    """
    if not db.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            rates = sorted({
                (row[0], row[1]) for row in conn.execute(
                    "SELECT policy_cycle, repo_rate_pct FROM mpc_meetings "
                    "WHERE repo_rate_pct IS NOT NULL AND policy_cycle IS NOT NULL"
                )
            })
    except sqlite3.Error:
        return None

    before = [rate for cycle, rate in rates if cycle < f"{cycle_start}-01"]
    after = [rate for cycle, rate in rates if cycle <= f"{cycle_end}-31"]
    if not before or not after:
        return None
    return int(round((after[-1] - before[-1]) * 100))


def check_repo_column(rows: list[dict]) -> list[str]:
    """RBI's repo figures against the Sentinel's. A disagreement is a problem, not a warning."""
    problems = []
    for row in rows:
        stated = int(row["repo_bps"])
        ours = repo_change_bps(row["cycle_start"], row["cycle_end"])
        if ours is not None and ours != stated:
            problems.append(
                f"{row['month']}: RBI's table says the repo rate moved {stated} bps over "
                f"{row['cycle_start']} to {row['cycle_end']}, the Sentinel's rate history says {ours}"
            )
    return problems


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="RBI Bulletin, State of the Economy, for the India tab")
    parser.add_argument("--out", type=Path, help="India edition folder to write soe.json into "
                                                 "(default: the newest edition that has charts)")
    parser.add_argument("--month", help="one edition, as 2026-07 (default: the latest published)")
    parser.add_argument("--history", action="store_true",
                        help="rebuild the transmission history from the archive; writes no soe.json")
    parser.add_argument("--from", dest="since", metavar="YYYY-MM",
                        help="with --history, the first edition to read (default: the editions "
                             "the current cycle covers)")
    parser.add_argument("--no-cache", action="store_true", help="re-read pages instead of using the local cache")
    args = parser.parse_args()

    session = build_session()
    use_cache = not args.no_cache
    problems: list[str] = []

    # ── The edition ────────────────────────────────────────────────────────────
    try:
        edition = find_latest(session) if not args.month else find_month(session, args.month)
        if edition is None:
            print(f"No State of the Economy in the {args.month} Bulletin.")
            return 1
        page = fetch_article(session, edition, use_cache=use_cache)
        briefing = parse_briefing(page, edition)
        transmission = parse_transmission(page)
    except SoeError as exc:
        print(f"Could not read the article: {exc}")
        return 1

    published = date.fromisoformat(briefing["published"])
    age = (date.today() - published).days
    print(f"State of the Economy, {published:%B %Y} (published {published:%d %b %Y}, {age} days ago)")
    print(f"   {edition.url}")
    print(f"   Summary: {len(briefing['summary'].split())} words; "
          f"conclusion: {len(briefing['conclusion'])} paragraph(s)")
    if age > MAX_EDITION_AGE_DAYS:
        problems.append(f"the newest edition is {age} days old; an edition has been missed")

    # ── The transmission history ───────────────────────────────────────────────
    history = {(row["month"], row["cycle_type"], row["cycle_start"]): row for row in read_history()}

    if transmission is None:
        print("   No transmission table in this edition.")
    else:
        for row in history_rows(edition, briefing, transmission):
            history[(row["month"], row["cycle_type"], row["cycle_start"])] = row
        current = transmission["cycles"][-1]
        print(f"   Transmission: {current['cycle_type']} cycle {current['cycle_start']} to "
              f"{current['cycle_end']}, repo {current['repo_bps']} bps, "
              f"fresh loans {current['walr_fresh_bps']} bps, "
              f"fresh deposits {current['wadtdr_fresh_bps']} bps")

    if args.history:
        current_start = max((row["cycle_start"] for row in history.values()), default=None)
        if current_start is None:
            print("Nothing to backfill: no cycle has been read yet.")
            return 1
        first = args.since or current_start
        wanted = [m for m in month_range(first, edition.month)
                  if not any(key[0] == m for key in history)]
        print(f"\nBackfilling {len(wanted)} edition(s) from {first}")
        for month in wanted:
            time.sleep(PAUSE_SECONDS)
            try:
                past = find_month(session, month)
                if past is None:
                    problems.append(f"{month}: the Bulletin has no State of the Economy article")
                    continue
                past_page = fetch_article(session, past, use_cache=use_cache)
                past_briefing = parse_briefing(past_page, past)
                past_transmission = parse_transmission(past_page)
                if past_transmission is None:
                    print(f"   {month}: no transmission table")
                    continue
                for row in history_rows(past, past_briefing, past_transmission):
                    history[(row["month"], row["cycle_type"], row["cycle_start"])] = row
                print(f"   {month}: read")
            except SoeError as exc:
                problems.append(f"{month}: {exc}")

    rows = list(history.values())
    if rows:
        problems.extend(check_repo_column(rows))
        write_history(rows)
        print(f"\n{_rel(TRANSMISSION_CSV)}: {len(rows)} rows")

    # ── The briefing, into the edition folder ─────────────────────────────────
    if not args.history:
        out_dir = args.out or latest_edition_folder()
        if out_dir is None:
            problems.append("no India edition folder with charts; soe.json was not written "
                            "(run generate_india.py first)")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / BRIEFING_FILENAME
            with path.open("w", encoding="utf-8") as fh:
                json.dump(briefing, fh, indent=1, ensure_ascii=False)
            print(f"{_rel(path)} written")

    if problems:
        print("\nFINISHED WITH PROBLEMS")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
