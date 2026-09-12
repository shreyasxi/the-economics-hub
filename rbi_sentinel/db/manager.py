"""
rbi_sentinel/db/manager.py

SQLite CRUD layer for the RBI Sentinel pipeline.
All DB access goes through this module — no inline SQL elsewhere.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from rbi_sentinel.config import DB_PATH, SCORING_MODEL_VERSION

log = logging.getLogger("rbi_sentinel.db")

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


# ── Connection ─────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist. Safe to call on every pipeline run."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(schema)
    log.info("DB initialised at %s", DB_PATH)


# ── mpc_meetings ───────────────────────────────────────────────────────────────

def upsert_meeting(
    meeting_date: str,
    *,
    policy_cycle: Optional[str] = None,
    repo_rate_pct: Optional[float] = None,
    rate_action: Optional[str] = None,
    rate_change_bps: Optional[int] = None,
    vote_hawkish: Optional[int] = None,
    vote_dovish: Optional[int] = None,
    notes: Optional[str] = None,
) -> int:
    """Insert or update a meeting row. Returns meeting_id."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO mpc_meetings
                (meeting_date, policy_cycle, repo_rate_pct, rate_action,
                 rate_change_bps, vote_hawkish, vote_dovish, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(meeting_date) DO UPDATE SET
                policy_cycle    = COALESCE(excluded.policy_cycle, policy_cycle),
                repo_rate_pct   = COALESCE(excluded.repo_rate_pct, repo_rate_pct),
                rate_action     = COALESCE(excluded.rate_action, rate_action),
                rate_change_bps = COALESCE(excluded.rate_change_bps, rate_change_bps),
                vote_hawkish    = COALESCE(excluded.vote_hawkish, vote_hawkish),
                vote_dovish     = COALESCE(excluded.vote_dovish, vote_dovish),
                notes           = COALESCE(excluded.notes, notes),
                updated_at      = datetime('now')
            """,
            (meeting_date, policy_cycle, repo_rate_pct, rate_action,
             rate_change_bps, vote_hawkish, vote_dovish, notes),
        )
        row = conn.execute(
            "SELECT meeting_id FROM mpc_meetings WHERE meeting_date = ?",
            (meeting_date,),
        ).fetchone()
    return row["meeting_id"]


def get_all_meetings(order: str = "ASC") -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM mpc_meetings ORDER BY meeting_date {order}"
        ).fetchall()
    return [dict(r) for r in rows]


def get_meeting_by_date(meeting_date: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM mpc_meetings WHERE meeting_date = ?",
            (meeting_date,),
        ).fetchone()
    return dict(row) if row else None


# ── rbi_documents ──────────────────────────────────────────────────────────────

def upsert_document(
    meeting_id: int,
    doc_type: str,
    publication_date: str,
    source_url: str,
    source_format: str,
    fetch_status: str,
    raw_text: Optional[str] = None,
    word_count: Optional[int] = None,
    cache_path: Optional[str] = None,
) -> int:
    """Insert or update a document row. Returns doc_id."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO rbi_documents
                (meeting_id, doc_type, publication_date, source_url,
                 source_format, fetch_status, raw_text, word_count,
                 fetch_timestamp, cache_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            ON CONFLICT(meeting_id, doc_type) DO UPDATE SET
                fetch_status    = excluded.fetch_status,
                raw_text        = COALESCE(excluded.raw_text, raw_text),
                word_count      = COALESCE(excluded.word_count, word_count),
                source_url      = excluded.source_url,
                fetch_timestamp = datetime('now'),
                cache_path      = COALESCE(excluded.cache_path, cache_path)
            """,
            (meeting_id, doc_type, publication_date, source_url,
             source_format, fetch_status, raw_text, word_count, cache_path),
        )
        row = conn.execute(
            "SELECT doc_id FROM rbi_documents WHERE meeting_id = ? AND doc_type = ?",
            (meeting_id, doc_type),
        ).fetchone()
    return row["doc_id"]


def get_document(meeting_id: int, doc_type: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM rbi_documents WHERE meeting_id = ? AND doc_type = ?",
            (meeting_id, doc_type),
        ).fetchone()
    return dict(row) if row else None


def get_documents_without_scores(
    model_version: str = SCORING_MODEL_VERSION,
) -> list[dict]:
    """
    Return documents that are ready to score but have no score yet.
    Ready = fetch succeeded AND (raw_text stored OR cache_path exists on disk).
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*
            FROM rbi_documents d
            LEFT JOIN sentiment_scores s
                ON s.doc_id = d.doc_id
               AND s.scoring_model_version = ?
            WHERE d.fetch_status IN ('success', 'cached')
              AND (d.raw_text IS NOT NULL OR d.cache_path IS NOT NULL)
              AND s.score_id IS NULL
            ORDER BY d.publication_date ASC
            """,
            (model_version,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── sentiment_scores ───────────────────────────────────────────────────────────

def upsert_score(
    doc_id: int,
    meeting_id: int,
    *,
    scoring_model_version: str = SCORING_MODEL_VERSION,
    overall_score: float,
    score_confidence: Optional[float] = None,
    inflation_stance: Optional[float] = None,
    growth_stance: Optional[float] = None,
    liquidity_stance: Optional[float] = None,
    rate_guidance: Optional[float] = None,
    fx_external_stance: Optional[float] = None,
    lexicon_raw_score: Optional[float] = None,
    lexicon_hawkish_hits: Optional[int] = None,
    lexicon_dovish_hits: Optional[int] = None,
    llm_raw_response: Optional[str] = None,
    narrative_summary: Optional[str] = None,
    key_phrases: Optional[list] = None,
) -> int:
    key_phrases_json = json.dumps(key_phrases) if key_phrases else None
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sentiment_scores (
                doc_id, meeting_id, scoring_model_version,
                overall_score, score_confidence,
                inflation_stance, growth_stance, liquidity_stance,
                rate_guidance, fx_external_stance,
                lexicon_raw_score, lexicon_hawkish_hits, lexicon_dovish_hits,
                llm_raw_response, narrative_summary, key_phrases,
                scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(doc_id, scoring_model_version) DO UPDATE SET
                overall_score       = excluded.overall_score,
                score_confidence    = excluded.score_confidence,
                inflation_stance    = excluded.inflation_stance,
                growth_stance       = excluded.growth_stance,
                liquidity_stance    = excluded.liquidity_stance,
                rate_guidance       = excluded.rate_guidance,
                fx_external_stance  = excluded.fx_external_stance,
                lexicon_raw_score   = excluded.lexicon_raw_score,
                lexicon_hawkish_hits= excluded.lexicon_hawkish_hits,
                lexicon_dovish_hits = excluded.lexicon_dovish_hits,
                llm_raw_response    = excluded.llm_raw_response,
                narrative_summary   = excluded.narrative_summary,
                key_phrases         = excluded.key_phrases,
                scored_at           = datetime('now')
            """,
            (doc_id, meeting_id, scoring_model_version,
             overall_score, score_confidence,
             inflation_stance, growth_stance, liquidity_stance,
             rate_guidance, fx_external_stance,
             lexicon_raw_score, lexicon_hawkish_hits, lexicon_dovish_hits,
             llm_raw_response, narrative_summary, key_phrases_json),
        )
        row = conn.execute(
            "SELECT score_id FROM sentiment_scores WHERE doc_id = ? AND scoring_model_version = ?",
            (doc_id, scoring_model_version),
        ).fetchone()
    return row["score_id"]


def get_scores_for_meeting(
    meeting_id: int,
    model_version: str = SCORING_MODEL_VERSION,
) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*, d.doc_type
            FROM sentiment_scores s
            JOIN rbi_documents d ON d.doc_id = s.doc_id
            WHERE s.meeting_id = ? AND s.scoring_model_version = ?
            """,
            (meeting_id, model_version),
        ).fetchall()
    return [dict(r) for r in rows]


def get_scores_for_cycle(
    policy_cycle: str,
    model_version: str = SCORING_MODEL_VERSION,
) -> list[dict]:
    """
    All document scores belonging to one policy cycle.

    A single MPC decision is published across several dates — the resolution
    and governor statement on the day, the minutes 14 days later, and a
    Monthly Bulletin reprint of the first two some weeks after that. Scores
    must be gathered across every meeting row sharing a policy_cycle, or a
    "composite" ends up being one document renormalised to 100%.

    Bulletin reprints are excluded: they are the same text as the press
    release and would double-count the resolution. Documents with no
    extracted text are excluded for the same reason they carry no analysis.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*, d.doc_type
            FROM sentiment_scores s
            JOIN rbi_documents d ON d.doc_id = s.doc_id
            JOIN mpc_meetings   m ON m.meeting_id = d.meeting_id
            WHERE m.policy_cycle = ?
              AND s.scoring_model_version = ?
              AND d.source_kind = 'press_release'
              AND d.word_count IS NOT NULL AND d.word_count > 0
            ORDER BY d.publication_date
            """,
            (policy_cycle, model_version),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_policy_cycles() -> list[dict]:
    """
    One row per policy cycle, with the anchor meeting that represents it.

    The anchor is the meeting whose date IS the decision date — the row the
    composite is stored against, so existing chart queries keep working.
    Note meeting_id is assigned in fetch order (newest first), not date
    order, so it cannot be used to pick the anchor.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT c.policy_cycle,
                   (SELECT a.meeting_id
                      FROM mpc_meetings a
                     WHERE a.policy_cycle = c.policy_cycle
                     ORDER BY (a.meeting_date <> a.policy_cycle), a.meeting_date
                     LIMIT 1)      AS anchor_meeting_id,
                   COUNT(*)        AS meeting_rows
            FROM mpc_meetings c
            WHERE c.policy_cycle IS NOT NULL
            GROUP BY c.policy_cycle
            ORDER BY c.policy_cycle
            """
        ).fetchall()
    return [dict(r) for r in rows]


# ── meeting_composites ─────────────────────────────────────────────────────────

def upsert_composite(
    meeting_id: int,
    *,
    scoring_model_version: str = SCORING_MODEL_VERSION,
    composite_overall_score: Optional[float] = None,
    resolution_score: Optional[float] = None,
    minutes_score: Optional[float] = None,
    governor_score: Optional[float] = None,
    score_divergence: Optional[float] = None,
    composite_narrative: Optional[str] = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO meeting_composites (
                meeting_id, scoring_model_version,
                composite_overall_score, resolution_score,
                minutes_score, governor_score,
                score_divergence, composite_narrative, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(meeting_id, scoring_model_version) DO UPDATE SET
                composite_overall_score = excluded.composite_overall_score,
                resolution_score        = excluded.resolution_score,
                minutes_score           = excluded.minutes_score,
                governor_score          = excluded.governor_score,
                score_divergence        = excluded.score_divergence,
                composite_narrative     = excluded.composite_narrative,
                computed_at             = datetime('now')
            """,
            (meeting_id, scoring_model_version,
             composite_overall_score, resolution_score,
             minutes_score, governor_score,
             score_divergence, composite_narrative),
        )


