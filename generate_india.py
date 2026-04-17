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
  - See docs/india_manual_reminders.md for exact URLs and entry workflow

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
from style.economics_hub_style import EconStyle


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



def load_cag_data(cag_path=DEFAULT_CAG):
    """
    Load CAG Monthly Accounts Dashboard data.
    Returns: (cag_summary dict, df_monthly with month-over-month data)
    """
    if not cag_path.exists():
        print(f"   ⚠ CAG file not found: {cag_path}")
        return None, None
    
    try:
        xlsx = pd.ExcelFile(cag_path)
        
        # Load actual data (cumulative YTD)
        df_actual = pd.read_excel(xlsx, sheet_name='actual')
        df_actual = df_actual.dropna(subset=['FY', 'Month'])
        
        # Load budget estimates
        df_bere = pd.read_excel(xlsx, sheet_name='BERE')
        
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
        
        # Calculate Net Tax Revenue
        gross_tax = (
            latest.get('Corporation Tax', 0) + 
            latest.get('Income Tax', 0) + 
            latest.get('CGST', 0) + 
            latest.get('IGST', 0) + 
            latest.get('UTGST', 0) +
            latest.get('Customs', 0) + 
            latest.get('Union Excise', 0) +
            latest.get('Securities Transcation Tax', 0)
        )
        net_tax_ytd = gross_tax - latest.get('Devolution to State', 0)
        
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
            capex_mom = (capex_monthly - capex_prev_monthly) / 100  # Convert to L Cr
        
        fiscal_deficit_mom = None
        if fiscal_deficit_monthly is not None and fiscal_deficit_prev_monthly is not None:
            fiscal_deficit_mom = (fiscal_deficit_monthly - fiscal_deficit_prev_monthly) / 100
        
        # Load GDP data for % of GDP calculations
        df_gdp = pd.read_excel(xlsx, sheet_name='GDP')
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
            'gdp': gdp / 100 if gdp else None,  # ₹ Lakh Cr
            # YTD values (₹ Lakh Cr)
            'fiscal_deficit_ytd': fiscal_deficit_ytd / 100,
            'fiscal_deficit_pct_gdp': fiscal_deficit_pct_gdp,  # % of GDP
            'capex_ytd': capex_ytd / 100,
            'revenue_exp_ytd': revenue_exp_ytd / 100,
            'net_tax_ytd': net_tax_ytd / 100,
            'gross_tax_ytd': gross_tax / 100,
            # Monthly values (₹ Lakh Cr)
            'capex_monthly': capex_monthly / 100 if capex_monthly else None,
            'fiscal_deficit_monthly': fiscal_deficit_monthly / 100 if fiscal_deficit_monthly else None,
            # MoM changes
            'capex_mom': capex_mom,
            'fiscal_deficit_mom': fiscal_deficit_mom,
            # Budget
            'capex_pct_be': capex_pct_be,
            'be_capex': be_capex / 100 if be_capex else None,
            'be_revenue_exp': be_revenue_exp / 100 if be_revenue_exp else None,
            # Tax breakdown (₹ Lakh Cr)
            'corp_tax_ytd': latest.get('Corporation Tax', 0) / 100,
            'income_tax_ytd': latest.get('Income Tax', 0) / 100,
            'gst_ytd': (latest.get('CGST', 0) + latest.get('IGST', 0) + latest.get('UTGST', 0)) / 100,
            'customs_ytd': latest.get('Customs', 0) / 100,
            'excise_ytd': latest.get('Union Excise', 0) / 100,
            # Expenditure breakdown
            'interest_ytd': latest.get('Interest Payments', 0) / 100,
            'subsidies_ytd': latest.get('Major Subsidies', 0) / 100,
        }
        
        print(f"   Loaded CAG data: {current_fy} through {latest_month}")
        print(f"   Capex YTD: ₹{capex_ytd/100:.1f}L Cr ({capex_pct_be:.1f}% of BE)")
        
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
    """Manufacturing + Services PMI with expansion/contraction zones."""
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

    _format_date_axis(ax, len(dates))
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
# CHART 4: FPI FLOWS (WEEKLY)
# ═══════════════════════════════════════════

