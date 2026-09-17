"""
Economics Hub — The Week in Headlines

Writes news.json into a Weekly Markets edition folder: the week's top headlines
in a World and an India column, shown under the Weekly tab's header. Each
edition keeps its own headlines, so they are archived and pruned with its charts.

The weekly workflow runs this right after generate_weekly.py and publishes
news.json with the charts. A feed that fails is a warning, never a failed run,
and the workflow step may fail without stopping the charts. Nothing is filled
in: a column left too thin is simply not shown.

Usage:
    python generate_news.py                            # newest local edition in output/weekly/
    python generate_news.py --out output/weekly/2026-09-19
Feeds and filters:  config/news_settings.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config.news_settings as news_settings
from data.news import build_news

PROJECT_ROOT = Path(__file__).resolve().parent


def latest_edition(weekly_dir: Path) -> Path | None:
    """
    The newest edition folder that has charts. Never a new, empty folder: the
    dashboard serves the newest weekly folder, so one holding only news.json
    would hide every chart.
    """
    editions = sorted((p for p in weekly_dir.iterdir() if p.is_dir() and any(p.glob("*.png"))),
                      key=lambda p: p.name) if weekly_dir.exists() else []
    return editions[-1] if editions else None


def main() -> int:
    parser = argparse.ArgumentParser(description="The Week in Headlines for the Weekly Markets tab")
    parser.add_argument("--out", type=Path, help="edition folder to write news.json into "
                                                 "(default: the newest one in output/weekly/)")
    args = parser.parse_args()

    out_dir = args.out or latest_edition(PROJECT_ROOT / "output" / "weekly")
    if out_dir is None or not out_dir.is_dir():
        print("No weekly edition to add headlines to. Run generate_weekly.py first.")
        return 1

    print("Economics Hub — The Week in Headlines")
    news, problems = build_news(news_settings)
    with open(out_dir / "news.json", "w") as fh:
        json.dump(news, fh, indent=1, ensure_ascii=False)

    h = news["headlines"]
    print(f"\n   {h['from']} to {h['to']}")
    for region in ("world", "india"):
        print(f"     {region.title():6s} {len(h[region]['items'])} headlines"
              + ("" if h[region]["items"] else "  (column left out)"))

    if problems:
        print(f"\n   ⚠ {len(problems)} warning(s); the strip was built from the feeds that worked:")
        for p in problems:
            print(f"     - {p}")
    print(f"\n✅ {out_dir / 'news.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
