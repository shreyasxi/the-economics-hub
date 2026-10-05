"""
Economics Hub — India Macro Dashboard
========================================
Generates India-specific charts from data/india_macro.db (SQLite),
with CSV fallback for legacy compatibility.
Also generates fiscal charts from CAG Monthly Accounts Dashboard.

Data sources:
  AUTO (india_macro.db — populated by data/fetchers/india_fetcher.py):
  - CPI Headline / Core / Food: FRED (OECD series, ~6-week lag)
  - Bank Credit / Deposit Growth: RBI DBIE
  - M3 Money Supply:             RBI DBIE
  - IIP:                         MoSPI General, 2022–23-base published YoY growth
  - FPI Flows:                   RBI DBIE
  - Exports / Imports:           RBI DBIE
  - Forex Reserves (weekly):     RBI DBIE

  MANUAL (enter into DB via india_fetcher --seed or SQLite direct write):
  - Manufacturing PMI:   S&P Global (1st biz day of month)
  - Services PMI:        S&P Global (3rd biz day of month)
  - GST Revenue:         PIB / Finance Ministry (1st of month, ₹ Lakh Cr)
  - See docs/project_reminders.md for exact URLs and entry workflow

  CAG EXCEL (data/cag_monthly_accounts.xlsx):
  - Fiscal Deficit, Capital Expenditure, Net Tax Revenue, etc.
  - Source: CAG DAMA Dashboard (released with ~1 month lag)

Usage:
  python generate_india.py                    # Generate all charts
  python generate_india.py --cag path.xlsx    # Use custom CAG file
  python generate_india.py --months 18        # Last 18 months only
  python generate_india.py --mode dashboard   # Explicit mode flag
"""

import argparse
import re
import sys
import io
from pathlib import Path
from datetime import datetime

# Force UTF-8 output on Windows (avoids cp1252 errors with ₹, →, ⚠ etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe

# ── Project imports ──
sys.path.insert(0, str(Path(__file__).parent))
from charts.style import EconStyle


# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════

DEFAULT_CSV   = Path(__file__).parent / "data" / "india_manual.csv"
DEFAULT_CAG   = Path(__file__).parent / "data" / "cag_monthly_accounts.xlsx"
DEFAULT_DB    = Path(__file__).parent / "data" / "india_macro.db"
TRANSMISSION_CSV = Path(__file__).parent / "data" / "rbi_transmission.csv"
OUTPUT_BASE   = Path(__file__).parent / "output" / "india"

# Colors
C_COMPOSITE     = "#FF9933"     # Saffron — composite/India
C_GST           = "#2ca02c"     # Green — revenue
C_CREDIT        = "#003366"     # Navy — credit
C_UNEMPLOYMENT  = "#CC0000"     # Red — unemployment
C_FPI_POS       = "#065F46"     # Dark green — inflows
C_FPI_NEG       = "#991B1B"     # Dark red — outflows

# Fiscal chart colors
C_CAPEX         = "#1E40AF"     # Blue — capital expenditure
C_REVENUE_EXP   = "#DC2626"     # Red — revenue expenditure
C_FISCAL_DEF    = "#B91C1C"     # Dark red — fiscal deficit
C_TAX           = "#059669"     # Green — tax revenue
C_CORP_TAX      = "#1E3A8A"     # Navy — corporation tax
C_INCOME_TAX    = "#7C3AED"     # Purple — income tax
C_GST_TAX       = "#059669"     # Green — GST
C_CUSTOMS       = "#D97706"     # Amber — customs

# Section colors for table (matching macro_table style)
SECTION_COLORS = {
    "INFLATION":        "#B91C1C",
    "PMI":              "#FF9933",
    "FISCAL":           "#059669",
    "CREDIT & FLOWS":   "#7C3AED",
    "LABOUR":           "#0F172A",
    "MONETARY":         "#0369A1",   # Blue — monetary conditions section
    "EXTERNAL SECTOR":  "#0F766E",   # Teal — external sector section
}

# New chart colors for additions
C_DEPOSIT      = "#0EA5E9"    # Sky blue — deposit growth
C_EXPORTS      = "#059669"    # Green — exports
C_IMPORTS      = "#DC2626"    # Red — imports
C_DEFICIT_LINE = "#991B1B"    # Dark red — trade deficit line
C_RESERVES     = "#0369A1"    # Blue — forex reserves
C_REPO_RATE    = "#FF9933"    # Saffron — RBI repo rate
C_IIP_POS      = "#16A34A"    # Green — positive IIP
C_IIP_NEG      = "#DC2626"    # Red — negative IIP

SECTION_BG = "#F1F5F9"  # Slate 100


# ═══════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════

def load_india_data(csv_path=DEFAULT_CSV, months=None):
    """
    Load India monthly macro data.
    Primary:  data/india_macro.db  (india_monthly table)
    Fallback: data/india_manual.csv (legacy)
    """
    # ── Try SQLite primary source ─────────────────────────────────────────────
    if DEFAULT_DB.exists():
        try:
            import sqlite3
            with sqlite3.connect(DEFAULT_DB) as conn:
                df = pd.read_sql_query(
                    "SELECT * FROM india_monthly ORDER BY month ASC", conn
                )
            if not df.empty:
                df["date"] = pd.to_datetime(df["month"])
                df = df.drop(
                    columns=["month", "source_flags", "fetched_at"],
                    errors="ignore",
                )

                if "india_fpi_net_inr_cr" in df.columns:
                    df["india_fpi_nsdl_lcr"] = (
                        df["india_fpi_net_inr_cr"] / CRORE_PER_LAKH_CRORE
                    )

                if "india_fpi_mtd_inr_cr" in df.columns:
                    df["india_fpi_mtd_lcr"] = (
                        df["india_fpi_mtd_inr_cr"] / CRORE_PER_LAKH_CRORE
                    )

                if "india_fpi_mtd_asof" in df.columns:
                    df["india_fpi_mtd_asof"] = pd.to_datetime(
                        df["india_fpi_mtd_asof"],
                        errors="coerce",
                    )

                df = df.sort_values("date").reset_index(drop=True)

                if months:
                    cutoff = df["date"].max() - pd.DateOffset(months=months)
                    df = df[df["date"] >= cutoff].reset_index(drop=True)

                print(f"   Loaded {len(df)} months from india_macro.db")
                print(f"   Range: {df['date'].min():%b %Y} to {df['date'].max():%b %Y}")

                return df
        except Exception as e:
            print(f"   Warning: SQLite load failed ({e}), falling back to CSV")

    # ── CSV fallback ──────────────────────────────────────────────────────────
    if not csv_path.exists():
        print(f"❌ No data source found. Run: python data/fetchers/india_fetcher.py --seed")
        sys.exit(1)

    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df[[c for c in df.columns if not c.startswith("Unnamed")]]
    df = df.sort_values("date").reset_index(drop=True)

    if months:
        cutoff = df["date"].max() - pd.DateOffset(months=months)
        df = df[df["date"] >= cutoff].reset_index(drop=True)

    print(f"   Loaded {len(df)} months from {csv_path.name} (CSV fallback)")
    print(f"   Range: {df['date'].min():%b %Y} to {df['date'].max():%b %Y}")
    return df


def load_forex_weekly(n_weeks=78):
    """
    Load weekly forex reserves from india_macro.db (india_weekly table).
    Returns DataFrame with columns: week_ending (datetime), forex_reserves_usd_bn,
    forex_reserves_wow_chg.  Returns None if no data is available.
    """
    if not DEFAULT_DB.exists():
        return None
    try:
        import sqlite3
        with sqlite3.connect(DEFAULT_DB) as conn:
            df = pd.read_sql_query(
                "SELECT * FROM india_weekly ORDER BY week_ending DESC LIMIT ?",
                conn, params=[n_weeks]
            )
        if df.empty:
            return None
        df = df.sort_values("week_ending").reset_index(drop=True)
        df["week_ending"] = pd.to_datetime(df["week_ending"])
        df = df.drop(columns=["fetched_at"], errors="ignore")
        print(f"   Loaded {len(df)} weeks of forex reserve data")
        return df
    except Exception as e:
        print(f"   Warning: Forex weekly load failed: {e}")
        return None



# ─────────────────────────────────────────────────────────────────────────────
# Unit conversion — CAG Monthly Accounts
# ─────────────────────────────────────────────────────────────────────────────
# The CAG workbook records every monetary value in ₹ crore.
# 1 lakh crore = 100,000 crore.
#
# Until 2026-09 this module divided by 100 and labelled the result
# "₹ Lakh Crore", overstating every published fiscal figure by exactly 1,000×.
# Feb-26 capital expenditure (₹87,041 crore = ₹0.87 lakh crore) was published
# as ₹870 lakh crore — roughly half of India's annual GDP, for one month.
CRORE_PER_LAKH_CRORE = 100_000


def crore_to_lakh_crore(value):
    """Convert ₹ crore (CAG workbook native unit) to ₹ lakh crore."""
    if value is None:
        return None
    return value / CRORE_PER_LAKH_CRORE


# ─────────────────────────────────────────────────────────────────────────────
# CAG manual rows — a stop-gap while the CGA website does not publish the
# updated workbook. Figures are typed from CGA's monthly accounts web page into
# data/cag_manual_accounts.csv and merged with the workbook here. Every value is
# checked; a row that fails stops the run rather than publishing a wrong chart.
# ─────────────────────────────────────────────────────────────────────────────
CAG_MANUAL = Path(__file__).parent / "data" / "cag_manual_accounts.csv"

# csv column -> workbook column. Only what the fiscal charts draw: CGA's web
# page no longer gives tax revenue by head, so those columns are not collected.
CAG_MANUAL_FIELDS = {
    "revenue_expenditure": "Revenue Expenditure",
    "interest_payments": "Interest Payments",
    "major_subsidies": "Major Subsidies",
    "capital_expenditure": "Capital Expenditure",
    "fiscal_deficit": "Fiscal Deficit",
}
CAG_REQUIRED = ("revenue_expenditure", "capital_expenditure", "fiscal_deficit")
# Plausible range in Rs CRORE for a year-to-date figure. Wide on purpose: they
# exist to catch a value typed in lakh crore (1,000x too small) or with extra digits.
_CAG_BOUNDS = {
    "fiscal_deficit": (-1_000_000, 3_000_000),
}
_CAG_DEFAULT_BOUNDS = (1_000, 8_000_000)

# The "Sources of financing the deficit" page, Rs crore year to date: external
# financing plus the domestic total, and the domestic rows (a) to (i). Rows (h)
# surplus cash and (i) ways and means advances are not shown every month, so
# they may be blank; the two identities below prove a blank row is zero.
CAG_FINANCING_DOMESTIC = (
    "fin_market_borrowings", "fin_small_savings_securities", "fin_state_provident_funds",
    "fin_special_deposits", "fin_nssf", "fin_others", "fin_cash_balance",
    "fin_surplus_cash", "fin_wma",
)
CAG_FINANCING_FIELDS = ("fin_external", "fin_domestic") + CAG_FINANCING_DOMESTIC
_CAG_FINANCING_OPTIONAL = ("fin_surplus_cash", "fin_wma")
_CAG_FINANCING_BOUND = 3_000_000   # |Rs crore|: catches a digit too many
_CAG_FINANCING_TOLERANCE = 1.0     # Rs crore: the page rounds rows to paise and the deficit to a crore
_FISCAL_MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


class CagManualError(ValueError):
    """A manual CAG row failed its checks: the run stops instead of publishing it."""


def _fiscal_sort_key(fy, month):
    """Order rows by financial year, then Apr..Mar."""
    return (str(fy), _FISCAL_MONTHS.index(str(month).split("-")[0]) if str(month)[:3] in _FISCAL_MONTHS else 99)


def _financing_problems(where, values):
    """Check one row's financing figures against each other and the fiscal deficit."""
    missing = [k for k in CAG_FINANCING_FIELDS if k not in values and k not in _CAG_FINANCING_OPTIONAL]
    if missing:
        return [f"{where}: financing is incomplete, missing {', '.join(missing)}"]
    problems = [f"{where}: {k} {values[k]:,.0f} is outside ±{_CAG_FINANCING_BOUND:,} Rs crore (a digit too many?)"
                for k in CAG_FINANCING_FIELDS if k in values and abs(values[k]) > _CAG_FINANCING_BOUND]
    domestic = sum(values.get(k, 0.0) for k in CAG_FINANCING_DOMESTIC)
    if abs(domestic - values["fin_domestic"]) > _CAG_FINANCING_TOLERANCE:
        problems.append(f"{where}: domestic financing rows add up to {domestic:,.2f}, not the domestic total "
                        f"{values['fin_domestic']:,.2f}; a row is mistyped or missing")
    total = values["fin_external"] + values["fin_domestic"]
    if "fiscal_deficit" not in values:
        problems.append(f"{where}: financing needs the fiscal_deficit on the same row")
    elif abs(total - values["fiscal_deficit"]) > _CAG_FINANCING_TOLERANCE:
        problems.append(f"{where}: external + domestic financing is {total:,.2f}, not the fiscal deficit "
                        f"{values['fiscal_deficit']:,.0f}")
    return problems


def read_cag_manual(path=CAG_MANUAL):
    """
    Validated manual rows as (actual_rows, budget_rows, gdp_rows, financing_rows)
    DataFrames. The first three use the workbook's column names; financing_rows
    has FY, Month and the fin_* columns. Raises CagManualError listing every problem.
    """
    empty = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    if not path.exists():
        return empty
    raw = pd.read_csv(path, dtype=str, comment="#").fillna("")
    raw = raw[raw["fy"].str.strip() != ""]
    if raw.empty:
        return empty

    problems, actual, budget, gdp, financing = [], [], [], [], []
    for i, r in raw.iterrows():
        where = f"line {i + 2} ({r['fy']} {r['month']})"
        fy, month = r["fy"].strip(), r["month"].strip()
        if not re.fullmatch(r"\d{4}-\d{2}", fy) or int(fy[-2:]) != (int(fy[2:4]) + 1) % 100:
            problems.append(f"{where}: fy must look like 2026-27")
            continue
        values = {}
        for key in list(CAG_MANUAL_FIELDS) + ["gdp"] + list(CAG_FINANCING_FIELDS):
            text = r.get(key, "").replace(",", "").strip()
            if text == "":
                continue
            try:
                values[key] = float(text)
            except ValueError:
                problems.append(f"{where}: {key} is not a number: {r[key]!r}")

        if any(k in values for k in CAG_FINANCING_FIELDS):
            problems.extend(_financing_problems(where, values))
            financing.append({"FY": fy, "Month": month,
                              **{k: values.get(k, np.nan) for k in CAG_FINANCING_FIELDS}})

        if month in ("BE", "RE"):
            for key in ("capital_expenditure", "revenue_expenditure"):
                if key not in values:
                    problems.append(f"{where}: a {month} row needs {key}")
            if month == "BE" and "gdp" not in values:
                problems.append(f"{where}: the BE row needs gdp (nominal GDP in Rs crore)")
            if "gdp" in values and not (10_000_000 <= values["gdp"] <= 100_000_000):
                problems.append(f"{where}: gdp {values['gdp']:,.0f} is not in Rs crore "
                                "(expected 1,00,00,000 to 10,00,00,000)")
            budget.append({"FY": fy, "Month": month,
                           **{CAG_MANUAL_FIELDS[k]: v for k, v in values.items() if k in CAG_MANUAL_FIELDS}})
            if "gdp" in values:
                gdp.append({"FY": fy, "GDP": values["gdp"]})
            continue

        m = re.fullmatch(r"([A-Z][a-z]{2})-(\d{2})", month)
        if not m or m.group(1) not in _FISCAL_MONTHS:
            problems.append(f"{where}: month must look like Jul-26, BE or RE")
            continue
        expected_year = fy[2:4] if _FISCAL_MONTHS.index(m.group(1)) <= 8 else fy[-2:]
        if m.group(2) != expected_year:
            problems.append(f"{where}: {month} does not fall in financial year {fy}")
        for key in CAG_REQUIRED:
            if key not in values:
                problems.append(f"{where}: {key} is missing")
        for key in [k for k in CAG_MANUAL_FIELDS if k in values]:
            lo, hi = _CAG_BOUNDS.get(key, _CAG_DEFAULT_BOUNDS)
            if not lo <= values[key] <= hi:
                problems.append(f"{where}: {key} {values[key]:,.0f} is outside {lo:,}–{hi:,} Rs crore "
                                "(typed in lakh crore, or a digit too many?)")
        actual.append({"FY": fy, "Month": month,
                       **{CAG_MANUAL_FIELDS[k]: v for k, v in values.items() if k in CAG_MANUAL_FIELDS}})

    if problems:
        raise CagManualError("data/cag_manual_accounts.csv has problems:\n  " + "\n  ".join(problems))
    return pd.DataFrame(actual), pd.DataFrame(budget), pd.DataFrame(gdp), pd.DataFrame(financing)


