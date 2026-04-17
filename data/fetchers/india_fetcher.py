"""
data/fetchers/india_fetcher.py

India Macro Data Fetcher — ETL pipeline with three sources.
Writes into data/india_macro.db via india_db_manager.

Sources:
  1. FRED (fredapi)    — CPI headline, food, core  (OECD series, ~6-week lag)
  2. jugaad-data       — RBI repo rate (diagnostic); weekly FPI flows from NSE
  3. RBI DBIE Excel    — "50 Macroeconomic Indicators.xlsx" (manual drop required)
                         Parsed from: Monthly, Fortnightly, Weekly sheets
                         Covers: IIP, Trade, Forex Reserves, Bank Credit, Deposits, M3

Usage:
  python data/fetchers/india_fetcher.py --append    # fetch latest, upsert to DB
  python data/fetchers/india_fetcher.py --seed      # one-time CSV → SQLite migration
  python data/fetchers/india_fetcher.py --dry-run   # print what would be fetched

DBIE EXCEL — MANUAL DROP REQUIRED:
  The RBI DBIE portal (https://data.rbi.org.in/DBIE/#/dbie/ind1) uses a stateful
  WAF that blocks automated downloads.  Download the file manually (clicking the
  link above), place it at:
      data/50 Macroeconomic Indicators.xlsx
  then run --append to parse and upsert.  If the file is missing, DBIE parsing
  is skipped gracefully — existing DB data is preserved.
"""

import argparse
import json
import logging
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Project path setup ────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from data.india_db_manager import (
    init_db,
    seed_from_csv,
    upsert_monthly,
    upsert_weekly,
    get_latest_monthly_date,
    get_latest_weekly_date,
)

log = logging.getLogger("india.fetcher")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Local DBIE Excel — update manually by downloading from:
# https://data.rbi.org.in/DBIE/#/dbie/ind1
DBIE_EXCEL_LOCAL = _ROOT / "data" / "50 Macroeconomic Indicators.xlsx"

# FRED series IDs for India CPI (OECD-sourced, ~6-week lag)
FRED_SERIES = {
    "india_cpi_yoy":      "CPALTT01INM657N",   # CPI All Items India
    "india_food_cpi_yoy": "CPALFD01INM661N",   # Food & Non-Alcoholic Beverages India
    "india_core_cpi_yoy": "CPGRLE01INM657N",   # Core CPI ex-food & energy India
}

# Path to the rbi_sentinel DB for repo rate fallback
SENTINEL_DB = _ROOT / "data" / "rbi_sentinel.db"

# Path to legacy CSV for --seed
DEFAULT_CSV = _ROOT / "data" / "india_manual.csv"

# Column layout of the DBIE Excel (0-indexed, header row = row index 3)
_MONTHLY_COLS = {
    "period":     1,
    "iip":        4,    # IIP index (base 2011-12=100)
    "exports":    17,   # Foreign Trade Exports Total (USD Million)
    "imports":    18,   # Foreign Trade Imports Total (USD Million)
    "trade_bal":  19,   # Foreign Trade Balance Total (USD Million, negative = deficit)
}

_FORTNIGHTLY_COLS = {
    "period":    1,
    "deposits":  4,    # Aggregate Deposits of SCBs (₹ Crore)
    "credit":    5,    # Bank Credit to Commercial Sector (₹ Crore)
    "m3":        11,   # Broad Money M3 (₹ Crore)
}

_WEEKLY_COLS = {
    "period":         1,
    "forex_reserves": 17,   # Foreign Exchange Reserves (USD Million)
}

