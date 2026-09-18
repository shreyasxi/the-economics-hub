"""
RBI Bulletin — State of the Economy: where it is read from and what must hold.

The article is the RBI's monthly account of the Indian economy, published in the
Bulletin around the 22nd-25th. Two things are taken from it:

  1. the opening summary and concluding assessment, shown at the top of the
     India tab (`data/rbi_soe.py` -> soe.json -> app.py);
  2. Table IV.3, the transmission of policy rate changes to bank deposit and
     lending rates, which becomes `data/rbi_transmission.csv` and the
     pass-through chart on the India tab.

Access (checked 17 Sep 2026): the web page on rbi.org.in serves a normal request.
The PDF and the Current Statistics spreadsheets live on rbidocs.rbi.org.in, which
answers scripts with a CAPTCHA, so nothing here ever asks for them. Past editions
come from the Bulletin page's own month archive, an ASP.NET postback.

Nothing in the article is summarised or rewritten: the dashboard shows RBI's own
sentences or it shows nothing.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────
# SOURCE
# ─────────────────────────────────────────────

BULLETIN_URL = "https://rbi.org.in/Scripts/BS_ViewBulletin.aspx"
ARTICLE_URL = "https://rbi.org.in/scripts/BS_ViewBulletin.aspx?Id={article_id}"

# The link text on the Bulletin contents page. Constant since the article began
# in November 2020; a month whose contents page has no such link is reported as
# missing, never guessed at.
ARTICLE_TITLE = "State of the Economy"

# The article's first edition (RBI Bulletin, November 2020). Asking for an
# earlier month is a mistake in the caller, not an empty result.
FIRST_EDITION = "2020-11"

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REQUEST_TIMEOUT = 45          # seconds; the Bulletin page is large and slow
PAUSE_SECONDS = 2.0           # between requests, and a backfill reads one month at a time
MAX_ATTEMPTS = 3

CACHE_DIR = PROJECT_ROOT / "data" / "rbi_soe_cache"     # git-ignored
BRIEFING_FILENAME = "soe.json"                          # written into the India edition folder
TRANSMISSION_CSV = PROJECT_ROOT / "data" / "rbi_transmission.csv"   # tracked history

# ─────────────────────────────────────────────
# BRIEFING
# ─────────────────────────────────────────────

# The opening summary has run between 77 and 101 words in every edition read
# (Jan 2021 to Aug 2026). Anything far outside that is not the summary: the page
# layout has changed and the run should fail rather than publish the wrong text.
SUMMARY_MIN_WORDS = 45
SUMMARY_MAX_WORDS = 320

# The concluding section, kept behind a disclosure on the page. Long conclusions
# are shown in full; the cap is a guard against swallowing the annex.
CONCLUSION_MAX_PARAGRAPHS = 3

# An edition older than this is not shown on the dashboard. The article appears
# monthly, so 45 days means one edition has been missed entirely.
MAX_EDITION_AGE_DAYS = 45

ATTRIBUTION = "Reserve Bank of India &middot; Bulletin"

# ─────────────────────────────────────────────
# WHAT CHANGED SINCE LAST MONTH
# ─────────────────────────────────────────────

# Each section of the article opens by saying what happened to its part of the
# economy, with the figures in it: "The headline consumer price index (CPI)
# inflation increased marginally to 4.45 per cent (y-o-y) in July 2026 from 4.38
# per cent in June". Taking that opening sentence from this edition and from the
# month before puts RBI's own verdict on each topic side by side, and carries the
# numbers without any figure being parsed out of the prose and re-presented.
#
# The section headings are stable where the summary's wording is not: over the 19
# editions from Feb 2025 to Aug 2026, Aggregate Supply and Financial Conditions
# appear in all 19, Global and Inflation in 19 and 18, Aggregate Demand in 18.
# Headings drift slightly ("II. Global Setting" and "II. Global Section" are the
# same section), so each is matched by pattern.
#
# A topic missing from either month is left out rather than filled in.
TOPIC_SECTIONS: list[tuple[str, str]] = [
    ("Inflation", r"(?i)^inflation$"),
    ("Demand", r"(?i)^aggregate demand$"),
    ("Supply", r"(?i)^aggregate supply$"),
    ("Money and credit", r"(?i)financial conditions$"),
    ("Global", r"(?i)^[IVX]+\.\s*(the\s+)?global\s"),
]

# Chart pointers are dropped from a quoted sentence: "(Chart III.5a)" is a
# direction to look at a picture that is not on this page. Nothing else in the
# sentence is touched.
CHART_REFERENCE = r"\s*\((?:see\s+)?(?:Chart|Table)[^)]*\)"

# Rows shown at most; five topics is the whole set.
CHANGES_MAX = 5

# A sentence shorter than this is a fragment, not a verdict worth quoting.
CHANGES_MIN_WORDS = 8

# ─────────────────────────────────────────────
# TRANSMISSION TABLE (Table IV.3, numbered differently in older editions)
# ─────────────────────────────────────────────

# The table is found by what its caption says, never by its number: it has been
# Table 5 (2021), Table 4 (2023) and Table IV.3 (2026), and the wording moves
# between "Transmission to Banks' Deposit and Lending Rates" and "Banks' Deposit
# and Lending Rates during the Ongoing Easing Cycle".
TRANSMISSION_CAPTION = r"(transmission|deposit and lending rates)"

# The eight numeric columns, in the order RBI prints them. The parser matches
# each header cell to one of these patterns and fails if the order or the count
# changes, so a renamed or inserted column stops the run instead of quietly
# shifting every value one place.
TRANSMISSION_COLUMNS: list[tuple[str, str]] = [
    ("repo_bps",               r"repo\s*rate"),
    ("wadtdr_fresh_bps",       r"wadtdr.*fresh"),
    ("wadtdr_outstanding_bps", r"wadtdr.*outstanding"),
    ("eblr_bps",               r"\beblr\b"),
    ("mclr_bps",               r"mclr"),
    ("walr_fresh_bps",         r"walr.*fresh"),
    ("walr_outstanding_bps",   r"walr.*outstanding"),
    ("overall_bps",            r"overall|interest\s*rate\s*effect"),
]

# "Overall interest rate effect" was added to the table during 2025; editions
# before that end at the outstanding-loans column. Trailing columns listed here
# may be absent. Any other missing or reordered column stops the run.
TRANSMISSION_OPTIONAL: set[str] = {"overall_bps"}

# What each column is, for the chart and the dashboard's insight text.
COLUMN_LABELS: dict[str, str] = {
    "repo_bps":               "Policy repo rate",
    "wadtdr_fresh_bps":       "Fresh deposits",
    "wadtdr_outstanding_bps": "Outstanding deposits",
    "eblr_bps":               "External benchmark lending rate",
    "mclr_bps":               "1-year MCLR (median)",
    "walr_fresh_bps":         "Fresh rupee loans",
    "walr_outstanding_bps":   "Outstanding rupee loans",
    "overall_bps":            "Overall interest rate effect",
}

# How a cycle's row is labelled. RBI writes it three ways, all seen between
# 2025 and 2026:
#   "Easing Cycle Feb 2025 to Jun 2026"      -> CYCLE_ROW, one row
#   "Easing Phase" then "Feb 2025 to Jun 2025" -> CYCLE_LABEL_ROW then PERIOD_ROW
#   "May-2026"                                -> MONTHLY_ROW, the monthly block
# The middle word has been Cycle, Phase and Period, and month names carry
# footnote marks ("Jun* 2025"), so both are matched loosely.
CYCLE_ROW = r"(?i)^(tightening|easing)\s+(?:cycle|phase|period)\s+(.+?)\s+to\s+(.+?)$"
CYCLE_LABEL_ROW = r"(?i)^(tightening|easing)(?:\s+(?:cycle|phase|period))?$"
PERIOD_ROW = r"(?i)^([A-Za-z]+[*^#]?\s+\d{4})\s+to\s+([A-Za-z]+[*^#]?\s+\d{4})$"
MONTHLY_ROW = r"(?i)^([A-Z][a-z]{2,})[-\s](\d{4})$"

# No policy rate has moved more than this in a single cycle; a parse that returns
# a larger number has read the wrong row or the wrong units.
MAX_PLAUSIBLE_BPS = 1000