def load_cag_tables(cag_path=DEFAULT_CAG, manual_path=CAG_MANUAL):
    """
    (actual, budget, gdp) tables: the workbook's sheets plus validated manual rows.
    A workbook row wins over a manual row for the same FY and month, so a newer
    official workbook supersedes the stop-gap automatically.
    """
    xlsx = pd.ExcelFile(cag_path)
    df_actual = pd.read_excel(xlsx, sheet_name='actual').dropna(subset=['FY', 'Month'])
    df_bere = pd.read_excel(xlsx, sheet_name='BERE')
    df_gdp = pd.read_excel(xlsx, sheet_name='GDP')
    man_actual, man_budget, man_gdp, _ = read_cag_manual(manual_path)

    def merge(book, manual, keys):
        if manual.empty:
            return book
        have = set(map(tuple, book[keys].astype(str).values))
        new = manual[[tuple(map(str, k)) not in have for k in manual[keys].values]]
        superseded = len(manual) - len(new)
        if superseded:
            print(f"   Note: {superseded} manual CAG row(s) superseded by the workbook — they can be deleted")
        return pd.concat([book, new], ignore_index=True)

    if not man_actual.empty:
        man_actual = man_actual.assign(_manual=True)
    df_actual = merge(df_actual, man_actual, ['FY', 'Month'])
    df_actual = df_actual.iloc[sorted(range(len(df_actual)),
                                      key=lambda i: _fiscal_sort_key(df_actual['FY'].iloc[i], df_actual['Month'].iloc[i]))]
    df_actual = df_actual.reset_index(drop=True)
    df_bere = merge(df_bere, man_budget, ['FY', 'Month'])
    df_gdp = merge(df_gdp, man_gdp, ['FY'])

    # A typed year-to-date spending figure cannot be below the month before it.
    # (Checked for manual rows only: the official history has the odd restatement.)
    if '_manual' in df_actual.columns:
        manual = df_actual['_manual'].eq(True)
        for i in df_actual.index[manual]:
            if i == 0 or df_actual.at[i - 1, 'FY'] != df_actual.at[i, 'FY']:
                continue
            for col in ('Revenue Expenditure', 'Capital Expenditure', 'Interest Payments'):
                if pd.notna(df_actual.at[i, col]) and df_actual.at[i, col] < df_actual.at[i - 1, col]:
                    raise CagManualError(
                        f"CAG {col} falls year-to-date at {df_actual.at[i, 'FY']} {df_actual.at[i, 'Month']} "
                        f"({df_actual.at[i - 1, col]:,.0f} → {df_actual.at[i, col]:,.0f}) — check the manual rows")
        df_actual = df_actual.drop(columns='_manual')

    # The latest financial year needs its Budget Estimate and GDP, or the
    # "% of BE" and "% of GDP" figures cannot be drawn.
    latest_fy = df_actual['FY'].iloc[-1]
    if df_bere[(df_bere['FY'] == latest_fy) & (df_bere['Month'] == 'BE')].empty:
        raise CagManualError(f"CAG {latest_fy} has monthly rows but no BE row — add it to data/cag_manual_accounts.csv")
    if df_gdp[df_gdp['FY'] == latest_fy].empty:
        raise CagManualError(f"CAG {latest_fy} has no GDP — add gdp to its BE row in data/cag_manual_accounts.csv")
    return df_actual, df_bere, df_gdp


def load_cag_financing(manual_path=CAG_MANUAL):
    """
    Checked financing rows (FY, Month, fin_* in Rs crore) from the manual CSV.
    The workbook has no financing page, so these rows stay in use even after a
    newer workbook supersedes the same month's other figures.
    """
    return read_cag_manual(manual_path)[3]


def load_cag_data(cag_path=DEFAULT_CAG):
    """
    Load CAG Monthly Accounts Dashboard data.
    Returns: (cag_summary dict, df_monthly with month-over-month data)
    """
    if not cag_path.exists():
        print(f"   ⚠ CAG file not found: {cag_path}")
        return None, None, None

    try:
        df_actual, df_bere, df_gdp = load_cag_tables(cag_path)
    except CagManualError:
        raise                          # a bad manual figure stops the run
    except Exception as e:
        print(f"   ⚠ Error loading CAG data: {e}")
        return None, None, None

    try:
        
        # Get current FY
        current_fy = df_actual['FY'].iloc[-1]
        df_current_fy = df_actual[df_actual['FY'] == current_fy].copy()
        
        # Get previous FY for comparison
        all_fys = sorted(df_actual['FY'].unique())
        prev_fy = all_fys[-2] if len(all_fys) >= 2 else None
        df_prev_fy = df_actual[df_actual['FY'] == prev_fy].copy() if prev_fy else None
        
        # Latest month data
        latest = df_current_fy.iloc[-1]
        latest_month = latest['Month']
        
        # Previous month data (for MoM calculation)
        prev_month_data = df_current_fy.iloc[-2] if len(df_current_fy) >= 2 else None
        
        # Calculate MONTHLY values (not cumulative) by differencing
        def calc_monthly(df):
            """Convert cumulative YTD to monthly values."""
            df = df.copy()
            cols_to_diff = ['Capital Expenditure', 'Fiscal Deficit', 'Revenue Expenditure',
                           'Corporation Tax', 'Income Tax', 'CGST', 'Customs', 'Union Excise',
                           'Interest Payments', 'Major Subsidies', 'Devolution to State']
            
            for col in cols_to_diff:
                if col in df.columns:
                    df[f'{col}_monthly'] = df[col].diff()
                    # First month is actual value
                    df.loc[df.index[0], f'{col}_monthly'] = df.loc[df.index[0], col]
            
            return df
        
        df_current_monthly = calc_monthly(df_current_fy)
        df_prev_monthly = calc_monthly(df_prev_fy) if df_prev_fy is not None else None
        
        # Get Budget Estimates
        be_row = df_bere[(df_bere['FY'] == current_fy) & (df_bere['Month'] == 'BE')]
        be_capex = be_row['Capital Expenditure'].values[0] if len(be_row) > 0 else None
        be_revenue_exp = be_row['Revenue Expenditure'].values[0] if len(be_row) > 0 else None
        
        # Calculate key metrics
        capex_ytd = latest['Capital Expenditure']
        fiscal_deficit_ytd = latest['Fiscal Deficit']
        revenue_exp_ytd = latest['Revenue Expenditure']
        
        # Calculate monthly values for latest month
        capex_monthly = df_current_monthly.iloc[-1].get('Capital Expenditure_monthly', None)
        fiscal_deficit_monthly = df_current_monthly.iloc[-1].get('Fiscal Deficit_monthly', None)
        
        # Previous month's monthly value (for MoM change)
        if len(df_current_monthly) >= 2:
            capex_prev_monthly = df_current_monthly.iloc[-2].get('Capital Expenditure_monthly', None)
            fiscal_deficit_prev_monthly = df_current_monthly.iloc[-2].get('Fiscal Deficit_monthly', None)
        else:
            capex_prev_monthly = None
            fiscal_deficit_prev_monthly = None
        
        # % of BE achieved
        capex_pct_be = (capex_ytd / be_capex * 100) if be_capex else None
        
        # Parse month for display
        month_map = {'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9,
                     'Oct': 10, 'Nov': 11, 'Dec': 12, 'Jan': 1, 'Feb': 2, 'Mar': 3}
        month_str = latest_month.split('-')[0]
        month_num = month_map.get(month_str, 12)
        year_suffix = latest_month.split('-')[1]
        year = int('20' + year_suffix)
        
        # MoM changes (in ₹ Lakh Cr)
        capex_mom = None
        if capex_monthly is not None and capex_prev_monthly is not None:
            capex_mom = (capex_monthly - capex_prev_monthly) / CRORE_PER_LAKH_CRORE  # Convert to L Cr
        
        fiscal_deficit_mom = None
        if fiscal_deficit_monthly is not None and fiscal_deficit_prev_monthly is not None:
            fiscal_deficit_mom = (fiscal_deficit_monthly - fiscal_deficit_prev_monthly) / CRORE_PER_LAKH_CRORE
        
        # GDP for % of GDP calculations
        gdp_row = df_gdp[df_gdp['FY'] == current_fy]
        gdp = gdp_row['GDP'].values[0] if len(gdp_row) > 0 else None
        
        # Calculate fiscal deficit as % of GDP
        fiscal_deficit_pct_gdp = (fiscal_deficit_ytd / gdp * 100) if gdp else None
        
        cag_summary = {
            'fy': current_fy,
            'prev_fy': prev_fy,
            'latest_month': latest_month,
            'latest_date': datetime(year, month_num, 1),
            # GDP
            'gdp': gdp / CRORE_PER_LAKH_CRORE if gdp else None,  # ₹ Lakh Cr
            # YTD values (₹ Lakh Cr)
            'fiscal_deficit_ytd': fiscal_deficit_ytd / CRORE_PER_LAKH_CRORE,
            'fiscal_deficit_pct_gdp': fiscal_deficit_pct_gdp,  # % of GDP
            'capex_ytd': capex_ytd / CRORE_PER_LAKH_CRORE,
            'revenue_exp_ytd': revenue_exp_ytd / CRORE_PER_LAKH_CRORE,
            # Monthly values (₹ Lakh Cr)
            'capex_monthly': capex_monthly / CRORE_PER_LAKH_CRORE if capex_monthly else None,
            'fiscal_deficit_monthly': fiscal_deficit_monthly / CRORE_PER_LAKH_CRORE if fiscal_deficit_monthly else None,
            # MoM changes
            'capex_mom': capex_mom,
            'fiscal_deficit_mom': fiscal_deficit_mom,
            # Budget
            'capex_pct_be': capex_pct_be,
            'be_capex': be_capex / CRORE_PER_LAKH_CRORE if be_capex else None,
            'be_revenue_exp': be_revenue_exp / CRORE_PER_LAKH_CRORE if be_revenue_exp else None,
            # Expenditure breakdown
            'interest_ytd': latest.get('Interest Payments', 0) / CRORE_PER_LAKH_CRORE,
            'subsidies_ytd': latest.get('Major Subsidies', 0) / CRORE_PER_LAKH_CRORE,
        }
        
        print(f"   Loaded CAG data: {current_fy} through {latest_month}")
        print(f"   Capex YTD: ₹{capex_ytd / CRORE_PER_LAKH_CRORE:.2f}L Cr ({capex_pct_be:.1f}% of BE)")
        
        return cag_summary, df_current_monthly, df_prev_monthly
        
    except Exception as e:
        print(f"   ⚠ Error loading CAG data: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None


# ═══════════════════════════════════════════
# CHART HELPERS
# ═══════════════════════════════════════════

def _add_end_label(ax, dates, vals, label, color, offset_x=8, offset_y=0):
    """Add end-of-line label with value."""
    if len(dates) == 0 or len(vals) == 0:
        return
    last_val = float(vals[-1]) if hasattr(vals[-1], 'item') else float(vals[-1])
    ax.annotate(
        f"{label}  {last_val:.1f}",
        xy=(dates[-1], last_val),
        xytext=(offset_x, offset_y), textcoords="offset points",
        fontsize=9, fontweight="bold", color=color,
        fontfamily=EconStyle.FONT_FAMILY,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                  edgecolor="none", alpha=0.85),
        zorder=10,
    )


def _format_date_axis(ax, n_points: int = 0):
    """
    Dynamically space x-axis date labels based on the number of data points
    so labels never overlap regardless of dataset size.

    Pass n_points explicitly (len(dates)) for best results; the fallback
    estimates from the axis x-range in months when not provided.
    """
    if n_points <= 0:
        try:
            xmin, xmax = ax.get_xlim()
            # matplotlib stores dates as float days since epoch
            n_points = max(1, int((xmax - xmin) / 30))
        except Exception:
            n_points = 24

    if n_points <= 18:
        interval = 1
    elif n_points <= 36:
        interval = 3
    elif n_points <= 60:
        interval = 6
    else:
        interval = 12

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=8)


# ═══════════════════════════════════════════
# CHART 1: PMI DASHBOARD
# ═══════════════════════════════════════════

def chart_pmi(df, output_dir):
    """Single-panel India PMI chart: manufacturing vs services, no smoothing."""
    series = [
        ("india_mfg_pmi", "Manufacturing", "#3C78C8", "-"),
        ("india_svc_pmi", "Services", "#269B91", (0, (5, 3))),  # shorter dashed
    ]

    data = df.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.dropna(subset=["date"]).sort_values("date")

    for key, _, _, _ in series:
        data[key] = pd.to_numeric(data.get(key, np.nan), errors="coerce")
        data[key] = data[key].replace([np.inf, -np.inf], np.nan)

    data = data.dropna(subset=[s[0] for s in series], how="all")
    if data.empty:
        print("   ⚠ Skipping PMI — no observations")
        return None

    # Preserve missing months as gaps rather than joining across absent releases
    data["date"] = data["date"].dt.to_period("M").dt.to_timestamp()
    data = data.drop_duplicates("date", keep="last").set_index("date")
    data = data.reindex(pd.date_range(data.index.min(), data.index.max(), freq="MS"))

    values = data[[s[0] for s in series]].to_numpy(dtype=float)
    bottom = min(49.0, float(np.nanmin(values)) - 1.0)
    top = max(55.0, float(np.nanmax(values)) + 1.5)

    # Match IIP’s aspect ratio while retaining PMI’s existing width.
    fig, ax = EconStyle.create_figure(size=(8.2, 4.23))

    # Leave modest room on the right for latest-value labels
    x_left = data.index[0] - pd.Timedelta(days=10)
    x_right = data.index[-1] + pd.Timedelta(days=45)
    ax.set_xlim(x_left, x_right)
    ax.set_ylim(bottom, top)

    # The expansion threshold organizes the chart; guides remain secondary.
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linewidth=.5, color="#E2E6E9", zorder=0)
    ax.xaxis.grid(False)
    ax.axhspan(bottom, 50, color="#64748B", alpha=.035, linewidth=0, zorder=0)
    ax.axhline(50, color="#303B45", linewidth=1.25, zorder=2)

    # A light teal ribbon encodes the Services lead, only where both exist.
    mfg_values = data["india_mfg_pmi"].to_numpy(dtype=float)
    svc_values = data["india_svc_pmi"].to_numpy(dtype=float)
    ax.fill_between(data.index, mfg_values, svc_values,
                    where=np.isfinite(mfg_values) & np.isfinite(svc_values)
                          & (svc_values > mfg_values),
                    interpolate=True, color="#269B91", alpha=.055,
                    linewidth=0, zorder=1)

    for spine in ["top", "right", "left", "bottom"]:
        ax.spines[spine].set_visible(False)

    ax.tick_params(axis="both", length=0, pad=6)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(2.5))
    ax.set_ylabel(
        "PMI",
        fontsize=EconStyle.FONT_SIZE_AXIS,
        fontweight="bold",
        color=EconStyle.INK,
    )

    # Plot series
    latest_points = []

    for key, label, color, linestyle in series:
        valid = data[key].dropna()
        if valid.empty:
            continue

        latest_date = valid.index[-1]
        latest_val = float(valid.iloc[-1])

        line, = ax.plot(
            data.index.to_pydatetime(),
            data[key].values,
            color=color,
            linewidth=2.2,
            linestyle=linestyle,
            zorder=4,
            antialiased=True,
            solid_capstyle="round",
            solid_joinstyle="round",
            dash_capstyle="round",
            dash_joinstyle="round",
        )

        ax.scatter(
            [latest_date],
            [latest_val],
            s=38,
            color=color,
            edgecolors="#27323B",
            linewidths=1.1,
            zorder=6,
        )

        latest_points.append({
            "label": label,
            "date": latest_date,
            "value": latest_val,
            "color": color,
        })

    if not latest_points:
        print("   ⚠ Skipping PMI — no valid series")
        return None

    # Separate latest labels slightly if the two values are very close
    latest_points = sorted(latest_points, key=lambda x: x["value"], reverse=True)

    if len(latest_points) == 2:
        y1 = latest_points[0]["value"]
        y2 = latest_points[1]["value"]

        if abs(y1 - y2) < 1.0:
            latest_points[0]["label_y"] = y1 + 0.40
            latest_points[1]["label_y"] = y2 - 0.40
        else:
            latest_points[0]["label_y"] = y1
            latest_points[1]["label_y"] = y2
    else:
        for p in latest_points:
            p["label_y"] = p["value"]

    # Direct labels identify the series without repeating current values above.
    label_x = data.index[-1] + pd.Timedelta(days=21)

    for p in latest_points:
        ax.annotate(
            f"{p['label']}  {p['value']:.1f}",
            xy=(p["date"], p["value"]),
            xytext=(label_x, p["label_y"]),
            textcoords="data",
            fontsize=10,
            fontweight="bold",
            color="#202A33",
            ha="left",
            va="center",
            arrowprops=dict(
                arrowstyle="-",
                color="#596570",
                linewidth=0.7,
                shrinkA=0,
                shrinkB=4,
            ),
            annotation_clip=False,
            zorder=7,
        )

    # Threshold label
    ax.annotate(
        "50 · Expansion threshold",
        xy=(0.01, 50),
        xycoords=("axes fraction", "data"),
        xytext=(0, 4),
        textcoords="offset points",
        fontsize=8.5,
        color=EconStyle.INK_MUTED,
        ha="left",
        va="bottom",
    )

    # X-axis formatting
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.tick_params(axis="x", pad=8, labelsize=EconStyle.FONT_SIZE_TICK)
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")

    EconStyle.set_title(
        ax, "India PMI — Growth Momentum",
        "Manufacturing (solid) · Services (dashed) · 50 = no change",
    )

    ax.set_title(ax.get_title(loc="left"), loc="left", pad=16,
                 fontproperties=EconStyle._get_font("bold"),
                 fontsize=EconStyle.FONT_SIZE_TITLE, color=EconStyle.TEXT_TITLE)
    EconStyle.add_top_rule(ax)

    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    EconStyle.add_source(
        fig,
        "S&P Global · monthly PMI",
        date_text=f"Latest observation: {data.index[-1]:%b %Y}",
    )

    fp = output_dir / "01_india_pmi.png"
    EconStyle.save_chart(fig, fp)

    print("   ✓ PMI")
    return fp

