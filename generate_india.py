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
  - IIP:                         RBI DBIE
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

# ── Project imports ──
sys.path.insert(0, str(Path(__file__).parent))
from charts.style import EconStyle


# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════

DEFAULT_CSV   = Path(__file__).parent / "data" / "india_manual.csv"
DEFAULT_CAG   = Path(__file__).parent / "data" / "cag_monthly_accounts.xlsx"
DEFAULT_DB    = Path(__file__).parent / "data" / "india_macro.db"
OUTPUT_BASE   = Path(__file__).parent / "output" / "india"

# Colors
C_MFG_PMI       = "#003366"     # Navy — manufacturing
C_SVC_PMI       = "#CC0066"     # Magenta — services
C_COMPOSITE     = "#FF9933"     # Saffron — composite/India
C_GST           = "#2ca02c"     # Green — revenue
C_CREDIT        = "#003366"     # Navy — credit
C_UNEMPLOYMENT  = "#CC0000"     # Red — unemployment
C_FPI_POS       = "#065F46"     # Dark green — inflows
C_FPI_NEG       = "#991B1B"     # Dark red — outflows
C_PMI_50        = "#999999"     # Grey — expansion/contraction line

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
C_M3           = "#8B5CF6"    # Violet — money supply
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
                df = df.drop(columns=["month", "source_flags", "fetched_at"], errors="ignore")
                if "india_fpi_net_inr_cr" in df.columns:          # NSDL, Rs crore -> Rs lakh crore
                    df["india_fpi_nsdl_lcr"] = df["india_fpi_net_inr_cr"] / CRORE_PER_LAKH_CRORE
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
    """Manufacturing + Services PMI with expansion/contraction zones.
    Includes custom horizontal X-axis logic that forces the latest date to appear,
    optimized for higher label density.
    """
    fig, ax = EconStyle.create_figure(size="wide")

    dates = df["date"].tolist()

    # Manufacturing PMI
    if "india_mfg_pmi" in df.columns:
        vals = df["india_mfg_pmi"].values
        ax.plot(dates, vals, color=C_MFG_PMI, linewidth=2.5,
                label="Manufacturing", zorder=5, solid_capstyle="round")
        # Shadow for depth
        ax.plot(dates, vals, color=C_MFG_PMI, linewidth=3.7,
                alpha=0.07, zorder=4, solid_capstyle="round")
        _add_end_label(ax, dates, vals, "Mfg", C_MFG_PMI)

    # Services PMI
    if "india_svc_pmi" in df.columns:
        vals = df["india_svc_pmi"].values
        ax.plot(dates, vals, color=C_SVC_PMI, linewidth=2.2,
                label="Services", zorder=5, solid_capstyle="round")
        # Shadow for depth
        ax.plot(dates, vals, color=C_SVC_PMI, linewidth=3.4,
                alpha=0.07, zorder=4, solid_capstyle="round")
        _add_end_label(ax, dates, vals, "Svc", C_SVC_PMI, offset_y=-14)

    # Expansion/contraction line at 50
    ax.axhline(y=50, color=C_PMI_50, linewidth=1.2, linestyle="--", zorder=1)

    # Light fill: green above 50, red below 50 for manufacturing
    if "india_mfg_pmi" in df.columns:
        mfg = df["india_mfg_pmi"].values
        ax.fill_between(dates, 50, mfg, where=(mfg >= 50),
                        color=C_FPI_POS, alpha=0.04, interpolate=True)
        ax.fill_between(dates, 50, mfg, where=(mfg < 50),
                        color=C_FPI_NEG, alpha=0.04, interpolate=True)

    # ── CUSTOM X-AXIS OVERRIDE (DENSE HORIZONTAL) ──
    # 1. More aggressive interval: Every 1 month if < 18 months, 2 months if < 36, etc.
    interval = 1 if len(dates) <= 18 else (2 if len(dates) <= 36 else (4 if len(dates) <= 72 else 6))
    locator = mdates.MonthLocator(interval=interval)
    
    # 2. Get the mathematical ticks Matplotlib *wants* to use
    locs = locator.tick_values(dates[0], dates[-1])
    last_date_num = mdates.date2num(dates[-1])
    
    # 3. Shorter exclusion zone: Keep ticks at least ~40 days away from the last date
    new_locs = [loc for loc in locs if (last_date_num - loc) > 40 and loc >= mdates.date2num(dates[0])]
    
    # 4. Strictly append the absolute latest date
    new_locs.append(last_date_num) 
    
    # 5. Apply the custom ticks with perfectly horizontal formatting
    ax.xaxis.set_ticks(new_locs)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=8)

    ax.set_ylabel("PMI Index", fontsize=EconStyle.FONT_SIZE_AXIS)
    
    # Legend at top-right, inline with subtitle
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)

    EconStyle.set_title(ax, "India PMI Dashboard",
                        "S&P Global Manufacturing & Services PMI")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "S&P Global (IHS Markit)")

    fp = output_dir / "01_india_pmi.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ PMI Dashboard")
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

