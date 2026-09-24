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
(with the United States summary table and the Sahm rule chart) the Sahm
rule, and the 5y5y forward inflation expectation rate (Weekly charts the 5-
and 10-year breakevens). Eurozone and UK CPI/unemployment moved to the
scoreboard (the FRED copies had stopped updating). The Emerging Markets section uses EM bond
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
    # The CPI indexes (all items and the categories in CPI_CATEGORIES below)
    # are added after this dict.
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

# ─────────────────────────────────────────────
# US CPI BY CATEGORY
# ─────────────────────────────────────────────
# The inflation chart splits headline CPI inflation into what each category
# contributed. The indexes are NOT seasonally adjusted: those are the ones BLS
# aggregates (seasonally adjusted indexes do not add up), and their 12-month
# change is the headline rate BLS publishes. Food, energy, core goods and core
# services cover all items exactly once; shelter is part of core services, and
# the chart shows it and the rest of core services as separate bars.
#   key: (FRED series, name); each becomes indicator "us_cpi_<key>"
CPI_INDEXES = {
    "all_items":     ("CPIAUCNS", "US CPI, all items (NSA)"),
    "food":          ("CPIUFDNS", "US CPI, food (NSA)"),
    "energy":        ("CPIENGNS", "US CPI, energy (NSA)"),
    "core_goods":    ("CUUR0000SACL1E", "US CPI, commodities less food and energy commodities (NSA)"),
    "core_services": ("CUUR0000SASLE", "US CPI, services less energy services (NSA)"),
    "shelter":       ("CUUR0000SAH1", "US CPI, shelter (NSA)"),
}

# BLS relative importance in December (CPI-U, U.S. city average, percent of
# all items), keyed by year: each December's figures are the weights for the
# twelve months after it. A 12-month change starts up to two Decembers back,
# so the chart's three years need five Decembers.
#
# UPDATE EVERY FEBRUARY: BLS publishes the December figures with January's
# CPI, at https://www.bls.gov/cpi/tables/relative-importance/<year>.htm (the
# rows Food, Energy, Commodities less food and energy commodities, Services
# less energy services, Shelter). Until the new year is added, the run fails
# and names what is missing. A mistyped figure fails it too: the chart checks
# that the categories add up to the headline rate.
CPI_RELATIVE_IMPORTANCE = {
    2021: {"food": 13.370, "energy": 7.348, "core_goods": 21.699, "core_services": 57.583, "shelter": 32.946},
    2022: {"food": 13.531, "energy": 6.921, "core_goods": 21.361, "core_services": 58.187, "shelter": 34.413},
    2023: {"food": 13.555, "energy": 6.655, "core_goods": 18.891, "core_services": 60.899, "shelter": 36.191},
    2024: {"food": 13.691, "energy": 6.216, "core_goods": 19.388, "core_services": 60.705, "shelter": 35.483},
    2025: {"food": 13.698, "energy": 6.383, "core_goods": 19.176, "core_services": 60.744, "shelter": 35.625},
}

MACRO_INDICATORS.update({
    f"us_cpi_{key}": {
        "series": series, "name": name, "frequency": "monthly", "transform": "level",
        "unit": "index", "group": "inflation", "history_years": 5, "max_age": 75,
    }
    for key, (series, name) in CPI_INDEXES.items()
})