def chart_gva_contributions(output_dir, db_path=DEFAULT_DB):
    """Official broad-sector contributions from the validated offline SQLite snapshot."""
    from matplotlib.lines import Line2D
    from data.fetchers.mospi_gva import load, SECTORS, LEVEL_KEYS
    import sqlite3

    import os
    fp = output_dir / '22_india_gva_contributions.png'
    try:
        if os.environ.get('GVA_UPDATE_FAILED') == 'true':
            raise ValueError('Saturday GVA update failed; stale snapshot not substituted')
        records = load(db_path)
    except (ValueError, OSError, sqlite3.Error) as exc:
        fp.unlink(missing_ok=True)
        print(f'   WARNING: GVA chart omitted — {exc}')
        return None
    panel = pd.DataFrame(
        r for r in records
        if r["headline_yoy"] is not None
    )

    if panel.empty:
        raise ValueError(
            "MoSPI GVA: no complete YoY comparisons; run the GVA fetcher first"
        )

    latest = panel.iloc[-1]
    x = np.arange(len(panel))

    # House categorical palette: agriculture green, industry terracotta,
    # services cobalt. Warm/cool separation keeps the three sectors distinct.
    colors = (
        EconStyle.CATEGORICAL_COLORS[2],
        EconStyle.CATEGORICAL_COLORS[6],
        EconStyle.CATEGORICAL_COLORS[0],
    )

    fig, ax = EconStyle.create_figure(size="wide")

    above = np.zeros(len(panel))
    below = np.zeros(len(panel))

    latest_sector_values = []

    # ── Sector contributions ───────────────────────────────────────────
    for key, name, color in zip(LEVEL_KEYS[:3], SECTORS, colors):
        values = panel[key + "_pp"].to_numpy()

        base = np.where(values >= 0, above, below).copy()

        ax.bar(
            x,
            values,
            bottom=base,
            width=0.68,
            color=color,
            edgecolor=EconStyle.BAR_EDGE_COLOR,
            linewidth=EconStyle.BAR_EDGE_WIDTH,
            zorder=3,
        )

        latest_sector_values.append(
            (name, float(values[-1]), color)
        )

        above += np.clip(values, 0, None)
        below += np.clip(values, None, 0)

    # ── Headline Real GVA ─────────────────────────────────────────────
    headline = panel["headline_yoy"].to_numpy()
    latest_gva = float(headline[-1])

    ax.plot(
        x,
        headline,
        color="#000000",
        linewidth=1.35,
        marker="o",
        markersize=3.7,
        markeredgecolor="white",
        markeredgewidth=0.5,
        zorder=5,
    )

    ax.scatter(
        [x[-1]],
        [latest_gva],
        s=42,
        color="black",
        edgecolors="white",
        linewidths=0.8,
        zorder=6,
    )

    # Only direct label retained in the plotting area
    ax.annotate(
        f"{latest_gva:.2f}%",
        xy=(x[-1], latest_gva),
        xytext=(0, 11),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=10.5,
        fontweight="bold",
        color="black",
        annotation_clip=False,
        zorder=7,
    )

    # Zero-growth reference
    ax.axhline(
        0,
        color=EconStyle.INK,
        linewidth=0.8,
        zorder=4,
    )

    # ── Axes ──────────────────────────────────────────────────────────
    top = max(above.max(), headline.max())

    ax.set_ylim(
        min(below.min(), 0) - 0.2,
        top * 1.30,
    )

    # No longer need the large right-hand margin for direct labels
    ax.set_xlim(-0.65, x[-1] + 0.65)

    ax.yaxis.set_major_locator(
        mticker.MultipleLocator(2)
    )

    ax.set_ylabel(
        "Contribution to YoY growth (percentage points)",
        fontsize=9,
    )

    ax.grid(
        axis="x",
        visible=False,
    )

    ax.grid(
        axis="y",
        color=EconStyle.GRID_COLOR,
        linewidth=0.6,
        alpha=0.5,
        zorder=0,
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.tick_params(
        axis="both",
        length=0,
    )

    # ── Quarter labels ────────────────────────────────────────────────
    ax.set_xticks(x)

    ax.set_xticklabels(
        [f"Q{r.fiscal_quarter}" for r in panel.itertuples()],
        fontsize=8,
    )

    # Fiscal-year labels centred beneath each group
    for fy, group in panel.groupby("fiscal_year", sort=False):
        positions = group.index.to_numpy()

        ax.text(
            positions.mean(),
            -0.10,
            f"FY{fy}",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8,
            color=EconStyle.INK_MUTED,
        )

    # ── Latest-quarter indicator row ─────────────────────────────────
    legend_handles = []
    legend_labels = []

    for name, value, color in latest_sector_values:
        legend_handles.append(
            mpatches.Patch(
                facecolor=color,
                edgecolor=EconStyle.BAR_EDGE_COLOR,
                linewidth=EconStyle.BAR_EDGE_WIDTH,
            )
        )

        legend_labels.append(
            f"{name} ({value:+.2f} pp)"
        )

    # Real GVA as fourth indicator
    legend_handles.append(
        Line2D(
            [0],
            [0],
            color="black",
            linewidth=1.35,
            marker="o",
            markersize=4,
            markerfacecolor="black",
            markeredgecolor="white",
            markeredgewidth=0.6,
        )
    )

    legend_labels.append(
        f"Real GVA ({latest_gva:.2f}%)"
    )

    ax.legend(
    legend_handles,
    legend_labels,
    loc="upper left",
    bbox_to_anchor=(0.0, 0.985),
    bbox_transform=ax.transAxes,
    ncol=4,
    frameon=False,
    fontsize=8.5,
    handlelength=1.0,
    handleheight=0.9,
    handletextpad=0.45,
    columnspacing=1.25,
    borderaxespad=0,
)

    # ── Title ─────────────────────────────────────────────────────────
    EconStyle.set_title(
        ax,
        "What Is Driving India’s Growth?",
        "Quarterly real GVA · Constant 2022-23 prices",
    )

    EconStyle.add_top_rule(ax)

    # Larger plotting area; only source remains below
    fig.tight_layout(
        rect=[0.02, 0.075, 0.98, 0.96]
    )

    EconStyle.add_source(
        fig,
        "MoSPI / NSO · eSankhyiki; NAS 2026",
        date_text=(
            f"Release "
            f"{pd.Timestamp(latest['release_date']):%d %b %Y}"
        ),
    )

    fp = output_dir / "22_india_gva_contributions.png"
    EconStyle.save_chart(fig, fp)

    print("   ✓ What Is Driving India’s Growth?")
    return fp


def chart_investment_rate(output_dir):
    """India gross fixed capital formation as a share of GDP, annual and unsmoothed."""
    from data.fetchers.gmd_investment import load_snapshot

    values, meta = load_snapshot()
    valid = values.dropna()

    if valid.empty:
        print("   ⚠ Skipping India Investment Rate — no observations")
        return None

    first_year = int(valid.index[0])
    latest_year = int(valid.index[-1])
    latest_value = float(valid.iloc[-1])

    color = "#E5822A"

    # Keep a wide source canvas. On the dashboard this should ultimately
    # be rendered in the same two-column grid as the GVA chart.
    fig, ax = EconStyle.create_figure(size="wide")

    ax.set_axisbelow(True)

    ax.yaxis.grid(True, linewidth=.5, color="#E2E6E9", zorder=0)
    ax.xaxis.grid(False)

    # ── Long-run average ────────────────────────────────────────────────
    long_run_avg = float(valid.mean())

    ax.axhline(
        long_run_avg,
        color="#46515C",
        linewidth=1.15,
        linestyle=(0, (4, 4)),
        zorder=2,
    )

    # The cycle is defined relative to the unchanged full-sample average.
    ax.fill_between(valid.index, valid.values, long_run_avg,
                    where=valid.values >= long_run_avg, interpolate=True,
                    color=color, alpha=.12, linewidth=0, zorder=1)
    ax.fill_between(valid.index, valid.values, long_run_avg,
                    where=valid.values < long_run_avg, interpolate=True,
                    color="#64748B", alpha=.045, linewidth=0, zorder=1)

    # ── Main series ────────────────────────────────────────────────────
    line, = ax.plot(
        valid.index,
        valid.values,
        color=color,
        linewidth=2.5,
        zorder=5,
        antialiased=True,
        solid_capstyle="round",
        solid_joinstyle="round",
    )

    # Latest point only
    ax.scatter(
        [latest_year],
        [latest_value],
        s=46,
        color=color,
        edgecolors="#27323B",
        linewidths=1.1,
        zorder=7,
    )

    # Latest direct label
    ax.annotate(
        f"{latest_value:.1f}%",
        xy=(latest_year, latest_value),
        xytext=(10, 0),
        textcoords="offset points",
        fontsize=11,
        fontweight="bold",
        color="#202A33",
        ha="left",
        va="center",
        annotation_clip=False,
        zorder=8,
    )

    # Long-run average label
    ax.annotate(
        f"Long-run avg  {long_run_avg:.1f}%",
        xy=(first_year, long_run_avg),
        xytext=(6, -6),
        textcoords="offset points",
        fontsize=8.5,
        fontweight="semibold",
        color="#46515C",
        ha="left",
        va="top",
        annotation_clip=False,
        zorder=6,
    )

    # ── Axes ───────────────────────────────────────────────────────────
    spread = float(valid.max() - valid.min())

    lower = np.floor((valid.min() - max(1.0, spread * 0.08)) / 2) * 2
    upper = np.ceil((valid.max() + max(1.0, spread * 0.10)) / 2) * 2

    ax.set_ylim(lower, upper)

    # Modest right margin only for direct labels
    ax.set_xlim(first_year - 0.5, latest_year + 3.0)

    # Historical context is deliberately separate from the average-based fills.
    # Short phase strips sit above the data; event stems stop shy of the line.
    # 2016 anchors the twin-balance-sheet episode (Economic Survey 2016–17),
    # rather than implying that the prolonged crisis began in a single year.
    from matplotlib.patches import Rectangle
    context_ink = "#56616D"
    for start, end in [(2003, 2008), (2021, latest_year)]:
        if first_year <= start < end <= latest_year:
            phase_y = upper - (.9 if start == 2003 else 2.6)
            ax.add_patch(Rectangle((start, phase_y), end - start, .16,
                                   facecolor="#64748B", alpha=.10,
                                   edgecolor="none", zorder=1))
            ax.plot([start, end], [phase_y, phase_y],
                    color=context_ink, linewidth=.55, zorder=3)
    if first_year <= 2003 and latest_year >= 2008:
        ax.text(2005.5, upper - 1.25, "2003–08 investment boom",
                ha="center", va="top", fontsize=8.5,
                color=context_ink, zorder=6)
    if first_year <= 2021 < latest_year:
        ax.text(latest_year + 2.7, upper - 2.15,
                "2021 onward: recovery /\npublic capex / manufacturing\npush / PLI era",
                ha="right", va="bottom", fontsize=8.5, linespacing=1.2,
                color=context_ink, zorder=6)
    events = [
        (1991, 1991, long_run_avg + 3.8, "liberalisation\nreforms", "bottom"),
        (2016, 2016, long_run_avg + 4.0, "twin-balance-sheet\ncrisis", "bottom"),
        (2020, 2020, lower + 2.1, "2020 Covid", "top"),
    ]
    for year, label_year, label_y, label, alignment in events:
        if year not in valid.index:
            continue
        point_y = float(valid.loc[year])
        direction = 1 if label_y > point_y else -1
        stem_y = (long_run_avg + .6 if year == 1991
                  else point_y + direction * .3)
        ax.annotate(label, xy=(year, stem_y),
                    xytext=(label_year, label_y), textcoords="data",
                    ha="center", va=alignment, fontsize=8.5,
                    linespacing=1.2, color=context_ink,
                    arrowprops=dict(arrowstyle="-", color=context_ink,
                                    linewidth=.55, shrinkA=4, shrinkB=0),
                    zorder=6)

    xticks = list(range(
        int(np.ceil(first_year / 10) * 10),
        latest_year + 1,
        10
    ))

    if latest_year not in xticks:
        xticks.append(latest_year)

    ax.set_xticks(sorted(set(xticks)))

    ax.yaxis.set_major_locator(mticker.MultipleLocator(4))

    ax.set_ylabel(
        "% of GDP",
        fontsize=EconStyle.FONT_SIZE_AXIS,
        fontweight="bold",
        color=EconStyle.INK,
    )

    for spine in ["top", "right", "left", "bottom"]:
        ax.spines[spine].set_visible(False)

    ax.tick_params(axis="both", length=0)

    # ── Title ──────────────────────────────────────────────────────────
    EconStyle.set_title(
        ax,
        "India’s Investment Cycle",
        "Gross fixed capital formation · % of GDP · annual",
    )

    EconStyle.add_top_rule(ax)

    fig.tight_layout(
        rect=[0.02, 0.04, 0.98, 0.96]
    )

    EconStyle.add_source(
        fig,
        "Global Macro Database · Müller et al. (2025)",
        date_text=f"Vintage {meta['vintage']}",
    )

    fp = output_dir / "20_india_gross_fixed_capital_formation.png"
    EconStyle.save_chart(fig, fp)

    print(
        f"   ✓ India’s Gross Fixed Capital Formation Trend "
        f"({first_year}–{latest_year}, latest {latest_value:.1f}%)"
    )

    return fp


def chart_risk_appetite(output_dir):
    """Smallcap/large-cap price-index ratio; no network calls or imputed dates."""
    from data.nse_indices import ROOT, load_risk_appetite
    import os
    fp = output_dir / '21_india_risk_appetite.png'
    try:
        if os.environ.get('NSE_RISK_UPDATE_FAILED') == 'true':
            raise ValueError('Saturday NSE refresh failed')
        panel, meta = load_risk_appetite()
        if (pd.Timestamp.now().normalize()-pd.Timestamp(meta['last_date'])).days > 10:
            raise ValueError('Last matched NSE close is more than ten days old')
    except (ValueError, OSError, KeyError) as exc:
        fp.unlink(missing_ok=True)
        print(f'   WARNING: Risk Appetite omitted — {exc}')
        return None
    values = panel["relative_100"]
    first, last = values.index[0], values.index[-1]
    fig, ax = EconStyle.create_figure(size="wide")
    color = "#B91C1C"
    # Use the union only for rendering gaps: no value exists on an unmatched date.
    dates = values.index.union(pd.DatetimeIndex(meta["unmatched_dates"]))
    ax.plot(dates, values.reindex(dates), color=color, linewidth=2.35,
            solid_capstyle="round", solid_joinstyle="round", zorder=4)
    ax.axhline(100, color=EconStyle.INK_MUTED, linewidth=0.8,
               linestyle=(0, (4, 4)), alpha=0.65, zorder=2)
    ax.scatter([last], [values.iloc[-1]], s=46, color=color,
               edgecolors="white", linewidths=1.1, zorder=6)
    ax.annotate(f"{values.iloc[-1]:.1f}", (last, values.iloc[-1]), xytext=(9, 0),
                textcoords="offset points", fontsize=11, fontweight="bold",
                color=color, va="center", annotation_clip=False)
    ax.text(0.015, 0.96, "Rising = small caps outperform", transform=ax.transAxes,
            va="top", fontsize=9, color=EconStyle.INK_MUTED)
    ax.set_xlim(first - pd.Timedelta(days=45), last + pd.Timedelta(days=220))
    ax.set_ylim(np.floor(values.min() / 10) * 10 - 5, np.ceil(values.max() / 10) * 10 + 10)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.set_ylabel("Relative performance", fontsize=EconStyle.FONT_SIZE_AXIS,
                  fontweight="bold", color=EconStyle.INK)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    EconStyle.set_title(ax, "Indian Risk Appetite",
                        f"NIFTY Smallcap 250 / NIFTY 50 · price indices · {first:%d %b %Y} = 100")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[.02, .04, .98, .96])
    EconStyle.add_source(fig, "NSE Indices · daily closing values",
                         date_text=f"Through {last:%d %b %Y}")
    fp = output_dir / "21_india_risk_appetite.png"
    EconStyle.save_chart(fig, fp)
    print("   ✓ Indian Risk Appetite")
    return fp


