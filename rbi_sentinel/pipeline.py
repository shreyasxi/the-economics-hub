"""
rbi_sentinel/pipeline.py

Orchestrator: fetch -> clean -> score -> compute composite -> generate charts.
Called by generate_rbi_sentinel.py. Not invoked directly.
"""

import logging
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, date, timedelta
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

# Stop a scoring run after this many consecutive failures. A run that cannot
# score several documents in a row has an account- or network-level problem,
# not a document-level one, and continuing just burns wall-clock time.
MAX_CONSECUTIVE_SCORING_FAILURES = 5


# ── Chart imports (lazy) ────────────────────────────────────────────────────────

def _import_charts():
    from rbi_sentinel.charts import (
        stance_meter,
        sentiment_trajectory,
        doc_comparison,
        subdimension_radar,
        rate_and_sentiment,
    )
    return (
        stance_meter, sentiment_trajectory, doc_comparison,
        subdimension_radar, rate_and_sentiment,
    )


# ── Stage 1: Fetch ──────────────────────────────────────────────────────────────

# Incremental discovery re-reads this far behind the newest stored document, so a
# late-listed press release or a revised date is still picked up.
DISCOVERY_MARGIN_DAYS = 45


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

    # Step 1: Discover document links — only recent pages on incremental runs
    stop_before = None
    if incremental:
        latest = db.latest_publication_date()
        if latest:
            stop_before = date.fromisoformat(latest) - timedelta(days=DISCOVERY_MARGIN_DAYS)
    all_docs = fetcher.discover_all_documents(stop_before=stop_before)

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


# ── Stage 1b: Extract text (free) ───────────────────────────────────────────────

def run_extract_text() -> None:
    """
    Extract and store text for any fetched document that has none yet.

    run_fetch() caches the HTML but leaves raw_text empty; extraction normally
    happens inside run_clean_and_score(), which also calls the LLM. That
    couples "read the document" to "pay to score it", so a newly fetched
    document has no word_count until you have spent money on it — and
    word_count is what migrate_policy_cycle uses to identify a real decision.

    This stage breaks that dependency. It costs nothing, and afterwards the
    cycle migration and any sanity checks can run before a single token is
    billed.
    """
    log.info("=== TEXT EXTRACTION (no API calls) ===")

    pending = [
        d for d in db.get_documents_without_text()
        if d.get("cache_path")
    ]
    if not pending:
        log.info("Every fetched document already has text")
        return

    # Historical rows whose cache file is not on this machine are RBI's advance
    # schedule notices (no body text; cached on the machine that built the
    # database, and the cache is git-ignored). They can never be extracted
    # here, so they are counted once rather than warned about on every run.
    available = [d for d in pending if Path(d["cache_path"]).exists()]
    absent = len(pending) - len(available)
    if absent:
        log.info("%d historical document(s) without a local cache file skipped", absent)
    if not available:
        return
    log.info("%d document(s) awaiting extraction", len(available))
    extracted = failed = 0

    for doc in available:
        cache_path = Path(doc["cache_path"])

        raw_bytes = cache_path.read_bytes()
        if doc.get("source_format") == "pdf":
            text = pdf_extractor.extract_text(raw_bytes)
        else:
            text = html_extractor.extract_text(raw_bytes)

        if not text:
            log.warning(
                "Extracted nothing from %s %s — the page layout may have "
                "changed; check HTML_CONTENT_SELECTORS",
                doc["doc_type"], doc["publication_date"],
            )
            failed += 1
            continue

        norm = text_normalizer.normalize(text)
        db.upsert_document(
            meeting_id=doc["meeting_id"],
            doc_type=doc["doc_type"],
            publication_date=doc["publication_date"],
            source_url=doc["source_url"],
            source_format=doc.get("source_format", "html"),
            fetch_status=doc["fetch_status"],
            raw_text=norm["text"],
            word_count=norm["word_count"],
            cache_path=doc.get("cache_path"),
        )
        log.info(
            "Extracted %s %s: %d words",
            doc["doc_type"], doc["publication_date"], norm["word_count"],
        )
        extracted += 1

    log.info("Extraction complete: %d extracted, %d failed", extracted, failed)