def prune_non_anchor_composites(
    model_version: str = SCORING_MODEL_VERSION,
) -> int:
    """
    Delete composites attached to meeting rows that are not a cycle anchor.

    Before policy cycles existed, every publication date got its own
    composite — so one decision produced up to three, each built from a
    single document. Those rows would still be picked up by the charts.
    Returns the number deleted.
    """
    with _connect() as conn:
        cur = conn.execute(
            """
            DELETE FROM meeting_composites
            WHERE scoring_model_version = ?
              AND meeting_id NOT IN (
                    SELECT (SELECT a.meeting_id
                              FROM mpc_meetings a
                             WHERE a.policy_cycle = c.policy_cycle
                             ORDER BY (a.meeting_date <> a.policy_cycle),
                                      a.meeting_date
                             LIMIT 1)
                      FROM mpc_meetings c
                     WHERE c.policy_cycle IS NOT NULL
                     GROUP BY c.policy_cycle
              )
            """,
            (model_version,),
        )
        return cur.rowcount


def get_latest_composite(
    model_version: str = SCORING_MODEL_VERSION,
) -> Optional[dict]:
    """Return the composite for the most recent meeting with a score."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT mc.*, m.meeting_date, m.repo_rate_pct, m.rate_action
            FROM meeting_composites mc
            JOIN mpc_meetings m ON m.meeting_id = mc.meeting_id
            WHERE mc.scoring_model_version = ?
              AND mc.composite_overall_score IS NOT NULL
            ORDER BY m.meeting_date DESC
            LIMIT 1
            """,
            (model_version,),
        ).fetchone()
    return dict(row) if row else None