def chart_sector_rotation_12m(output_dir):
    """Independent India allIndices chart; optional-source failures remove old output."""
    import json
    from data.fetchers.nse_sector_rotation import load_rotation_data
    from charts.templates.change_bars import render_change_bars

    fp = output_dir / "23_india_sector_rotation_12m_benchmark.png"
    try:
        import os
        if os.environ.get('NSE_ROTATION_UPDATE_FAILED') == 'true':
            raise ValueError('Saturday NSE rotation refresh failed')
        rows, metadata = load_rotation_data()
    except Exception as exc:
        fp.unlink(missing_ok=True)
        fp.with_suffix(".json").unlink(missing_ok=True)
        print(f"   ⚠ WARNING: NIFTY Sector Rotation omitted — {exc}")
        return None
    observed = datetime.strptime(metadata["observation_date"], "%Y-%m-%d")
    snapshot_time = datetime.strptime(metadata["timestamp"], "%d-%b-%Y %H:%M")
    fig = render_change_bars(
        [r["label"] for r in rows], [r["return_pct"] for r in rows],
        "NIFTY Sector Rotation — Trailing 12 Months",
        "Price return over the past year, not total return",
        "NSE (allIndices, price indices)", size=(EconStyle.SIZE_WIDE[0], 5.1),
        benchmark="NIFTY 50", source_date=f"Snapshot {snapshot_time:%d %b %Y %H:%M} IST", bottom_margin=.09,
    )
    EconStyle.save_chart(fig, fp)
    metadata["rows"] = rows
    fp.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"   ✓ NIFTY Sector Rotation (NSE through {observed:%d %b %Y})")
    return fp


def chart_sector_valuations(output_dir):
    """Own-history percentiles; approved metrics, completed reference months only."""
    import json
    import os
    from data.fetchers.nse_valuations.production import load_chart_data
    fp = output_dir / "22_india_sector_valuations.png"
    metadata_path = fp.with_suffix(".json")
    # An optional-data failure must not leave an older chart in this edition.
    def omit(reason):
        fp.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        print(f"   ⚠ WARNING: Indian Sector Valuations omitted — {reason}")
        return None
    if os.environ.get("NSE_VALUATIONS_UPDATE_FAILED") == "true":
        return omit("official NSE valuation update failed in this workflow")
    try:
        rows, metadata = load_chart_data()
    except (ValueError, OSError, KeyError) as exc:
        return omit(str(exc))
    for warning in metadata["warnings"]:
        print(f"   ⚠ WARNING: {warning}")
    if not rows:
        return omit("no index has a current metric and 60 completed valid months")

    from charts.templates.change_bars import BAR_MAX_PX, _bar_path
    from matplotlib.patches import PathPatch

    # Presentation only: keep loader order and exact statistics in metadata.
    # Names, a fixed 0–100 percentile span, then two separate numeric columns.
    fig, ax = EconStyle.create_figure(size=(EconStyle.SIZE_WIDE[0], 5.1))
    ax.set_xlim(-82, 95)
    benchmark_first = rows[0]["index"] == "Nifty 50"
    positions = [i + (.45 if benchmark_first and i > 0 else 0)
                 for i in range(len(rows))]
    bottom = positions[-1] + .5
    header_top = -1.8
    ax.set_ylim(bottom, header_top)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    EconStyle.set_title(
        ax, "NIFTY Sector Valuations",
        "Current P/E or P/B percentile versus own history · 50 = median",
    )
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[.02, .12, .98, .96])
    # Only the benchmark row has a background tint.
    if benchmark_first:
        benchmark_tint = ("#E2EBEF" if rows[0]["percentile"] > 90 or
                          rows[0]["percentile"] < 10 else "#EEF2F5")
        ax.axhspan(-.55, .55, color=benchmark_tint, linewidth=0, zorder=0)
        ax.axhline(.725, color="#BCC5CD", linewidth=.7, zorder=1)
    # Use exact percentiles for emphasis, independent of displayed rounding.
    extremes = [row["percentile"] > 90 or row["percentile"] < 10
                for row in rows]
    # A quiet gutter separates the percentile scale from the scan columns.
    ax.plot([58, 58], [-1.1, bottom], color="#DDE2E7",
            linewidth=.6, zorder=1)
    for guide in (-25, 25):
        ax.plot([guide, guide], [-.55, bottom], color=EconStyle.GRID_COLOR,
                linewidth=.55, zorder=1)
    ax.plot([0, 0], [-.55, bottom], color="#34424F",
            linewidth=1.35, zorder=4)
    for x, cue, align in [(-50, "CHEAPER ←", "left"),
                           (50, "→ RICHER", "right")]:
        ax.text(x, -1.38, cue, ha=align, va="center", fontsize=7,
                color=EconStyle.INK_MUTED)
    for x, label in [(-25, "25"), (0, "50 MEDIAN"), (25, "75")]:
        ax.text(x, -.88, label, ha="center", va="center",
                fontsize=7.5 if x == 0 else 7,
                color="#34424F" if x == 0 else EconStyle.INK_MUTED,
                fontweight="bold" if x == 0 else "normal")
    transform = ax.get_yaxis_transform()
    percentile_x = .835
    valuation_x = .995
    valuation_ink = "#80505E"
    scan_fontsize = EconStyle.FONT_SIZE_BAR_LABEL + 2
    for x, label, align in [(percentile_x, "PERCENTILE", "center"),
                             (valuation_x, "VALUATION", "right")]:
        ax.text(x, -.88, label, transform=transform, ha=align, va="center",
                fontsize=7, fontweight="semibold",
                color=valuation_ink if label == "VALUATION" else EconStyle.INK_MUTED)

    box = ax.get_window_extent(fig.canvas.get_renderer())
    px_per_x = box.width / (ax.get_xlim()[1] - ax.get_xlim()[0])
    px_per_y = box.height / (bottom - header_top)
    half_h = min(.25, BAR_MAX_PX / 2 / px_per_y)
    # Small end radii and house charcoal outlines give the bars crisp edges.
    rx, ry = 3 / px_per_x, 3 / px_per_y
    for position, row, extreme in zip(positions, rows, extremes):
        benchmark = row["index"] == "Nifty 50"
        display_position = row["percentile"] - 50
        # Medium-saturation blue / teal families encode the two history sides.
        if display_position >= 0:
            color = "#477BA6" if extreme else "#86A7C4"
        else:
            color = "#438B82" if extreme else "#85B3AE"
        if display_position != 0:
            ax.add_patch(PathPatch(
                _bar_path(display_position, position, half_h, rx, ry),
                facecolor=color, edgecolor=EconStyle.BAR_EDGE_COLOR,
                linewidth=EconStyle.BAR_EDGE_WIDTH + (.1 if extreme else 0), zorder=3,
            ))
        ax.text(0, position, row["label"], transform=transform,
                ha="left", va="center", fontsize=EconStyle.FONT_SIZE_CATEGORY + 2,
                color=EconStyle.INK, fontweight="bold" if benchmark else "normal")
        # Ordinal rounding is typography only; bar length uses the exact value.
        percentile_label = int(round(row["percentile"]))
        suffix = ("th" if 10 <= percentile_label % 100 <= 20 else
                  {1: "st", 2: "nd", 3: "rd"}.get(percentile_label % 10, "th"))
        percentile_text = ("Lowest\nin sample" if row["percentile"] == 0
                           else f"{percentile_label}{suffix}")
        ax.text(percentile_x, position, percentile_text, transform=transform,
                ha="center", va="center", fontsize=scan_fontsize,
                fontweight="bold", color="#171D24" if extreme else "#586270", zorder=5)
        precision = 1 if row["metric"] == "P/E" else 2
        ax.text(valuation_x, position,
                f'{row["current_multiple"]:.{precision}f}× {row["metric"]}',
                transform=transform, ha="right", va="center", fontsize=scan_fontsize,
                color=valuation_ink, fontweight="bold", zorder=5)
    observed = datetime.strptime(metadata['source']['observation_date'], '%Y-%m-%d')
    fig.add_artist(plt.Line2D([.04, .96], [.105, .105],
                             transform=fig.transFigure, color="#DDE2E7", linewidth=.6))
    # Two compact lines leave the house credit its usual corner.
    fig.text(.04, .065, "Source: NSE Indices · P/E: Apr 2021 onward · P/B: up to 10Y",
             fontsize=EconStyle.FONT_SIZE_SOURCE, color=EconStyle.TEXT_MUTED)
    fig.text(.04, .025, f"Through {observed:%d %b %Y} · Current month excluded from reference history",
             fontsize=7, color=EconStyle.TEXT_MUTED)
    EconStyle.draw_credit(fig)
    EconStyle.save_chart(fig, fp)
    metadata["rows"] = rows
    metadata_path.write_text(json.dumps(metadata, indent=2)+"\n")
    print(f"   ✓ Indian Sector Valuations (NSE through {observed:%d %b %Y})")
    return fp


# ═══════════════════════════════════════════
# CHART 2: GST REVENUE
# ═══════════════════════════════════════════

def chart_gst(df, output_dir):
    """Monthly GST collection bar chart with trend line."""
    if "india_gst_revenue" not in df.columns:
        print("   ⚠ Skipping GST — column not found")
        return None

    fig, ax = EconStyle.create_figure(size="wide")

    dates = df["date"].tolist()
    vals = df["india_gst_revenue"].values

    # Subtle gridlines behind bars
    ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
    ax.set_axisbelow(True)

    # Uniform color for all bars
    bar_width = 20  # days
    ax.bar(dates, vals, width=bar_width, color=C_GST, alpha=0.75,
           edgecolor="none", zorder=3, label="Monthly GST")

    # 3-month moving average trend
    if len(vals) >= 3:
        ma3 = pd.Series(vals).rolling(3).mean().values
        ax.plot(dates, ma3, color="#000000", linewidth=2, linestyle="-",
                label="3M Avg", zorder=5, solid_capstyle="round")
        # End label for MA
        valid_ma = [(d, v) for d, v in zip(dates, ma3) if not np.isnan(v)]
        if valid_ma:
            _add_end_label(ax, [d for d, _ in valid_ma],
                          [v for _, v in valid_ma], "3M Avg", "#000000")

    # ₹2 Lakh Cr reference
    ax.axhline(y=2.0, color="#FF9933", linewidth=1.5, linestyle="--",
               alpha=0.7, zorder=2, label="₹2L Cr Target")

    _format_date_axis(ax, len(dates))
    ax.set_ylim(bottom=1.3, top=np.nanmax(df["india_gst_revenue"].values) * 1.05)
    ax.set_ylabel("₹ Lakh Crore", fontsize=EconStyle.FONT_SIZE_AXIS)
    
    # Legend at top-right, inline with subtitle
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=3, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)

    EconStyle.set_title(ax, "GST Revenue Collections",
                        "Monthly Gross GST Revenue (₹ Lakh Crore)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "PIB / GST Council")

    fp = output_dir / "02_india_gst.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ GST Revenue")
    return fp


# ═══════════════════════════════════════════
# CHART: NIFTY IT INDEX (TRAILING 12 MONTHS)
# ═══════════════════════════════════════════

def chart_nifty_it_trend(output_dir):
    """
    NIFTY IT index level over the trailing 12 months (Yahoo Finance, ^CNXIT).
    Moved from the Weekly Markets dashboard in Sep 2026; the India workflow
    runs every Saturday, so the series stays weekly-fresh.
    """
    from data.fetchers.yfinance_fetcher import YFinanceFetcher

    try:
        series = YFinanceFetcher().get_close_series("^CNXIT", period="1y")
    except Exception as e:
        print(f"   ⚠ Skipping NIFTY IT — fetch failed: {e}")
        return None
    if series is None or series.empty:
        print("   ⚠ Skipping NIFTY IT — no data returned")
        return None

    dates = series.index.to_pydatetime()
    vals = series.values

    fig, ax = EconStyle.create_figure(size="wide")
    ax.plot(dates, vals, color="#B91C1C", linewidth=2.5, solid_capstyle="round")
    ax.plot(dates, vals, color="#B91C1C", linewidth=3.7, alpha=0.07, solid_capstyle="round")

    # Crop the y-axis tightly around the data
    padding = (vals.max() - vals.min()) * 0.1
    ax.set_ylim(vals.min() - padding, vals.max() + padding)

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.yaxis.grid(True, linestyle="-", alpha=0.15, color="#9CA3AF", zorder=0)
    ax.set_ylabel("Index Level", fontsize=EconStyle.FONT_SIZE_AXIS)

    # Latest week shaded, with the last close labelled
    if len(dates) > 5:
        ax.axvspan(dates[-6], dates[-1], color="#DC2626", alpha=0.1)
        ax.annotate(
            f"{vals[-1]:,.0f}",
            xy=(dates[-1], vals[-1]),
            xytext=(8, 0), textcoords="offset points",
            fontsize=9, fontweight="bold", color="#B91C1C",
            fontfamily=EconStyle.FONT_FAMILY,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85),
            zorder=10,
        )

    EconStyle.set_title(ax, "NIFTY IT Index — Trailing 12 Months", "NSE IT sector benchmark index level")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "Yahoo Finance (NSE)")

    fp = output_dir / "04_india_nifty_it_trend.png"
    EconStyle.save_chart(fig, fp)
    print("   ✓ NIFTY IT (12 months)")
    return fp


# ═══════════════════════════════════════════
# CHART: FOREIGN PORTFOLIO FLOWS (MONTHLY)
# ═══════════════════════════════════════════

def fpi_freshness(df, today=None):
    """
    Assess freshness of the canonical NSDL monthly FPI series.

    Policy:
      - Expected observation = previous completed calendar month.
      - One month behind during days 1–6: warning only.
      - One month behind from day 7 onward: strong stale warning.
      - Two or more completed months behind: critical; omit the FPI chart/row.
    """
    col = "india_fpi_nsdl_lcr"

    now = pd.Timestamp(
        today if today is not None else datetime.now()
    ).normalize()

    expected_month = (
        now.to_period("M") - 1
    ).to_timestamp()

    manual_command = (
        "python -m data.india_manual_entry set "
        f"{expected_month:%Y-%m} --fpi <Rs crore>"
    )

    if col not in df.columns:
        return {
            "status": "critical",
            "latest_month": None,
            "expected_month": expected_month,
            "lag_months": None,
            "manual_command": manual_command,
        }

    valid = df.loc[
        df[col].notna(),
        ["date", col],
    ].copy()

    if valid.empty:
        return {
            "status": "critical",
            "latest_month": None,
            "expected_month": expected_month,
            "lag_months": None,
            "manual_command": manual_command,
        }

    latest_month = (
        pd.Timestamp(valid["date"].max())
        .to_period("M")
        .to_timestamp()
    )

    lag_months = (
        (expected_month.year - latest_month.year) * 12
        + expected_month.month
        - latest_month.month
    )

    if lag_months <= 0:
        status = "ok"
    elif lag_months >= 2:
        status = "critical"
    elif now.day <= 6:
        status = "warning"
    else:
        status = "stale"

    return {
        "status": status,
        "latest_month": latest_month,
        "expected_month": expected_month,
        "lag_months": lag_months,
        "manual_command": manual_command,
    }