def fpi_series(df):
    """
    The FPI series to publish, never a mix of the two:
      NSDL net investment (Rs lakh crore), entered monthly with
        python -m data.india_manual_entry set YYYY-MM --fpi <Rs crore>
      otherwise RBI's net portfolio investment (US$ bn) from the DBIE workbook.
    """
    if "india_fpi_nsdl_lcr" in df.columns and df["india_fpi_nsdl_lcr"].notna().any():
        return {
            "col": "india_fpi_nsdl_lcr", "unit": "₹L Cr", "axis": "Net FPI Flows (₹ Lakh Crore)",
            "subtitle": "Monthly net FPI investment in India (₹ lakh crore) — last 24 months",
            "source": "NSDL (FPI net investment, all segments)",
            "fmt": lambda v: f"{'−' if v < 0 else ''}₹{abs(v):.2f}L Cr",
        }
    return {
        "col": "india_fpi_flows", "unit": "$B", "axis": "Net FPI Flows ($B)",
        "subtitle": "Monthly net portfolio investment into India ($B) — last 24 months",
        "source": "RBI DBIE (Net Portfolio Investment)",
        "fmt": lambda v: f"{'−' if v < 0 else ''}${abs(v):.1f}B",
    }


def chart_fpi_flows(df, output_dir):
    """
    Monthly net FPI flows, last 24 months: NSDL figures when entered, otherwise
    RBI's net portfolio investment (see fpi_series).
    """
    series = fpi_series(df)
    col = series["col"]
    if col not in df.columns or not df[col].notna().any():
        print("   ⚠ Skipping FPI Flows — no monthly data found")
        return None

    # Drop empty rows and get the last 24 months
    df_fpi = df.dropna(subset=[col]).tail(24).copy()
    
    if df_fpi.empty:
        return None

    fig, ax = EconStyle.create_figure(size="wide")
    
    dates = df_fpi["date"].tolist()
    vals = df_fpi[col].values

    # Subtle horizontal grid
    ax.yaxis.grid(True, linestyle="-", alpha=0.15, color="#9CA3AF", zorder=0)
    ax.set_axisbelow(True)

    # Clean Spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Colors: Green for Inflows, Red for Outflows
    try:
        colors = [C_FPI_POS if v >= 0 else C_FPI_NEG for v in vals]
    except NameError:
        colors = ["#10B981" if v >= 0 else "#EF4444" for v in vals]

    # Draw the bars (width=20 days looks perfectly spaced for monthly data)
    ax.bar(dates, vals, width=20, color=colors, alpha=0.9, edgecolor="none", zorder=3)

    # Bold Zero Line
    ax.axhline(y=0, color="#000000", linewidth=1.2, zorder=4)

    # Labels & Formatting
    _format_date_axis(ax, len(dates))
    ax.set_ylabel(series["axis"], fontsize=EconStyle.FONT_SIZE_AXIS)

    # Calculate Cumulative 24M for the floating badge
    cum_flow = df_fpi[col].sum()
    
    # Custom floating badge in the top right
    bbox_props = dict(boxstyle="round,pad=0.4", fc="white", ec="#0F172A", lw=1.5)
    ax.text(0.98, 1.05, f"24M Cumulative: {'+' if cum_flow >= 0 else ''}{series['fmt'](cum_flow)}", 
            transform=ax.transAxes, fontsize=10, fontweight='bold', 
            color="#0F172A", ha="right", va="bottom", bbox=bbox_props)

    EconStyle.set_title(ax, "Foreign Portfolio Flows", series["subtitle"])
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, series["source"])

    fp = output_dir / "03_india_fpi_monthly.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ FPI Flows (Monthly)")
    return fp


