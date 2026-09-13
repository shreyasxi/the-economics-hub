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
# Confirmed against live RBI press release pages (April 2026):
#   Content lives in <td> inside <table class="tablebg">, inside div.grid_11
HTML_CONTENT_SELECTORS = [
    ("v2026", "table.tablebg td"),              # Current RBI layout (confirmed 2026)
    ("v2024", "div.grid_11 td"),                # Grid layout fallback
    ("v2023", "div.right_blue_border td"),      # Right column fallback
    ("v2022", "div#doublescroll td"),            # Scroll wrapper fallback
    ("v2020", "div.text1 td"),                  # Outer text div fallback
    ("v2019", "td.tabletext"),                  # Legacy tabletext class
    ("v2018", "div.contentBx"),                 # Older layout
]

# Minimum word count for extracted text to be considered valid (not an error page)
MIN_VALID_WORD_COUNT = 100

# ── Scoring Model ─────────────────────────────────────────────────────────────
# Bump this string when the lexicon or LLM prompt changes.
# Old rows are preserved in the DB under their original version string.
# Bump this whenever the scoring method changes. sentiment_scores is
# UNIQUE(doc_id, scoring_model_version), so a new version writes new rows and
# leaves the previous generation queryable for comparison rather than
# overwriting it.
#
#   hybrid_v1  Haiku 4.5, 8k input cap (truncated 78% of minutes), documents
#              grouped by publication date so most composites rested on a
#              single document.
#   hybrid_v2  Opus 5 at low effort, 32k input cap (no truncation), documents
#              grouped by policy cycle.
SCORING_MODEL_VERSION = "hybrid_v2"

# Fusion weights
LEXICON_WEIGHT = 0.25
LLM_WEIGHT = 0.75

# Conflict threshold: |lexicon_score - llm_score| > this → WARNING + low confidence
CONFLICT_THRESHOLD = 0.4

# Low-confidence threshold: use Sonnet instead of Haiku for re-scoring
LOW_CONFIDENCE_THRESHOLD = 0.55

# ── Anthropic API ─────────────────────────────────────────────────────────────
# Default model. Scoring a central bank document is a judgement task, not an
# extraction task, and the two models disagree on real documents -- Opus reads
# "downside risks to growth" as dovish where Haiku reads it as marginally
# hawkish. At ~$0.15 per MPC meeting the accuracy is worth the difference.
LLM_DEFAULT_MODEL = "claude-opus-5"
# Fallback for low-confidence re-runs. Sonnet 5 supersedes Sonnet 4.6 and is
# both newer and cheaper ($2/$10 per MTok against $3/$15).
LLM_FALLBACK_MODEL = "claude-sonnet-5"

# Max tokens to send to the LLM.
# Was 8000, which truncated 78% of the minutes -- the longest documents and the
# ones weighted highest (0.50) in the composite. 32k clears every document in
# the corpus (longest is ~9,700 words) and costs ~$0.09 more per full rescore.
LLM_MAX_INPUT_TOKENS = 32000

# Max tokens the model may return.
# On thinking-capable models (Opus 5, Sonnet 5, ...) this budget is shared
# between thinking and the visible JSON, so 1024 risked a truncated response.
LLM_MAX_OUTPUT_TOKENS = 4096

# Reasoning effort, for models that accept output_config.effort.
# Scoring a policy document is not a hard reasoning problem, and low effort
# keeps thinking short -- which matters because thinking bills as output.
# Set to None to omit the parameter entirely.
LLM_EFFORT = "low"

# Models that reject output_config.effort. Passing it to these is a 400.
LLM_MODELS_WITHOUT_EFFORT = (
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
)

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