def fpi_series(df):
    """
    Canonical published FPI series.

    Completed months come only from NSDL net investment, manually entered
    in Rs crore. RBI DBIE portfolio investment remains in the database for
    reference but is never substituted into this chart.
    """
    return {
        "col": "india_fpi_nsdl_lcr",
        "unit": "₹L Cr",
        "axis": "Net FPI Flows (₹ Lakh Crore)",
        "subtitle": (
            "Monthly net FPI investment in India (₹ lakh crore); "
        ),
        "source": "NSDL (FPI net investment, all segments)",
        "fmt": lambda v: (
            f"{'−' if v < 0 else ''}₹{abs(v):.2f}L Cr"
        ),
    }


def chart_fpi_flows(df, output_dir):
    """
    NSDL monthly FPI flows.

    Completed months use india_fpi_nsdl_lcr.
    An optional current-month MTD observation is shown as a grey bar and is
    excluded from the completed-month cumulative calculation.
    """
    series = fpi_series(df)
    col = series["col"]

    has_completed = (
        col in df.columns
        and df[col].notna().any()
    )

    has_mtd_columns = all(
        c in df.columns
        for c in ["india_fpi_mtd_lcr", "india_fpi_mtd_asof"]
    )

    has_any_mtd = (
        has_mtd_columns
        and df["india_fpi_mtd_lcr"].notna().any()
        and df["india_fpi_mtd_asof"].notna().any()
    )

    if not has_completed and not has_any_mtd:
        print("   ⚠ Skipping FPI Flows — no NSDL data found")
        return None

    # Last 24 completed NSDL months.
    if has_completed:
        df_completed = (
            df.dropna(subset=[col])
            .tail(24)
            .copy()
        )
    else:
        df_completed = pd.DataFrame()

    # Optional current-month MTD observation.
    mtd_row = None

    if has_any_mtd:
        mtd_candidates = df[
            df["india_fpi_mtd_lcr"].notna()
            & df["india_fpi_mtd_asof"].notna()
        ].copy()

        # Defensive check: stored MTD date must belong to the same month row.
        mtd_candidates = mtd_candidates[
            mtd_candidates["date"].dt.to_period("M")
            == mtd_candidates["india_fpi_mtd_asof"].dt.to_period("M")
        ]

        if not mtd_candidates.empty:
            candidate = mtd_candidates.iloc[-1]

            candidate_period = candidate["date"].to_period("M")

            # Once a final NSDL figure exists for this month, the grey MTD bar
            # automatically disappears.
            completed_same_month = (
                has_completed
                and (
                    (
                        df["date"].dt.to_period("M")
                        == candidate_period
                    )
                    & df[col].notna()
                ).any()
            )

            if not completed_same_month:
                mtd_row = candidate

    fig, ax = EconStyle.create_figure(size="wide")

    # Subtle horizontal grid.
    ax.yaxis.grid(
        True,
        linestyle="-",
        alpha=0.15,
        color="#9CA3AF",
        zorder=0,
    )
    ax.set_axisbelow(True)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    all_dates = []

    # Completed monthly bars.
    if not df_completed.empty:
        completed_dates = df_completed["date"].tolist()
        completed_vals = df_completed[col].values

        try:
            completed_colors = [
                C_FPI_POS if v >= 0 else C_FPI_NEG
                for v in completed_vals
            ]
        except NameError:
            completed_colors = [
                "#10B981" if v >= 0 else "#EF4444"
                for v in completed_vals
            ]

        ax.bar(
            completed_dates,
            completed_vals,
            width=20,
            color=completed_colors,
            alpha=0.9,
            edgecolor="none",
            zorder=3,
        )

        all_dates.extend(completed_dates)

    # Current month-to-date bar.
    if mtd_row is not None:
        mtd_date = mtd_row["date"]
        mtd_val = float(mtd_row["india_fpi_mtd_lcr"])
        mtd_asof = mtd_row["india_fpi_mtd_asof"]

        ax.bar(
            [mtd_date],
            [mtd_val],
            width=20,
            color="#9CA3AF",
            alpha=0.9,
            edgecolor="none",
            zorder=3,
        )

        all_dates.append(mtd_date)

        asof_text = mtd_asof.strftime("%d %b").lstrip("0")

        ax.annotate(
            "*",
            xy=(mtd_date, mtd_val),
            xytext=(0, 8 if mtd_val >= 0 else -8),
            textcoords="offset points",
            ha="center",
            va="bottom" if mtd_val >= 0 else "top",
            fontsize=14,
            fontweight="bold",
            color="#475569",
            zorder=5,
        )

    # Zero line.
    ax.axhline(
        y=0,
        color="#000000",
        linewidth=1.2,
        zorder=4,
    )

    if all_dates:
        _format_date_axis(ax, len(all_dates))

    ax.set_ylabel(
        series["axis"],
        fontsize=EconStyle.FONT_SIZE_AXIS,
    )

    # Cumulative badge includes COMPLETED observations only.
    if not df_completed.empty:
        cum_flow = df_completed[col].sum()
        n_completed = len(df_completed)

        bbox_props = dict(
            boxstyle="round,pad=0.4",
            fc="white",
            ec="#0F172A",
            lw=1.5,
        )

        ax.text(
            0.98,
            1.05,
            (
                f"{n_completed}M Cumulative: "
                f"{'+' if cum_flow >= 0 else ''}"
                f"{series['fmt'](cum_flow)}"
            ),
            transform=ax.transAxes,
            fontsize=10,
            fontweight="bold",
            color="#0F172A",
            ha="right",
            va="bottom",
            bbox=bbox_props,
        )

    EconStyle.set_title(
        ax,
        "Foreign Portfolio Flows",
        series["subtitle"],
    )
    EconStyle.add_top_rule(ax)

    fig.tight_layout(
        rect=[0.02, 0.04, 0.98, 0.96]
    )

    source_text = series["source"]

    if mtd_row is not None:
        mtd_asof = mtd_row["india_fpi_mtd_asof"]
        source_text += (
            f" · * Grey bar: MTD through "
            f"{mtd_asof.strftime('%d %b %Y').lstrip('0')}"
        )

    EconStyle.add_source(fig, source_text)

    fp = output_dir / "03_india_fpi_monthly.png"
    EconStyle.save_chart(fig, fp)

    print("   ✓ FPI Flows (Monthly, NSDL)")
    return fp


# ═══════════════════════════════════════════
# CHART 5: INDIA SUMMARY TABLE
# ═══════════════════════════════════════════

def chart_table(df, output_dir, cag_data=None, df_weekly=None):
    """
    India summary table — Bloomberg/FT style matching macro_table.py
    Includes CPI section, CAG fiscal data with asterisk, and External Sector
    when forex/trade data is available in india_macro.db.
    """
    EconStyle.apply_global_style()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None

    # Determine CAG availability
    has_cag = cag_data is not None

        # FPI is NSDL-only. Do not show a materially stale FPI value beside
    # newer indicators in the Economic Snapshot.
    fpi_info = fpi_freshness(df)

    credit_flow_items = [
        (
            "Bank Credit Growth",
            "india_bank_credit_yoy",
            "% YoY",
            lambda v: f"{v:.1f}%",
        ),
    ]

    if (
        fpi_info["status"] != "critical"
        and fpi_info["latest_month"] is not None
    ):
        fpi_cfg = fpi_series(df)

        credit_flow_items.append(
            (
                "Net FPI Flows",
                fpi_cfg["col"],
                fpi_cfg["unit"],
                fpi_cfg["fmt"],
            )
        )

    # ═══════════════════════════════════════════
    # DEFINE TABLE STRUCTURE
    # ═══════════════════════════════════════════
    TABLE_SECTIONS = [
        ("INFLATION", [
            ("CPI (Headline)", "india_cpi_yoy", "% YoY", lambda v: f"{v:.2f}%"),
            ("Core CPI", "india_core_cpi_yoy", "% YoY", lambda v: f"{v:.2f}%"),
            ("Food CPI", "india_food_cpi_yoy", "% YoY", lambda v: f"{v:.2f}%"),
        ]),
        ("PMI", [
            ("Manufacturing PMI", "india_mfg_pmi", "index", lambda v: f"{v:.1f}"),
            ("Services PMI", "india_svc_pmi", "index", lambda v: f"{v:.1f}"),
            ("Composite PMI", "india_composite_pmi", "index", lambda v: f"{v:.1f}"),
        ]),
        ("FISCAL *" if has_cag else "FISCAL", [
            ("GST Revenue", "india_gst_revenue", "₹L Cr", lambda v: f"₹{v:.2f}L Cr"),
        ]),
        ("CREDIT & FLOWS", [
            ("Bank Credit Growth", "india_bank_credit_yoy", "% YoY", lambda v: f"{v:.1f}%"),
            ("Net FPI Flows", fpi_series(df)["col"], fpi_series(df)["unit"], fpi_series(df)["fmt"]),
        ]),
        ("LABOUR", [
            ("Unemployment (PLFS)", "india_unemployment", "%", lambda v: f"{v:.1f}%"),
        ]),
        ("EXTERNAL SECTOR", [
            ("Exports", "india_exports_usd_bn", "$B", lambda v: f"${v:.1f}B"),
            ("Imports", "india_imports_usd_bn", "$B", lambda v: f"${v:.1f}B"),
            ("Trade Deficit", "india_trade_deficit_usd_bn", "$B", lambda v: f"${v:.1f}B"),
        ]),
    ]

    # Determine if we have any external sector data worth showing
    has_external = any(
        col in df.columns and df[col].notna().any()
        for col in ["india_exports_usd_bn", "india_imports_usd_bn", "india_trade_deficit_usd_bn"]
    )
    if not has_external:
        TABLE_SECTIONS = [s for s in TABLE_SECTIONS if s[0] != "EXTERNAL SECTOR"]
    
    # ═══════════════════════════════════════════
    # BUILD ROW DATA
    # ═══════════════════════════════════════════
    rows = []
    for section_name, items in TABLE_SECTIONS:
        for display_name, col, unit, fmt_fn in items:
            if col in df.columns:
                # Hunt backwards for the most recent non-empty data specifically for this indicator
                valid_data = df[df[col].notna()]
                
                if not valid_data.empty:
                    val = valid_data.iloc[-1][col]
                    
                    # Calculate MoM change safely using the last two valid rows
                    if len(valid_data) >= 2:
                        chg = val - valid_data.iloc[-2][col]
                    else:
                        chg = None
                    
                    rows.append({
                        "section": section_name,
                        "name": display_name,
                        "value": val,
                        "value_str": fmt_fn(val),
                        "change": chg,
                        "unit": unit,
                    })
    
    # Add weekly forex reserves if available (from india_weekly table)
    if df_weekly is not None and not df_weekly.empty and "forex_reserves_usd_bn" in df_weekly.columns:
        latest_fx = df_weekly.iloc[-1]
        fx_val = latest_fx.get("forex_reserves_usd_bn")
        fx_chg = latest_fx.get("forex_reserves_wow_chg")
        if pd.notna(fx_val):
            # Find or create EXTERNAL SECTOR section
            ext_section_name = "EXTERNAL SECTOR"
            # Insert forex at beginning of external sector rows
            ext_rows_start = len(rows)
            for i, r in enumerate(rows):
                if r["section"] == ext_section_name:
                    ext_rows_start = i
                    break
            rows.insert(ext_rows_start, {
                "section": ext_section_name,
                "name": "Forex Reserves",
                "value": fx_val,
                "value_str": f"${fx_val:.1f}B",
                "change": float(fx_chg) if pd.notna(fx_chg) else None,
                "unit": "WoW",
            })
            # Ensure section colors knows about EXTERNAL SECTOR
            if ext_section_name not in SECTION_COLORS:
                SECTION_COLORS[ext_section_name] = "#0F766E"

    # Add CAG fiscal data if available
    if has_cag:
        fiscal_section = "FISCAL *"
        
        # Find insert position (after GST Revenue)
        insert_idx = len(rows)
        for i, r in enumerate(rows):
            if r['name'] == 'GST Revenue':
                insert_idx = i + 1
                break
        
        cag_rows = [
            ("Capex", cag_data['capex_monthly'], 
             f"₹{cag_data['capex_monthly']:.2f}L Cr" if cag_data['capex_monthly'] else "-",
             cag_data['capex_mom'], "₹L Cr"),
            ("Capex (% of BE)", cag_data['capex_pct_be'],
             f"{cag_data['capex_pct_be']:.1f}%" if cag_data['capex_pct_be'] else "-",
             None, "YTD"),
            ("Fiscal Deficit (% of GDP)", cag_data['fiscal_deficit_pct_gdp'],
             f"{cag_data['fiscal_deficit_pct_gdp']:.1f}%" if cag_data['fiscal_deficit_pct_gdp'] else "-",
             None, "YTD"),
        ]
        
        for name, val, val_str, chg, unit in cag_rows:
            rows.insert(insert_idx, {
                "section": fiscal_section,
                "name": name,
                "value": val,
                "value_str": val_str,
                "change": chg,
                "unit": unit,
            })
            insert_idx += 1

    # ═══════════════════════════════════════════
    # CALCULATE FIGURE DIMENSIONS
    # ═══════════════════════════════════════════
    n = len(rows)
    sections_seen = []
    for r in rows:
        if r["section"] not in sections_seen:
            sections_seen.append(r["section"])

    row_h = 0.25
    cat_gap = 0.45
    header_block = 1.4
    content_h = (0.65 * len(sections_seen)) + (row_h * n)
    footer_space = 0.70 if has_cag else 0.55  # Reduced from 0.95
    fig_h = header_block + content_h + footer_space

    fig, ax = EconStyle.create_figure(size=(7.0, fig_h))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    # Column positions
    cx = {"name": 0.5, "latest": 5.5, "change": 7.5, "unit": 9.5}

    # ═══════════════════════════════════════════
    # TITLE BLOCK
    # ═══════════════════════════════════════════
    y = fig_h - 0.4
    # Standard name, parallel to the Weekly tab's "Market Snapshot" table.
    ax.text(0.5, y, "INDIA ECONOMIC SNAPSHOT", fontsize=20, fontweight="bold",
            color="#000000", fontfamily="sans-serif", ha="left")

    y -= 0.25
    month_str = latest["date"].strftime("%B %Y")
    ax.text(0.5, y, month_str, fontsize=10, color="#000000", ha="left")

    # ═══════════════════════════════════════════
    # COLUMN HEADERS
    # ═══════════════════════════════════════════
    y -= 0.5
    headers = [("name", "INDICATOR"), ("latest", "LATEST"), 
               ("change", "MoM CHG"), ("unit", "UNIT")]
    for key, label in headers:
        ha = "left" if key == "name" else "right"
        ax.text(cx[key], y, label, fontsize=9, fontweight="bold",
                color="#000000", ha=ha, fontfamily="sans-serif")

    y -= 0.15
    ax.plot([0.5, 9.5], [y, y], color="#000000", linewidth=1.2)

    # ═══════════════════════════════════════════
    # DATA ROWS
    # ═══════════════════════════════════════════
    cur_section = None

    def _draw_section_bar(ax, y, height):
        rect = plt.Rectangle(
            (0, y - height/2), 10, height,
            facecolor=SECTION_BG, edgecolor="none", zorder=0
        )
        ax.add_patch(rect)

    for i, row in enumerate(rows):
        # Section header
        if row["section"] != cur_section:
            cur_section = row["section"]
            y -= cat_gap
            _draw_section_bar(ax, y, 0.25)
            sec_key = cur_section.replace(" *", "")  # Remove asterisk for color lookup
            sec_color = SECTION_COLORS.get(sec_key, "#000000")
            ax.text(cx["name"], y, cur_section, fontsize=9, fontweight="bold",
                    color=sec_color, ha="left", va="center")
            y -= 0.20

        y -= row_h

        # Name
        ax.text(cx["name"], y, row["name"], fontsize=10, fontweight="medium",
                color="#000000", ha="left", va="center")

        # Latest value
        ax.text(cx["latest"], y, row["value_str"], fontsize=10,
                color="#334155", ha="right", va="center")

        # MoM Change
        if row["change"] is not None:
            chg = row["change"]
            
            # Determine color based on indicator type
            if "unemployment" in row["name"].lower():
                chg_color = "#065f46" if chg <= 0 else "#991b1b"
            elif "fpi" in row["name"].lower():
                chg_color = "#065f46" if chg >= 0 else "#991b1b"
            elif "deficit" in row["name"].lower():
                # Lower deficit is better
                chg_color = "#065f46" if chg <= 0 else "#991b1b"
            elif row["section"].replace(" *", "") == "INFLATION":
                chg_color = "#991b1b" if chg > 0 else "#065f46"
            else:
                chg_color = "#065f46" if chg >= 0 else "#991b1b"
            
            chg_str = f"{chg:+.2f}"
        else:
            chg_str = "-"
            chg_color = "#64748b"

        ax.text(cx["change"], y, chg_str, fontsize=10, fontweight="bold",
                color=chg_color, ha="right", va="center")

        # Unit
        ax.text(cx["unit"], y, row["unit"], fontsize=9,
                color="#64748b", ha="right", va="center")

        # Dotted separator
        ax.plot([0.5, 9.5], [y - row_h/2, y - row_h/2],
                color="#e2e8f0", linewidth=0.8, linestyle=":")

    # ═══════════════════════════════════════════
    # FOOTER (tighter spacing)
    # ═══════════════════════════════════════════
    footer_y = y - row_h/2 - 0.25  # Reduced from 0.40

    source_text = "Source: S&P Global, RBI DBIE, FRED, MoSPI, PIB, CAG"
    ax.text(0.5, footer_y, source_text,
            fontsize=8, color="#666666", ha="left", va="bottom")
    
    if has_cag:
        footer_y -= 0.15
        ax.text(0.5, footer_y, "* Latest fiscal data",
                fontsize=7, color="#666666", ha="left", va="bottom", style='italic')
    
    # The credit, in the table's own coordinates. A point and a half up on the
    # chart size, as the weekly summary table is: both are drawn larger than a
    # chart, and both would look undersized at the chart's own 7.5pt.
    EconStyle.draw_credit(fig, x=9.5, y=footer_y,
                          size=EconStyle.WATERMARK_SIZE + 1.5,
                          ax=ax, transform=ax.transData)

    # Set tight ylim to trim extra space
    ax.set_ylim(footer_y - 0.1, fig_h)

    fp = output_dir / "00_india_table.png"
    fig.savefig(fp, dpi=EconStyle.DPI, bbox_inches="tight",
                facecolor=EconStyle.BACKGROUND, pad_inches=0.08)
    plt.close(fig)
    print(f"   ✓ India Summary Table")
    return fp