# Approximate INR/USD rate used to convert FPI flows from ₹ Crore → USD bn.
# This is intentionally a rough conversion constant — FPI flow direction and
# magnitude matter more than precision here.  Update annually if needed.
_INR_USD_RATE = 84.0


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 1: FRED — CPI
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_fred_cpi(fred_api_key: str, dry_run: bool = False) -> dict[str, dict]:
    """
    Fetch all three India CPI series from FRED.
    Returns { "YYYY-MM": { "india_cpi_yoy": float, ... }, ... }
    Bounded to last 36 months to limit upsert scope.
    """
    try:
        from fredapi import Fred
    except ImportError:
        log.error("fredapi not installed. Run: pip install fredapi")
        return {}

    fred = Fred(api_key=fred_api_key)
    start = (date.today() - timedelta(days=36 * 31)).strftime("%Y-%m-%d")
    results: dict[str, dict] = {}

    for db_col, series_id in FRED_SERIES.items():
        try:
            raw = fred.get_series(series_id, observation_start=start)
            raw = raw.dropna()
            for dt, val in raw.items():
                month_key = dt.strftime("%Y-%m")
                results.setdefault(month_key, {})
                results[month_key][db_col] = round(float(val), 4)
                results[month_key].setdefault("_sources", {})[db_col] = f"fred_{series_id}"
            log.info("FRED %s (%s): %d observations", db_col, series_id, len(raw))
        except Exception as e:
            log.warning("FRED fetch failed for %s (%s): %s", db_col, series_id, e)

    if dry_run:
        log.info("[dry-run] FRED CPI: %d months would be upserted", len(results))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2a: jugaad-data — RBI Repo Rate (diagnostic only)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_repo_rate_current(dry_run: bool = False) -> Optional[float]:
    """
    Diagnostic fetch of the current RBI repo rate.
    Not written to india_monthly — rate history lives in rbi_sentinel.db.
    Fallback: most recent value from rbi_sentinel.db mpc_meetings table.
    """
    rate = _fetch_via_jugaad()
    if rate is not None:
        log.info("jugaad-data repo rate: %.2f%%", rate)
        return rate

    rate = _fetch_repo_rate_from_sentinel_db()
    if rate is not None:
        log.warning("jugaad-data failed — sentinel DB fallback: repo rate = %.2f%%", rate)
        return rate

    log.error("Both jugaad-data and sentinel DB fallback failed for repo rate.")
    return None


def _fetch_via_jugaad() -> Optional[float]:
    try:
        from jugaad_data.rbi import RBI  # type: ignore
        rates = RBI().current_rates()
        for key in ("Policy Repo Rate", "repo_rate", "Repo Rate"):
            if key in rates:
                # Scraped value includes the '%' sign (e.g. '5.25%').
                # Some range values look like '8.35% - 9.90%' — take only the first number.
                raw = str(rates[key]).split("-")[0].replace("%", "").strip()
                return float(raw)
        log.warning("jugaad-data returned unexpected keys: %s", list(rates.keys()))
        return None
    except Exception as e:
        log.warning("jugaad-data RBI fetch failed: %s", e)
        return None


