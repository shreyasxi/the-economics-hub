"""
Economics Hub — Macro Pulse Configuration
==========================================
Indicator definitions for the monthly macro dashboard.
All data from FRED unless noted. Run generate_macro.py
on the 2nd Saturday of each month (after NFP + CPI release).

Manual overrides (India unemployment etc.) go in MANUAL_DATA below.
"""

from datetime import datetime

# ─────────────────────────────────────────────
# MANUAL DATA OVERRIDES
# ─────────────────────────────────────────────
# Update these each month with latest figures.
# Format: value (float), date string, source note.
#
# HOW TO UPDATE:
#   1. Go to https://unemploymentinindia.cmie.com/ (CMIE)
#      or check RBI monthly bulletin
#   2. Update the "value" field below
#   3. Update the "as_of" date
#   4. Run generate_macro.py

MANUAL_DATA = {
    # ═══════════════════════════════════════════
    # EMERGING MARKETS (Manual - no FRED source)
    # ═══════════════════════════════════════════
    "em_lc_bonds": {                # <--- CHANGED from em_pmi_composite
        "value": 26.47,             # <--- Price of EMLC ETF
        "previous_value": 25.91,    
        "as_of": "2026-02-11",
        "source": "",               
        "name": "EM Local Currency Bonds",
        "unit": "USD",
    },
    # Add more manual entries here as needed
}


# ─────────────────────────────────────────────
# MACRO INDICATORS (FRED)
# ─────────────────────────────────────────────
# Each indicator:
#   - series: FRED series ID
#   - name: Display name
#   - frequency: "daily", "weekly", "monthly"
#   - transform: how to compute the display value
#       "level"   → latest raw value
#       "yoy_pct" → year-over-year % change (for CPI, M2 etc.)
#       "mom_pct" → month-over-month % change
#   - unit: display unit
#   - group: which chart/table section

MACRO_INDICATORS = {

    # ═══════════════════════════════════════════
    # INFLATION
    # ═══════════════════════════════════════════
    "us_cpi_yoy": {
        "series": "CPIAUCSL",
        "name": "US CPI (All Items)",
        "frequency": "monthly",
        "transform": "yoy_pct",
        "unit": "% YoY",
        "group": "inflation",
        "color": "#003366",      # Navy (US)
        "history_years": 3,
    },
    "us_core_pce": {
        "series": "PCEPILFE",
        "name": "US Core PCE",
        "frequency": "monthly",
        "transform": "yoy_pct",
        "unit": "% YoY",
        "group": "inflation",
        "color": "#1f77b4",      # Blue
        "history_years": 3,
    },
    "us_inflation_exp": {
        "series": "T5YIFR",
        "name": "5Y5Y Inflation Expectations",
        "frequency": "daily",
        "transform": "level",
        "unit": "%",
        "group": "inflation",
        "color": "#ff7f0e",      # Orange
        "history_years": 3,
    },
    "ez_cpi_yoy": {
        "series": "CP0000EZ19M086NEST",
        "name": "Eurozone CPI",
        "frequency": "monthly",
        "transform": "yoy_pct",
        "unit": "% YoY",
        "group": "inflation_intl",
        "color": "#008080",      # Teal (Europe)
        "history_years": 3,
    },
    "uk_cpi_yoy": {
        "series": "GBRCPIALLMINMEI",
        "name": "UK CPI",
        "frequency": "monthly",
        "transform": "yoy_pct",
        "unit": "% YoY",
        "group": "inflation_intl",
        "color": "#2ca02c",      # Green
        "history_years": 3,
    },

    # ═══════════════════════════════════════════
    # LABOUR MARKET
    # ═══════════════════════════════════════════
    "us_unemployment": {
        "series": "UNRATE",
        "name": "US Unemployment Rate",
        "frequency": "monthly",
        "transform": "level",
        "unit": "%",
        "group": "labour",
        "color": "#003366",
        "history_years": 3,
    },
    "us_claims": {
        "series": "ICSA",
        "name": "Initial Jobless Claims",
        "frequency": "weekly",
        "transform": "level",
        "unit": "K",             # Will divide by 1000 for display
        "group": "labour",
        "color": "#d62728",      # Red
        "history_years": 3,
    },
    "us_payrolls": {
        "series": "PAYEMS",
        "name": "Non-Farm Payrolls",
        "frequency": "monthly",
        "transform": "mom_abs",  # Month-over-month absolute change (in thousands)
        "unit": "K jobs",
        "group": "labour",
        "color": "#1f77b4",
        "history_years": 3,
    },
    "ez_unemployment": {
        "series": "LRHUTTTTEZM156S",
        "name": "Eurozone Unemployment",
        "frequency": "monthly",
        "transform": "level",
        "unit": "%",
        "group": "labour_intl",
        "color": "#008080",
        "history_years": 3,
    },
    "uk_unemployment": {
        "series": "LRHUTTTTGBM156S",
        "name": "UK Unemployment",
        "frequency": "monthly",
        "transform": "level",
        "unit": "%",
        "group": "labour_intl",
        "color": "#2ca02c",
        "history_years": 3,
    },

    # ═══════════════════════════════════════════
    # FINANCIAL CONDITIONS & CREDIT
    # ═══════════════════════════════════════════
    "nfci": {
        "series": "NFCI",
        "name": "Chicago Fed NFCI",
        "frequency": "weekly",
        "transform": "level",
        "unit": "index",
        "group": "financial_conditions",
        "color": "#000000",      # Black
        "history_years": 3,
    },
    "hy_spread": {
        "series": "BAMLH0A0HYM2",
        "name": "US HY Credit Spread",
        "frequency": "daily",
        "transform": "level",
        "unit": "bps",
        "group": "financial_conditions",
        "color": "#d62728",      # Red
        "history_years": 3,
    },

    # ═══════════════════════════════════════════
    # EMERGING MARKETS (NEW SECTION)
    # ═══════════════════════════════════════════
    "em_hy_spread": {
        "series": "BAMLEMHBHYCRPIOAS",
        "name": "EM HY Credit Spread",
        "frequency": "daily",
        "transform": "level",
        "unit": "bps",
        "group": "emerging_markets",
        "color": "#FF9933",      # Saffron/EM color
        "history_years": 3,
    },
    "em_corp_spread": {
        "series": "BAMLEMCBPIOAS",
        "name": "EM Corporate Spread",
        "frequency": "daily",
        "transform": "level",
        "unit": "bps",
        "group": "emerging_markets",
        "color": "#CC0066",      # Magenta
        "history_years": 3,
    },
    "em_usd_index": {
        "series": "DTWEXEMEGS",
        "name": "USD Index (vs EM)",
        "frequency": "daily",
        "transform": "level",
        "unit": "index",
        "group": "emerging_markets",
        "color": "#003366",
        "history_years": 3,
    },

    # ═══════════════════════════════════════════
    # MONEY & RATES
    # ═══════════════════════════════════════════
    "m2_yoy": {
        "series": "M2SL",
        "name": "M2 Money Supply",
        "frequency": "monthly",
        "transform": "yoy_pct",
        "unit": "% YoY",
        "group": "money",
        "color": "#003366",
        "history_years": 3,
    },
    "spread_2s10s": {
        "series": "T10Y2Y",
        "name": "2s10s Spread",
        "frequency": "daily",
        "transform": "level",
        "unit": "pp",
        "group": "money",
        "color": "#d62728",
        "history_years": 3,
    },
    "real_yield_10y": {
        "series": "DFII10",
        "name": "10Y Real Yield (TIPS)",
        "frequency": "daily",
        "transform": "level",
        "unit": "%",
        "group": "money",
        "color": "#ff7f0e",
        "history_years": 3,
    },
}