def chart_fpi(df_weekly, output_dir):
    """
    Weekly FPI net flows from NSE via jugaad-data.
    Reads from india_weekly.fpi_net_flows_usd_bn (weekly table).
    Shows last 52 weeks as green/red bars with rolling 4-week MA and cumulative annotation.
    """
    if df_weekly is None or df_weekly.empty or "fpi_net_flows_usd_bn" not in df_weekly.columns:
        print("   ⚠ Skipping FPI — no weekly FPI data (run india_fetcher.py --append first)")
        return None

    plot_df = df_weekly[df_weekly["fpi_net_flows_usd_bn"].notna()].copy()
    if plot_df.empty:
        print("   ⚠ Skipping FPI — all weekly FPI values are null")
        return None

    # Limit to last 52 weeks for a clean annual view
    plot_df = plot_df.tail(52).reset_index(drop=True)
    dates = plot_df["week_ending"].tolist()
    vals  = plot_df["fpi_net_flows_usd_bn"].values
    colors = [C_FPI_POS if v >= 0 else C_FPI_NEG for v in vals]

    fig, ax = EconStyle.create_figure(size="wide")

    ax.yaxis.grid(True, linestyle="-", alpha=0.15, color="#9CA3AF", zorder=0)
    ax.set_axisbelow(True)

    bar_width = 5   # days — narrower than monthly bars
    ax.bar(dates, vals, width=bar_width, color=colors, alpha=0.8,
           edgecolor="none", zorder=3)
    ax.axhline(y=0, color="#000000", linewidth=0.8, zorder=2)

    # 4-week rolling MA
    ma = plot_df["fpi_net_flows_usd_bn"].rolling(4, min_periods=2).mean()
    ax.plot(dates, ma.values, color="#1E3A5F", linewidth=1.8,
            linestyle="--", zorder=6, label="4-Week MA")

    # Cumulative annotation
    cumulative = float(vals.sum())
    cum_color  = C_FPI_POS if cumulative >= 0 else C_FPI_NEG
    ax.text(0.99, 1.02, f"52W Cumulative: ${cumulative:+.1f}B",
            transform=ax.transAxes, fontsize=11, fontweight="bold",
            color=cum_color, ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=cum_color, linewidth=1.5))

    _format_date_axis(ax, len(dates))
    ax.set_ylabel("Net FPI Flows ($B)", fontsize=EconStyle.FONT_SIZE_AXIS)

    EconStyle.set_title(ax, "Foreign Portfolio Flows",
                        "Weekly Net FPI/FII Flows into India ($B) — Last 52 Weeks")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "NSE / jugaad-data")

    fp = output_dir / "04_india_fpi.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ FPI Flows")
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
    cag_month = cag_data['latest_month'] if has_cag else None

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
        col in df.columns and pd.notna(df.iloc[-1].get(col))
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
            if col in df.columns and pd.notna(latest.get(col)):
                val = latest[col]
                
                # Calculate MoM change
                if prev is not None and col in df.columns and pd.notna(prev.get(col)):
                    chg = val - prev[col]
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
             f"₹{cag_data['capex_monthly']:.0f}L Cr" if cag_data['capex_monthly'] else "-",
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

    source_text = "Source: S&P Global, RBI DBIE, FRED, MoSPI, PIB, CAG, NSDL"
    ax.text(0.5, footer_y, source_text,
            fontsize=8, color="#666666", ha="left", va="bottom")
    
    if has_cag:
        footer_y -= 0.15
        ax.text(0.5, footer_y, f"* Latest ({cag_month}) Fiscal data",
                fontsize=7, color="#666666", ha="left", va="bottom", style='italic')
    
    ax.text(9.5, footer_y, EconStyle.WATERMARK_TEXT,
            fontproperties=EconStyle._get_masthead_font(),
            fontsize=13, color="#1A1A1A", ha="right", va="bottom")

    # Set tight ylim to trim extra space
    ax.set_ylim(footer_y - 0.1, fig_h)

    fp = output_dir / "05_india_table.png"
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
    Bank Credit Growth vs Deposit Growth — grouped bars with CD ratio overlay.
    Deposit data populated when DBIE endpoints are configured.
    """
    has_credit = "india_bank_credit_yoy" in df.columns and df["india_bank_credit_yoy"].notna().any()
    has_deposit = "india_deposit_growth_yoy" in df.columns and df["india_deposit_growth_yoy"].notna().any()

    if not has_credit:
        print("   ⚠ Skipping Credit/Deposit — no data")
        return None

    fig, ax = EconStyle.create_figure(size="wide")
    dates = df["date"].tolist()
    bar_width = 8  # days

    if has_deposit:
        # Grouped bars
        dates_credit = [d - pd.Timedelta(days=bar_width / 2) for d in dates]
        dates_dep    = [d + pd.Timedelta(days=bar_width / 2) for d in dates]
        credit_vals  = df["india_bank_credit_yoy"].values
        deposit_vals = df["india_deposit_growth_yoy"].values

        ax.bar(dates_credit, credit_vals, width=bar_width, color=C_CREDIT,
               alpha=0.8, label="Bank Credit YoY", edgecolor="none", zorder=3)
        ax.bar(dates_dep, deposit_vals, width=bar_width, color=C_DEPOSIT,
               alpha=0.8, label="Deposit Growth YoY", edgecolor="none", zorder=3)

        # Credit-Deposit ratio overlay on right axis
        cd_ratio = credit_vals / deposit_vals * 100
        ax2 = ax.twinx()
        ax2.plot(dates, cd_ratio, color="#0F172A", linewidth=1.5,
                 linestyle="--", zorder=6, label="C/D Ratio")
        ax2.axhline(y=75, color="#0F172A", linewidth=0.7, linestyle=":",
                    alpha=0.5)
        ax2.set_ylabel("Credit-Deposit Ratio (%)", fontsize=EconStyle.FONT_SIZE_AXIS,
                       color="#0F172A")
        ax2.tick_params(axis="y", colors="#0F172A")
        ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    else:
        # Credit only until DBIE is configured
        credit_vals = df["india_bank_credit_yoy"].values
        ax.bar(dates, credit_vals, width=16, color=C_CREDIT,
               alpha=0.75, label="Bank Credit YoY", edgecolor="none", zorder=3)
        ax.text(0.02, 0.04, "Deposit data pending DBIE configuration",
                transform=ax.transAxes, fontsize=8, color="#94A3B8",
                style="italic", va="bottom")

    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=3, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)
    ax.axhline(y=0, color="#000000", linewidth=0.6, zorder=2)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))

    _format_date_axis(ax, len(dates))
    ax.set_ylabel("YoY Growth (%)", fontsize=EconStyle.FONT_SIZE_AXIS)

    EconStyle.set_title(ax, "Bank Credit & Deposit Growth",
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
    Data populated when DBIE endpoints are configured in india_fetcher.py.
    """
    if "india_iip_yoy" not in df.columns or not df["india_iip_yoy"].notna().any():
        print("   ⚠ Skipping IIP — data pending DBIE configuration")
        return None

    df_iip = df.dropna(subset=["india_iip_yoy"]).copy()
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
    Forex Reserves: dual-panel — area chart for level + bar chart for WoW change.
    Data sourced from india_weekly table (weekly RBI release).
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

    # Left panel: Reserves level (area chart)
    ax_level.fill_between(dates, 0, levels, color=C_RESERVES, alpha=0.12)
    ax_level.plot(dates, levels, color=C_RESERVES, linewidth=2.0,
                  zorder=5, solid_capstyle="round")
    _add_end_label(ax_level, dates, levels, f"${levels[-1]:.0f}B", C_RESERVES)
    ax_level.set_ylabel("USD Billion", fontsize=EconStyle.FONT_SIZE_AXIS)
    ax_level.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax_level.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax_level.get_xticklabels(), rotation=0, ha="center", fontsize=8)
    EconStyle.set_title(ax_level, "Forex Reserves Level", "USD Billion")
    EconStyle.add_top_rule(ax_level)

    # Right panel: WoW change
    if "forex_reserves_wow_chg" in df_weekly.columns:
        chg_vals = df_weekly["forex_reserves_wow_chg"].fillna(0).values
        chg_colors = [C_IIP_POS if v >= 0 else C_IIP_NEG for v in chg_vals]
        ax_chg.bar(dates, chg_vals, color=chg_colors, width=5,
                   alpha=0.8, edgecolor="none", zorder=3)
        ax_chg.axhline(y=0, color="#000000", linewidth=0.8, zorder=2)
        ax_chg.set_ylabel("WoW Change ($B)", fontsize=EconStyle.FONT_SIZE_AXIS)
        ax_chg.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax_chg.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        plt.setp(ax_chg.get_xticklabels(), rotation=0, ha="center", fontsize=8)
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
    Monthly Exports and Imports as grouped bars; Trade Deficit as line on right axis.
    Data populated when DBIE endpoints are configured.
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

    ax.yaxis.grid(True, linestyle="-", alpha=0.12, color="#9CA3AF", zorder=0)
    ax.set_axisbelow(True)

    ax.bar(dates_exp, exports, width=bar_width, color=C_EXPORTS,
           alpha=0.8, label="Exports", edgecolor="none", zorder=3)
    ax.bar(dates_imp, imports, width=bar_width, color="#DC2626",
           alpha=0.75, label="Imports", edgecolor="none", zorder=3)

    ax2.plot(dates, deficit, color=C_DEFICIT_LINE, linewidth=2.0,
             linestyle="--", zorder=6, label="Trade Deficit")
    _add_end_label(ax2, dates, deficit, f"Deficit\n${deficit[-1]:.0f}B",
                   C_DEFICIT_LINE, offset_y=5)

    ax.set_ylabel("USD Billion", fontsize=EconStyle.FONT_SIZE_AXIS)
    ax2.set_ylabel("Trade Deficit ($B)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color=C_DEFICIT_LINE)
    ax2.tick_params(axis="y", colors=C_DEFICIT_LINE)

    # Combined legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2,
              loc="lower right", bbox_to_anchor=(1.1, 1.02),
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
    capex = (df_monthly['Capital Expenditure_monthly'] / 100).values  # ₹ Lakh Cr
    rev_exp = (df_monthly['Revenue Expenditure'].diff().fillna(df_monthly['Revenue Expenditure'].iloc[0]) / 100).values
    
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
    
    # Add value labels on capex bars only
    for i, c in enumerate(capex):
        if not np.isnan(c) and c > 0:
            ax.text(x[i] - width/2, c + 30, f'₹{c:.0f}L', ha='center', va='bottom',
                   fontsize=7, color=C_CAPEX, fontweight='bold', zorder=10)
    
    # Capex ratio line (secondary insight)
    valid_idx = ~np.isnan(capex) & ~np.isnan(rev_exp) & (rev_exp > 0)
    ratio = np.where(valid_idx, capex / (capex + rev_exp) * 100, np.nan)
    
    ax2 = ax.twinx()
    ax2.plot(x[valid_idx], ratio[valid_idx], color='#000000', linewidth=2, 
            marker='o', markersize=4, label='Capex Share %', zorder=10)
    ax2.set_ylabel('Capex as % of Total Expenditure', fontsize=9, color='#333333')
    ax2.set_ylim(0, 50)
    ax2.tick_params(axis='y', colors='#333333')
    
    # Target line
    ax2.axhline(y=25, color='#059669', linewidth=1.5, linestyle='--', alpha=0.7, zorder=6)
    ax2.text(len(months)-1, 26, 'Target: 25%', fontsize=8, color='#059669', ha='right')
    
    ax.set_xticks(x)
    ax.set_xticklabels(months, fontsize=9)
    ax.set_ylabel('₹ Lakh Crore', fontsize=EconStyle.FONT_SIZE_AXIS)
    
    # Legend at top-right, inline with subtitle
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles=handles, loc='lower right', bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)
    
    EconStyle.set_title(ax, "Expenditure Quality",
                        f"Capital vs Revenue Expenditure — FY{cag_data['fy'][-2:]}")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, f"CAG Monthly Accounts | Data through {cag_data['latest_month']}")
    
    fp = output_dir / "07_india_expenditure_quality.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Expenditure Quality Chart")
    return fp


