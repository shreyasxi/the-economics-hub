"""
Economics Hub — World tab configuration
========================================
Countries, data sources and central bank meeting calendars for the World
tab (generate_macro.py writes the snapshot; app.py renders it).

Every scoreboard cell is either AUTO (fetched from an official API each run;
a failed or stale fetch fails the run) or MANUAL (no free machine-readable
source; keyed in with `python -m data.world_manual_entry`, shown as "awaiting
entry" when missing and flagged when old — never guessed).

Central bank calendars are the banks' own published schedules. Update them
once a year when the next year's dates appear (see MEETING_SOURCES).
"""

from __future__ import annotations

# ─────────────────────────────────────────────
# COUNTRIES — scoreboard rows, chart colours
# ─────────────────────────────────────────────
COUNTRIES = {
    "US": {"label": "United States", "color": "#003366"},
    "EA": {"label": "Euro area",     "color": "#008080"},
    "UK": {"label": "United Kingdom", "color": "#6B7280"},
    "JP": {"label": "Japan",         "color": "#800080"},
    "CN": {"label": "China",         "color": "#CC0000"},
    "IN": {"label": "India",         "color": "#FF9933"},
}

# ─────────────────────────────────────────────
# SCOREBOARD COLUMNS
# ─────────────────────────────────────────────
#   good        "up" / "down": which direction of change is coloured green.
#               None: change shown in neutral ink.
#   max_age     days since the observation period STARTED before a value
#               counts as stale (monthly periods start on the 1st, so a
#               monthly series released ~6 weeks after month-end is ~75 days
#               old on release day).
SCOREBOARD_COLUMNS = {
    "mfg_pmi":      {"label": "Mfg PMI",       "unit": "",  "good": "up",   "max_age": 70},
    "cpi_yoy":      {"label": "CPI inflation", "unit": "%", "good": "down", "max_age": 110},
    "unemployment": {"label": "Unemployment",  "unit": "%", "good": "down", "max_age": 160},
    "policy_rate":  {"label": "Policy rate",   "unit": "%", "good": None,   "max_age": 21},
    "ten_year":     {"label": "10Y yield",     "unit": "%", "good": None,   "max_age": 14},
    "fx_ytd":       {"label": "Currency YTD",  "unit": "%", "good": "up",   "max_age": 7},
}

# Where each cell comes from. "manual" cells are the only ones the manual
# entry tool accepts; everything else is fetched.
CELL_SOURCES = {
    "US": {
        "mfg_pmi": "manual",
        "cpi_yoy": "FRED CPIAUCSL (BLS)",
        "unemployment": "FRED UNRATE (BLS)",
        "policy_rate": "FRED DFEDTARL/DFEDTARU + FOMC statement",
        "ten_year": "FRED DGS10",
        "fx_ytd": "Yahoo Finance DX-Y.NYB (DXY)",
    },
    "EA": {
        "mfg_pmi": "manual",
        "cpi_yoy": "Eurostat prc_hicp_minr (HICP)",
        "unemployment": "Eurostat une_rt_m",
        "policy_rate": "FRED ECBDFR (deposit facility rate)",
        "ten_year": "Deutsche Bundesbank (German Bund)",
        "fx_ytd": "Yahoo Finance EURUSD=X",
    },
    "UK": {
        "mfg_pmi": "manual",
        "cpi_yoy": "OECD Prices (ONS CPI)",
        "unemployment": "OECD Labour Force Statistics (ONS)",
        "policy_rate": "Bank of England IUDBEDR (Bank Rate)",
        "ten_year": "Bank of England IUDMNPY (par yield)",
        "fx_ytd": "Yahoo Finance GBPUSD=X",
    },
    "JP": {
        "mfg_pmi": "manual",
        "cpi_yoy": "manual",
        "unemployment": "OECD Labour Force Statistics",
        "policy_rate": "BIS central bank policy rates",
        "ten_year": "Ministry of Finance Japan (JGB)",
        "fx_ytd": "Yahoo Finance JPY=X",
    },
    "CN": {
        "mfg_pmi": "manual",
        "cpi_yoy": "OECD Prices (NBS CPI)",
        "unemployment": "manual",
        "policy_rate": "BIS central bank policy rates (1Y LPR)",
        "ten_year": "manual",
        "fx_ytd": "Yahoo Finance CNY=X",
    },
    "IN": {
        "mfg_pmi": "India database (S&P Global, entered monthly)",
        "cpi_yoy": "India database (MoSPI, entered monthly)",
        "unemployment": "India database (PLFS, entered monthly)",
        "policy_rate": "RBI Sentinel database (MPC Resolution)",
        "ten_year": "RBI DBIE workbook (FBIL 10-year G-Sec)",
        "fx_ytd": "Yahoo Finance INR=X",
    },
}

