"""
Weekly Markets tab: which chart goes in which section, in page order.

Charts are named by their filename without the numeric prefix
('10b_india_sector_rotation.png' -> 'india_sector_rotation'), so renumbering
a file never moves it. Every chart the generator writes must appear here
exactly once; tests/test_weekly_sections.py fails otherwise, and the page
shows an unlisted chart under "Other" rather than hiding it.

Previously sections matched keywords in filenames, which filed Copper/Gold
and Gold/SPX under Commodities ("gold") and real yields under Fixed Income
("yield"), leaving the sections meant for them short.
"""

SUMMARY_CHART = "summary_table"

# Page order. Each section also gets a jump link in the tab header.
WEEKLY_SECTIONS: list[tuple[str, list[str]]] = [
    ("Equities", [
        "equities_weekly", "equities_trend",
        "sector_rotation", "sector_rotation_12m",
        "defensives_cyclicals", "market_breadth",
        "risk_appetite_ratio",
    ]),
    ("Commodities", [
        "commodities_weekly", "commodities_trend",
        "crude_oil_curve", "agri_weekly",
        "commodity_cycle", "commodities_breadth",
        "gold_real_rates",
    ]),
    ("Rates, Inflation & Credit", [
        "yield_curve", "move_index",
        "real_yields", "breakeven_inflation",
        "credit_spreads", "bond_etf_returns",
    ]),
    ("Currencies", [
        "fx_weekly", "fx_trend",
    ]),
    ("Emerging Markets & India", [
        "em_equity_weekly", "em_fx_weekly",
        "india_sector_rotation", "india_sector_rotation_12m",
        "india_vs_em_peers", "india_vix_vs_us",
        "em_stress_monitor", "em_vix",
    ]),
    ("Cross-Asset Signals", [
        "vix_trend", "stock_bond_correlation",
        "copper_gold_ratio", "gold_spx_ratio",
        "commodities_vs_equities",
    ]),
    ("Crypto", [
        "btc_mvrv_zscore", "btc_zscore_global_m2",
        "eth_btc_ratio", "btc_global_m2",
    ]),
]