def _fetch_repo_rate_from_sentinel_db() -> Optional[float]:
    if not SENTINEL_DB.exists():
        return None
    try:
        with sqlite3.connect(SENTINEL_DB) as conn:
            row = conn.execute(
                "SELECT repo_rate_pct FROM mpc_meetings "
                "WHERE repo_rate_pct IS NOT NULL "
                "ORDER BY meeting_date DESC LIMIT 1"
            ).fetchone()
        return float(row[0]) if row else None
    except Exception as e:
        log.error("Sentinel DB repo rate read failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2b: jugaad-data — Latest-Day FPI Flows from NSE
# ═══════════════════════════════════════════════════════════════════════════════

# NSE FII/DII daily snapshot endpoint — returns the current/last trading day only.
# No historical range parameter exists on this endpoint.
_NSE_FIIDII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"

def fetch_weekly_fpi_jugaad(dry_run: bool = False) -> dict[str, dict]:
    """
    Fetch the latest trading day's FII/FPI net cash-market flow from NSE.

    Uses jugaad-data's NSELive session (which already carries the correct NSE
    cookies and headers) to hit the /api/fiidiiTradeReact endpoint.

    The endpoint returns only the current/last trading day — there is no
    historical range.  Each weekly pipeline run upserts one entry:
        week_ending = the trading date embedded in the response
        fpi_net_flows_usd_bn = net FII/FPI cash flow (₹ Crore → USD bn)

    Conversion: ₹ Crore → USD bn = inr_crore × 10⁷ INR / (INR_USD × 10⁹)
                                  = inr_crore / (INR_USD × 100)

    Entirely wrapped in try/except — NSE changes must not crash the pipeline.
    Returns { "YYYY-MM-DD": { "fpi_net_flows_usd_bn": float } }
    """
    try:
        from jugaad_data.nse import NSELive  # type: ignore

        nse = NSELive()
        resp = nse.s.get(_NSE_FIIDII_URL, timeout=15)
        resp.raise_for_status()
        records = resp.json()

        # Find the FII/FPI record (category label varies: "FII/FPI" or "FII")
        fii_record = next(
            (r for r in records
             if isinstance(r, dict) and "fii" in str(r.get("category", "")).lower()),
            None,
        )
        if fii_record is None:
            log.warning("FII/FPI record not found in NSE response: %s", records)
            return {}

        # Parse net value — strip commas, cast to float
        net_inr_crore = float(str(fii_record["netValue"]).replace(",", "").strip())

        # Parse trading date from the record ("16-Apr-2026" format)
        trading_date = pd.to_datetime(fii_record["date"], format="%d-%b-%Y")
        date_str = trading_date.strftime("%Y-%m-%d")

        # Convert ₹ Crore → USD bn
        fpi_usd_bn = round(net_inr_crore / (_INR_USD_RATE * 100), 4)

        log.info(
            "NSE FPI snapshot: %s | net ₹%.0f Cr (%.4f USD bn)",
            date_str, net_inr_crore, fpi_usd_bn,
        )
        if dry_run:
            log.info("[dry-run] Would upsert FPI for %s: %.4f USD bn", date_str, fpi_usd_bn)
            return {}

        return {date_str: {"fpi_net_flows_usd_bn": fpi_usd_bn}}

    except Exception as e:
        log.warning("NSE FPI fetch failed (site may have changed): %s", e)
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 3: RBI DBIE — Local Excel File (manual drop)
# ═══════════════════════════════════════════════════════════════════════════════

def _yoy_pct(series: pd.Series) -> pd.Series:
    """YoY % change from a level series sorted oldest-first. Returns rounded floats."""
    shifted = series.shift(12)
    return ((series - shifted) / shifted.abs() * 100).round(4)


def _parse_period_monthly(raw: str) -> Optional[str]:
    """Convert 'Mar-2026' or 'Mar-26' → 'YYYY-MM'. Returns None on failure."""
    for fmt in ("%b-%Y", "%b-%y"):
        try:
            return pd.to_datetime(raw, format=fmt).strftime("%Y-%m")
        except Exception:
            continue
    return None


def fetch_dbie_monthly(source: Path) -> dict[str, dict]:
    """
    Parse Monthly sheet: IIP YoY, Exports, Imports, Trade Deficit.
    FPI is NOT extracted here — it comes from jugaad-data (weekly).
    """
    try:
        df = pd.read_excel(source, sheet_name="Monthly", header=None)
    except Exception as e:
        log.warning("Failed to read Monthly sheet: %s", e)
        return {}

    data = df.iloc[4:].copy()
    data = data[data.iloc[:, _MONTHLY_COLS["period"]].notna()].reset_index(drop=True)
    data["_month"] = data.iloc[:, _MONTHLY_COLS["period"]].astype(str).apply(_parse_period_monthly)
    data = data[data["_month"].notna()].sort_values("_month").reset_index(drop=True)

    def _col(key):
        return pd.to_numeric(data.iloc[:, _MONTHLY_COLS[key]], errors="coerce")

    iip_yoy  = _yoy_pct(_col("iip"))
    exports  = (_col("exports")   / 1000).round(4)
    imports  = (_col("imports")   / 1000).round(4)
    deficit  = (-_col("trade_bal") / 1000).round(4)

    results: dict[str, dict] = {}
    for i, month in enumerate(data["_month"]):
        row: dict = {}
        if pd.notna(iip_yoy.iloc[i]):
            row["india_iip_yoy"] = float(iip_yoy.iloc[i])
        if pd.notna(exports.iloc[i]):
            row["india_exports_usd_bn"] = float(exports.iloc[i])
        if pd.notna(imports.iloc[i]):
            row["india_imports_usd_bn"] = float(imports.iloc[i])
        if pd.notna(deficit.iloc[i]):
            row["india_trade_deficit_usd_bn"] = float(deficit.iloc[i])
        if row:
            row["_sources"] = {k: "dbie_excel_monthly" for k in row}
            results[month] = row

    log.info("DBIE Monthly sheet: %d months parsed", len(results))
    return results


def fetch_dbie_fortnightly(source: Path) -> dict[str, dict]:
    """
    Parse Fortnightly sheet: Bank Credit YoY, Deposit Growth YoY, M3 YoY.
    Takes last fortnightly reading per calendar month, then calculates 12-month YoY.
    """
    try:
        df = pd.read_excel(source, sheet_name="Fortnightly", header=None)
    except Exception as e:
        log.warning("Failed to read Fortnightly sheet: %s", e)
        return {}

    data = df.iloc[4:].copy()
    data = data[data.iloc[:, _FORTNIGHTLY_COLS["period"]].notna()].reset_index(drop=True)
    data["_dt"] = pd.to_datetime(data.iloc[:, _FORTNIGHTLY_COLS["period"]], errors="coerce")
    data = data[data["_dt"].notna()].copy()
    data["_month"] = data["_dt"].dt.strftime("%Y-%m")
    data["_credit"]   = pd.to_numeric(data.iloc[:, _FORTNIGHTLY_COLS["credit"]],   errors="coerce")
    data["_deposits"] = pd.to_numeric(data.iloc[:, _FORTNIGHTLY_COLS["deposits"]], errors="coerce")
    data["_m3"]       = pd.to_numeric(data.iloc[:, _FORTNIGHTLY_COLS["m3"]],       errors="coerce")

    monthly = data.sort_values("_dt").groupby("_month").last().reset_index()
    monthly = monthly.sort_values("_month").reset_index(drop=True)

    credit_yoy   = _yoy_pct(monthly["_credit"])
    deposits_yoy = _yoy_pct(monthly["_deposits"])
    m3_yoy       = _yoy_pct(monthly["_m3"])

    results: dict[str, dict] = {}
    for i, month in enumerate(monthly["_month"]):
        row: dict = {}
        if pd.notna(credit_yoy.iloc[i]):
            row["india_bank_credit_yoy"] = float(credit_yoy.iloc[i])
        if pd.notna(deposits_yoy.iloc[i]):
            row["india_deposit_growth_yoy"] = float(deposits_yoy.iloc[i])
        if pd.notna(m3_yoy.iloc[i]):
            row["india_m3_yoy"] = float(m3_yoy.iloc[i])
        if row:
            row["_sources"] = {k: "dbie_excel_fortnightly" for k in row}
            results[month] = row

    log.info("DBIE Fortnightly sheet: %d months parsed", len(results))
    return results


def fetch_dbie_weekly(source: Path) -> dict[str, dict]:
    """
    Parse Weekly sheet: Forex Reserves (USD bn) + WoW change.
    Returns { "YYYY-MM-DD": { "forex_reserves_usd_bn": float, "forex_reserves_wow_chg": float } }
    """
    try:
        df = pd.read_excel(source, sheet_name="Weekly", header=None)
    except Exception as e:
        log.warning("Failed to read Weekly sheet: %s", e)
        return {}

    data = df.iloc[4:].copy()
    data = data[data.iloc[:, _WEEKLY_COLS["period"]].notna()].reset_index(drop=True)
    data["_dt"] = pd.to_datetime(data.iloc[:, _WEEKLY_COLS["period"]], errors="coerce")
    data = data[data["_dt"].notna()].copy()
    data["_date_str"] = data["_dt"].dt.strftime("%Y-%m-%d")
    data["_reserves"] = (
        pd.to_numeric(data.iloc[:, _WEEKLY_COLS["forex_reserves"]], errors="coerce") / 1000
    ).round(4)
    data = data.sort_values("_dt").reset_index(drop=True)
    data["_wow"] = data["_reserves"].diff().round(4)

    results: dict[str, dict] = {}
    for _, row in data.iterrows():
        if pd.isna(row["_reserves"]):
            continue
        results[row["_date_str"]] = {
            "forex_reserves_usd_bn": float(row["_reserves"]),
            "forex_reserves_wow_chg": float(row["_wow"]) if pd.notna(row["_wow"]) else None,
        }

    log.info("DBIE Weekly sheet: %d weeks parsed", len(results))
    return results


def fetch_dbie_all(dry_run: bool = False) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Load the local DBIE Excel and parse all three sheets.
    If the file is missing, logs an error and returns empty dicts.

    Returns:
        monthly_data  — { "YYYY-MM":    { column: value, ... } }
        forex_weekly  — { "YYYY-MM-DD": { column: value, ... } }
    """
    if not DBIE_EXCEL_LOCAL.exists():
        log.error(
            "DBIE Excel not found at %s. Download manually from "
            "https://data.rbi.org.in/DBIE/#/dbie/ind1 and place it there.",
            DBIE_EXCEL_LOCAL,
        )
        return {}, {}

    monthly_data: dict[str, dict] = {}

    for month, vals in fetch_dbie_monthly(DBIE_EXCEL_LOCAL).items():
        monthly_data.setdefault(month, {}).update(vals)

    for month, vals in fetch_dbie_fortnightly(DBIE_EXCEL_LOCAL).items():
        monthly_data.setdefault(month, {}).update(vals)

    forex_weekly = fetch_dbie_weekly(DBIE_EXCEL_LOCAL)

    if dry_run:
        log.info("[dry-run] DBIE: %d months, %d forex weeks would be upserted",
                 len(monthly_data), len(forex_weekly))

    return monthly_data, forex_weekly


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

def run_append(fred_api_key: Optional[str], dry_run: bool = False) -> None:
    """
    Fetch latest data from all sources and upsert into india_macro.db.

      Source 1 (FRED)      — monthly CPI YoY series
      Source 2a (jugaad)   — repo rate diagnostic (not written to DB)
      Source 2b (jugaad)   — weekly FPI net flows → india_weekly.fpi_net_flows_usd_bn
      Source 3 (DBIE Excel)— monthly IIP/Trade/Credit/M3 + weekly forex reserves
    """
    init_db()

    monthly_data: dict[str, dict] = {}


    # Source 2a: jugaad-data repo rate (diagnostic only)
    fetch_repo_rate_current(dry_run=dry_run)

    # Source 3: DBIE Excel
    dbie_monthly, forex_weekly = fetch_dbie_all(dry_run=dry_run)
    for month, vals in dbie_monthly.items():
        monthly_data.setdefault(month, {}).update(vals)

    # ── Write monthly data ────────────────────────────────────────────────────
    if not dry_run:
        for month, row in monthly_data.items():
            source_flags = row.get("_sources", {})
            clean_row = {k: v for k, v in row.items() if not k.startswith("_")}
            clean_row["source_flags"] = json.dumps(source_flags)
            upsert_monthly(month, clean_row)
        log.info("Upserted %d months into india_monthly", len(monthly_data))
    else:
        log.info("[dry-run] Would upsert %d months into india_monthly", len(monthly_data))

    # ── Weekly table: forex reserves (from DBIE) ──────────────────────────────
    if not dry_run and forex_weekly:
        for week_ending, row in forex_weekly.items():
            upsert_weekly(week_ending, row)
        log.info("Upserted %d weeks (forex) into india_weekly", len(forex_weekly))

    # Source 2b: jugaad-data FPI flows → india_weekly
    fpi_weekly = fetch_weekly_fpi_jugaad(dry_run=dry_run)
    if not dry_run and fpi_weekly:
        for week_ending, row in fpi_weekly.items():
            upsert_weekly(week_ending, row)
        log.info("Upserted %d weeks (FPI) into india_weekly", len(fpi_weekly))

    # ── Summary ───────────────────────────────────────────────────────────────
    if not dry_run:
        log.info("DB state: latest monthly=%s, latest weekly=%s",
                 get_latest_monthly_date(), get_latest_weekly_date())
    else:
        log.info("[dry-run] Complete — no DB changes made")


def run_seed(csv_path: Path = DEFAULT_CSV) -> None:
    """One-time migration: india_manual.csv → india_monthly table."""
    init_db()
    count = seed_from_csv(csv_path)
    log.info("Seeded %d months from %s", count, csv_path.name)
    log.info("Latest month in DB: %s", get_latest_monthly_date())


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="India Macro Data Fetcher — populates data/india_macro.db"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--append",  action="store_true",
                      help="Fetch latest data from all sources and upsert into DB")
    mode.add_argument("--seed",    action="store_true",
                      help="One-time migration: india_manual.csv → india_macro.db")
    mode.add_argument("--dry-run", action="store_true",
                      help="Fetch data but make no DB changes (logging only)")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                        help="Path to india_manual.csv for --seed")
    args = parser.parse_args()

    import os
    fred_api_key = os.environ.get("FRED_API_KEY")

    if args.seed:
        run_seed(args.csv)
    elif args.append:
        run_append(fred_api_key, dry_run=False)
    elif args.dry_run:
        run_append(fred_api_key, dry_run=True)


if __name__ == "__main__":
    main()
