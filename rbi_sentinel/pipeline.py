"""
rbi_sentinel/pipeline.py

Orchestrator: fetch -> clean -> score -> compute composite -> generate charts.
Called by generate_rbi_sentinel.py. Not invoked directly.
"""

import logging
import sqlite3
from collections import Counter
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from rbi_sentinel.config import (
    ASSETS_DIR,
    COMPARISON_CHART_MEETINGS,
    DB_PATH,
    DOC_GOVERNOR,
    DOC_MINUTES,
    DOC_RESOLUTION,
    FETCH_CACHED,
    FETCH_FAILED,
    FETCH_SUCCESS,
    MPC_INCEPTION_DATE,
    OUTPUT_DIR,
    SCORING_MODEL_VERSION,
)
from rbi_sentinel.db import manager as db
from rbi_sentinel.cleaners import html_extractor, pdf_extractor, text_normalizer
from rbi_sentinel.sentiment.hybrid_scorer import HybridScorer
from rbi_sentinel.sentiment.score_normalizer import compute_meeting_composite

log = logging.getLogger("rbi_sentinel.pipeline")


# ── Chart imports (lazy) ────────────────────────────────────────────────────────

def _import_charts():
    from rbi_sentinel.charts import (
        stance_meter,
        sentiment_trajectory,
        doc_comparison,
        subdimension_radar,
        rate_and_sentiment,
        meeting_timeline,
    )
    return (
        stance_meter, sentiment_trajectory, doc_comparison,
        subdimension_radar, rate_and_sentiment, meeting_timeline,
    )


# ── Stage 1: Fetch ──────────────────────────────────────────────────────────────

def run_fetch(*, incremental: bool = True, dry_run: bool = False) -> None:
    """
    Discover and cache all RBI MPC documents using the master fetcher.

    Flow:
      1. MasterFetcher.discover_all_documents() scrapes the single search URL,
         paginates via ASP.NET ProcessPaging POST, stops at Oct 2016 cutoff.
      2. For each discovered doc: upsert meeting row + document row.
      3. Fetch the press release page and cache it locally.

    If incremental=True, skip documents whose cache file already exists.
    If dry_run=True, only run discovery and log -- no DB writes or downloads.
    """
    from rbi_sentinel.fetchers.master_fetcher import MasterFetcher

    log.info(
        "=== FETCH STAGE - MASTER FETCHER (incremental=%s, dry_run=%s) ===",
        incremental, dry_run,
    )

    fetcher = MasterFetcher()

    # Step 1: Discover all document links
    all_docs = fetcher.discover_all_documents()

    if not all_docs:
        log.warning(
            "Discovery returned 0 documents. "
            "Check network access to rbi.org.in and inspect logs/rbi_sentinel.log."
        )
        return

    type_counts = Counter(d["doc_type"] for d in all_docs)
    log.info(
        "Discovery complete: %d documents found (by type: %s)",
        len(all_docs), dict(type_counts),
    )

    if dry_run:
        log.info("[dry-run] Documents that would be fetched:")
        for doc in all_docs:
            log.info(
                "  [dry-run] %-20s | %s | %s",
                doc["doc_type"], doc["publication_date"], doc["title"][:70],
            )
        log.info("[dry-run] Fetch stage complete -- no DB writes, no downloads")
        return

    # Step 2 & 3: Upsert meeting + document, fetch content
    fetched = 0
    skipped = 0
    failed = 0

    for doc_info in all_docs:
        pub_date = doc_info["publication_date"]
        doc_type = doc_info["doc_type"]
        source_url = doc_info["source_url"]
        meeting_date = pub_date   # Reconciled with minutes lag in scoring stage

        # Incremental skip
        if incremental:
            existing_meeting = db.get_meeting_by_date(meeting_date)
            if existing_meeting:
                existing_doc = db.get_document(existing_meeting["meeting_id"], doc_type)
                if existing_doc and existing_doc["fetch_status"] in (FETCH_SUCCESS, FETCH_CACHED):
                    log.debug("Skipping already-fetched %s %s", doc_type, pub_date)
                    skipped += 1
                    continue

        # Upsert meeting row
        meeting_id = db.upsert_meeting(meeting_date)

        # Fetch press release page and cache
        raw_bytes, cache_path, fetch_status = fetcher.fetch_press_release(doc_info)

        db.upsert_document(
            meeting_id=meeting_id,
            doc_type=doc_type,
            publication_date=pub_date,
            source_url=source_url,
            source_format="html",
            fetch_status=fetch_status,
            cache_path=cache_path if cache_path else None,
        )

        if fetch_status == FETCH_FAILED:
            log.warning("Fetch failed for %s %s -- stub stored", doc_type, pub_date)
            failed += 1
        else:
            log.info("Stored %s %s (%s)", doc_type, pub_date, fetch_status)
            fetched += 1

    log.info(
        "Fetch stage complete: fetched=%d, skipped=%d, failed=%d",
        fetched, skipped, failed,
    )