def get_all_composites(
    model_version: str = SCORING_MODEL_VERSION,
) -> list[dict]:
    """Return all composites joined with meeting metadata, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT mc.*, m.meeting_date, m.repo_rate_pct, m.rate_action,
                   m.rate_change_bps, m.vote_hawkish, m.vote_dovish
            FROM meeting_composites mc
            JOIN mpc_meetings m ON m.meeting_id = mc.meeting_id
            WHERE mc.scoring_model_version = ?
            ORDER BY m.meeting_date ASC
            """,
            (model_version,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_composites(
    n: int,
    model_version: str = SCORING_MODEL_VERSION,
) -> list[dict]:
    """Return the n most recent composites, oldest first (for bar charts)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT mc.*, m.meeting_date, m.repo_rate_pct, m.rate_action
            FROM meeting_composites mc
            JOIN mpc_meetings m ON m.meeting_id = mc.meeting_id
            WHERE mc.scoring_model_version = ?
              AND mc.composite_overall_score IS NOT NULL
            ORDER BY m.meeting_date DESC
            LIMIT ?
            """,
            (model_version, n),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ── fetch_log ─────────────────────────────────────────────────────────────────

def log_fetch(
    url: str,
    attempt_number: int,
    success: bool,
    *,
    http_status: Optional[int] = None,
    error_message: Optional[str] = None,
    response_bytes: Optional[int] = None,
    duration_ms: Optional[int] = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO fetch_log
                (url, attempt_number, http_status, success,
                 error_message, response_bytes, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (url, attempt_number, http_status, int(success),
             error_message, response_bytes, duration_ms),
        )