# ── Stage 1c: Policy cycles ─────────────────────────────────────────────────────

def run_assign_cycles() -> None:
    """
    Classify documents by source and attach every meeting row to its policy
    cycle. Idempotent. Must run after text extraction (a cycle is anchored on
    a Resolution with text) and before scoring (only press releases are scored).
    Without it a newly fetched meeting has no cycle, no composite, and never
    reaches the dashboard.
    """
    from rbi_sentinel.db.migrate_policy_cycle import migrate
    log.info("=== POLICY CYCLE ASSIGNMENT ===")
    migrate(dry_run=False)


# ── Stage 2: Clean + Score ──────────────────────────────────────────────────────

def run_clean_and_score(
    *,
    full_rescore: bool = False,
    dry_run: bool = False,
    review_mode: bool = False,
) -> tuple[int, int]:
    """
    Clean raw text from cached documents and score with hybrid scorer.
    Returns (documents scored, documents that could not be scored).
    If full_rescore=True, re-score all documents (regardless of existing scores).
    If review_mode=True, print narratives to stdout without writing to DB.
    """
    log.info(
        "=== SCORE STAGE (full_rescore=%s, dry_run=%s, review_mode=%s) ===",
        full_rescore, dry_run, review_mode,
    )

    if full_rescore:
        # Score press releases only. The Monthly Bulletin reprints the
        # resolution and governor statement weeks later; those 100 documents
        # are the same text, are excluded from composites, and scoring them
        # would add ~$4 of API spend per full rescore for no analytical gain.
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM rbi_documents
            WHERE raw_text IS NOT NULL
              AND fetch_status IN ('success','cached')
              AND source_kind = 'press_release'
            ORDER BY publication_date
            """
        ).fetchall()
        conn.close()
        docs_to_score = [dict(r) for r in rows]
    else:
        docs_to_score = [
            d for d in db.get_documents_without_scores()
            if d.get("source_kind") == "press_release"
            # Same historical schedule notices as in run_extract_text: no text
            # stored and no cache file here, so there is nothing to score.
            and (d.get("raw_text") or (d.get("cache_path") and Path(d["cache_path"]).exists()))
        ]

    if not docs_to_score:
        log.info("No documents pending scoring")
        return 0, 0

    log.info("%d documents to score", len(docs_to_score))

    scoring_failures = 0
    consecutive_failures = 0
    scored = 0
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

        if score_result is None:
            # The document could not be scored. Store nothing — a missing
            # score is honest, a fabricated one is not.
            consecutive_failures += 1
            scoring_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_SCORING_FAILURES:
                log.error(
                    "Aborting: %d consecutive scoring failures. This is almost "
                    "always an account-level problem (spend cap reached, key "
                    "revoked, model unavailable) rather than anything about "
                    "these documents, and every remaining call would fail the "
                    "same way. %d of %d documents were scored before the stop.",
                    consecutive_failures, scored, len(docs_to_score),
                )
                break
            continue

        consecutive_failures = 0

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
        scored += 1
        log.info(
            "Scored doc %d (%s %s): %.3f  [%d/%d]",
            doc_id, doc_type, meeting_date,
            score_result["overall_score"], scored, len(docs_to_score),
        )

    # Recompute composites after all scoring
    if not dry_run and not review_mode:
        run_compute_composites()

    if scoring_failures:
        log.error(
            "Score stage finished INCOMPLETE: %d scored, %d could not be "
            "scored and were not stored. Composites cover only the cycles "
            "whose documents were scored; re-run to fill the rest.",
            scored, scoring_failures,
        )
    else:
        log.info("Score stage complete: %d document(s) scored", scored)
    return scored, scoring_failures


# ── Stage 2b: Compute Composites ────────────────────────────────────────────────

def run_compute_composites() -> None:
    """
    Recompute meeting_composites, one per policy cycle.

    RBI publishes a single decision across several dates — resolution and
    governor statement on the day, minutes 14 days later, and a Monthly
    Bulletin reprint of the first two some weeks after. Composites are
    therefore computed per policy_cycle, not per meeting row, and stored
    against the cycle's anchor meeting so chart queries are unaffected.

    Run rbi_sentinel.db.migrate_policy_cycle first; without policy_cycle
    populated this falls back to the old per-meeting behaviour and logs a
    warning, because that produced composites made of one document.
    """
    log.info("=== COMPOSITE COMPUTATION ===")

    cycles = db.get_all_policy_cycles()
    if not cycles:
        log.warning(
            "No policy_cycle values found — falling back to per-meeting "
            "composites, which double-count Bulletin reprints and treat "
            "minutes as a separate meeting. Run: "
            "python -m rbi_sentinel.db.migrate_policy_cycle"
        )
        for meeting in db.get_all_meetings():
            scores = db.get_scores_for_meeting(meeting["meeting_id"])
            if not scores:
                continue
            db.upsert_composite(
                meeting_id=meeting["meeting_id"],
                **compute_meeting_composite(scores),
            )
        log.info("Composite computation complete (legacy per-meeting mode)")
        return

    pruned = db.prune_non_anchor_composites()
    if pruned:
        log.info(
            "Pruned %d composite(s) attached to non-anchor meeting rows "
            "(pre-cycle artefacts, each built from a single document)", pruned,
        )

    written = skipped = 0
    doc_counts = Counter()
    for cycle in cycles:
        scores = db.get_scores_for_cycle(cycle["policy_cycle"])
        if not scores:
            skipped += 1
            continue
        composite = compute_meeting_composite(scores)
        db.upsert_composite(
            meeting_id=cycle["anchor_meeting_id"], **composite
        )
        written += 1
        doc_counts[len(scores)] += 1
        log.debug(
            "Composite for cycle %s: %.3f from %d document(s)",
            cycle["policy_cycle"],
            composite.get("composite_overall_score") or 0,
            len(scores),
        )

    log.info(
        "Composites written for %d of %d cycles (%d had no scores)",
        written, len(cycles), skipped,
    )
    for n in sorted(doc_counts):
        log.info("  %d cycle(s) built from %d document(s)", doc_counts[n], n)
    log.info("Composite computation complete")


# ── Stage 2c: Rate decisions ────────────────────────────────────────────────────

def run_record_decisions() -> tuple[int, int, int]:
    """
    Record each cycle's repo rate decision from its Resolution text, so a new
    meeting no longer needs seed_rbi_rates.py edited by hand.

    Only fills cycles with no recorded decision. Where one exists and the text
    disagrees, it logs an error and leaves the stored value alone — a human
    decides which is right. Verified against all 61 decisions from Oct 2016 to
    Aug 2026: rate, action and size match exactly, including when each meeting
    is chained on the previous extracted rate.
    Returns (recorded, conflicts, unreadable).
    """
    from rbi_sentinel.cleaners.policy_facts import complete_rate_decision, extract_policy_facts

    log.info("=== RATE DECISIONS ===")
    recorded = conflicts = unreadable = 0
    previous_rate = None
    for cycle in db.get_cycle_decisions():
        facts = extract_policy_facts(cycle["resolution_text"])
        found = complete_rate_decision(facts["rate_decision"], previous_rate)
        stored = cycle["repo_rate_pct"] is not None and cycle["rate_action"] is not None

        if stored:
            if found and (abs(found["repo_rate_pct"] - cycle["repo_rate_pct"]) > 1e-9
                          or found["rate_action"] != cycle["rate_action"]):
                conflicts += 1
                log.error(
                    "Rate decision conflict for %s: stored %.2f%% %s, Resolution text says %.2f%% %s — "
                    "stored value kept; check the Resolution",
                    cycle["policy_cycle"], cycle["repo_rate_pct"], cycle["rate_action"],
                    found["repo_rate_pct"], found["rate_action"],
                )
            previous_rate = cycle["repo_rate_pct"]
            continue

        if not found:
            unreadable += 1
            log.error(
                "Could not read the rate decision for %s from its Resolution — "
                "record it with seed_rbi_rates.py", cycle["policy_cycle"],
            )
            continue

        db.set_rate_decision(cycle["anchor_meeting_id"], **found)
        recorded += 1
        previous_rate = found["repo_rate_pct"]
        log.info(
            "Recorded %s: %s, repo rate %.2f%% (%+d bps)",
            cycle["policy_cycle"], found["rate_action"], found["repo_rate_pct"],
            found["rate_change_bps"] or 0,
        )

    log.info("Rate decisions: %d recorded, %d conflict(s), %d unreadable", recorded, conflicts, unreadable)
    return recorded, conflicts, unreadable


# ── Stage 3: Charts ─────────────────────────────────────────────────────────────

def run_generate_charts(
    output_dir: Optional[Path] = None,
    mode: str = "dashboard",
) -> None:
    """Generate the RBI charts from DB data into a clean month folder."""
    log.info("=== CHART GENERATION (mode=%s) ===", mode)

    today = date.today().strftime("%Y-%m")
    if output_dir is None:
        output_dir = OUTPUT_DIR / today
    output_dir.mkdir(parents=True, exist_ok=True)
    # Start clean: a retired chart left in the folder would otherwise be
    # published again and shown by the dashboard's catch-all section.
    for old in output_dir.glob("*.png"):
        old.unlink()

    (
        stance_meter_mod, trajectory_mod, comparison_mod,
        radar_mod, rate_mod,
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

    # Chart 03: Tripartite comparison — last 6 MPC cycles
    # Pass the full composites list so _merge_by_cycle().tail(6) always finds 6 unique cycles.
    comparison_mod.generate(
        composites=composites,
        output_path=output_dir / "03_rbi_resolution_vs_minutes.png",
        mode=mode,
        n_meetings=6,
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

    # Chart 06 (Meeting History) was merged into chart 02 in Sep 2026: its bar
    # panel repeated the trajectory's scores, and its decision dots now run as
    # a strip beneath the trajectory on the same time axis.

    # Chart 07 (Governor vs. Committee Divergence) was removed in Sep 2026.
    # It plotted governor_score - composite_overall_score, but the governor
    # score is itself 15% of that composite, so the chart partly compared a
    # number with itself and the divergence was damped by construction.

    log.info("Charts saved to %s", output_dir)
    _publish_charts(output_dir)


# ── Chart freshness ─────────────────────────────────────────────────────────────

FINGERPRINT_FILE = ".data_fingerprint"


def _publish_charts(output_dir: Path) -> None:
    """
    Copy freshly generated charts into assets/ — the folder the dashboard and
    Streamlit Cloud read — and stamp them with the data fingerprint.

    RBI charts have no CI workflow, so this copy used to be manual; forgetting
    it left the dashboard on old images even after a regeneration.
    """
    target = ASSETS_DIR / output_dir.name
    target.mkdir(parents=True, exist_ok=True)
    produced = {png.name for png in output_dir.glob("*.png")}
    for stale in target.glob("*.png"):
        if stale.name not in produced:
            stale.unlink()
            log.info("Removed retired chart %s from %s", stale.name, target)
    for png in sorted(output_dir.glob("*.png")):
        shutil.copy2(png, target / png.name)
    stamp = db.chart_data_fingerprint()
    for folder in (output_dir, target):
        (folder / FINGERPRINT_FILE).write_text(stamp + "\n")
    log.info("Published charts to %s (fingerprint %s)", target, stamp[:12])


def latest_published_charts() -> Optional[Path]:
    """The newest month folder under assets/rbi_sentinel, which the app shows."""
    folders = sorted(p for p in ASSETS_DIR.glob("20[0-9][0-9]-[01][0-9]") if p.is_dir())
    return folders[-1] if folders else None


def charts_are_current() -> bool:
    """True when the published charts were drawn from the data now in the DB."""
    folder = latest_published_charts()
    if folder is None:
        return False
    stamp = folder / FINGERPRINT_FILE
    return stamp.exists() and stamp.read_text().strip() == db.chart_data_fingerprint()


def refresh_charts_if_stale(mode: str = "dashboard") -> bool:
    """Regenerate and publish the charts if the data has changed. Returns True if it did."""
    if charts_are_current():
        log.info("Charts are current; no regeneration needed")
        return False
    log.warning("Chart data has changed since the charts were published; regenerating")
    run_generate_charts(mode=mode)
    return True