# ═══════════════════════════════════════════
# CHART 5: INDIA MACRO PULSE TABLE
# ═══════════════════════════════════════════

def chart_table(df, output_dir, cag_data=None, df_weekly=None):
    """
    India Macro Pulse Table — Bloomberg/FT style matching macro_table.py
    Includes CPI section, CAG fiscal data with asterisk, and External Sector
    when forex/trade data is available in india_macro.db.
    """
    EconStyle.apply_global_style()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None

    # Determine CAG availability
    has_cag = cag_data is not None

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
    ax.text(0.5, y, "INDIA MACRO PULSE", fontsize=20, fontweight="bold",
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
    
    ax.text(9.5, footer_y, EconStyle.WATERMARK_TEXT,
            fontproperties=EconStyle._get_masthead_font(),
            fontsize=13, color="#1A1A1A", ha="right", va="bottom")

    # Set tight ylim to trim extra space
    ax.set_ylim(footer_y - 0.1, fig_h)

    fp = output_dir / "00_india_table.png"
    fig.savefig(fp, dpi=EconStyle.DPI, bbox_inches="tight",
                facecolor=EconStyle.BACKGROUND, pad_inches=0.08)
    plt.close(fig)
    print(f"   ✓ India Macro Pulse Table")
    return fp


# ═══════════════════════════════════════════
# CHART 6: INFLATION BAR CHART (YOUR VERSION)
# ═══════════════════════════════════════════

def chart_inflation_bar(df, output_dir):
    """Side-by-side bar chart for Headline vs Food Inflation (Aug '24 onwards)."""
    if "india_cpi_yoy" not in df.columns or "india_food_cpi_yoy" not in df.columns:
        print("   ⚠ Skipping Inflation Bar — columns not found")
        return None

    # 1. FILTER DATA
    df_subset = df[df["date"] >= "2024-08-01"].copy()
    
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
    
    # 7. Formatting
    _format_date_axis(ax, len(dates))
    ax.set_ylabel("YoY % Change", fontsize=EconStyle.FONT_SIZE_AXIS)

    # 8. LEGEND (Now includes the RBI Band)
    handles, labels = ax.get_legend_handles_labels()
    patch_band = mpatches.Patch(color="#E5E7EB", label="RBI Band (2-6%)")
    handles.append(patch_band)
    
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.02), 
              ncol=3, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)

    EconStyle.set_title(ax, "India's Inflation Dynamics",
                        "Headline vs. Food Inflation (% Year-on-Year)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "MoSPI / RBI")

    fp = output_dir / "06_india_inflation_bar.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Inflation Bar Chart")
    return fp


# ═══════════════════════════════════════════
# (Chart 12 removed — RBI Repo Rate is covered in the RBI Sentinel section)
# ═══════════════════════════════════════════



# ═══════════════════════════════════════════
# CHART 13: MONEY SUPPLY vs CREDIT
# ═══════════════════════════════════════════

