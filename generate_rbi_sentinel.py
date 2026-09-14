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
    python generate_rbi_sentinel.py --auto          # Unattended run (GitHub Actions): everything,
                                                    # plus the live tone log; exits 1 if anything needs attention
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
        "--auto",
        action="store_true",
        help="Unattended incremental run: fetch, score, record decisions, live log, refresh charts if stale",
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
        refresh_charts_if_stale,
        run_assign_cycles,
        run_clean_and_score,
        run_extract_text,
        run_fetch,
        run_generate_charts,
        run_record_decisions,
    )

    problems: list[str] = []

    if not args.charts_only:
        # ── Stage 1: Fetch ────────────────────────────────────────────────────
        run_fetch(
            incremental=not args.full,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            log.info("Dry-run: skipping extraction, scoring and decisions")
        else:
            # ── Stage 1b–1c: text, then policy cycles ─────────────────────────
            # Without these a newly fetched meeting is never classified as a
            # press release (so never scored) and never assigned a cycle.
            run_extract_text()
            run_assign_cycles()

            # ── Stage 2: Clean + Score (composites recomputed inside) ─────────
            scored, failed = run_clean_and_score(
                full_rescore=args.full,
                dry_run=False,
                review_mode=args.review_mode,
            )
            if failed:
                problems.append(f"{failed} document(s) could not be scored")

            # ── Stage 2c: Rate decisions from the Resolution text ─────────────
            if not args.review_mode:
                _, conflicts, unreadable = run_record_decisions()
                if conflicts:
                    problems.append(f"{conflicts} rate decision conflict(s)")
                if unreadable:
                    problems.append(f"{unreadable} rate decision(s) could not be read")

    # ── Live test log (automated runs only) ────────────────────────────────────
    if args.auto and not args.dry_run:
        from rbi_sentinel import live_log
        live_log.record_decision_day_tone()
        waiting = live_log.record_market_closes()
        if waiting:
            log.warning("10-year close still needed for: %s", ", ".join(waiting))

    # ── Stage 3: Charts ────────────────────────────────────────────────────────
    if not args.dry_run and not args.review_mode:
        if args.auto:
            refresh_charts_if_stale(mode=args.mode)
        else:
            run_generate_charts(mode=args.mode)

    if problems:
        log.error("=== RBI SENTINEL PIPELINE FINISHED WITH PROBLEMS: %s ===", "; ".join(problems))
        sys.exit(1)
    log.info("=== RBI SENTINEL PIPELINE COMPLETE ===")


if __name__ == "__main__":
    main()
