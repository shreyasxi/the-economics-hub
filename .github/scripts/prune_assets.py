"""
Keep only the four newest editions of a dashboard in assets/.

The dashboard shows only the newest folder of each pipeline, but every run
used to stay in the repository for good. Deleted folders remain in git history.

  weekly                      folders YYYY-MM-DD; one edition per calendar week
                              (Mon–Sun), the newest folder of that week
  macro, india, rbi_sentinel  folders YYYY-MM; one edition per month

Standard library only.  Run from the project root:
    python .github/scripts/prune_assets.py weekly [--dry-run]
    python .github/scripts/prune_assets.py macro
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import date
from pathlib import Path

EDITIONS_TO_KEEP = 4
ASSETS = Path(__file__).resolve().parents[2] / "assets"
WEEKLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTHLY = re.compile(r"^\d{4}-\d{2}$")
PIPELINES = {"weekly": "weekly", "macro": "monthly", "india": "monthly", "rbi_sentinel": "monthly"}


def folders_to_delete(names: list[str], cadence: str, keep: int = EDITIONS_TO_KEEP) -> list[str]:
    """Dated folder names that fall outside the newest `keep` editions."""
    pattern = WEEKLY if cadence == "weekly" else MONTHLY
    dated = sorted(n for n in names if pattern.match(n))
    if cadence == "weekly":
        newest_per_week: dict[tuple[int, int], str] = {}
        for name in dated:
            newest_per_week[date.fromisoformat(name).isocalendar()[:2]] = name   # later dates overwrite
        kept = {newest_per_week[w] for w in sorted(newest_per_week)[-keep:]}
    else:
        kept = set(dated[-keep:])
    return [n for n in dated if n not in kept]


def main() -> None:
    parser = argparse.ArgumentParser(description="Keep the four newest editions in assets/<pipeline>/")
    parser.add_argument("pipeline", choices=sorted(PIPELINES))
    parser.add_argument("--dry-run", action="store_true", help="list what would be deleted")
    args = parser.parse_args()

    folder = ASSETS / args.pipeline
    names = [p.name for p in folder.iterdir() if p.is_dir()] if folder.exists() else []
    doomed = folders_to_delete(names, PIPELINES[args.pipeline])
    for name in doomed:
        print(f"{'would delete' if args.dry_run else 'deleted'} assets/{args.pipeline}/{name}")
        if not args.dry_run:
            shutil.rmtree(folder / name)
    kept = sorted(set(n for n in names if (WEEKLY if PIPELINES[args.pipeline] == "weekly" else MONTHLY).match(n)) - set(doomed))
    print(f"Keeping {len(kept)} edition(s) in assets/{args.pipeline}: {', '.join(kept) or 'none'}")


if __name__ == "__main__":
    main()