# ── Stage 2: Clean + Score ──────────────────────────────────────────────────────

def run_clean_and_score(
    *,
    full_rescore: bool = False,
    dry_run: bool = False,
    review_mode: bool = False,
) -> None:
    """
    Clean raw text from cached documents and score with hybrid scorer.
    If full_rescore=True, re-score all documents (regardless of existing scores).
    If review_mode=True, print narratives to stdout without writing to DB.
    """
    log.info(
        "=== SCORE STAGE (full_rescore=%s, dry_run=%s, review_mode=%s) ===",
        full_rescore, dry_run, review_mode,
    )

    if full_rescore:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM rbi_documents "
            "WHERE raw_text IS NOT NULL AND fetch_status IN ('success','cached')"
        ).fetchall()
        conn.close()
        docs_to_score = [dict(r) for r in rows]
    else:
        docs_to_score = db.get_documents_without_scores()

    if not docs_to_score:
        log.info("No documents pending scoring")
        return

    log.info("%d documents to score", len(docs_to_score))
    scorer = HybridScorer()

    for doc in docs_to_score:
        doc_id = doc["doc_id"]
        meeting_id = doc["meeting_id"]
        doc_type = doc["doc_type"]
        source_format = doc.get("source_format", "html")
        cache_path = doc.get("cache_path")
        publication_date = doc.get("publication_date", "")
        meeting_date = publication_date

        # Read text -- prefer stored raw_text, fall back to cache file
        raw_text = doc.get("raw_text")

        if not raw_text and cache_path:
            try:
                raw_bytes = Path(cache_path).read_bytes()
                if source_format == "pdf":
                    raw_text = pdf_extractor.extract_text(raw_bytes)
                else:
                    raw_text = html_extractor.extract_text(raw_bytes)
            except Exception as exc:
                log.error("Failed to read cache for doc %d: %s", doc_id, exc)
                continue

        if not raw_text:
            log.warning("No text for doc %d (%s %s)", doc_id, doc_type, publication_date)
            continue

        # Normalize
        norm = text_normalizer.normalize(raw_text)

        if dry_run:
            log.info(
                "[dry-run] Would score doc %d: %s %s (%d words)",
                doc_id, doc_type, meeting_date, norm["word_count"],
            )
            continue

        # Score
        score_result = scorer.score(
            text=norm["text"],
            doc_type=doc_type,
            meeting_date=meeting_date,
            sentences=norm.get("sentences"),
        )

        if review_mode:
            print(f"\n{'='*60}")
            print(f"DOC: {doc_type} | DATE: {meeting_date}")
            print(f"Score: {score_result['overall_score']:+.3f} | Confidence: {score_result.get('score_confidence', 0):.2f}")
            print(f"\nNARRATIVE:\n{score_result.get('narrative_summary', 'N/A')}")
            print(f"\nKEY PHRASES: {score_result.get('key_phrases', [])}")
            continue

        # Store text in DB (so re-scoring never needs the cache file)
        db.upsert_document(
            meeting_id=meeting_id,
            doc_type=doc_type,
            publication_date=publication_date,
            source_url=doc.get("source_url", ""),
            source_format=source_format,
            fetch_status=doc.get("fetch_status", "success"),
            raw_text=norm["full_text"],
            word_count=norm["word_count"],
            cache_path=cache_path,
        )

        # Store score
        db.upsert_score(
            doc_id=doc_id,
            meeting_id=meeting_id,
            **score_result,
        )
        log.info(
            "Scored doc %d (%s %s): %.3f",
            doc_id, doc_type, meeting_date, score_result["overall_score"],
        )

    # Recompute composites after all scoring
    if not dry_run and not review_mode:
        run_compute_composites()

    log.info("Score stage complete")