# ═══════════════════════════════════════════
# CHART 6: INFLATION BAR CHART (YOUR VERSION)
# ═══════════════════════════════════════════

def chart_inflation_bar(df, output_dir):
    """Side-by-side bar chart for Headline vs Food Inflation (Aug '24 onwards)."""
    import os
    import json
    from data.fetchers.mospi_inflation import ROOT as CPI_MAIN_ROOT
    fp = output_dir / '06_india_inflation_bar.png'
    status_file = CPI_MAIN_ROOT / 'status.json'
    try:
        status = json.loads(status_file.read_text()) if status_file.exists() else {}
    except (ValueError, OSError) as exc:
        status = {'status':'failed'}
        print(f'   WARNING: Main CPI readiness could not be read — {exc}')
    manual_fallback = os.environ.get('CPI_MANUAL_FALLBACK') == 'true'
    if not manual_fallback and (os.environ.get('CPI_MAIN_UPDATE_FAILED') == 'true' or status.get('status') != 'ready'):
        fp.unlink(missing_ok=True)
        print('   WARNING: Main inflation chart omitted — official update failed or unresolved manual CPI conflict; use documented explicit manual fallback')
        return None
    if "india_cpi_yoy" not in df.columns or "india_food_cpi_yoy" not in df.columns:
        print("   ⚠ Skipping Inflation Bar — columns not found")
        return None

    # 1. FILTER DATA
    df_subset = df[(df["date"] >= "2024-08-01") &
                   (df['india_cpi_yoy'].notna() | df['india_food_cpi_yoy'].notna())].copy()
    if not manual_fallback:
        # Readiness cannot authorize DB changes made after the source check.
        # Every displayed value must still agree with the validated rate set.
        expected = {(r['month'],r['column']):r['value'] for r in status.get('changes',[])}
        for _, row in df_subset.iterrows():
            month = row['date'].strftime('%Y-%m')
            for column in ('india_cpi_yoy','india_food_cpi_yoy'):
                value = row[column]
                target = expected.get((month,column))
                if pd.isna(value) or target is None or abs(value-target) > .005000001:
                    fp.unlink(missing_ok=True)
                    print(f'   WARNING: Main inflation omitted — {month} {column} no longer matches validated official snapshot')
                    return None
    if manual_fallback:
        # Explicit emergency mode: display only re-entered, concept-labelled
        # manual pairs. Old CFPI values can never enter this Food series.
        import sqlite3
        with sqlite3.connect(DEFAULT_DB) as conn:
            entries = conn.execute('SELECT month,source_flags FROM india_monthly').fetchall()
        qualified = []
        for month, encoded_flags in entries:
            flags = json.loads(encoded_flags or '{}')
            if all(str(flags.get(c,'')).startswith('manual:') and
                   flags.get(c+':manual_concept') == concept for c,concept in
                   [('india_cpi_yoy','CPI (General)'),('india_food_cpi_yoy','Food and beverages')]):
                qualified.append(pd.Timestamp(month))
        df_subset = df_subset[df_subset['date'].isin(qualified)]
        print('   WARNING: Explicit manual CPI fallback; official automation is not ready')
    
    if len(df_subset) == 0:
        return None

    fig, ax = EconStyle.create_figure(size="wide")

    dates = df_subset["date"].tolist()
    headline = df_subset["india_cpi_yoy"].values
    food = df_subset["india_food_cpi_yoy"].values

    # 2. Bar Sizing
    bar_width = 12  
    dates_headline = [d - pd.Timedelta(days=bar_width/2) for d in dates]
    dates_food = [d + pd.Timedelta(days=bar_width/2) for d in dates]

    # 3. Colors
    c_headline = "#1E3A8A"  
    c_food = "#D97706"      

    # 4. RBI TOLERANCE BAND (2-6%)
    ax.axhspan(2, 6, color="#E5E7EB", alpha=0.6, zorder=0)

    # 5. Plotting Bars
    ax.bar(dates_headline, headline, width=bar_width, color=c_headline, 
           label="Headline CPI", edgecolor="none", zorder=3)
    
    ax.bar(dates_food, food, width=bar_width, color=c_food, 
           label="Food Inflation", edgecolor="none", zorder=3)

    # 6. Reference Lines
    ax.axhline(y=0, color="black", linewidth=1.0, zorder=2)
    ax.axhline(y=4, color="#666666", linewidth=0.8, linestyle=":", zorder=1)
    ax.axvline(pd.Timestamp('2026-01-01')-pd.Timedelta(days=16),color='#666666',linestyle='--',linewidth=.7)
    
    # 7. Formatting
    _format_date_axis(ax, len(dates))
    ax.set_ylabel("YoY % Change", fontsize=EconStyle.FONT_SIZE_AXIS)

    # 8. LEGEND (Now includes the RBI Band)
    handles, labels = ax.get_legend_handles_labels()
    patch_band = mpatches.Patch(color="#E5E7EB", label="RBI Band (2-6%)")
    handles.append(patch_band)
    
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=3, frameon=False, fontsize=9, handletextpad=0.4,
              borderaxespad=0, borderpad=0)

    EconStyle.set_title(ax, "India's Inflation Dynamics",
                        "Headline vs. Food inflation (% YoY)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    source = "Manual MoSPI emergency fallback" if manual_fallback else "MoSPI"
    fig.text(0.04, 0.02,
             f"Source: {source} · 2012-base through Dec 2025; 2024-base from Jan 2026 · Updated {max(dates):%b %Y}",
             fontproperties=EconStyle._get_font("regular"),
             fontsize=EconStyle.FONT_SIZE_SOURCE, color=EconStyle.TEXT_MUTED,
             ha="left", va="bottom")
    EconStyle.draw_credit(fig, x=0.96, y=0.02)

    fp = output_dir / "06_india_inflation_bar.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Inflation Bar Chart")
    return fp


# ═══════════════════════════════════════════
# (Chart 12 removed — RBI Repo Rate is covered in the RBI Sentinel section)
# ═══════════════════════════════════════════



# ═══════════════════════════════════════════
# CHART 14: CREDIT vs DEPOSIT GROWTH
# ═══════════════════════════════════════════

def chart_credit_deposit(df, output_dir):
    """
    Bank Credit vs Deposit Growth — Clean line chart with 'Jaws' liquidity gap fill.
    Legend moved inside the chart, safely ignores NaN values.
    """
    has_credit = "india_bank_credit_yoy" in df.columns and df["india_bank_credit_yoy"].notna().any()
    has_deposit = "india_deposit_growth_yoy" in df.columns and df["india_deposit_growth_yoy"].notna().any()

    if not has_credit:
        print("   ⚠ Skipping Credit/Deposit — no data")
        return None

    fig, ax = EconStyle.create_figure(size="wide")
    dates = df["date"].tolist()

    # Subtle horizontal grid only
    ax.yaxis.grid(True, linestyle="-", alpha=0.15, color="#9CA3AF", zorder=0)
    ax.set_axisbelow(True)
    
    # Clean up spines for a modern, open look
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    C_CREDIT_LINE = "#1E3A8A"  # Deep professional Navy
    C_DEPOSIT_LINE = "#D97706" # Bright Amber/Orange (highly distinct from Navy)

    if has_deposit:
        credit_vals  = df["india_bank_credit_yoy"].values
        deposit_vals = df["india_deposit_growth_yoy"].values

        # 1. Plot the Thick Trend Lines
        ax.plot(dates, credit_vals, color=C_CREDIT_LINE, linewidth=2.5, 
                label="Credit Growth YoY", zorder=4, solid_capstyle="round")
        ax.plot(dates, deposit_vals, color=C_DEPOSIT_LINE, linewidth=2.5, 
                linestyle="--", label="Deposit Growth YoY", zorder=4, solid_capstyle="round")

        # 2. Visual Liquidity Gap (The "Jaws" Shaded Regions)
        ax.fill_between(dates, credit_vals, deposit_vals, where=(credit_vals > deposit_vals), 
                        facecolor='#EF4444', alpha=0.15, interpolate=True, label="Liquidity Squeeze")
        
        ax.fill_between(dates, credit_vals, deposit_vals, where=(credit_vals <= deposit_vals), 
                        facecolor='#10B981', alpha=0.15, interpolate=True, label="Surplus Liquidity")
    else:
        credit_vals = df["india_bank_credit_yoy"].values
        ax.plot(dates, credit_vals, color=C_CREDIT_LINE, linewidth=2.5, label="Credit Growth YoY", zorder=4)

    # Bold Zero Line
    ax.axhline(y=0, color="#000000", linewidth=1.0, zorder=2)

    # Legend moved INSIDE the chart (upper left), arranged in a clean 2x2 grid
    ax.legend(loc="upper left", ncol=2, frameon=True, facecolor="white", 
              edgecolor="none", framealpha=0.85, fontsize=9, borderpad=0.6)
    
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    _format_date_axis(ax, len(dates))
    
    # Pad the top of the Y-axis slightly, using np.nanmax to safely ignore missing recent data
    if has_deposit:
        ax.set_ylim(top=max(np.nanmax(credit_vals), np.nanmax(deposit_vals)) * 1.15)
    else:
        ax.set_ylim(top=np.nanmax(credit_vals) * 1.15)
        
    ax.set_ylabel("YoY Growth (%)", fontsize=EconStyle.FONT_SIZE_AXIS)

    EconStyle.set_title(ax, "Systemic Liquidity: Bank Credit & Deposit Growth",
                        "Scheduled Commercial Banks — YoY Growth (%)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "RBI DBIE")

    fp = output_dir / "14_india_credit_deposit.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Bank Credit & Deposit Growth")
    return fp


# ═══════════════════════════════════════════
# CHART 17: INDUSTRIAL PRODUCTION (IIP)
# ═══════════════════════════════════════════

def chart_iip(df, output_dir):
    """Current-base General IIP published growth; offline, with opt-in fallback."""
    from data.fetchers.mospi_iip import load, BASE_YEAR
    import os
    import sqlite3
    fp = output_dir / '15_india_iip.png'
    manual = os.environ.get('IIP_MANUAL_FALLBACK') == 'true'
    try:
        if os.environ.get('IIP_UPDATE_FAILED') == 'true' and not manual:
            raise ValueError('official IIP update failed')
        rows = load(DEFAULT_DB, manual_fallback=manual)
        df_iip = pd.DataFrame({'date':pd.to_datetime([r['month'] for r in rows]),
                               'india_iip_yoy':[r['growth_rate'] for r in rows]})
        # Missing manual months remain gaps; a 3M average needs three consecutive months.
        df_iip = df_iip.set_index('date').reindex(pd.date_range(df_iip.date.min(),df_iip.date.max(),freq='MS')).rename_axis('date').reset_index()
    except (ValueError,OSError,KeyError,sqlite3.Error) as exc:
        fp.unlink(missing_ok=True)
        print(f'   ⚠ Skipping IIP — {exc}')
        return None

    from matplotlib.offsetbox import AnnotationBbox, HPacker, TextArea

    fig, ax = EconStyle.create_figure(size=(9.5, 4.9))
    dates = df_iip["date"].tolist()
    vals = df_iip["india_iip_yoy"].values
    positive, negative = "#A070E0", "#B96764"

    # Understated calendar band: visual context, without a causal claim.
    right_edge = dates[-1] + pd.Timedelta(days=35)
    cycle_start = pd.Timestamp("2025-04-01")
    if right_edge > cycle_start:
        ax.axvspan(cycle_start, right_edge, color="#F4F4F4", zorder=0)
        ax.text(cycle_start + pd.Timedelta(days=14), 0.96, "Recent cycle",
                transform=ax.get_xaxis_transform(), fontsize=8,
                color="#858585", va="top", zorder=2)

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linewidth=0.6, color="#E7E7E7", zorder=1)
    ax.xaxis.grid(False)

    # Slim monthly bars retain every observation and the full historical range.
    ax.bar(dates, vals, width=16,
           color=[positive if v >= 0 else negative for v in vals],
           edgecolor=EconStyle.BAR_EDGE_COLOR, linewidth=0.7, zorder=3)

    # Keep the existing consecutive-month calculation unchanged.
    ma3 = None
    if len(vals) >= 3:
        ma3 = pd.Series(vals).rolling(3).mean().values
        line, = ax.plot(dates, ma3, color=EconStyle.INK, linewidth=3.0,
                        zorder=5, antialiased=True,
                        solid_capstyle="round", solid_joinstyle="round")
        line.set_path_effects([
            pe.Stroke(linewidth=4.2, foreground="white"), pe.Normal(),
        ])

    latest_date = dates[-1]
    latest_val = float(vals[-1])
    latest_color = positive if latest_val >= 0 else negative
    latest_ma = ma3[-1] if ma3 is not None else np.nan
    endpoint_value = latest_ma if np.isfinite(latest_ma) else latest_val
    if np.isfinite(latest_ma):
        ax.scatter([latest_date], [latest_ma], s=43, color=EconStyle.INK,
                   edgecolor="white", linewidth=1.1, zorder=6)

    # One packed callout keeps the two readings together as values evolve.
    label_style = dict(fontproperties=EconStyle._get_font("bold"), fontsize=10)
    parts = [TextArea(f"{latest_val:.1f}%", textprops={
        **label_style, "color": latest_color})]
    if np.isfinite(latest_ma):
        parts.append(TextArea(f" · 3M avg {latest_ma:.1f}%", textprops={
            **label_style, "color": EconStyle.INK}))
    callout = AnnotationBbox(
        HPacker(children=parts, align="baseline", pad=0, sep=0),
        (mdates.date2num(latest_date), endpoint_value),
        xybox=(0, 24), boxcoords="offset points", box_alignment=(1, 0),
        frameon=True, pad=0.3, bboxprops=dict(facecolor="white", edgecolor="none"),
        arrowprops=dict(arrowstyle="-", color=EconStyle.INK_MUTED, linewidth=0.7),
        annotation_clip=False, zorder=7,
    )
    ax.add_artist(callout)

    # ── Zero-growth reference ─────────────────────────────────────────────
    ax.axhline(
        y=0,
        color="#000000",
        linewidth=0.9,
        zorder=2,
    )

    # ── Axes ──────────────────────────────────────────────────────────────
    _format_date_axis(ax, len(dates))

    ax.yaxis.set_major_formatter(
        mticker.FormatStrFormatter("%.1f%%")
    )

    ax.set_ylabel(
        "YoY Growth (%)",
        fontsize=EconStyle.FONT_SIZE_AXIS,
        fontweight="bold",
        color=EconStyle.INK,
    )

    # Cleaner frame
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)

    # One linear axis includes the entire historical spike with breathing room.
    low, high = min(0, np.nanmin(vals)), max(0, np.nanmax(vals))
    span = max(high - low, 1)
    ax.set_ylim(low - span * 0.07, high + span * 0.12)
    ax.set_xlim(dates[0] - pd.Timedelta(days=23), right_edge)

    # The subtitle and unified latest callout explain the series without a legend.

    # ── Title ─────────────────────────────────────────────────────────────
    EconStyle.set_title(
        ax,
        "India’s Industrial Momentum (IIP)",
        "General IIP · YoY growth · 3M average" + (" · EMERGENCY MANUAL" if manual else ""),
    )

    EconStyle.add_top_rule(ax)

    fig.tight_layout(
        rect=[0.02, 0.04, 0.98, 0.96]
    )

    EconStyle.add_source(
        fig,
        f"MoSPI / NSO · 2022–23 base · history from {dates[0]:%b %Y}; legacy series excluded"
    )

    fp = output_dir / "15_india_iip.png"
    EconStyle.save_chart(fig, fp)

    print("   ✓ IIP Industrial Production")
    return fp


