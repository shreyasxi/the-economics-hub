"""
Keep only the last four weekly editions in assets/weekly/.

The dashboard shows only the newest folder, but every Saturday's charts used
to stay in the repository for good. An edition is one calendar week (Mon–Sun):
if a week was generated twice (say a Saturday run and a Sunday re-run), only
its newest folder is kept. Deleted folders remain in git history.

Standard library only.  Run from the project root:
    python .github/scripts/prune_weekly_assets.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import date
from pathlib import Path

WEEKS_TO_KEEP = 4
WEEKLY_DIR = Path(__file__).resolve().parents[2] / "assets" / "weekly"
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def folders_to_delete(names: list[str], weeks: int = WEEKS_TO_KEEP) -> list[str]:
    """Dated folder names outside the newest folder of each of the last `weeks` weeks."""
    newest_per_week: dict[tuple[int, int], str] = {}
    for name in sorted(n for n in names if DATED.match(n)):
        newest_per_week[date.fromisoformat(name).isocalendar()[:2]] = name   # later dates overwrite
    keep = {newest_per_week[w] for w in sorted(newest_per_week)[-weeks:]}
    return [n for n in sorted(names) if DATED.match(n) and n not in keep]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--dry-run", action="store_true", help="list what would be deleted")
    args = parser.parse_args()

    names = [p.name for p in WEEKLY_DIR.iterdir() if p.is_dir()] if WEEKLY_DIR.exists() else []
    doomed = folders_to_delete(names)
    kept = sorted(n for n in names if DATED.match(n) and n not in doomed)
    for name in doomed:
        print(f"{'would delete' if args.dry_run else 'deleted'} assets/weekly/{name}")
        if not args.dry_run:
            shutil.rmtree(WEEKLY_DIR / name)
    print(f"Keeping {len(kept)} weekly edition(s): {', '.join(kept) or 'none'}")


if __name__ == "__main__":
    main()
