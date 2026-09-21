#!/usr/bin/env python3
"""
Economics Hub — Signal or noise

Writes signals.json into a Weekly Markets edition folder: every series in
config/signals_settings.py, ranked by how unusual the week's move was for that
series (the move divided by the size of a typical week over the past three
years). The Analysis page reads the file from the newest weekly edition, so the
board is archived and pruned with the charts it sits beside.

A series that fails to download, or has not traded this week, is left out of
the ranking and listed with the reason; nothing is filled in for it. If more
than a quarter of the series cannot be measured, the run fails and writes
nothing, rather than rank whatever happened to download.

Usage:
    python generate_signals.py                            # newest edition in output/weekly/, week to last Friday
    python generate_signals.py --out output/weekly/2026-09-19
    python generate_signals.py --week-end 2026-09-18      # a Friday
Series and thresholds:  config/signals_settings.py
Arithmetic:             data/signals.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import config.signals_settings as cfg
from data.signals import assess, last_friday_before, rank


def latest_edition(weekly_dir: Path) -> Path | None:
    """
    The newest edition folder that has charts, as generate_news.py picks it.
    Never a new, empty folder: the dashboard serves the newest weekly folder,
    so one holding only signals.json would hide every chart.
    """
    editions = sorted((p for p in weekly_dir.iterdir() if p.is_dir() and any(p.glob("*.png"))),
                      key=lambda p: p.name) if weekly_dir.exists() else []
    return editions[-1] if editions else None


def _friday(text: str) -> date:
    day = date.fromisoformat(text)
    if day.weekday() != 4:
        raise argparse.ArgumentTypeError(f"{text} is a {day:%A}; the week ends on a Friday")
    return day


def main() -> int:
    parser = argparse.ArgumentParser(description="Signal or noise: the week's unusual moves, for the Analysis page")
    parser.add_argument("--out", type=Path, help="edition folder to write signals.json into "
                                                 "(default: the newest one in output/weekly/)")
    parser.add_argument("--week-end", type=_friday, help="the Friday the week ends on (default: the last one before today)")
    args = parser.parse_args()

    from config.settings import FRED_API_KEY
    if not FRED_API_KEY or FRED_API_KEY == "YOUR_FRED_API_KEY":
        sys.exit("FRED_API_KEY is not set. Add it to .env locally or to the GitHub Actions secrets.")

    out_dir = args.out or latest_edition(PROJECT_ROOT / "output" / "weekly")
    if out_dir is None or not out_dir.is_dir():
        print("No weekly edition to add the board to. Run generate_weekly.py first.")
        return 1

    from data.fetchers.fred_fetcher import FredFetcher
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    yf_fetcher = YFinanceFetcher()
    fred_fetcher = FredFetcher(api_key=FRED_API_KEY)

    week_end = args.week_end or last_friday_before(date.today())
    print("Economics Hub — Signal or noise")
    print(f"   Week to Friday {week_end:%d %b %Y}, {len(cfg.SERIES)} series\n")

    rows, left_out = [], []
    for spec in cfg.SERIES:
        try:
            if spec["source"] == "yfinance":
                series = yf_fetcher.get_close_series(spec["code"], period=f"{cfg.HISTORY_YEARS}y")
            else:
                series = fred_fetcher.fetch_series(spec["code"], period_years=cfg.HISTORY_YEARS)
        except Exception as exc:
            print(f"   - {spec['name']}: download failed ({exc})")
            left_out.append({"id": spec["id"], "name": spec["name"], "reason": "download failed"})
            continue
        row, reason = assess(series, spec, week_end, window_weeks=cfg.TYPICAL_WINDOW_WEEKS,
                             min_weeks=cfg.MIN_WEEKS, stale_days=cfg.STALE_DAYS)
        if row is None:
            print(f"   - {spec['name']}: left out, {reason}")
            left_out.append({"id": spec["id"], "name": spec["name"], "reason": reason})
        else:
            rows.append(row)

    missing = len(left_out) / len(cfg.SERIES)
    if missing > cfg.MAX_MISSING_SHARE:
        print(f"\nFAILED: {len(left_out)} of {len(cfg.SERIES)} series could not be measured "
              f"(limit {cfg.MAX_MISSING_SHARE:.0%}), so nothing was written.")
        return 1

    ranked = rank(rows)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "week": {"from": (week_end - timedelta(days=7)).isoformat(), "to": week_end.isoformat()},
        "window_weeks": cfg.TYPICAL_WINDOW_WEEKS,
        "history_years": cfg.HISTORY_YEARS,
        "notable": cfg.NOTABLE,
        "rows": ranked,
        "left_out": left_out,
    }
    with open(out_dir / "signals.json", "w") as fh:
        json.dump(payload, fh, indent=1)

    notable = sum(abs(r["multiple"]) >= cfg.NOTABLE for r in ranked)
    print(f"\n   {len(ranked)} ranked, {len(left_out)} left out; {notable} moved {cfg.NOTABLE:g}x a typical week or more")
    for i, r in enumerate(ranked[:12], 1):
        unit = "bp" if r["measure"] == "bp" else "%"
        print(f"   {i:2d}. {r['name']:34s} {r['move']:+8.2f}{unit:2s} typical {r['typical']:6.2f}  "
              f"{r['multiple']:+5.1f}x  since {r['since'] or 'start of data ' + r['history_from']}")
    print(f"\nWritten: {out_dir / 'signals.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
