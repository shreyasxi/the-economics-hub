"""
rbi_sentinel/config.py

Central configuration for the RBI Sentinel pipeline.
All URLs, paths, model constants, and scoring parameters live here.
"""

from pathlib import Path

# ── Project Paths ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "rbi_sentinel_cache"
DB_PATH = DATA_DIR / "rbi_sentinel.db"
LOG_PATH = PROJECT_ROOT / "logs" / "rbi_sentinel.log"
OUTPUT_DIR = PROJECT_ROOT / "output" / "rbi_sentinel"
ASSETS_DIR = PROJECT_ROOT / "assets" / "rbi_sentinel"

# ── RBI Website ───────────────────────────────────────────────────────────────
RBI_BASE_URL = "https://www.rbi.org.in"

# Press release base URL (used for individual document fetches)
RBI_PRESS_RELEASE_URL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"

# Master search URL — returns all MPC documents (Resolutions, Minutes, Governor Statements)
# Single entry point; document type is routed from h3 text on each result card.
RBI_SEARCH_URL = (
    "https://www.rbi.org.in/scripts/SearchResults.aspx"
    "?search=Monetary+Policy+Committee"
)

# Kept for reference / legacy fetchers — not used by master_fetcher
RESOLUTION_KEYWORDS = [
    "Monetary Policy Statement",
    "Resolution of the Monetary Policy Committee",
    "MPC Resolution",
]
MINUTES_KEYWORDS = [
    "Minutes of the Monetary Policy Committee",
    "MPC Minutes",
]
GOVERNOR_KEYWORDS = [
    "Governor's Statement",
    "Statement by Governor",
]

# ── HTTP / Retry Settings ─────────────────────────────────────────────────────
REQUEST_TIMEOUT_SECONDS = 30
RATE_LIMIT_DELAY_SECONDS = 2.5       # Minimum gap between requests to rbi.org.in
MAX_RETRY_ATTEMPTS = 4
RETRY_MIN_WAIT_SECONDS = 2
RETRY_MAX_WAIT_SECONDS = 30

# User-Agent string — identify as a research bot, not a browser
USER_AGENT = (
    "Mozilla/5.0 (compatible; EconomicsHubBot/1.0; "
    "+https://economicshub.substack.com)"
)

# ── Versioned CSS Selectors ───────────────────────────────────────────────────
# Tried in order; first match wins. Logs which version succeeded.
HTML_CONTENT_SELECTORS = [
    ("v2024", "div.contentBx"),
    ("v2022", "div#outer table td.tabletext"),
    ("v2020", "td.tabletext"),
    ("v2019", "div.tabletext"),
    ("fallback", "body"),
]

# Minimum word count for extracted text to be considered valid (not an error page)
MIN_VALID_WORD_COUNT = 100

# ── Scoring Model ─────────────────────────────────────────────────────────────
# Bump this string when the lexicon or LLM prompt changes.
# Old rows are preserved in the DB under their original version string.
SCORING_MODEL_VERSION = "hybrid_v1"

# Fusion weights
LEXICON_WEIGHT = 0.25
LLM_WEIGHT = 0.75

# Conflict threshold: |lexicon_score - llm_score| > this → WARNING + low confidence
CONFLICT_THRESHOLD = 0.4

# Low-confidence threshold: use Sonnet instead of Haiku for re-scoring
LOW_CONFIDENCE_THRESHOLD = 0.55

# ── Anthropic API ─────────────────────────────────────────────────────────────
# Default model: Haiku (fast, cheap, sufficient for structured extraction)
LLM_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
# Fallback for low-confidence re-runs
LLM_FALLBACK_MODEL = "claude-sonnet-4-6"

# Max tokens to send to the LLM (preserve intro + conclusion on truncation)
LLM_MAX_INPUT_TOKENS = 8000
LLM_MAX_OUTPUT_TOKENS = 1024

# ── Chart Settings ────────────────────────────────────────────────────────────
# How many recent meetings to show in the Resolution vs Minutes comparison bar chart
COMPARISON_CHART_MEETINGS = 8

# MPC began October 2016 — oldest meeting date to include in historical fetch
MPC_INCEPTION_DATE = "2016-10-04"

# ── Document Type Constants ───────────────────────────────────────────────────
DOC_RESOLUTION = "resolution"
DOC_MINUTES = "minutes"
DOC_GOVERNOR = "governor_statement"

# Minutes are published ~14 days after the resolution
MINUTES_LAG_DAYS = 14

# ── Rate Action Labels ────────────────────────────────────────────────────────
RATE_HIKE = "hike"
RATE_CUT = "cut"
RATE_HOLD = "hold"

# ── Fetch Status Labels ───────────────────────────────────────────────────────
FETCH_SUCCESS = "success"
FETCH_FAILED = "failed"
FETCH_CACHED = "cached"