# ═══════════════════════════════════════════
# CHART 18: MONETARY TRANSMISSION
# ═══════════════════════════════════════════

TRANSMISSION_SERIES = [
    # column, label, colour, line style
    ("repo_bps",             "Policy repo rate",  "#000000",  "-"),
    ("walr_fresh_bps",       "Fresh loans",       "#1E3A8A",  "-"),
    ("walr_outstanding_bps", "Existing loans",    "#0B8F82",  "-"),
    ("wadtdr_fresh_bps",     "Fresh deposits",    "#D97706",  "--"),
]


class TransmissionDataError(ValueError):
    """The transmission history is present but cannot be trusted."""


def load_transmission(path=TRANSMISSION_CSV):
    """
    The current rate cycle from data/rbi_transmission.csv, one row per edition.

    Each edition of RBI's State of the Economy restates the cycle to date, so
    reading the same row across editions gives the path of pass-through through
    the cycle — including the recent months when fresh deposit rates gave some
    of the cut back. Only the newest cycle is returned; earlier cycles stay in
    the file as history.

    Missing file: returns None, and the chart is skipped. A file that is there
    but malformed raises, because wrong basis points on a chart are worse than
    no chart.
    """
    if not path.exists():
        return None

    df = pd.read_csv(path)
    needed = {"month", "cycle_type", "cycle_start", "cycle_end"} | {c for c, _, _, _ in TRANSMISSION_SERIES}
    missing = needed - set(df.columns)
    if missing:
        raise TransmissionDataError(f"{path.name} is missing columns {sorted(missing)}")
    if df.empty:
        return None

    # Every figure in the file is checked, not only the ones about to be drawn:
    # a blank or a stray word anywhere means the file was hand-edited, and the
    # run stops rather than charting whatever survives.
    for column, label, _, _ in TRANSMISSION_SERIES:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        if df[column].isna().any():
            raise TransmissionDataError(
                f"{path.name}: {label} is blank or not a number in "
                f"{df.loc[df[column].isna(), 'month'].tolist()}"
            )

    # The newest cycle that has enough months to draw a path. When the RBI turns
    # from cutting to hiking, its table starts a new cycle with a single row, and
    # one point is not a chart: the completed cycle stays up, under its own dates,
    # until the new one has two months of bank rates behind it.
    starts = sorted(df["cycle_start"].unique(), reverse=True)
    drawable = [s for s in starts if (df["cycle_start"] == s).sum() >= 2]
    if not drawable:
        return None
    current_start = drawable[0]
    df = df[df["cycle_start"] == current_start].copy()
    # Two editions can restate the same data month (RBI revises the figures a
    # month later), so the newest edition's version of a month is the one kept.
    df = (df.sort_values(["cycle_end", "month"])
            .drop_duplicates(subset="cycle_end", keep="last"))

    # Every row must describe the same cycle, and RBI's own repo column must not
    # wander within it: both would mean rows from different tables were mixed.
    if df["cycle_type"].nunique() != 1:
        raise TransmissionDataError(f"{path.name}: cycle {current_start} holds more than one cycle type")

    df["date"] = pd.to_datetime(df["cycle_end"], format="%Y-%m")
    return df


def chart_rate_transmission(output_dir, path=TRANSMISSION_CSV):
    """
    How much of the policy rate move has reached bank lending and deposit rates.

    Drawn as the path through the cycle rather than one set of bars: the gap
    between the repo line and the others is the part of the move that has not
    reached borrowers and savers, and the way that gap widens or narrows month
    by month is the point of the chart.
    """
    df = load_transmission(path)
    if df is None or len(df) < 2:
        print("   ⚠ Skipping Monetary Transmission — no RBI transmission history "
              "(run: python generate_soe.py --history)")
        return None

    fig, ax = EconStyle.create_figure(size="wide")
    dates = df["date"].tolist()

    ax.yaxis.grid(True, linestyle="-", alpha=0.15, color="#9CA3AF", zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ends: list[tuple[float, str, str]] = []
    for column, label, color, style in TRANSMISSION_SERIES:
        values = df[column].values
        # The repo rate holds between MPC decisions, so it is drawn as steps;
        # bank rates are monthly averages and are drawn as lines.
        ax.plot(dates, values, color=color, linewidth=2.5, linestyle=style, zorder=4,
                solid_capstyle="round", label=label,
                drawstyle="steps-post" if column == "repo_bps" else "default")
        ends.append((float(values[-1]), label, color))

    ax.axhline(y=0, color="#000000", linewidth=1.0, zorder=2)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%d"))
    ax.set_ylabel("Cumulative change (basis points)", fontsize=EconStyle.FONT_SIZE_AXIS)

    # Ticks every second month: sixteen monthly labels ran into each other.
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=8)

    span = df[[c for c, _, _, _ in TRANSMISSION_SERIES]].values
    low, high = span.min() - 20, max(span.max(), 0) + 20
    ax.set_ylim(low, high)
    # The axis stops with the data: empty months to the right would read as a
    # gap in reporting rather than as room for the labels.
    ax.set_xlim(dates[0], dates[-1] + pd.Timedelta(days=42))

    # End labels, nudged apart when two series finish within a hair of each
    # other (fresh and existing loans ended one basis point apart in Jun 2026).
    gap = (high - low) * 0.075
    placed: list[float] = []
    for value, label, color in sorted(ends, reverse=True):
        y = value
        for taken in placed:
            if abs(y - taken) < gap:
                y = taken - gap
        placed.append(y)
        ax.annotate(
            f"{label}  {value:,.0f}",
            xy=(dates[-1], y), xytext=(10, 0), textcoords="offset points",
            va="center", fontsize=9, fontweight="bold", color=color,
            fontfamily=EconStyle.FONT_FAMILY, annotation_clip=False, zorder=10,
        )

    cycle = df["cycle_type"].iloc[0]
    start = pd.to_datetime(df["cycle_start"].iloc[0], format="%Y-%m")
    EconStyle.set_title(
        ax,
        "Monetary Transmission: How Far the Repo Cut Has Travelled"
        if cycle == "easing" else "Monetary Transmission: How Far the Repo Rise Has Travelled",
        f"Cumulative change since the start of the {cycle} cycle ({start:%b %Y}), "
        f"basis points — bank rates through {df['date'].iloc[-1]:%b %Y}",
    )
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "RBI Bulletin, State of the Economy (Table IV.3)")

    fp = output_dir / "18_india_rate_transmission.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Monetary Transmission ({len(df)} editions)")
    return fp


# ═══════════════════════════════════════════
# CHART 16: FOREX RESERVES
# ═══════════════════════════════════════════

def chart_forex_reserves(df_weekly, output_dir):
    """
    Forex Reserves: dual-panel — bounded area chart for level + bar chart for WoW change.
    """
    if df_weekly is None or df_weekly.empty:
        print("   ⚠ Skipping Forex Reserves — data pending DBIE configuration")
        return None
    if "forex_reserves_usd_bn" not in df_weekly.columns:
        return None
    if not df_weekly["forex_reserves_usd_bn"].notna().any():
        return None

    fig, (ax_level, ax_chg) = EconStyle.create_figure(
        size="wide", nrows=1, ncols=2
    )

    dates = df_weekly["week_ending"].tolist()
    levels = df_weekly["forex_reserves_usd_bn"].values

    # Clean up spines and add subtle grids for both panels
    for ax in [ax_level, ax_chg]:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.yaxis.grid(True, linestyle="-", alpha=0.15, color="#9CA3AF", zorder=0)
        ax.set_axisbelow(True)

    C_RESERVES = "#0369A1" # Deep Blue

    # ── LEFT PANEL: Reserves Level ──
    # Dynamically bound the Y-axis so the trend isn't squashed by 0
    min_level = min(levels)
    max_level = max(levels)
    y_bottom = min_level - 15  # Add a $15B visual cushion below the lowest point

    # Fill down to the new floor instead of 0
    ax_level.fill_between(dates, y_bottom, levels, color=C_RESERVES, alpha=0.12, zorder=3)
    ax_level.plot(dates, levels, color=C_RESERVES, linewidth=2.5, zorder=5, solid_capstyle="round")
    
    # Apply dynamic limits
    ax_level.set_ylim(bottom=y_bottom, top=max_level + 15)
    
    _add_end_label(ax_level, dates, levels, f"${levels[-1]:.0f}B", C_RESERVES, offset_y=5)
    ax_level.set_ylabel("USD Billion", fontsize=EconStyle.FONT_SIZE_AXIS)
    
    # Use our universal date formatter
    _format_date_axis(ax_level, len(dates))
    
    EconStyle.set_title(ax_level, "Forex Reserves Level", "USD Billion")
    EconStyle.add_top_rule(ax_level)

    # ── RIGHT PANEL: WoW Change ──
    if "forex_reserves_wow_chg" in df_weekly.columns:
        chg_vals = df_weekly["forex_reserves_wow_chg"].fillna(0).values
        C_POS = "#16A34A"
        C_NEG = "#DC2626"
        chg_colors = [C_POS if v >= 0 else C_NEG for v in chg_vals]
        
        ax_chg.bar(dates, chg_vals, color=chg_colors, width=4,
                   alpha=0.85, edgecolor="none", zorder=3)
        
        # Bold Zero Line
        ax_chg.axhline(y=0, color="#000000", linewidth=1.2, zorder=4)
        
        ax_chg.set_ylabel("WoW Change ($B)", fontsize=EconStyle.FONT_SIZE_AXIS)
        
        # Use our universal date formatter
        _format_date_axis(ax_chg, len(dates))
        
        EconStyle.set_title(ax_chg, "Weekly Change", "WoW Change (USD Billion)")
        EconStyle.add_top_rule(ax_chg)

    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "RBI DBIE")

    fp = output_dir / "16_india_forex_reserves.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Forex Reserves")
    return fp


# ═══════════════════════════════════════════
# CHART 17: TRADE BALANCE
# ═══════════════════════════════════════════

def chart_trade_balance(df, output_dir):
    """
    Monthly Exports and Imports as faded grouped bars; Trade Deficit as a bold, distinct line.
    """
    needed = ["india_exports_usd_bn", "india_imports_usd_bn"]
    has_data = all(
        col in df.columns and df[col].notna().any() for col in needed
    )
    if not has_data:
        print("   ⚠ Skipping Trade Balance — data pending DBIE configuration")
        return None

    df_trade = df.dropna(subset=needed).copy()
    if df_trade.empty:
        return None

    fig, ax = EconStyle.create_figure(size="wide")
    ax2 = ax.twinx()

    dates = df_trade["date"].tolist()
    exports = df_trade["india_exports_usd_bn"].values
    imports = df_trade["india_imports_usd_bn"].values
    deficit = imports - exports  # positive = deficit (imports > exports)

    bar_width = 10
    dates_exp = [d - pd.Timedelta(days=bar_width / 2) for d in dates]
    dates_imp = [d + pd.Timedelta(days=bar_width / 2) for d in dates]

    # Clean Spines
    ax.spines['top'].set_visible(False)
    ax2.spines['top'].set_visible(False)

    ax.yaxis.grid(True, linestyle="-", alpha=0.15, color="#9CA3AF", zorder=0)
    ax.set_axisbelow(True)

    # Colors
    C_EXPORTS = "#059669"      # Green
    C_IMPORTS = "#DC2626"      # Red
    C_DEFICIT_BOLD = "#0F172A" # Dark Slate/Navy — completely distinct from the Red bars

    # Fade the bars to push them into the background (alpha reduced to 0.45)
    ax.bar(dates_exp, exports, width=bar_width, color=C_EXPORTS,
           alpha=0.45, label="Exports", edgecolor="none", zorder=3)
    ax.bar(dates_imp, imports, width=bar_width, color=C_IMPORTS,
           alpha=0.45, label="Imports", edgecolor="none", zorder=3)

    # Bold, distinct deficit line (solid, thick, dark)
    ax2.plot(dates, deficit, color=C_DEFICIT_BOLD, linewidth=3.5,
             linestyle="-", zorder=6, label="Trade Deficit")
             
    # Custom end label for Trade Deficit to perfectly format the $ and B
    last_val = deficit[-1]
    ax2.annotate(
        f"Deficit\n${last_val:.1f}B",
        xy=(dates[-1], last_val),
        xytext=(8, 5), textcoords="offset points",
        fontsize=9, fontweight="bold", color=C_DEFICIT_BOLD,
        fontfamily=EconStyle.FONT_FAMILY,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85),
        zorder=10,
    )

    ax.set_ylabel("USD Billion", fontsize=EconStyle.FONT_SIZE_AXIS)
    ax2.set_ylabel("Trade Deficit ($B)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color=C_DEFICIT_BOLD)
    ax2.tick_params(axis="y", colors=C_DEFICIT_BOLD)

    # Combined legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2,
              loc="lower right", bbox_to_anchor=(1.1, 1.05),
              ncol=3, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)

    _format_date_axis(ax, len(dates))

    EconStyle.set_title(ax, "India Trade Balance",
                        "Monthly Merchandise Exports & Imports ($B)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "RBI DBIE / DGCI&S")

    fp = output_dir / "17_india_trade.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Trade Balance")
    return fp


# ═══════════════════════════════════════════
# CHART 7: EXPENDITURE QUALITY (FT-STYLE)
# ═══════════════════════════════════════════

def chart_expenditure_quality(cag_data, df_monthly, output_dir):
    """
    FT-style chart: Capex vs Revenue Expenditure quality ratio.
    Shows the composition of government spending over the fiscal year.
    """
    if cag_data is None or df_monthly is None:
        print("   ⚠ Skipping Expenditure Quality — no CAG data")
        return None
    
    fig, ax = EconStyle.create_figure(size="wide")
    
    # Get monthly data
    months = df_monthly['Month'].str.split('-').str[0].tolist()
    capex = (df_monthly['Capital Expenditure_monthly'] / CRORE_PER_LAKH_CRORE).values  # ₹ Lakh Cr
    rev_exp = (df_monthly['Revenue Expenditure'].diff().fillna(df_monthly['Revenue Expenditure'].iloc[0]) / CRORE_PER_LAKH_CRORE).values
    
    x = np.arange(len(months))
    width = 0.35
    
    # Remove default spines grid, add custom subtle grid
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(True)
    
    # Draw gridlines manually at specific y positions (behind everything)
    y_max = max(max(capex[~np.isnan(capex)]), max(rev_exp[~np.isnan(rev_exp)])) * 1.1
    for y_val in np.arange(0, y_max, 500):
        ax.axhline(y=y_val, color='#E5E7EB', linewidth=0.5, zorder=0)
    
    # Bars with higher zorder
    bars1 = ax.bar(x - width/2, capex, width, label='Capital Expenditure', 
                   color=C_CAPEX, alpha=0.9, edgecolor='white', linewidth=0.5, zorder=5)
    bars2 = ax.bar(x + width/2, rev_exp, width, label='Revenue Expenditure',
                   color=C_REVENUE_EXP, alpha=0.9, edgecolor='white', linewidth=0.5, zorder=5)
    
    # Capex ratio line (secondary insight)
    valid_idx = ~np.isnan(capex) & ~np.isnan(rev_exp) & (rev_exp > 0)
    ratio = np.where(valid_idx, capex / (capex + rev_exp) * 100, np.nan)

    ax2 = ax.twinx()
    ax2.plot(x[valid_idx], ratio[valid_idx], color='#000000', linewidth=2,
            marker='o', markersize=4, label='Capex share (right axis)', zorder=10)
    ax2.set_ylabel('Capex as % of Total Expenditure', fontsize=9, color='#333333')
    # Headroom on both axes keeps a clear band at the top for the legend
    ax2.set_ylim(0, max(50, np.nanmax(ratio) * 1.4) if valid_idx.any() else 50)
    ax2.tick_params(axis='y', colors='#333333')

    # Value labels on the capex bars, drawn on the top axes with a white backing
    # so the share line passes behind them rather than through them.
    _lbl_off = np.nanmax(np.concatenate([capex, rev_exp])) * 0.02
    for i, c in enumerate(capex):
        if not np.isnan(c) and c > 0:
            ax2.text(x[i] - width/2, c + _lbl_off, f'₹{c:.2f}L', transform=ax.transData,
                     ha='center', va='bottom', fontsize=7, color=C_CAPEX, fontweight='bold', zorder=12,
                     bbox=dict(boxstyle='round,pad=0.12', facecolor='white', edgecolor='none'))

    ax.set_xticks(x)
    ax.set_xticklabels(months, fontsize=9)
    ax.set_ylabel('₹ Lakh Crore', fontsize=EconStyle.FONT_SIZE_AXIS)
    ax.set_ylim(0, np.nanmax(np.concatenate([capex, rev_exp])) * 1.3)

    # Legend in the clear top band, on the top axes so the share line cannot cover
    # it: left-axis items first, then right-axis items
    handles, _ = ax.get_legend_handles_labels()
    handles2, _ = ax2.get_legend_handles_labels()
    ax2.legend(handles=handles + handles2, loc='upper left', ncol=3, frameon=False, fontsize=8.5,
               handletextpad=0.4, columnspacing=1.2, borderaxespad=0.4).set_zorder(20)

    if cag_data.get('capex_pct_be') is not None:
        ax.text(0.98, 1.05, f"Capex to {cag_data['latest_month']}: {cag_data['capex_pct_be']:.1f}% of Budget",
                transform=ax.transAxes, fontsize=10, fontweight='bold', color="#0F172A", ha="right",
                va="bottom", bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#0F172A", lw=1.5))
    subtitle = f"Capital vs Revenue Expenditure — FY{cag_data['fy'][-2:]}"
    EconStyle.set_title(ax, "Expenditure Quality", subtitle)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, f"CAG Monthly Accounts | Data through {cag_data['latest_month']}")
    
    fp = output_dir / "07_india_expenditure_quality.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Expenditure Quality Chart")
    return fp


