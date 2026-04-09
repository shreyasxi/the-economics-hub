"""
generate_rbi_sentinel.py

RBI Sentinel — top-level pipeline runner.

Usage:
    python generate_rbi_sentinel.py                 # Incremental: new meetings only
    python generate_rbi_sentinel.py --full          # Full historical rescore
    python generate_rbi_sentinel.py --charts-only   # Skip fetch/score, regenerate charts
    python generate_rbi_sentinel.py --dry-run       # Fetch + clean only, no DB/chart writes
    python generate_rbi_sentinel.py --review-mode   # Print narratives to stdout, no writes
    python generate_rbi_sentinel.py --mode newsletter
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path (in case script is run directly)
sys.path.insert(0, str(Path(__file__).parent))

from rbi_sentinel.config import LOG_PATH
from rbi_sentinel.db.manager import init_db


def _setup_logging(verbose: bool = False) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RBI Sentinel — automated MPC sentiment pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full historical rescore (ignores existing scores)",
    )
    parser.add_argument(
        "--charts-only",
        action="store_true",
        help="Skip fetch/score stages — regenerate charts from existing DB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch + clean only — no DB writes, no LLM calls, no chart generation",
    )
    parser.add_argument(
        "--review-mode",
        action="store_true",
        help="Score and print narratives to stdout — no DB writes or chart generation",
    )
    parser.add_argument(
        "--mode",
        choices=["dashboard", "newsletter"],
        default="dashboard",
        help="Chart title mode (default: dashboard)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _setup_logging(verbose=args.verbose)
    log = logging.getLogger("rbi_sentinel")

    log.info("=== RBI SENTINEL PIPELINE START ===")
    log.info(
        "Mode: %s | full=%s | charts_only=%s | dry_run=%s | review_mode=%s",
        args.mode, args.full, args.charts_only, args.dry_run, args.review_mode,
    )

    # Always initialise DB first
    init_db()

    from rbi_sentinel.pipeline import (
        run_fetch,
        run_clean_and_score,
        run_generate_charts,
    )

    if not args.charts_only:
        # ── Stage 1: Fetch ────────────────────────────────────────────────────
        run_fetch(
            incremental=not args.full,
            dry_run=args.dry_run,
        )

        # ── Stage 2: Clean + Score ────────────────────────────────────────────
        if not args.dry_run:
            run_clean_and_score(
                full_rescore=args.full,
                dry_run=False,
                review_mode=args.review_mode,
            )
        elif args.dry_run:
            log.info("Dry-run: skipping score stage")

    # ── Stage 3: Charts ────────────────────────────────────────────────────────
    if not args.dry_run and not args.review_mode:
        run_generate_charts(mode=args.mode)

    log.info("=== RBI SENTINEL PIPELINE COMPLETE ===")


if __name__ == "__main__":
    main()