# ═══════════════════════════════════════════
# CHART 8: TAX REVENUE COMPOSITION (WATERFALL)
# ═══════════════════════════════════════════

def chart_tax_composition(cag_data, output_dir):
    """
    FT-style waterfall showing tax revenue composition.
    """
    if cag_data is None:
        print("   ⚠ Skipping Tax Composition — no CAG data")
        return None
    
    fig, ax = EconStyle.create_figure(size="wide")
    
    # Tax components
    components = [
        ('Corporation\nTax', cag_data['corp_tax_ytd'], C_CORP_TAX),
        ('Income\nTax', cag_data['income_tax_ytd'], C_INCOME_TAX),
        ('GST', cag_data['gst_ytd'], C_GST_TAX),
        ('Customs', cag_data['customs_ytd'], C_CUSTOMS),
        ('Excise', cag_data['excise_ytd'], '#6B7280'),
    ]
    
    names = [c[0] for c in components]
    values = [c[1] for c in components]
    colors = [c[2] for c in components]
    
    # Subtle gridlines BEHIND bars
    ax.xaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
    ax.set_axisbelow(True)
    
    # Horizontal bar chart
    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, values, color=colors, alpha=0.85, edgecolor='white', linewidth=0.5, height=0.6, zorder=3)
    
    # Add value labels
    for i, (bar, val) in enumerate(zip(bars, values)):
        ax.text(val + 20, bar.get_y() + bar.get_height()/2, 
               f'₹{val:.0f}L Cr', va='center', fontsize=10, fontweight='bold', color=colors[i])
    
    # Percentage labels
    total = sum(values)
    for i, (bar, val) in enumerate(zip(bars, values)):
        pct = val / total * 100
        ax.text(val/2, bar.get_y() + bar.get_height()/2,
               f'{pct:.0f}%', va='center', ha='center', fontsize=10, 
               fontweight='bold', color='white')
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=10)
    ax.set_xlabel('₹ Lakh Crore', fontsize=EconStyle.FONT_SIZE_AXIS)
    ax.invert_yaxis()
    
    # Add total annotation
    ax.text(0.98, 0.02, f"Gross Tax: ₹{cag_data['gross_tax_ytd']:.0f}L Cr\nNet (post devolution): ₹{cag_data['net_tax_ytd']:.0f}L Cr",
            transform=ax.transAxes, fontsize=10, ha='right', va='bottom',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor='#E5E7EB'))
    
    EconStyle.set_title(ax, "Union Tax Revenue Composition",
                        f"YTD through {cag_data['latest_month']} — FY{cag_data['fy'][-2:]}")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "CAG Monthly Accounts Dashboard")
    
    fp = output_dir / "08_india_tax_composition.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Tax Revenue Composition")
    return fp