def chart_money_supply(df, output_dir):
    """
    M3 YoY % vs Bank Credit YoY % dual-line trend chart.
    M3 data populated when DBIE endpoints are configured in india_fetcher.py.
    Falls back to credit-only chart if M3 not yet available.
    """
    has_credit = "india_bank_credit_yoy" in df.columns
    has_m3 = "india_m3_yoy" in df.columns and df["india_m3_yoy"].notna().any()

    if not has_credit:
        print("   ⚠ Skipping Money Supply — no credit data")
        return None

    fig, ax = EconStyle.create_figure(size="wide")
    dates = df["date"].tolist()

    # Bank Credit YoY
    credit = df["india_bank_credit_yoy"].values
    ax.plot(dates, credit, color=C_CREDIT, linewidth=2.5, label="Bank Credit YoY",
            zorder=5, solid_capstyle="round")
    ax.plot(dates, credit, color=C_CREDIT, linewidth=3.7, alpha=0.07,
            zorder=4, solid_capstyle="round")
    ax.fill_between(dates, 0, credit, color=C_CREDIT, alpha=0.04)
    _add_end_label(ax, dates, credit, "Credit", C_CREDIT, offset_y=6)

    # M3 YoY (when available)
    if has_m3:
        m3 = df["india_m3_yoy"].values
        ax.plot(dates, m3, color=C_M3, linewidth=2.2, linestyle="--",
                label="M3 Money Supply YoY", zorder=5, solid_capstyle="round")
        _add_end_label(ax, dates, m3, "M3", C_M3, offset_y=-14)
    else:
        ax.text(0.02, 0.04, "M3 data pending DBIE configuration",
                transform=ax.transAxes, fontsize=8, color="#94A3B8",
                style="italic", va="bottom")

    # Reference line
    ax.axhline(y=15, color="#999999", linewidth=0.8, linestyle="--", zorder=1, alpha=0.5)
    ax.text(dates[0], 15.2, "15%", fontsize=7, color="#888888",
            va="bottom", fontfamily=EconStyle.FONT_FAMILY)

    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)

    _format_date_axis(ax, len(dates))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax.set_ylabel("YoY Growth (%)", fontsize=EconStyle.FONT_SIZE_AXIS)

    EconStyle.set_title(ax, "Monetary Conditions — Credit & Money Supply",
                        "Bank Credit YoY vs M3 Money Supply YoY (%)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "RBI DBIE")

    fp = output_dir / "13_india_money_supply.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Money Supply vs Credit")
    return fp


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
# CHART 15: IIP — INDUSTRIAL PRODUCTION
# ═══════════════════════════════════════════