# Cells whose period is coarser than the column default: China's 10-year is a
# month-end figure; India's comes from the weekly DBIE sheet, refreshed monthly.
MAX_AGE_OVERRIDES = {("CN", "ten_year"): 75, ("IN", "ten_year"): 45}

# Cells fed by a file the owner refreshes by hand (India database, DBIE
# workbook). Old values here are flagged on the page, not treated as a
# broken source.
HAND_REFRESHED = {("IN", "mfg_pmi"), ("IN", "cpi_yoy"), ("IN", "unemployment"), ("IN", "ten_year")}

# What to key in for each manual cell, and where to find it.
MANUAL_FIELDS = {
    ("US", "mfg_pmi"): ("S&P Global US Manufacturing PMI", "https://www.pmi.spglobal.com/Public/Release/PressReleases"),
    ("EA", "mfg_pmi"): ("HCOB Eurozone Manufacturing PMI", "https://www.pmi.spglobal.com/Public/Release/PressReleases"),
    ("UK", "mfg_pmi"): ("S&P Global UK Manufacturing PMI", "https://www.pmi.spglobal.com/Public/Release/PressReleases"),
    ("JP", "mfg_pmi"): ("S&P Global Japan Manufacturing PMI", "https://www.pmi.spglobal.com/Public/Release/PressReleases"),
    ("CN", "mfg_pmi"): ("S&P Global China General Manufacturing PMI", "https://www.pmi.spglobal.com/Public/Release/PressReleases"),
    ("JP", "cpi_yoy"): ("Statistics Bureau of Japan, national CPI all items, % YoY", "https://www.stat.go.jp/english/data/cpi/"),
    ("CN", "unemployment"): ("NBS surveyed urban unemployment rate", "https://www.stats.gov.cn/english/PressRelease/"),
    ("CN", "ten_year"): ("ChinaBond 10-year government bond yield, month-end", "https://yield.chinabond.com.cn/"),
}

# Plausible ranges; a value outside is refused (typo guard, not a forecast).
MANUAL_RANGES = {
    "mfg_pmi": (30.0, 70.0),
    "cpi_yoy": (-5.0, 30.0),
    "unemployment": (0.0, 30.0),
    "ten_year": (-1.0, 20.0),
}