# ═══════════════════════════════════════════
# CHART 9: FISCAL CONSOLIDATION TRACKER
# ═══════════════════════════════════════════

def chart_fiscal_tracker(cag_data, df_monthly, df_prev_monthly, output_dir):
    """
    FT-style fiscal consolidation tracker: Current FY vs Previous FY trajectory.
    """
    if cag_data is None or df_monthly is None:
        print("   ⚠ Skipping Fiscal Tracker — no CAG data")
        return None
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    
    for ax in axes:
        ax.set_facecolor(EconStyle.BACKGROUND)
        # Subtle gridlines
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.set_axisbelow(True)
    
    month_order = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']
    
    # Current FY
    df_curr = df_monthly.copy()
    df_curr['month_name'] = df_curr['Month'].str.split('-').str[0]
    df_curr['month_idx'] = df_curr['month_name'].map({m: i for i, m in enumerate(month_order)})
    df_curr = df_curr.sort_values('month_idx')
    
    x_curr = df_curr['month_idx'].values
    capex_curr = (df_curr['Capital Expenditure'] / 100).values
    deficit_curr = (df_curr['Fiscal Deficit'] / 100).values
    
    # Previous FY (if available)
    if df_prev_monthly is not None:
        df_prev = df_prev_monthly.copy()
        df_prev['month_name'] = df_prev['Month'].str.split('-').str[0]
        df_prev['month_idx'] = df_prev['month_name'].map({m: i for i, m in enumerate(month_order)})
        df_prev = df_prev.sort_values('month_idx')
        
        x_prev = df_prev['month_idx'].values
        capex_prev = (df_prev['Capital Expenditure'] / 100).values
        deficit_prev = (df_prev['Fiscal Deficit'] / 100).values
    
    # LEFT: Capex YTD Progress
    ax1 = axes[0]
    if df_prev_monthly is not None:
        ax1.plot(x_prev, capex_prev, color='#9CA3AF', linewidth=2, linestyle='--',
                label=f"FY{cag_data['prev_fy'][-2:]}", marker='o', markersize=3, zorder=4)
    ax1.plot(x_curr, capex_curr, color=C_CAPEX, linewidth=2.5,
            label=f"FY{cag_data['fy'][-2:]}", marker='o', markersize=4, zorder=5)
    ax1.fill_between(x_curr, 0, capex_curr, color=C_CAPEX, alpha=0.1, zorder=2)
    
    # Budget target line
    if cag_data['be_capex']:
        ax1.axhline(y=cag_data['be_capex'], color='#059669', linewidth=1.5, linestyle='--', zorder=3)
        ax1.text(11, cag_data['be_capex'] + 20, f"BE: ₹{cag_data['be_capex']:.0f}L Cr", 
                fontsize=8, color='#059669')
    
    ax1.set_xticks(range(12))
    ax1.set_xticklabels(month_order, fontsize=8)
    ax1.set_ylabel('₹ Lakh Crore (Cumulative)', fontsize=9)
    ax1.set_title('Capital Expenditure YTD', fontsize=12, fontweight='bold', pad=8)
    ax1.legend(loc='upper left', frameon=True, facecolor='white', fontsize=9)
    ax1.set_xlim(-0.5, 11.5)
    
    # End label
    ax1.annotate(f"₹{capex_curr[-1]:.0f}L Cr\n({cag_data['capex_pct_be']:.0f}% of BE)",
                xy=(x_curr[-1], capex_curr[-1]), xytext=(10, 0), textcoords='offset points',
                fontsize=9, fontweight='bold', color=C_CAPEX,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=C_CAPEX))
    
    # RIGHT: Fiscal Deficit YTD
    ax2 = axes[1]
    if df_prev_monthly is not None:
        ax2.plot(x_prev, deficit_prev, color='#9CA3AF', linewidth=2, linestyle='--',
                label=f"FY{cag_data['prev_fy'][-2:]}", marker='o', markersize=3, zorder=4)
    ax2.plot(x_curr, deficit_curr, color=C_FISCAL_DEF, linewidth=2.5,
            label=f"FY{cag_data['fy'][-2:]}", marker='o', markersize=4, zorder=5)
    ax2.fill_between(x_curr, 0, deficit_curr, color=C_FISCAL_DEF, alpha=0.1, zorder=2)
    
    ax2.set_xticks(range(12))
    ax2.set_xticklabels(month_order, fontsize=8)
    ax2.set_ylabel('₹ Lakh Crore (Cumulative)', fontsize=9)
    ax2.set_title('Fiscal Deficit YTD', fontsize=12, fontweight='bold', pad=8)
    ax2.legend(loc='upper left', frameon=True, facecolor='white', fontsize=9)
    ax2.set_xlim(-0.5, 11.5)
    
    # End label
    ax2.annotate(f"₹{deficit_curr[-1]:.0f}L Cr",
                xy=(x_curr[-1], deficit_curr[-1]), xytext=(10, 0), textcoords='offset points',
                fontsize=9, fontweight='bold', color=C_FISCAL_DEF,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=C_FISCAL_DEF))
    
    # Tight suptitle with less padding
    fig.suptitle(f"Fiscal Consolidation Tracker — FY{cag_data['fy'][-2:]} vs FY{cag_data['prev_fy'][-2:]}",
                fontsize=14, fontweight='bold', y=0.98)
    
    plt.tight_layout(rect=[0.02, 0.06, 0.98, 0.96])
    
    fig.text(0.02, 0.02, f"Source: CAG Monthly Accounts | Data through {cag_data['latest_month']}",
            fontsize=8, color="#666666")
    fig.text(0.98, 0.02, EconStyle.WATERMARK_TEXT,
        fontproperties=EconStyle._get_masthead_font(),
        fontsize=13, color="#1A1A1A", ha="right")
    
    fp = output_dir / "09_india_fiscal_tracker.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Fiscal Consolidation Tracker")
    return fp


