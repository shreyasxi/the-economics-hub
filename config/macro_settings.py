"""
Economics Hub — World tab: FRED series configuration
====================================================
The FRED series behind the World tab's United States section (inflation,
labour, Fed balance sheet) and its Emerging Markets section (EM corporate
dollar bond yields, the dollar against EM currencies and the rupee).

The six-economy scoreboard, central bank strip and calendar are configured
in config/world_settings.py; the equity valuation spreadsheets in
data/valuations.py.

Series retired in Sep 2026 because Weekly Markets already charts them, or
they carried little signal: HY/EM credit spreads, EMLC, NFCI, M2, 2s10s,
10y–3m, 10Y real yield, mortgage rate, housing starts, Michigan sentiment,
and (with the United States summary table and the Sahm rule chart) the Sahm
rule. Eurozone and UK CPI/unemployment moved to the scoreboard (the FRED
copies had stopped updating). The Emerging Markets section uses EM bond
YIELDS and the EM dollar index against the rupee, so it does not repeat
Weekly's EM stress monitor (spreads against the EM dollar index).
"""

# ─────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────
#   transform   level | yoy_pct | mom_abs  (YoY and MoM are matched by date)
#   max_age     days since the latest observation date before the series
#               counts as stopped; the run then fails instead of publishing it.
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
        "history_years": 3,
        "max_age": 75,
    },
    "us_core_pce": {
        "series": "PCEPILFE",
        "name": "US Core PCE",
        "frequency": "monthly",
        "transform": "yoy_pct",
        "unit": "% YoY",
        "group": "inflation",
        "history_years": 3,
        "max_age": 100,
    },
    "us_inflation_exp": {
        "series": "T5YIFR",
        "name": "5Y5Y Inflation Expectations",
        "frequency": "daily",
        "transform": "level",
        "unit": "%",
        "group": "inflation",
        "history_years": 3,
        "max_age": 10,
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
        "history_years": 3,
        "max_age": 75,
    },
    "us_claims": {
        "series": "ICSA",
        "name": "Initial Jobless Claims",
        "frequency": "weekly",
        "transform": "level",
        "unit": "K",             # divided by 1000 for display
        "group": "labour",
        "history_years": 3,
        "max_age": 21,
    },
    "us_payrolls": {
        "series": "PAYEMS",
        "name": "Non-Farm Payrolls",
        "frequency": "monthly",
        "transform": "mom_abs",  # month-over-month change in jobs (thousands); the labour chart's badge
        "unit": "K jobs",
        "group": "labour",
        "history_years": 3,
        "max_age": 75,
    },

    # ═══════════════════════════════════════════
    # FED BALANCE SHEET
    # ═══════════════════════════════════════════
    "fed_balance_sheet": {
        "series": "WALCL",
        "name": "Fed Balance Sheet (Total Assets)",
        "frequency": "weekly",
        "transform": "level",
        "unit": "$B",
        "group": "balance_sheet",
        "history_years": 6,
        "max_age": 21,
    },

    # ═══════════════════════════════════════════
    # EMERGING MARKETS
    # ═══════════════════════════════════════════
    # ICE BofA indices: FRED carries only the last three years. The H.10 series
    # (EM dollar index, USD/INR) are published weekly, on Mondays.
    "em_hy_yield": {
        "series": "BAMLEMHBHYCRPIEY",
        "name": "EM High Yield Corporate Bond Yield",
        "frequency": "daily",
        "transform": "level",
        "unit": "%",
        "group": "emerging_markets",
        "history_years": 3,
        "max_age": 10,
    },
    "em_ig_yield": {
        "series": "BAMLEMIBHGCRPIEY",
        "name": "EM Investment Grade Corporate Bond Yield",
        "frequency": "daily",
        "transform": "level",
        "unit": "%",
        "group": "emerging_markets",
        "history_years": 3,
        "max_age": 10,
    },
    "us_10y": {
        "series": "DGS10",
        "name": "US 10-Year Treasury Yield",
        "frequency": "daily",
        "transform": "level",
        "unit": "%",
        "group": "emerging_markets",
        "history_years": 3,
        "max_age": 10,
    },
    "em_usd_index": {
        "series": "DTWEXEMEGS",
        "name": "Dollar Index vs EM Currencies",
        "frequency": "daily",
        "transform": "level",
        "unit": "index",
        "group": "emerging_markets",
        "history_years": 3,
        "max_age": 16,
    },
    "usd_inr": {
        "series": "DEXINUS",
        "name": "Rupees per US Dollar",
        "frequency": "daily",
        "transform": "level",
        "unit": "INR",
        "group": "emerging_markets",
        "history_years": 3,
        "max_age": 16,
    },
}

# The other emerging-market currencies in the Fed's EME dollar index that FRED
# quotes daily. The dollar chart shows the index, the rupee and whichever of
# these has moved furthest each way, so the comparison set has to be wide;
# every one is quoted as local currency per dollar, so a rise is a weaker
# currency. Added to MACRO_INDICATORS below so each gets the same freshness
# check as everything else: a series FRED retires fails the run.
EM_FX_PEERS = {
    "usd_brl": ("DEXBZUS", "Brazilian real"),
    "usd_mxn": ("DEXMXUS", "Mexican peso"),
    "usd_zar": ("DEXSFUS", "South African rand"),
    "usd_krw": ("DEXKOUS", "South Korean won"),
    "usd_cny": ("DEXCHUS", "Chinese yuan"),
    "usd_thb": ("DEXTHUS", "Thai baht"),
    "usd_myr": ("DEXMAUS", "Malaysian ringgit"),
    "usd_twd": ("DEXTAUS", "Taiwan dollar"),
    "usd_sgd": ("DEXSIUS", "Singapore dollar"),
}

MACRO_INDICATORS.update({
    key: {
        "series": series, "name": name, "frequency": "daily", "transform": "level",
        "unit": "FX", "group": "emerging_markets", "history_years": 3, "max_age": 16,
    }
    for key, (series, name) in EM_FX_PEERS.items()
})