def chart_iip(df, output_dir):
    """
    IIP (Index of Industrial Production) YoY % — bar chart with 3M MA.
    Filtered to start from March 2022 to remove pandemic base-effect spikes.
    """
    if "india_iip_yoy" not in df.columns or not df["india_iip_yoy"].notna().any():
        print("   ⚠ Skipping IIP — data pending DBIE configuration")
        return None

    # ── NEW FILTER: Start from March 2022 ──
    df_iip = df[(df["date"] >= "2022-01-01") & (df["india_iip_yoy"].notna())].copy()
    
    if df_iip.empty:
        return None

    fig, ax = EconStyle.create_figure(size="wide")
    dates = df_iip["date"].tolist()
    vals  = df_iip["india_iip_yoy"].values

    ax.yaxis.grid(True, linestyle="-", alpha=0.12, color="#9CA3AF", zorder=0)
    ax.set_axisbelow(True)

    colors = [C_IIP_POS if v >= 0 else C_IIP_NEG for v in vals]
    ax.bar(dates, vals, width=20, color=colors, alpha=0.8,
           edgecolor="none", zorder=3, label="IIP YoY")

    # 3-month moving average
    if len(vals) >= 3:
        ma3 = pd.Series(vals).rolling(3).mean().values
        ax.plot(dates, ma3, color="#000000", linewidth=2.0, linestyle="-",
                label="3M Avg", zorder=5, solid_capstyle="round")
        valid_ma = [(d, v) for d, v in zip(dates, ma3) if not np.isnan(v)]
        if valid_ma:
            _add_end_label(ax, [d for d, _ in valid_ma],
                          [v for _, v in valid_ma], "3M Avg", "#000000")

    ax.axhline(y=0, color="#000000", linewidth=0.8, zorder=2)

    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)
    _format_date_axis(ax, len(dates))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax.set_ylabel("YoY Growth (%)", fontsize=EconStyle.FONT_SIZE_AXIS)

    EconStyle.set_title(ax, "Industrial Production (IIP)",
                        "Index of Industrial Production — YoY % Change")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "RBI DBIE / MoSPI")

    fp = output_dir / "15_india_iip.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ IIP Industrial Production")
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
    
    # The capex Budget Estimate spread evenly over twelve months: capex bars above
    # the line are running ahead of the pace that spends the full budget.
    pace = cag_data['be_capex'] / 12 if cag_data.get('be_capex') else None
    if pace:
        ax.axhline(y=pace, color=C_CAPEX, linewidth=1.5, linestyle=':', zorder=6,
                   label=f"Capex Budget ÷ 12 (₹{pace:.2f}L a month)")

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

    # Reference level (not an official target), named in the legend rather than
    # on the plot, where it collided with the share line
    ax2.axhline(y=25, color='#059669', linewidth=1.5, linestyle='--', alpha=0.7, zorder=6,
                label='25% reference')

    # Value labels on the capex bars. They are drawn on the top axes with a white
    # backing, so the reference lines pass behind them rather than through them.
    _lbl_off = np.nanmax(np.concatenate([capex, rev_exp])) * 0.02
    for i, c in enumerate(capex):
        if not np.isnan(c) and c > 0:
            ax2.text(x[i] - width/2, c + _lbl_off, f'₹{c:.2f}L', transform=ax.transData,
                     ha='center', va='bottom', fontsize=7, color=C_CAPEX, fontweight='bold', zorder=12,
                     bbox=dict(boxstyle='round,pad=0.12', facecolor='white', edgecolor='none'))

    ax.set_xticks(x)
    ax.set_xticklabels(months, fontsize=9)
    ax.set_ylabel('₹ Lakh Crore', fontsize=EconStyle.FONT_SIZE_AXIS)
    ax.set_ylim(0, np.nanmax(np.concatenate([capex, rev_exp, [pace or 0]])) * 1.3)

    # Legend in the clear top band, on the top axes so the share line cannot cover
    # it: left-axis items first, then right-axis items
    handles, names = ax.get_legend_handles_labels()
    handles = [handles[i] for i in sorted(range(len(names)), key=lambda i: names[i].startswith('Capex Budget'))]
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
    ("Market borrowings", "#1E3A8A", ("fin_market_borrowings",)),
    ("Small savings", "#0F766E", ("fin_small_savings_securities", "fin_nssf")),
    ("Other domestic", "#9CA3AF", ("fin_state_provident_funds", "fin_special_deposits", "fin_others")),
    ("Cash drawn down (+) / built up (−)", "#F59E0B", ("fin_cash_balance", "fin_surplus_cash", "fin_wma")),
    ("External", "#7C3AED", ("fin_external",)),
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
               edgecolor='white', linewidth=0.6, zorder=3)
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
    fig.text(0.98, 0.015, EconStyle.WATERMARK_TEXT,
            fontsize=10, fontweight='bold', color='#1A1A1A', ha='right')
    
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
    chart_gst(df, output_dir)
    chart_fpi_flows(df, output_dir)
    chart_nifty_it_trend(output_dir)
    chart_inflation_bar(df, output_dir)

    # ── Summary table (integrates CAG fiscal + weekly forex) ───────────────────
    chart_table(df, output_dir, cag_data, df_weekly)

    # ── Monetary Conditions charts ─────────────────────────────────────────────
    chart_money_supply(df, output_dir)
    chart_credit_deposit(df, output_dir)

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