# ─────────────────────────────────────────────
# OECD / BIS / YAHOO CODES
# ─────────────────────────────────────────────
OECD_CPI_AREAS = {"UK": "GBR", "CN": "CHN"}
OECD_UNEMP_AREAS = {"UK": "GBR", "JP": "JPN"}
# OECD publishes no euro-area CLI; G4E is its aggregate of Germany, France,
# Italy and Spain and is labelled as such wherever it appears.
OECD_CLI_AREAS = {"US": "USA", "EA": "G4E", "UK": "GBR", "JP": "JPN", "CN": "CHN", "IN": "IND"}
# Every country the OECD publishes a leading indicator for, for the ranked
# chart. Its aggregates (G7, G20, NAFTA, G4E, A5M) are deliberately left out:
# the chart ranks economies against each other, not blocs against economies.
OECD_CLI_COUNTRIES = {
    "AUS": "Australia", "BRA": "Brazil", "CAN": "Canada", "CHN": "China",
    "DEU": "Germany", "ESP": "Spain", "FRA": "France", "GBR": "United Kingdom",
    "IDN": "Indonesia", "IND": "India", "ITA": "Italy", "JPN": "Japan",
    "KOR": "South Korea", "MEX": "Mexico", "TUR": "Turkey",
    "USA": "United States", "ZAF": "South Africa",
}
BIS_POLICY_AREAS = {"JP": "JP", "CN": "CN"}   # UK Bank Rate comes from the BoE itself: BIS runs ~9 days behind
FX_TICKERS = {
    # (ticker, quoted as USD per unit of local currency?)
    "US": ("DX-Y.NYB", True),   # DXY: the dollar itself; up = stronger dollar
    "EA": ("EURUSD=X", True),
    "UK": ("GBPUSD=X", True),
    "JP": ("JPY=X", False),
    "CN": ("CNY=X", False),
    "IN": ("INR=X", False),
}

# FRED release ids for the calendar (dates come from FRED's release calendar).
FRED_RELEASES = {
    10: "US CPI",
    50: "US jobs report",
    53: "US GDP",
    54: "US PCE inflation",
}

# ─────────────────────────────────────────────
# CENTRAL BANKS — KPI strip and calendar
# ─────────────────────────────────────────────
# Decision (announcement) dates only; for two-day meetings the second day.
MEETING_SOURCES = {
    "fed": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "ecb": "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html",
    "boe": "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates",
    "boj": "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm",
}
MEETINGS_VERIFIED = "2026-09-15"

CENTRAL_BANKS = [
    {
        "id": "fed", "country": "US", "name": "Federal Reserve", "short": "Fed",
        "rate_label": "Fed funds target", "meeting_label": "FOMC decision",
        # 2027 dates are tentative until confirmed at the preceding meeting.
        "meetings": [
            "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
            "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
            "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
            "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
        ],
    },
    {
        "id": "ecb", "country": "EA", "name": "European Central Bank", "short": "ECB",
        "rate_label": "Deposit facility rate", "meeting_label": "ECB decision",
        "meetings": [
            "2026-10-29", "2026-12-17",
            "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-10",
            "2027-07-22", "2027-09-09", "2027-10-28", "2027-12-16",
        ],
    },
    {
        "id": "boe", "country": "UK", "name": "Bank of England", "short": "BoE",
        "rate_label": "Bank Rate", "meeting_label": "BoE decision",
        # 2027 dates are provisional.
        "meetings": [
            "2026-02-05", "2026-03-19", "2026-04-30", "2026-06-18",
            "2026-07-30", "2026-09-17", "2026-11-05", "2026-12-17",
            "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-17",
            "2027-07-29", "2027-09-16", "2027-11-04", "2027-12-16",
        ],
    },
    {
        "id": "boj", "country": "JP", "name": "Bank of Japan", "short": "BoJ",
        "rate_label": "Policy rate", "meeting_label": "BoJ decision",
        "meetings": [
            "2026-01-23", "2026-03-19", "2026-04-28", "2026-06-16",
            "2026-07-31", "2026-09-18", "2026-10-30", "2026-12-18",
            "2027-01-22", "2027-03-18", "2027-04-28", "2027-06-11",
            "2027-07-22", "2027-09-22", "2027-10-29", "2027-12-17",
        ],
    },
    {
        "id": "pboc", "country": "CN", "name": "People's Bank of China", "short": "PBoC",
        "rate_label": "1-year loan prime rate", "meeting_label": "China loan prime rate",
        # The LPR is fixed on the 20th of each month (moved to the next working
        # day when the 20th is a holiday) — there is no meeting calendar.
        "meetings": None,
    },
    {
        "id": "rbi", "country": "IN", "name": "Reserve Bank of India", "short": "RBI",
        "rate_label": "Repo rate", "meeting_label": "RBI MPC decision",
        # Rate, last move and next meeting come live from the RBI Sentinel database.
        "meetings": None,
    },
]