# ─────────────────────────────────────────────
# CHART DEFINITIONS
# ─────────────────────────────────────────────
# Which indicators go into which chart

MACRO_CHARTS = {
    "inflation": {
        "title": "Inflation Dashboard",
        "panels": [
            {
                "subtitle": "United States",
                "indicators": ["us_cpi_yoy", "us_core_pce", "us_inflation_exp"],
                "ylabel": "Rate (%)",
            },
            {
                "subtitle": "Eurozone · UK",
                "indicators": ["ez_cpi_yoy", "uk_cpi_yoy"],
                "ylabel": "CPI YoY (%)",
            },
        ],
    },
    "labour": {
        "title": "Labour Market Pulse",
        "primary": {
            "indicators": ["us_unemployment"],
            "ylabel": "Unemployment Rate (%)",
        },
        "secondary": {
            "indicators": ["us_claims"],
            "ylabel": "Initial Claims (4wk MA, K)",
        },
    },
    "financial_conditions": {
        "title": "Financial Conditions & Credit Stress",
        "primary": {
            "indicators": ["nfci"],
            "ylabel": "NFCI (0 = avg conditions)",
        },
        "secondary": {
            "indicators": ["hy_spread"],
            "ylabel": "HY OAS (bps)",
        },
    },
    "emerging_markets": {
        "title": "Emerging Markets Stress Monitor",
        "primary": {
            "indicators": ["em_hy_spread", "em_corp_spread"],
            "ylabel": "Credit Spread (bps)",
        },
        "secondary": {
            "indicators": ["em_usd_index"],
            "ylabel": "USD Index",
        },
    },
    "money": {
        "title": "Money, Rates & the Yield Curve Signal",
        "indicators": ["m2_yoy", "spread_2s10s", "real_yield_10y"],
        "ylabel": "Rate / Spread (%)",
    },
}


# ─────────────────────────────────────────────
# MACRO TABLE SECTIONS
# ─────────────────────────────────────────────
MACRO_TABLE_SECTIONS = [
    {
        "section": "INFLATION",
        "color": "#B91C1C",
        "rows": ["us_cpi_yoy", "us_core_pce", "us_inflation_exp",
                 "ez_cpi_yoy", "uk_cpi_yoy"],
    },
    {
        "section": "LABOUR MARKET",
        "color": "#0F172A",
        "rows": ["us_unemployment", "us_payrolls", "us_claims",
                 "ez_unemployment", "uk_unemployment"],
    },
    {
        "section": "FINANCIAL CONDITIONS",
        "color": "#059669",
        "rows": ["nfci", "hy_spread"],
    },
    {
        "section": "EMERGING MARKETS",
        "color": "#FF9933",
        "rows": ["em_hy_spread", "em_corp_spread", "em_usd_index"],
        "manual_rows": ["em_lc_bonds"],
    },
    {
        "section": "MONEY & RATES",
        "color": "#7C3AED",
        "rows": ["m2_yoy", "spread_2s10s", "real_yield_10y"],
    },
]