# ═══════════════════════════════════════════
# CHART 10: MONTHLY FISCAL PULSE
# ═══════════════════════════════════════════

def chart_monthly_fiscal_pulse(cag_data, df_monthly, output_dir):
    """
    FT-style single chart showing monthly capex with year-on-year comparison.
    """
    if cag_data is None or df_monthly is None:
        print("   ⚠ Skipping Monthly Fiscal Pulse — no CAG data")
        return None
    
    fig, ax = EconStyle.create_figure(size="wide")
    
    months = df_monthly['Month'].str.split('-').str[0].tolist()
    capex_monthly = (df_monthly['Capital Expenditure_monthly'] / 100).values
    
    x = np.arange(len(months))
    
    # Subtle gridlines BEHIND bars (like FPI chart)
    ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
    ax.set_axisbelow(True)
    
    # Color bars based on performance vs target: red for below, blue for above
    be_monthly_target = cag_data['be_capex'] / 12 if cag_data['be_capex'] else 0
    colors = [C_CAPEX if c >= be_monthly_target else '#B91C1C' for c in capex_monthly]
    
    bars = ax.bar(x, capex_monthly, color=colors, alpha=0.85, edgecolor='white', 
                 linewidth=0.5, width=0.7, zorder=3)
    
    # Add value labels
    for i, (bar, val) in enumerate(zip(bars, capex_monthly)):
        if not np.isnan(val) and val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, val + 3,
                   f'₹{val:.0f}L', ha='center', va='bottom', fontsize=8, 
                   fontweight='bold', color='#1F2937', zorder=5)
    
    # Monthly target line
    if be_monthly_target > 0:
        target_line = ax.axhline(y=be_monthly_target, color='#DC2626', linewidth=2, linestyle='--',
                  label=f'Monthly Target (₹{be_monthly_target:.0f}L Cr)', zorder=4)
    
    # 3-month moving average
    ma3 = pd.Series(capex_monthly).rolling(3, min_periods=1).mean().values
    ma_line, = ax.plot(x, ma3, color='#000000', linewidth=2, marker='o', markersize=4,
           label='3M Moving Avg', zorder=5)
    
    ax.set_xticks(x)
    ax.set_xticklabels(months, fontsize=9)
    ax.set_ylabel('₹ Lakh Crore', fontsize=EconStyle.FONT_SIZE_AXIS)
    
    # Legend at top-right, inline with subtitle (like inflation chart)
    ax.legend(loc='lower right', bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9, handletextpad=0.4, borderaxespad=0)
    
    # YTD annotation
    ax.text(0.98, 0.95, f"YTD: ₹{cag_data['capex_ytd']:.0f}L Cr\n({cag_data['capex_pct_be']:.1f}% of BE)",
            transform=ax.transAxes, fontsize=10, fontweight='bold',
            color=C_CAPEX, ha='right', va='top',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor=C_CAPEX), zorder=10)
    
    EconStyle.set_title(ax, "Monthly Capital Expenditure",
                        f"Government Capex Spending — FY{cag_data['fy'][-2:]}")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, f"CAG Monthly Accounts | Data through {cag_data['latest_month']}")
    
    fp = output_dir / "10_india_monthly_capex.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Monthly Fiscal Pulse")
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
        xlsx = pd.ExcelFile(cag_path)
        df_actual = pd.read_excel(xlsx, sheet_name='actual')
        df_actual = df_actual.dropna(subset=['FY', 'Month'])
        df_gdp = pd.read_excel(xlsx, sheet_name='GDP')
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
    
    # Target lines
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
    fig.text(0.02, 0.005, f"* FY26 shows Apr–{current_fy_month.split('-')[0]} YTD only",
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
    cag_data, df_monthly, df_prev_monthly = load_cag_data(args.cag)

    # ── Activity & PMI charts ──────────────────────────────────────────────────
    print(f"\n   Generating charts...")
    chart_pmi(df, output_dir)
    chart_gst(df, output_dir)
    chart_fpi(df_weekly, output_dir)
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
        chart_expenditure_quality(cag_data, df_monthly, output_dir)
        chart_tax_composition(cag_data, output_dir)
        chart_fiscal_tracker(cag_data, df_monthly, df_prev_monthly, output_dir)
        chart_monthly_fiscal_pulse(cag_data, df_monthly, output_dir)
        chart_fiscal_deficit_gdp(args.cag, output_dir)

    non_cag_count = 11  # charts 01–06 + 12–17 (chart 03/credit removed, 6 new)
    chart_count = non_cag_count + (5 if cag_data else 0)
    print(f"\n India Dashboard complete! {chart_count} charts saved to:")
    print(f"   {output_dir}")

    if cag_data:
        print(f"\n Fiscal Summary ({cag_data['fy']} through {cag_data['latest_month']}):")
        print(f"   Capex YTD: {cag_data['capex_ytd']:.0f} Lakh Cr ({cag_data['capex_pct_be']:.1f}% of BE)")
        print(f"   Fiscal Deficit YTD: {cag_data['fiscal_deficit_ytd']:.0f} Lakh Cr")
        print(f"   Net Tax Revenue YTD: {cag_data['net_tax_ytd']:.0f} Lakh Cr")


if __name__ == "__main__":
    main()
