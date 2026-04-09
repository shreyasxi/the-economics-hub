-- ── RBI SENTINEL SCHEMA v1 ────────────────────────────────────────────────────
-- All timestamps are ISO-8601 strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
-- Scores range from -1.0 (extremely dovish) to +1.0 (extremely hawkish).
-- scoring_model_version allows full re-analysis without data loss.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── 1. MPC MEETINGS ──────────────────────────────────────────────────────────
-- One row per MPC meeting cycle. Identified by the rate decision date.

CREATE TABLE IF NOT EXISTS mpc_meetings (
    meeting_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_date        TEXT NOT NULL UNIQUE,   -- Date of rate decision (YYYY-MM-DD)
    policy_cycle        TEXT,                   -- e.g. "FY2026-Q1" for grouping
    repo_rate_pct       REAL,                   -- Repo rate set at this meeting (%)
    rate_action         TEXT,                   -- "hike" | "cut" | "hold"
    rate_change_bps     INTEGER,                -- bps change (positive=hike, negative=cut, 0=hold)
    vote_hawkish        INTEGER,                -- Members voting hawkish/for hike
    vote_dovish         INTEGER,                -- Members voting dovish/for cut
    notes               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- ── 2. RAW DOCUMENTS ─────────────────────────────────────────────────────────
-- One row per (meeting, doc_type). Stores full extracted text for re-scoring.

CREATE TABLE IF NOT EXISTS rbi_documents (
    doc_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id          INTEGER NOT NULL REFERENCES mpc_meetings(meeting_id),
    doc_type            TEXT NOT NULL,          -- "resolution" | "minutes" | "governor_statement"
    publication_date    TEXT NOT NULL,          -- Date document was published (YYYY-MM-DD)
    source_url          TEXT NOT NULL,
    source_format       TEXT NOT NULL,          -- "html" | "pdf"
    fetch_status        TEXT NOT NULL,          -- "success" | "failed" | "cached"
    raw_text            TEXT,                   -- Full extracted text (NULL if fetch failed)
    word_count          INTEGER,
    fetch_timestamp     TEXT DEFAULT (datetime('now')),
    cache_path          TEXT,                   -- Relative path to cached file
    UNIQUE(meeting_id, doc_type)
);

-- ── 3. SENTIMENT SCORES ───────────────────────────────────────────────────────
-- One row per (document, scoring_model_version). Multiple rows valid per document
-- as the model evolves — old scores are never overwritten.

CREATE TABLE IF NOT EXISTS sentiment_scores (
    score_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id                      INTEGER NOT NULL REFERENCES rbi_documents(doc_id),
    meeting_id                  INTEGER NOT NULL REFERENCES mpc_meetings(meeting_id),
    scoring_model_version       TEXT NOT NULL,

    -- Primary Score
    overall_score               REAL NOT NULL,      -- [-1.0, +1.0] composite
    score_confidence            REAL,               -- [0.0, 1.0]

    -- Sub-Dimension Scores (all [-1.0, +1.0])
    inflation_stance            REAL,               -- Negative=dismissive; Positive=alarmed
    growth_stance               REAL,               -- Negative=concerned; Positive=optimistic
    liquidity_stance            REAL,               -- Negative=accommodative; Positive=tightening
    rate_guidance               REAL,               -- Negative=cuts ahead; Positive=hikes ahead
    fx_external_stance          REAL,               -- Negative=depreciation tolerant; Positive=defensive

    -- Lexicon Audit Trail
    lexicon_raw_score           REAL,
    lexicon_hawkish_hits        INTEGER,
    lexicon_dovish_hits         INTEGER,

    -- LLM Output
    llm_raw_response            TEXT,               -- Full JSON response (audit)
    narrative_summary           TEXT,               -- 2-paragraph Markdown for app display
    key_phrases                 TEXT,               -- JSON array of pivotal phrases

    scored_at                   TEXT DEFAULT (datetime('now')),
    UNIQUE(doc_id, scoring_model_version)
);

-- ── 4. MEETING COMPOSITES ─────────────────────────────────────────────────────
-- Denormalized per-meeting aggregate. Pre-computed so Streamlit loads without joins.

CREATE TABLE IF NOT EXISTS meeting_composites (
    composite_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id                  INTEGER NOT NULL REFERENCES mpc_meetings(meeting_id),
    scoring_model_version       TEXT NOT NULL,
    composite_overall_score     REAL,
    resolution_score            REAL,
    minutes_score               REAL,
    governor_score              REAL,
    score_divergence            REAL,               -- abs(resolution_score - minutes_score)
    composite_narrative         TEXT,               -- Combined 2-paragraph narrative
    computed_at                 TEXT DEFAULT (datetime('now')),
    UNIQUE(meeting_id, scoring_model_version)
);

-- ── 5. FETCH LOG ─────────────────────────────────────────────────────────────
-- Append-only audit log of every HTTP attempt. Never updated, only inserted.

CREATE TABLE IF NOT EXISTS fetch_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL,
    attempt_number  INTEGER NOT NULL DEFAULT 1,
    http_status     INTEGER,                        -- NULL if connection error
    success         INTEGER NOT NULL,               -- 0 or 1
    error_message   TEXT,
    response_bytes  INTEGER,
    duration_ms     INTEGER,
    logged_at       TEXT DEFAULT (datetime('now'))
);

-- ── INDICES ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_docs_meeting      ON rbi_documents(meeting_id);
CREATE INDEX IF NOT EXISTS idx_scores_doc        ON sentiment_scores(doc_id);
CREATE INDEX IF NOT EXISTS idx_scores_meeting    ON sentiment_scores(meeting_id);
CREATE INDEX IF NOT EXISTS idx_composite_mtg     ON meeting_composites(meeting_id);
CREATE INDEX IF NOT EXISTS idx_meetings_date     ON mpc_meetings(meeting_date);
CREATE INDEX IF NOT EXISTS idx_scores_version    ON sentiment_scores(scoring_model_version);
CREATE INDEX IF NOT EXISTS idx_composite_version ON meeting_composites(scoring_model_version);
