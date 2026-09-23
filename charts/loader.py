"""
Economics Hub — Chart Loader
Discovers the latest chart folder and returns sorted PNG paths.

Resolution order:
  1. assets/  — git-tracked, used on Streamlit Cloud and after CI commits
  2. output/  — local dev fallback (git-ignored but exists on disk)

Both directories are checked so local development works without a CI commit.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Directory resolution
# ---------------------------------------------------------------------------

def _get_base_dirs() -> list[Path]:
    return [
        PROJECT_ROOT / "assets",
        PROJECT_ROOT / "output",
    ]


def _latest_folder(subdir: str) -> tuple[Path | None, str | None]:
    """
    Find the most recent dated subfolder across both base directories.

    Weekly:      subdir = "weekly",  folders named YYYY-MM-DD
    Macro/India: subdir = "macro" or "india", folders named YYYY-MM

    Returns (path, date_label) or (None, None) if nothing is found.
    """
    candidates: list[Path] = []
    for base in _get_base_dirs():
        p = base / subdir
        if not p.exists():
            continue
        for child in p.iterdir():
            if child.is_dir():
                candidates.append(child)

    if not candidates:
        return None, None

    # Lexicographic sort works for both YYYY-MM-DD and YYYY-MM formats
    latest = sorted(candidates, key=lambda x: x.name)[-1]
    return latest, latest.name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_charts(subdir: str) -> tuple[list[Path], str | None]:
    """
    Return (sorted_png_list, date_label) for the latest folder under `subdir`.

    PNGs are sorted by natural order so that 10b_ sorts after 10_ and
    before 11_, handling the irregular numbering in the weekly pipeline.
    """
    folder, label = _latest_folder(subdir)
    if folder is None:
        return [], None

    pngs = sorted(
        folder.glob("*.png"),
        key=lambda p: _natural_sort_key(p.name),
    )
    return pngs, label


def get_folder_mtime(subdir: str) -> datetime | None:
    """
    Return the modification time of the most recently modified PNG in the
    latest folder. Used to display "Last updated: YYYY-MM-DD HH:MM".
    """
    folder, _ = _latest_folder(subdir)
    if folder is None:
        return None

    pngs = list(folder.glob("*.png"))
    if not pngs:
        return None

    return datetime.fromtimestamp(max(p.stat().st_mtime for p in pngs))


def is_pipeline_admin() -> bool:
    """
    Returns True only when the PIPELINE_KEY secret/env-var is set and non-empty.

    How it works:
    - Locally: set PIPELINE_KEY in .streamlit/secrets.toml (never committed)
    - Streamlit Cloud: do NOT add PIPELINE_KEY to app secrets → always False
    - Any random visitor to the deployed app: never sees pipeline controls

    This is safer than checking for env vars that Streamlit Cloud may set
    unpredictably across versions.
    """
    # Check Streamlit secrets first (works both locally and on Cloud)
    try:
        import streamlit as st
        key = st.secrets.get("PIPELINE_KEY", "")
        if key:
            return True
    except Exception:
        pass
    # Fallback: plain env var (for local runs outside Streamlit)
    return bool(os.environ.get("PIPELINE_KEY", "").strip())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _natural_sort_key(filename: str) -> list:
    """
    Natural sort key that handles mixed alphanumeric prefixes correctly.
    Example sort order: 00_, 01_, ..., 10_, 10b_, 10c_, 11_, ...
    """
    parts = re.split(r"(\d+)", filename)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def chart_key(filename: str) -> str:
    """'10b_india_sector_rotation.png' -> 'india_sector_rotation' (the name without its numeric prefix)."""
    return re.sub(r"^\d+[a-z]*_", "", Path(filename).stem)


def group_charts(charts: list[Path], sections: list[tuple[str, list[str]]]
                 ) -> tuple[list[tuple[str, list[Path]]], list[Path]]:
    """
    Charts placed into named sections by chart_key, in the order each section
    lists them. Returns (sections that have at least one chart, charts not listed
    anywhere). A listed chart missing from the folder is simply skipped.
    """
    by_key = {chart_key(c.name): c for c in charts}
    grouped, used = [], set()
    for title, keys in sections:
        found = [by_key[k] for k in keys if k in by_key]
        used.update(keys)
        if found:
            grouped.append((title, found))
    return grouped, [c for c in charts if chart_key(c.name) not in used]


# A filename is lower case and title-casing it gives "Btc Gold Ratio" and
# "India Gdp". These are the words that have to survive it — indicators,
# institutions and tickers keep their capitals, as they do in the chart's own
# title. Every caption and every search suggestion reads through this map, so a
# word added here is fixed in both places at once.
_ACRONYMS = {
    "btc": "BTC", "cag": "CAG", "cape": "CAPE", "cga": "CGA", "cli": "CLI",
    "cpi": "CPI", "eia": "EIA", "em": "EM", "erp": "ERP", "etf": "ETF",
    "eth": "ETH", "fpi": "FPI", "fx": "FX", "gdp": "GDP", "gsci": "GSCI",
    "gst": "GST", "iip": "IIP", "imf": "IMF", "inr": "INR", "it": "IT",
    "m2": "M2", "mospi": "MoSPI", "move": "MOVE", "mvrv": "MVRV",
    "nbfc": "NBFC", "nifty": "NIFTY", "nse": "NSE", "oecd": "OECD",
    "pmi": "PMI", "rbi": "RBI", "sahm": "Sahm", "spx": "S&P 500",
    "spy": "SPY", "tlt": "TLT", "us": "US", "usd": "USD", "vix": "VIX",
    "wti": "WTI", "yoy": "YoY",
    "vs": "vs", "and": "and", "per": "per",
    "12m": "12-Month", "3m": "3-Month",
}

# Names a filename cannot produce, or produces wrongly. Keyed by chart_key (the
# filename without its numeric prefix and extension), so renaming a chart's
# file is the only thing that can break one of these — and the fallback is then
# the derived name, not an error.
#
# These are shortened from the title drawn on the chart itself (WEEKLY_TITLES
# in generate_weekly.py, MACRO_TITLES in generate_macro.py): a caption sits
# under a chart that already carries its full title, so it only has to say
# which chart this is.
_TITLE_OVERRIDES = {
    # Cross-asset ratios: a slash reads as a ratio, an underscore does not
    "btc_mvrv_zscore":           "Bitcoin MVRV Z-Score",
    "btc_zscore_global_m2":      "Bitcoin vs Global M2 and the Z-Score",
    "btc_global_m2":             "Bitcoin vs Global M2",
    "eth_btc_ratio":             "ETH / BTC Ratio",
    "copper_gold_ratio":         "Copper / Gold Ratio",
    "gold_spx_ratio":            "Gold / S&P 500 Ratio",
    "spy_tlt_ratio":             "Stocks vs Bonds (SPY / TLT)",
    "brent_wti_spread":          "Brent – WTI Spread",
    "gold_real_rates":           "Gold vs Real Rates",
    "defensives_cyclicals":      "Defensive vs Cyclical Sectors",
    "stock_bond_correlation":    "Stock–Bond Correlation",
    "sector_rotation_12m":       "S&P 500 Sector Rotation (12 Months)",
    "india_sector_rotation_12m": "NIFTY Sector Rotation (12 Months)",
    "nifty_it_trend_custom":     "NIFTY IT Trend",
    "india_vix_vs_us":           "India VIX vs US VIX",
    "india_fiscal_deficit_gdp":  "India's Fiscal Deficit, % of GDP",
    "india_inflation_bar":       "India Inflation",
    # World page: "macro_" is a file prefix, and these say more than it does
    "macro_inflation":           "US Inflation Metrics",
    "macro_labour":              "US Labour Market",
    "macro_balance_sheet":       "Federal Reserve Balance Sheet",
    "macro_world_regime":        "Growth vs Inflation Momentum",
    "macro_oecd_cli":            "OECD Composite Leading Indicators",
    "macro_cape":                "Shiller CAPE and Excess CAPE Yield",
    "macro_equity_risk_premium": "US Equity Risk Premium",
    "macro_country_erp":         "Equity Risk Premiums Across the G20",
    "macro_regional_erp":        "Equity Risk Premiums by Region",
    "macro_ratings_vs_markets":  "Markets vs the Rating Agencies",
    "macro_em_borrowing":        "EM Dollar Borrowing Costs",
    "macro_em_dollar":           "The Dollar vs EM Currencies",
    "macro_sahm":                "Sahm Rule Recession Indicator",
}


def clean_title(filename: str) -> str:
    """
    Derive a human-readable chart title from a filename.

    '01_equities_weekly.png'  → 'Equities Weekly'
    '26_eth_btc_ratio.png'    → 'ETH / BTC Ratio'          (an override)
    '18_india_gdp.png'        → 'India GDP'                (the acronym map)

    Captions on the site are set in capitals by CSS, so this shows in full only
    in the search suggestions — but the casing is carried through both so the
    two never disagree.
    """
    stem = Path(filename).stem                    # strip .png
    stem = re.sub(r"^\d+[a-z]?_", "", stem)       # strip leading numeric prefix
    if stem in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[stem]
    # "macro_" is the World page's file prefix, not part of any chart's name —
    # but only stripped where something is left to name the chart by.
    if stem.startswith("macro_") and stem.count("_") > 1:
        stem = stem[len("macro_"):]
    return " ".join(_ACRONYMS.get(word, word.title()) for word in stem.split("_"))