# ═══════════════════════════════════════════
# CHART 9: DEFICIT FINANCING
# ═══════════════════════════════════════════

# (legend label, colour, fin_* columns added together). Securities against small
# savings (b) and the NSSF line (e) both record borrowing from small savings;
# amounts can shift between the two within the year while their sum stays smooth.
FINANCING_GROUPS = (
    ("Market borrowings", EconStyle.CATEGORICAL_COLORS[0], ("fin_market_borrowings",)),
    ("Small savings", EconStyle.CATEGORICAL_COLORS[1], ("fin_small_savings_securities", "fin_nssf")),
    ("Other domestic", EconStyle.CATEGORICAL_COLORS[10], ("fin_state_provident_funds", "fin_special_deposits", "fin_others")),
    ("Cash drawn down (+) / built up (−)", EconStyle.CATEGORICAL_COLORS[4], ("fin_cash_balance", "fin_surplus_cash", "fin_wma")),
    ("External", EconStyle.CATEGORICAL_COLORS[7], ("fin_external",)),
)


def chart_deficit_financing(output_dir, manual_path=CAG_MANUAL):
    """
    How the central government's fiscal deficit is financed: the year-to-date
    sources at each month of the latest financial year with financing rows,
    beside the full-year Budget Estimate.
    """
    fin = load_cag_financing(manual_path)
    if fin.empty:
        print("   ⚠ Skipping Deficit Financing — no financing rows in data/cag_manual_accounts.csv")
        return None

    fy = fin["FY"].max()
    rows = fin[fin["FY"] == fy]
    months = rows[~rows["Month"].isin(["BE", "RE"])]
    if months.empty:
        print(f"   ⚠ Skipping Deficit Financing — {fy} has no monthly financing rows")
        return None
    months = months.iloc[sorted(range(len(months)), key=lambda i: _fiscal_sort_key(fy, months["Month"].iloc[i]))]
    budget = rows[rows["Month"] == "BE"]
    table = pd.concat([months, budget], ignore_index=True)
    has_budget = not budget.empty

    # A blank row (h) or (i) counts as zero: the load checks proved the other
    # rows already add up to the domestic total.
    parts = {label: table[list(cols)].fillna(0).sum(axis=1).to_numpy() / CRORE_PER_LAKH_CRORE
             for label, _, cols in FINANCING_GROUPS}
    deficit = (table["fin_external"] + table["fin_domestic"]).to_numpy() / CRORE_PER_LAKH_CRORE

    crowded = len(table) > 7                          # later in the year: narrower slots
    x = np.arange(len(table), dtype=float)
    if has_budget:
        x[-1] += 0.9 if crowded else 0.5              # set the full-year bar apart
    width = 0.6

    fig, ax = EconStyle.create_figure(size="wide")
    ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)

    # Sources that finance the deficit stack up from zero; sources that absorb
    # money (a cash build-up, net repayments) stack down from it.
    up, down = np.zeros(len(table)), np.zeros(len(table))
    for label, colour, _ in FINANCING_GROUPS:
        v = parts[label]
        ax.bar(x, v, width, bottom=np.where(v >= 0, up, down), color=colour, label=label,
               edgecolor=EconStyle.BAR_EDGE_COLOR, linewidth=EconStyle.BAR_EDGE_WIDTH, zorder=3)
        up += np.clip(v, 0, None)
        down += np.clip(v, None, 0)
    ax.axhline(0, color='#000000', linewidth=1.0, zorder=4)

    ax.scatter(x, deficit, marker='D', s=40, color='#000000', edgecolor='white', linewidth=0.8,
               zorder=6, label='Fiscal deficit (net of all sources)')
    # Value labels sit beside each marker; once the year has more bars than fit,
    # only the latest month and the Budget keep theirs.
    labelled = range(len(x) - (2 if has_budget else 1), len(x)) if crowded else range(len(x))
    for i in labelled:
        ax.text(x[i] + width / 2 + 0.05, deficit[i], f"₹{deficit[i]:.2f}L", ha='left', va='center',
                fontsize=8, fontweight='bold', color='#000000', zorder=7)

    labels = [m.split('-')[0] for m in months['Month']]
    if has_budget:
        labels.append('Budget\n(full year)')
        ax.axvline((x[-2] + x[-1]) / 2, color='#9CA3AF', linewidth=0.8, linestyle=':', zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_xlim(x[0] - 0.6, x[-1] + (1.4 if crowded else 0.95))   # room for the last value label
    ax.set_ylim(min(down.min(), 0) * 1.3, up.max() * 1.15)
    ax.set_ylabel('₹ Lakh Crore', fontsize=EconStyle.FONT_SIZE_AXIS)

    handles, names = ax.get_legend_handles_labels()
    order = sorted(range(len(names)), key=lambda i: names[i].startswith('Fiscal deficit'))  # marker last
    ax.legend([handles[i] for i in order], [names[i] for i in order], loc='upper left', ncol=2,
              frameon=False, fontsize=8, handletextpad=0.4, columnspacing=1.2, borderaxespad=0.3)

    if has_budget:
        share = deficit[-2] / deficit[-1] * 100
        ax.text(0.98, 1.05, f"Deficit to {months['Month'].iloc[-1]}: {share:.1f}% of Budget",
                transform=ax.transAxes, fontsize=10, fontweight='bold', color="#0F172A", ha="right",
                va="bottom", bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#0F172A", lw=1.5))

    EconStyle.set_title(ax, "Deficit Financing",
                        f"How the FY{fy[-2:]} fiscal deficit is financed, year to date and in the Budget")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, f"CGA Monthly Accounts (sources of financing) | Data through {months['Month'].iloc[-1]}")

    fp = output_dir / "09_india_deficit_financing.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Deficit Financing")
    return fp


# ═══════════════════════════════════════════
# CHART 11: FISCAL DEFICIT % OF GDP (HISTORICAL)
# ═══════════════════════════════════════════

def chart_fiscal_deficit_gdp(cag_path, output_dir):
    """
    Historical fiscal deficit as % of GDP.
    FT-style bar chart with consolidation targets.
    """
    try:
        df_actual, df_bere, df_gdp = load_cag_tables(cag_path)
    except CagManualError:
        raise
    except Exception as e:
        print(f"   ⚠ Skipping Fiscal Deficit % GDP — {e}")
        return None
    
    # Build historical data
    historical = []
    current_fy = None
    current_fy_ytd_pct = None
    current_fy_month = None
    
    for fy in sorted(df_actual['FY'].unique()):
        fy_data = df_actual[df_actual['FY'] == fy]
        
        # Get March (full year) or last available
        march_data = fy_data[fy_data['Month'].str.startswith('Mar')]
        if len(march_data) > 0:
            row = march_data.iloc[-1]
            is_full_year = True
        else:
            row = fy_data.iloc[-1]
            is_full_year = False
            current_fy = fy
            current_fy_month = row['Month']
        
        fiscal_deficit = row['Fiscal Deficit']
        gdp_row = df_gdp[df_gdp['FY'] == fy]
        gdp = gdp_row['GDP'].values[0] if len(gdp_row) > 0 else None
        
        if gdp:
            deficit_pct = fiscal_deficit / gdp * 100
            historical.append({
                'FY': fy,
                'deficit_pct': deficit_pct,
                'is_full_year': is_full_year
            })
            if not is_full_year:
                current_fy_ytd_pct = deficit_pct
    
    # Filter to last 10 years
    historical = historical[-10:]
    
    fig, ax = EconStyle.create_figure(size="wide")
    
    # Subtle gridlines
    ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
    ax.set_axisbelow(True)
    
    # Format FY labels: "2016-17" -> "FY17"
    fys = ['FY' + h['FY'][-2:] for h in historical]
    values = [h['deficit_pct'] for h in historical]
    is_full = [h['is_full_year'] for h in historical]
    
    x = np.arange(len(fys))
    
    # Color: full year = solid, YTD = lighter
    colors = [C_FISCAL_DEF if f else '#FCA5A5' for f in is_full]
    
    bars = ax.bar(x, values, color=colors, alpha=0.85, edgecolor='white', 
                 linewidth=0.5, width=0.7, zorder=3)
    
    # Add value labels
    for i, (bar, val, full) in enumerate(zip(bars, values, is_full)):
        label = f"{val:.1f}%"
        if not full:
            label += "*"
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.15,
               label, ha='center', va='bottom', fontsize=9, 
               fontweight='bold', color='#1F2937' if full else '#991B1B', zorder=5)
    
    # Target lines. The latest year's budget target comes from its BE fiscal
    # deficit when one is recorded; otherwise the FY26 glide-path goal (below
    # 4.5% of GDP) is drawn only while FY26 is the latest year.
    latest_fy = df_actual['FY'].iloc[-1]
    be = df_bere[(df_bere['FY'] == latest_fy) & (df_bere['Month'] == 'BE')]
    gdp_latest = df_gdp.loc[df_gdp['FY'] == latest_fy, 'GDP']
    be_deficit = be['Fiscal Deficit'].iloc[0] if 'Fiscal Deficit' in be.columns and len(be) else None
    if be_deficit is not None and pd.notna(be_deficit) and len(gdp_latest):
        target = be_deficit / gdp_latest.iloc[0] * 100
        ax.axhline(y=target, color='#059669', linewidth=1.5, linestyle='--',
                   alpha=0.8, zorder=2, label=f"FY{latest_fy[-2:]} Budget: {target:.1f}%")
    elif latest_fy == '2025-26':
        ax.axhline(y=4.5, color='#059669', linewidth=1.5, linestyle='--',
                   alpha=0.8, zorder=2, label='FY26 Target: 4.5%')
    ax.axhline(y=3.0, color='#0369A1', linewidth=1.5, linestyle=':', 
              alpha=0.6, zorder=2, label='FRBM Target: 3.0%')
    
    # COVID annotation
    covid_idx = [i for i, h in enumerate(historical) if '2020-21' in h['FY']]
    if covid_idx:
        ax.annotate('COVID', xy=(covid_idx[0], historical[covid_idx[0]]['deficit_pct']),
                   xytext=(covid_idx[0], historical[covid_idx[0]]['deficit_pct'] + 1),
                   fontsize=8, color='#666666', ha='center',
                   arrowprops=dict(arrowstyle='->', color='#666666', lw=0.8))
    
    ax.set_xticks(x)
    ax.set_xticklabels(fys, fontsize=9, rotation=45, ha='right')
    ax.set_ylabel('% of GDP', fontsize=EconStyle.FONT_SIZE_AXIS)
    ax.set_ylim(0, max(values) * 1.2)
    
    # Legend at top-right (only target lines)
    ax.legend(loc='lower right', bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=8, handletextpad=0.4, borderaxespad=0)
    
    EconStyle.set_title(ax, "India's Fiscal Deficit",
                        "Central Government Fiscal Deficit as % of GDP")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.96])
    
    # Source and footnote (properly spaced)
    fig.text(0.02, 0.025, "Source: CAG Monthly Accounts",
            fontsize=8, color='#666666')
    if current_fy_month:                      # the latest year is still in progress
        fig.text(0.02, 0.005, f"* FY{current_fy[-2:]} shows Apr–{current_fy_month.split('-')[0]} YTD only",
                 fontsize=7, color='#666666', style='italic')
    # This chart writes its own footer rather than calling add_source, so it
    # has to ask for the credit itself.
    EconStyle.draw_credit(fig, x=0.98, y=0.015)
    
    fp = output_dir / "11_india_fiscal_deficit_gdp.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Fiscal Deficit % of GDP")
    return fp


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generate Economics Hub India Macro Dashboard"
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                        help="Path to india_manual.csv (fallback if DB unavailable)")
    parser.add_argument("--cag", type=Path, default=DEFAULT_CAG,
                        help="Path to CAG Monthly Accounts Excel file")
    parser.add_argument("--months", type=int, default=None,
                        help="Limit to last N months (default: all)")
    parser.add_argument("--mode", choices=["dashboard", "full"], default="dashboard",
                        help="dashboard: skip CAG if missing; full: require CAG")
    args = parser.parse_args()

    now = datetime.now()
    output_dir = OUTPUT_BASE / now.strftime("%Y-%m")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating Economics Hub — India Macro Dashboard")
    print(f"   Output: {output_dir}")

    # ── Load data ──────────────────────────────────────────────────────────────
    df = load_india_data(args.csv, args.months)
    df_weekly = load_forex_weekly()
    try:
        cag_data, df_monthly, df_prev_monthly = load_cag_data(args.cag)
    except CagManualError as e:
        sys.exit(f"❌ {e}")

    # ── Activity & PMI charts ──────────────────────────────────────────────────
    print(f"\n   Generating charts...")
    chart_pmi(df, output_dir)
    chart_investment_rate(output_dir)
    chart_gva_contributions(output_dir)
    chart_risk_appetite(output_dir)
    chart_sector_valuations(output_dir)
    chart_sector_rotation_12m(output_dir)
    chart_gst(df, output_dir)
    chart_fpi_flows(df, output_dir)
    chart_inflation_bar(df, output_dir)
    from charts.india_cpi_contributions import generate as chart_cpi_contributions
    chart_cpi_contributions(output_dir)

    # ── Summary table (integrates CAG fiscal + weekly forex) ───────────────────
    chart_table(df, output_dir, cag_data, df_weekly)

    # ── Monetary Conditions charts ─────────────────────────────────────────────
    chart_credit_deposit(df, output_dir)
    chart_rate_transmission(output_dir)

    # ── Economic Activity — IIP (new) ──────────────────────────────────────────
    chart_iip(df, output_dir)

    # ── External Sector charts (new) ──────────────────────────────────────────
    chart_forex_reserves(df_weekly, output_dir)
    chart_trade_balance(df, output_dir)

    # ── Fiscal charts (from CAG) — FROZEN, no changes ─────────────────────────
    if cag_data:
        # Tax composition and monthly capex were retired in Sep 2026: CGA no longer
        # publishes tax by head, and monthly capex repeated the other charts. The
        # consolidation tracker gave way to deficit financing: capex against its
        # Budget moved into Expenditure Quality, and the deficit target is on chart 11.
        chart_expenditure_quality(cag_data, df_monthly, output_dir)
        chart_deficit_financing(output_dir)
        chart_fiscal_deficit_gdp(args.cag, output_dir)

    chart_count = len(list(output_dir.glob("*.png")))
    print(f"\n India Dashboard complete! {chart_count} charts saved to:")
    print(f"   {output_dir}")

    if cag_data:
        print(f"\n Fiscal Summary ({cag_data['fy']} through {cag_data['latest_month']}):")
        print(f"   Capex YTD: {cag_data['capex_ytd']:.2f} Lakh Cr ({cag_data['capex_pct_be']:.1f}% of BE)")
        print(f"   Fiscal Deficit YTD: {cag_data['fiscal_deficit_ytd']:.2f} Lakh Cr")


if __name__ == "__main__":
    main()
