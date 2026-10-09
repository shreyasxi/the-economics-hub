"""Canonical data locations; importing this module never creates files.

The DBIE workbook and India manual CSV intentionally remain directly in data/.
CLI: python -m data.paths --relative INDIA_DB RBI_MONEY_MARKET_CSV
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_CACHE = DATA_DIR / "cache"
STORES_DIR = DATA_DIR / "stores"
INDIA_STORE_DIR = STORES_DIR / "india"
WORLD_STORE_DIR = STORES_DIR / "world"
SENTINEL_STORE_DIR = STORES_DIR / "rbi_sentinel"
INPUTS_DIR = DATA_DIR / "inputs"

# Owner-facing inputs: keep these two at the top level even after reorganization.
DBIE_WORKBOOK = DATA_DIR / "50 Macroeconomic Indicators.xlsx"
INDIA_MANUAL_CSV = DATA_DIR / "india_manual.csv"

INDIA_DB = INDIA_STORE_DIR / "india_macro.db"
CAG_WORKBOOK = INPUTS_DIR / "cag/cag_monthly_accounts.xlsx"
CAG_MANUAL_CSV = INPUTS_DIR / "cag/cag_manual_accounts.csv"
INDIA_TRADE_RELEASES = INDIA_STORE_DIR / "india_trade_releases.json"
INDIA_EQUITY_TRI = INDIA_STORE_DIR / "india_equity_tri.json"
GMD_INVESTMENT_CSV = INDIA_STORE_DIR / "gmd_investment.csv"
GMD_INVESTMENT_META = INDIA_STORE_DIR / "gmd_investment.json"

CPI_DIR = INDIA_STORE_DIR / "CPI"
CPI_CONTRIBUTIONS_DIR = CPI_DIR / "contributions"
CPI_ITEMS_DIR = CPI_DIR / "items"
CPI_MAIN_DIR = CPI_DIR / "main"
CPI_MAIN_STATUS = CPI_MAIN_DIR / "status.json"
GVA_DIR = INDIA_STORE_DIR / "gva"
IIP_DIR = INDIA_STORE_DIR / "IIP"
MOSPI_IIP_CSV = INDIA_STORE_DIR / "mospi_iip_industries.csv"
MOSPI_PLFS_CSV = INDIA_STORE_DIR / "mospi_plfs_monthly.csv"
MOSPI_SOURCES_DIR = INDIA_STORE_DIR / "mospi_activity_sources"

NSE_INDICES_DIR = INDIA_STORE_DIR / "nse_indices"
NSE_ROTATION_DIR = INDIA_STORE_DIR / "nse_rotation"
NSE_VALUATIONS_DIR = INDIA_STORE_DIR / "nse_valuations"
NIFTY_50_INPUT_DIR = INPUTS_DIR / "nse/NIFTY 50"
NIFTY_SMALLCAP_INPUT_DIR = INPUTS_DIR / "nse/NIFTY Small Cap 250"

RBI_SENTINEL_DB = SENTINEL_STORE_DIR / "rbi_sentinel.db"
RBI_SENTINEL_CACHE = DATA_CACHE / "rbi_sentinel"
RBI_SOE_CACHE = DATA_CACHE / "rbi_soe"
RBI_TRANSMISSION_CSV = INDIA_STORE_DIR / "rbi_transmission.csv"
RBI_MONEY_MARKET_CSV = INDIA_STORE_DIR / "rbi_money_market.csv"
RBI_WSS_CSV = INDIA_STORE_DIR / "rbi_wss_reserves.csv"
RBI_REER_CSV = INDIA_STORE_DIR / "rbi_reer.csv"
INDIA_EXTERNAL_CSV = INDIA_STORE_DIR / "india_external_vulnerability.csv"
RBI_LIVE_LOG_CSV = SENTINEL_STORE_DIR / "rbi_live_log.csv"
RBI_LIVE_MARKET_CSV = SENTINEL_STORE_DIR / "rbi_live_market.csv"
RBI_SURVEYS_DIR = INPUTS_DIR / "rbi/rbi_bimonthly_manual"
RBI_INFLATION_SURVEYS_DIR = RBI_SURVEYS_DIR / "inflation_survey"
RBI_CONSUMER_SURVEYS_DIR = RBI_SURVEYS_DIR / "consumer_survey"
CPI_INPUT_WORKBOOK = INPUTS_DIR / "mospi/cpi_1814.xlsx"
CPI_METADATA_WORKBOOK = INPUTS_DIR / "mospi/CPI Metadata.xlsx"

WORLD_MANUAL_CSV = WORLD_STORE_DIR / "world_manual.csv"
PBOC_LEDGER = WORLD_STORE_DIR / "pboc_reverse_repo.csv"
GDP_PPP_CSV = WORLD_STORE_DIR / "gdp_ppp.csv"
BDTI_IMAGE = WORLD_STORE_DIR / "bdti_raw_chart.png"


def archive_for_db(db, kind):
    """Use canonical archives for the main DB; keep custom DBs self-contained."""
    archives = {"gva": GVA_DIR, "IIP": IIP_DIR}
    archive = archives[kind]
    return archive if Path(db).resolve() == INDIA_DB.resolve() else Path(db).parent / archive.name


def mospi_sources_for(csv, series):
    """Preserve sibling evidence folders for explicitly supplied CSV paths."""
    canonical = {"iip": MOSPI_IIP_CSV, "plfs": MOSPI_PLFS_CSV}[series]
    parent = MOSPI_SOURCES_DIR if Path(csv).resolve() == canonical.resolve() else Path(csv).parent / MOSPI_SOURCES_DIR.name
    return parent / series


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Print canonical data paths, one per line")
    names = sorted(name for name, value in globals().items() if name.isupper() and isinstance(value, Path))
    parser.add_argument("names", nargs="+", choices=names)
    parser.add_argument("--relative", action="store_true", help="Paths relative to the repository")
    args = parser.parse_args()
    for name in args.names:
        value = globals()[name]
        print(value.relative_to(PROJECT_ROOT) if args.relative else value)


if __name__ == "__main__":
    main()
