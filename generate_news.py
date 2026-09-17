"""
Economics Hub — The Week in Headlines

Writes news.json into a Weekly Markets edition folder: the week's top headlines
in a World and an India column, shown under the Weekly tab's header. Each
edition keeps its own headlines, so they are archived and pruned with its charts.

Through the week, the Headline Collector workflow runs this with --collect every
4 hours, adding what the feeds hold to a pool of the week's headlines (8 days at
most, kept in GitHub's Actions cache between runs, never committed). The weekly
workflow restores that pool and runs this right after generate_weekly.py, so
the whole week is ranked, and publishes news.json with the charts. Without a
pool, the feeds are read once instead.

A feed that fails is a warning, never a failed run, and the workflow step may
fail without stopping the charts. Nothing is filled in: a column left too thin
is simply not shown.

Usage:
    python generate_news.py                            # newest local edition in output/weekly/
    python generate_news.py --out output/weekly/2026-09-19
    python generate_news.py --collect                  # add the feeds' headlines to the week's pool
Feeds and filters:  config/news_settings.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config.news_settings as news_settings
from data.news import build_news, collect_headlines, pool_from_json, pool_to_json

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_POOL = PROJECT_ROOT / "output" / "headline_pool" / "pool.json"


def latest_edition(weekly_dir: Path) -> Path | None:
    """
    The newest edition folder that has charts. Never a new, empty folder: the
    dashboard serves the newest weekly folder, so one holding only news.json
    would hide every chart.
    """
    editions = sorted((p for p in weekly_dir.iterdir() if p.is_dir() and any(p.glob("*.png"))),
                      key=lambda p: p.name) if weekly_dir.exists() else []
    return editions[-1] if editions else None


def load_pool(path: Path) -> tuple[dict | None, str | None]:
    """(pool, None); (None, None) when there is no pool yet; (None, reason) when it cannot be read."""
    if not path.exists():
        return None, None
    try:
        return pool_from_json(json.loads(path.read_text(encoding="utf-8"))), None
    except (OSError, ValueError) as exc:
        return None, f"Headline pool {path} could not be read, so it was set aside ({exc})"


def save_pool(pool: dict, path: Path) -> int:
    """Writes the pool through a temporary file, so a run cut short never leaves half a pool. Returns its size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pool_to_json(pool), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return path.stat().st_size


def _print_problems(problems: list[str], note: str) -> None:
    if problems:
        print(f"\n   ⚠ {len(problems)} warning(s); {note}:")
        for p in problems:
            print(f"     - {p}")


def collect(pool_path: Path) -> int:
    print("Economics Hub — collecting the week's headlines")
    pool, unreadable = load_pool(pool_path)
    if unreadable:
        print(f"   ⚠ {unreadable}; starting a new pool.")
    elif pool is None:
        print("   No pool yet; starting one.")

    pool, added, problems = collect_headlines(news_settings, pool)
    if all(n is None for n in added.values()):
        _print_problems(problems, "no feed answered")
        print("\n❌ Nothing was collected, so the pool was left as it was.")
        return 1

    for region, n in added.items():
        status = f"+{n} new" if n is not None else "no feed answered"
        print(f"     {region.title():6s} {status:18s} {len(pool['headlines'][region])} in the pool")
    size = save_pool(pool, pool_path)
    n = len(pool["reads"])
    print(f"\n   {n} read{'s' if n != 1 else ''} since {pool['reads'][0]:%Y-%m-%d %H:%M} UTC, {size / 1024:.0f} KB")
    _print_problems(problems, "the other feeds were collected")
    print(f"\n✅ {pool_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="The Week in Headlines for the Weekly Markets tab")
    parser.add_argument("--out", type=Path, help="edition folder to write news.json into "
                                                 "(default: the newest one in output/weekly/)")
    parser.add_argument("--collect", action="store_true",
                        help="add the feeds' current headlines to the week's pool, then stop")
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL,
                        help="the week's headline pool (default: output/headline_pool/pool.json)")
    args = parser.parse_args()

    if args.collect:
        return collect(args.pool)

    out_dir = args.out or latest_edition(PROJECT_ROOT / "output" / "weekly")
    if out_dir is None or not out_dir.is_dir():
        print("No weekly edition to add headlines to. Run generate_weekly.py first.")
        return 1

    print("Economics Hub — The Week in Headlines")
    pool, unreadable = load_pool(args.pool)
    news, problems = build_news(news_settings, pool=pool)
    if unreadable:
        problems.append(unreadable)
    with open(out_dir / "news.json", "w") as fh:
        json.dump(news, fh, indent=1, ensure_ascii=False)

    h, reads = news["headlines"], news["reads"]
    print(f"\n   {h['from']} to {h['to']}")
    if pool is None:
        print("   No headline pool, so the feeds were read once.")
    elif reads["count"]:
        print(f"   Ranked the week's pool: {reads['count']} reads since {reads['first']}")
    for region in ("world", "india"):
        print(f"     {region.title():6s} {len(h[region]['items'])} headlines"
              + ("" if h[region]["items"] else "  (column left out)"))

    _print_problems(problems, "the strip was built from what worked")
    print(f"\n✅ {out_dir / 'news.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