# ── Stage 2b: Compute Composites ────────────────────────────────────────────────

def run_compute_composites() -> None:
    """Recompute meeting_composites for all meetings with at least one score."""
    log.info("=== COMPOSITE COMPUTATION ===")
    meetings = db.get_all_meetings()
    for meeting in meetings:
        meeting_id = meeting["meeting_id"]
        meeting_date = meeting["meeting_date"]
        scores = db.get_scores_for_meeting(meeting_id)
        if not scores:
            continue
        composite = compute_meeting_composite(scores)
        db.upsert_composite(meeting_id=meeting_id, **composite)
        log.debug(
            "Composite for %s: %.3f",
            meeting_date, composite.get("composite_overall_score") or 0,
        )
    log.info("Composite computation complete")


# ── Stage 3: Charts ─────────────────────────────────────────────────────────────

def run_generate_charts(
    output_dir: Optional[Path] = None,
    mode: str = "dashboard",
) -> None:
    """Generate all 6 charts from DB data."""
    log.info("=== CHART GENERATION (mode=%s) ===", mode)

    today = date.today().strftime("%Y-%m")
    if output_dir is None:
        output_dir = OUTPUT_DIR / today
    output_dir.mkdir(parents=True, exist_ok=True)

    (
        stance_meter_mod, trajectory_mod, comparison_mod,
        radar_mod, rate_mod, timeline_mod,
    ) = _import_charts()

    composites = db.get_all_composites()
    latest = db.get_latest_composite()

    if not composites:
        log.warning("No composite data available -- charts will be empty")
        return

    # Chart 01: Stance Meter
    if latest:
        stance_meter_mod.generate(
            composite_score=latest["composite_overall_score"],
            meeting_date=latest["meeting_date"],
            output_path=output_dir / "01_rbi_stance_meter.png",
            mode=mode,
        )

    # Chart 02: Sentiment Trajectory
    trajectory_mod.generate(
        composites=composites,
        output_path=output_dir / "02_rbi_sentiment_trajectory.png",
        mode=mode,
    )

    # Chart 03: Resolution vs Minutes (last N meetings)
    recent = db.get_recent_composites(COMPARISON_CHART_MEETINGS)
    comparison_mod.generate(
        composites=recent,
        output_path=output_dir / "03_rbi_resolution_vs_minutes.png",
        mode=mode,
    )

    # Chart 04: Sub-dimension Radar
    current_scores = None
    prev_scores = None
    current_date = None
    prev_date = None

    if composites:
        latest_meeting = composites[-1]
        current_date = latest_meeting["meeting_date"]
        score_rows = db.get_scores_for_meeting(latest_meeting["meeting_id"])
        for preferred_type in [DOC_MINUTES, DOC_RESOLUTION]:
            for row in score_rows:
                if row.get("doc_type") == preferred_type:
                    current_scores = row
                    break
            if current_scores:
                break

        if len(composites) >= 2:
            prev_meeting = composites[-2]
            prev_date = prev_meeting["meeting_date"]
            prev_score_rows = db.get_scores_for_meeting(prev_meeting["meeting_id"])
            for preferred_type in [DOC_MINUTES, DOC_RESOLUTION]:
                for row in prev_score_rows:
                    if row.get("doc_type") == preferred_type:
                        prev_scores = row
                        break
                if prev_scores:
                    break

    if current_scores and current_date:
        radar_mod.generate(
            current_scores=current_scores,
            previous_scores=prev_scores,
            current_date=current_date,
            previous_date=prev_date,
            output_path=output_dir / "04_rbi_subdimension_radar.png",
            mode=mode,
        )

    # Chart 05: Rate vs Sentiment
    rate_mod.generate(
        composites=composites,
        output_path=output_dir / "05_rbi_rate_and_sentiment.png",
        mode=mode,
    )

    # Chart 06: Meeting Timeline
    timeline_mod.generate(
        composites=composites,
        output_path=output_dir / "06_rbi_meeting_timeline.png",
        mode=mode,
    )

    log.info("Charts saved to %s", output_dir)
