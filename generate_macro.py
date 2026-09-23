#!/usr/bin/env python3
"""
Economics Hub — World tab generator ("The World Economy")
==========================================================
Runs every Saturday via GitHub Actions (macro.yml); output goes to
output/macro/YYYY-MM/, so later runs in a month refresh the same edition.

Writes:
  world_snapshot.json       central bank rates, six-economy scoreboard,
                            global rate cycle, US data calendar
  01, 02, 07                US inflation, labour, Fed balance sheet
  10_macro_rate_cycle       central banks hiking and cutting each month (BIS)
  11_macro_oecd_cli         OECD composite leading indicators, one panel per economy
  14_macro_em_borrowing     EM corporate dollar bond yields vs the 10-year Treasury
  15_macro_em_dollar        the dollar against EM currencies and the rupee
  16_macro_cape             Shiller CAPE and excess CAPE yield since 1881
  17_macro_equity_risk_premium  Damodaran's implied S&P 500 equity risk premium
  18_macro_country_erp      G20 equity risk premiums: mature-market premium + country risk premium
  19_macro_regional_erp     GDP-weighted equity risk premium by region, now vs a year earlier
  20_macro_ratings_vs_markets  G20 country risk premium from ratings vs from CDS

Any automatic source that fails or has stopped updating makes the run exit
non-zero after writing what it could, so the workflow publishes nothing.

--rates-only refreshes just the central bank rates and the rate cycle chart
in the published edition (assets/macro/<latest month>/); rates.yml runs it
twice every weekday so a decision shows the day it is announced.
"""

import sys
import json
import re
import argparse
import warnings
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

# Suppress harmless Matplotlib date locator warnings
warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.image as mpimg

from charts.style import EconStyle
from data.fetchers.fred_fetcher import FredFetcher
from config.settings import FRED_API_KEY
from config.macro_settings import EM_FX_PEERS, MACRO_INDICATORS
from config.world_settings import OECD_CLI_COUNTRIES
from data.world_snapshot import (apply_rate_update, build_rate_update, build_snapshot, monthly,
                                 rates_fingerprint, yoy_by_date)
from data.world_manual_entry import load_rows as load_world_manual_rows
from data.valuations import fetch_country_risk, fetch_damodaran_erp, fetch_shiller
from rbi_sentinel.config import DB_PATH as RBI_SENTINEL_DB

import dbnomics

# ── DBNOMICS CONFIG & COLORS ──
COLOR_G7 = "#003366"
COLOR_EM = "#FF9933"
COLOR_POSITIVE = "#065F46"
COLOR_NEGATIVE = "#991B1B"
COLOR_NEUTRAL = "#666666"
COLOR_TARGET = "#CC0000"

# ---------------------------------------------------------------------------
# Title registry
# ---------------------------------------------------------------------------
# Each key maps to a (title, subtitle) pair for each mode.
#
#   mode = 'dashboard'  → Standard, descriptive titles for the Streamlit dashboard.
#   mode = 'newsletter' → Narrative, story-driven titles for Substack issues.
#
# Before each Substack publication, edit the 'newsletter' strings below to
# reflect the specific narrative you are writing about in that issue.
# ---------------------------------------------------------------------------

MACRO_TITLES: dict[str, dict[str, tuple[str, str]]] = {
    "inflation": {
        "dashboard": (
            "US Inflation Metrics",
            "Headline CPI and core PCE, % year on year, vs. 5y5y forward inflation expectations (monthly average)",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "US Inflation Metrics",
            "Headline CPI and core PCE, % year on year, vs. 5y5y forward inflation expectations (monthly average)",
        ),
    },
    "labour": {
        "dashboard": (
            "US Labour Market Indicators",
            "US unemployment rate (monthly) and initial jobless claims (weekly, 4-week average)",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "US Labour Market Indicators",
            "US unemployment rate (monthly) and initial jobless claims (weekly, 4-week average)",
        ),
    },
    "agflation": {
        "dashboard": (
            "Agricultural & Energy Input Pipeline",
            "Natural gas, fertilizer (urea) and wheat futures indexed to 100",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Futures Markets are Pricing the Agricultural Shock",
            "Rising European gas and fertilizer input futures are signaling a severe, lagged spike in global food costs",
        ),
    },
    "fed_balance_sheet": {
        "dashboard": (
            "Federal Reserve Balance Sheet",
            "Total assets held by the Fed (WALCL)  ·  QE expansion and QT drawdown",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Federal Reserve Balance Sheet",
            "Total assets held by the Fed (WALCL)  ·  QE expansion and QT drawdown",
        ),
    },
    "rate_cycle": {
        "dashboard": (
            "The Global Rate Cycle",
            "Central banks that raised (above the line) or cut (below) their policy rate each month",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Global Rate Cycle",
            "Central banks that raised (above the line) or cut (below) their policy rate each month",
        ),
    },
    "oecd_cli": {
        "dashboard": (
            "OECD Composite Leading Indicators",
            "Amplitude-adjusted, 100 = long-term trend  ·  "
            "phase = above or below trend, and rising or falling over three months",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "OECD Composite Leading Indicators",
            "Amplitude-adjusted, 100 = long-term trend  ·  "
            "phase = above or below trend, and rising or falling over three months",
        ),
    },
    "cape": {
        "dashboard": (
            "Shiller CAPE and Excess CAPE Yield",
            "S&P 500 price over ten-year average real earnings, and its earnings yield minus the real 10-year bond yield, monthly",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Shiller CAPE and Excess CAPE Yield",
            "S&P 500 price over ten-year average real earnings, and its earnings yield minus the real 10-year bond yield, monthly",
        ),
    },
    "equity_risk_premium": {
        "dashboard": (
            "US Equity Risk Premium",
            "Implied premium of expected S&P 500 returns over the 10-year Treasury yield, start of each month, %",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "US Equity Risk Premium",
            "Implied premium of expected S&P 500 returns over the 10-year Treasury yield, start of each month, %",
        ),
    },
    "country_erp": {
        "dashboard": (
            "Equity Risk Premiums Across the G20",
            "Mature-market premium plus the country risk premium from each sovereign's Moody's rating, %",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Equity Risk Premiums Across the G20",
            "Mature-market premium plus the country risk premium from each sovereign's Moody's rating, %",
        ),
    },
    "regional_erp": {
        "dashboard": (
            "Equity Risk Premiums by Region",
            "Each small dot is one country's total ERP  ·  the large dot is the region's "
            "GDP-weighted average",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Equity Risk Premiums by Region",
            "Each small dot is one country's total ERP  ·  the large dot is the region's "
            "GDP-weighted average",
        ),
    },
    "ratings_vs_markets": {
        "dashboard": (
            "Where Markets Disagree With the Rating Agencies",
            "Country risk premium priced by CDS markets minus the premium implied by the Moody's rating, G20",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Where Markets Disagree With the Rating Agencies",
            "Country risk premium priced by CDS markets minus the premium implied by the Moody's rating, G20",
        ),
    },
    "em_borrowing": {
        "dashboard": (
            "Emerging-Market Dollar Borrowing Costs",
            "Yield on EM companies' dollar bonds by credit rating vs. the 10-year US Treasury, %, weekly averages",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Emerging-Market Dollar Borrowing Costs",
            "Yield on EM companies' dollar bonds by credit rating vs. the 10-year US Treasury, %, weekly averages",
        ),
    },
    "em_dollar": {
        "dashboard": (
            "The Dollar vs. Emerging-Market Currencies",
            "Weekly averages indexed to 100 three years ago  ·  up = the currency weakened against the dollar",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Dollar vs. Emerging-Market Currencies",
            "Weekly averages indexed to 100 three years ago  ·  up = the currency weakened against the dollar",
        ),
    },
}

G7 = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany",
    "FR": "France", "IT": "Italy", "JP": "Japan", "CA": "Canada",
}

EMERGING_MARKETS = {
    "IN": "India", "BR": "Brazil", "MX": "Mexico", "ID": "Indonesia",
    "ZA": "South Africa", "TR": "Turkey", "TH": "Thailand",
    "PH": "Philippines", "CL": "Chile", "PL": "Poland",
}

IMF_WEO_CODES = {
    "IN": "IND", "BR": "BRA", "MX": "MEX", "ID": "IDN",
    "ZA": "ZAF", "TR": "TUR", "TH": "THA", "PH": "PHL",
    "CL": "CHL", "PL": "POL",
}

OECD_CODES = {
    "US": "USA", "GB": "GBR", "DE": "DEU", "FR": "FRA",
    "IT": "ITA", "JP": "JPN", "CA": "CAN",
    "IN": "IND", "BR": "BRA", "MX": "MEX", "ID": "IDN",
    "ZA": "ZAF", "TR": "TUR",
}

# ═══════════════════════════════════════════════
# DATA ENGINES (FRED + DBNOMICS)
# ═══════════════════════════════════════════════

class MacroDataEngine:
    """Fetch and transform macro data from FRED."""
    def __init__(self, fred_fetcher):
        self.fred = fred_fetcher
        self.cache = {} 

    def fetch_raw(self, ind_id):
        if ind_id in self.cache: return self.cache[ind_id]
        ind = MACRO_INDICATORS[ind_id]
        years = ind.get("history_years", 3)
        try:
            # --- NEW: Yahoo Finance Interceptor ---
            if "ticker" in ind:
                start_date = datetime.now() - timedelta(days=int((years + 1) * 365.25))
                df = yf.download(ind["ticker"], start=start_date, progress=False)
                data = df["Close"]
                if isinstance(data, pd.DataFrame): data = data.iloc[:, 0]
            # --- ORIGINAL: FRED Fetcher ---
            else:
                data = self.fred.fetch_series(ind["series"], period_years=years + 1)
                
            data = data.astype(float)
            self.cache[ind_id] = data
            return data
        except Exception as e:
            print(f"   ⚠ Failed to fetch {ind['name']}: {e}")
            return pd.Series(dtype=float)

    def get_transformed(self, ind_id):
        ind = MACRO_INDICATORS[ind_id]
        raw = self.fetch_raw(ind_id)
        if raw.empty: return pd.Series(dtype=float)

        transform = ind["transform"]
        years = ind.get("history_years", 3)
        cutoff = datetime.now() - timedelta(days=int(years * 365.25))

        # YoY and MoM are matched by calendar month, never by row count: FRED
        # has no October 2025 CPI or unemployment (US shutdown), and counting
        # rows across that gap published a 13-month change as US CPI YoY.
        if transform == "yoy_pct":
            result = yoy_by_date(raw)
        elif transform == "mom_abs":
            s = monthly(raw)
            prior = s.copy()
            prior.index = prior.index + pd.DateOffset(months=1)
            result = s - prior.reindex(s.index)
        else:
            result = raw
        return result[result.index >= cutoff].dropna()

    def get_latest(self, ind_id):
        series = self.get_transformed(ind_id)
        return float(series.iloc[-1]) if not series.empty else None

    def get_previous(self, ind_id, periods_ago=1):
        series = self.get_transformed(ind_id)
        return float(series.iloc[-(periods_ago + 1)]) if len(series) >= periods_ago + 1 else None

    def get_change(self, ind_id):
        latest = self.get_latest(ind_id)
        previous = self.get_previous(ind_id, 1)
        return latest - previous if latest is not None and previous is not None else None

    def freshness_problem(self, ind_id):
        """A message if the raw series is empty or its latest observation is older than max_age."""
        ind = MACRO_INDICATORS[ind_id]
        raw = self.fetch_raw(ind_id)
        if raw.empty:
            return f"{ind['name']} ({ind['series']}): no data"
        age = (datetime.now() - raw.index[-1].to_pydatetime()).days
        if age > ind["max_age"]:
            return (f"{ind['name']} ({ind['series']}): latest observation {raw.index[-1]:%Y-%m-%d} "
                    f"is {age} days old (limit {ind['max_age']}) — FRED may have stopped updating it")
        return None

def safe_fetch(provider, dataset, series_code, label=""):
    try:
        df = dbnomics.fetch_series(provider_code=provider, dataset_code=dataset, series_code=series_code)
        if df is not None and len(df) > 0:
            print(f"   ✓ Fetched: {label or series_code}")
            return df
        return None
    except Exception as e:
        print(f"   ⚠ Failed: {label or series_code} ({e})")
        return None

def extract_series(df, value_col="value", date_col="period"):
    if df is None: return pd.Series(dtype=float)
    out = df[[date_col, value_col]].copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    return out.dropna().set_index(date_col)[value_col]

def fetch_macro_em_vulnerability(output_dir, years=5):
    print("\n   Fetching EM Vulnerability Data...")
    cutoff = datetime.now() - pd.Timedelta(days=years * 365)
    rows = []

    for iso2, name in EMERGING_MARKETS.items():
        weo_code = IMF_WEO_CODES[iso2]
        row = {"country": name, "iso": iso2, "group": "EM"}

        cpi_df = safe_fetch("IMF", "IFS", f"M.{iso2}.PCPI_PC_CP_A_PT", f"{iso2} CPI")
        cpi = extract_series(cpi_df)
        if len(cpi) > 0 and len(cpi[cpi.index >= cutoff]) > 0:
            row["cpi_yoy"] = round(float(cpi[cpi.index >= cutoff].iloc[-1]), 2)

        ca_df = safe_fetch("IMF", "WEO:latest", f"{weo_code}.BCA_NGDPD", f"{iso2} CA")
        ca = extract_series(ca_df)
        if len(ca) > 0 and len(ca[ca.index >= cutoff]) > 0:
            row["current_account_gdp"] = round(float(ca[ca.index >= cutoff].iloc[-1]), 2)

        debt_df = safe_fetch("IMF", "WEO:latest", f"{weo_code}.GGXWDG_NGDP", f"{iso2} Debt")
        debt = extract_series(debt_df)
        if len(debt) > 0 and len(debt[debt.index >= cutoff]) > 0:
            row["govt_debt_gdp"] = round(float(debt[debt.index >= cutoff].iloc[-1]), 2)

        rows.append(row)

    df_out = pd.DataFrame(rows)
    df_out.to_csv(output_dir / "em_macro.csv", index=False)
    return df_out

# ═══════════════════════════════════════════════
# CHART BUILDERS
# ═══════════════════════════════════════════════

def _style_axis(ax, ylabel=None):
    ax.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.35)
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=EconStyle.FONT_SIZE_TICK)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=EconStyle.FONT_SIZE_AXIS, color=EconStyle.TEXT_SECONDARY, labelpad=6)

def _add_end_label(ax, dates, values, name, color):
    if len(values) == 0: return
    last_val, last_date = float(values[-1]), dates[-1]
    
    if abs(last_val) >= 1000: vs = f"{last_val:,.0f}"
    elif abs(last_val) >= 10: vs = f"{last_val:.1f}"
    else: vs = f"{last_val:.2f}"

    label = f" {name}  {vs}"
    ax.annotate(
        label, xy=(last_date, last_val), xytext=(4, 0), textcoords="offset points",
        fontproperties=EconStyle._get_font("bold"), fontsize=EconStyle.FONT_SIZE_ANNOTATION - 0.5,
        color=color, va="center", ha="left",
        path_effects=[pe.withStroke(linewidth=2.5, foreground=EconStyle.BACKGROUND)],
    )

# ── Line charts: inflation, labour, emerging markets ─────────────────────────
LINE_BLUE, LINE_TEAL, LINE_ORANGE = EconStyle.LINE_BLUE, EconStyle.LINE_TEAL, EconStyle.LINE_ORANGE
LINE_MAROON = EconStyle.LINE_MAROON
LINE_RUPEE, INK, INK_MUTED = EconStyle.LINE_RUPEE, EconStyle.INK, EconStyle.INK_MUTED


def _pchip_edge_slope(h0, h1, d0, d1):
    """End slope of a monotone cubic: three-point estimate, kept from overshooting (as in SciPy)."""
    s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if np.sign(s) != np.sign(d0):
        return 0.0
    if np.sign(d0) != np.sign(d1) and abs(s) > 3 * abs(d0):
        return 3 * d0
    return s


def monotone_curve(dates, values, per_segment=12):
    """
    A smooth line through monthly or weekly observations: a monotone cubic
    (Fritsch-Butland, the method of SciPy's PchipInterpolator) on the real
    time spacing. It passes through every observation and stays between each
    pair of neighbours, so it rounds the corners of a straight-segment line
    without inventing a peak, trough or level that is not in the data.
    Returns (timestamps, values) to plot.
    """
    x = ((pd.DatetimeIndex(dates) - pd.Timestamp("1970-01-01")) / pd.Timedelta(seconds=1)).to_numpy(dtype=float)
    y = np.asarray(values, dtype=float)
    if len(y) < 3:
        return pd.to_datetime(x, unit="s"), y
    h = np.diff(x)
    d = np.diff(y) / h
    m = np.zeros(len(y))
    w1, w2 = 2 * h[1:] + h[:-1], h[1:] + 2 * h[:-1]
    same_direction = d[:-1] * d[1:] > 0          # a local peak, trough or flat stretch gets slope 0
    with np.errstate(divide="ignore", invalid="ignore"):
        m[1:-1] = np.where(same_direction, (w1 + w2) / (w1 / d[:-1] + w2 / d[1:]), 0.0)
    m[0] = _pchip_edge_slope(h[0], h[1], d[0], d[1])
    m[-1] = _pchip_edge_slope(h[-1], h[-2], d[-1], d[-2])

    t = np.linspace(0.0, 1.0, per_segment, endpoint=False)
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    xs = (x[:-1, None] + h[:, None] * t).ravel()
    ys = (h00 * y[:-1, None] + h10 * (h * m[:-1])[:, None]
          + h01 * y[1:, None] + h11 * (h * m[1:])[:, None]).ravel()
    return pd.to_datetime(np.append(xs, x[-1]), unit="s"), np.append(ys, y[-1])


def weekly_average(series, today=None):
    """
    Mean of each complete Monday-to-Friday week, dated by its Friday. Weeks cut
    by the start of the data or not yet over are dropped, so every point is a
    full week of real observations.
    """
    s = series.dropna()
    if s.empty:
        return s
    today = pd.Timestamp(today or date.today())
    weekly = s.resample("W-FRI").mean().dropna()
    starts_in_data = weekly.index - pd.Timedelta(days=4) >= s.index[0].normalize()
    return weekly[starts_in_data & (weekly.index < today)]


def complete_month_average(series, today=None):
    """Mean of each calendar month that is fully inside the data and already over, dated the 1st."""
    s = series.dropna()
    if s.empty:
        return s
    today = pd.Timestamp(today or date.today())
    monthly_mean = s.groupby(s.index.to_period("M")).mean()
    monthly_mean.index = monthly_mean.index.to_timestamp()
    # A month's first trading day can fall as late as the 4th (weekend plus a holiday).
    first_full = monthly_mean.index[0] if s.index[0].day <= 4 else monthly_mean.index[0] + pd.DateOffset(months=1)
    return monthly_mean[(monthly_mean.index >= first_full) & (monthly_mean.index < today.replace(day=1))]


def _draw_line(ax, x, y, color, width=2.0, zorder=3, halo=True):
    """A line with a thin white edge, so lines that cross stay distinct (off where a reference line runs along the data)."""
    effects = [pe.Stroke(linewidth=width + 2.0, foreground="white"), pe.Normal()] if halo else None
    ax.plot(x, y, color=color, linewidth=width, zorder=zorder,
            solid_joinstyle="round", solid_capstyle="round", path_effects=effects)


def _end_dot(ax, x, y, color, zorder=6, size=34):
    ax.scatter([x], [y], s=size, color=color, edgecolors="white", linewidths=1.3, zorder=zorder)


def _style_line_axes(ax, y_format, nbins=6):
    """Horizontal grid, no y ticks or side spines, a black baseline and formatted y labels."""
    ax.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.5)
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(EconStyle.AXIS_COLOR)
    ax.spines["bottom"].set_linewidth(1.0)
    ax.tick_params(axis="y", length=0, labelsize=EconStyle.FONT_SIZE_TICK, pad=4)
    # No 2.5 steps: a 0.25 tick labelled to one decimal would print 3.75% as "3.8%".
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=nbins, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(y_format))


def _trim_yticks(ax, data_high):
    """Drop gridlines above the data, leaving clear headroom for a panel title."""
    lo, hi = ax.get_ylim()
    ticks = ax.yaxis.get_major_locator().tick_values(lo, hi)
    ax.set_yticks([t for t in ticks if lo <= t <= data_high + (hi - lo) * 0.02])


def _time_axis(ax, start, end, right_margin=0.2):
    """
    Year labels inside the data — every year for spans up to five years, then
    every 2, 5, 10 or 20 years — minor ticks between, and room on the right for end labels.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    span = end - start
    ax.set_xlim(start - span * 0.01, end + span * right_margin)
    span_years = span.days / 365.25
    step, minor_step = next((s, m) for limit, s, m in [(5, 1, None), (12, 2, 1), (30, 5, 1), (70, 10, 5), (1e9, 20, 10)]
                            if span_years <= limit)
    in_data = lambda yr: start <= pd.Timestamp(yr, 1, 1) <= end
    years = [pd.Timestamp(yr, 1, 1) for yr in range(start.year, end.year + 1) if yr % step == 0 and in_data(yr)]
    ax.set_xticks(years)
    ax.set_xticklabels([str(t.year) for t in years])
    if minor_step is None:
        minor = [q for q in pd.date_range(start.normalize(), end, freq="QS") if q.month != 1]
    else:
        minor = [pd.Timestamp(yr, 1, 1) for yr in range(start.year, end.year + 1)
                 if yr % minor_step == 0 and yr % step != 0 and in_data(yr)]
    ax.set_xticks(minor, minor=True)
    ax.tick_params(axis="x", which="major", length=4, width=0.8, color=EconStyle.AXIS_COLOR,
                   pad=4, labelsize=EconStyle.FONT_SIZE_TICK)
    ax.tick_params(axis="x", which="minor", length=2.5, width=0.6, color=EconStyle.AXIS_COLOR)


def _padded_ylim(ax, lows, highs, bottom=0.08, top=0.08):
    lo, hi = min(lows), max(highs)
    pad = (hi - lo) or abs(hi) or 1.0
    ax.set_ylim(lo - pad * bottom, hi + pad * top)


HEAVY_LINE = 2.5   # the Weekly tab's trend-line weight: visible at the dashboard's two-column size


def _spread_labels_centred(values, min_gap):
    """
    Label positions at least `min_gap` apart. Labels that collide are spread
    evenly around their own average, so each stays as close as possible to its
    line's end instead of all being pushed upwards. Returns positions in input order.
    """
    def positions(cluster):
        centre = sum(values[i] for i in cluster) / len(cluster)
        return [centre + (j - (len(cluster) - 1) / 2) * min_gap for j in range(len(cluster))]

    clusters = []
    for i in sorted(range(len(values)), key=lambda k: values[k]):
        clusters.append([i])
        while len(clusters) > 1 and positions(clusters[-1])[0] - positions(clusters[-2])[-1] < min_gap - 1e-12:
            clusters[-2:] = [clusters[-2] + clusters[-1]]
    placed = {}
    for cluster in clusters:
        placed.update(zip(cluster, positions(cluster)))
    return [placed[i] for i in range(len(values))]


def _margin_labels(ax, items, x):
    """
    End labels in the Weekly tab's style: name and latest value in bold, in the
    line's own colour, just right of the last observation. `items` are dicts
    with y, name, value and color. Nudged apart so none overlap.
    """
    lo, hi = ax.get_ylim()
    ys = _spread_labels_centred([it["y"] for it in items], (hi - lo) * 0.07)
    for it, ly in zip(items, ys):
        ax.annotate(f"{it['name']}  {it['value']}", xy=(x, ly), xytext=(10, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=9, fontweight="bold", color=it["color"], zorder=7,
                    annotation_clip=False, path_effects=[pe.withStroke(linewidth=3, foreground="white")])


def _value_label(ax, x, y, text, dy=0):
    """The latest value beside a single line's end dot (dy points up, to clear a reference line)."""
    ax.annotate(text, xy=(x, y), xytext=(8, dy), textcoords="offset points", va="center", ha="left",
                fontsize=9, fontweight="bold", color=INK, zorder=7,
                path_effects=[pe.withStroke(linewidth=3, foreground="white")])


def _panel_title(ax, text, badge=None, note=None):
    """A panel's name just inside its top edge, with an optional highlighted badge or muted note top right."""
    ax.annotate(text, xy=(0, 1), xycoords="axes fraction", xytext=(0, -7), textcoords="offset points",
                ha="left", va="top", fontsize=9, fontweight="bold", color=INK, zorder=8,
                path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    if note:
        ax.annotate(note, xy=(1, 1), xycoords="axes fraction", xytext=(0, -7), textcoords="offset points",
                    ha="right", va="top", fontsize=8.5, color=INK_MUTED, zorder=8,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    if badge:
        ax.annotate(badge, xy=(1, 1), xycoords="axes fraction", xytext=(-4, -8), textcoords="offset points",
                    ha="right", va="top", fontsize=9, fontweight="bold", color=EconStyle.REGION_COLORS["us"], zorder=8,
                    bbox=dict(boxstyle="round,pad=0.45", facecolor="#E6EDF6", edgecolor="#B9CBE3", linewidth=0.8))


def chart_inflation(engine, output_dir, mode="dashboard"):
    """US headline CPI and core PCE inflation, market inflation expectations and the Fed's 2% target."""
    cpi = engine.get_transformed("us_cpi_yoy")
    pce = engine.get_transformed("us_core_pce")
    # The daily 5y5y rate as averages of complete months, so all three lines are monthly.
    expectations = complete_month_average(engine.get_transformed("us_inflation_exp"))
    lines = [(s, name, color) for s, name, color in [
        (cpi, "Headline CPI", LINE_BLUE), (pce, "Core PCE", LINE_TEAL), (expectations, "5y5y expectations", LINE_ORANGE),
    ] if not s.empty]
    if not lines:
        raise ValueError("no US inflation series")

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size="wide")
    start = min(s.index[0] for s, _, _ in lines)
    end = max(s.index[-1] for s, _, _ in lines)

    labels = []
    for s, name, color in lines:
        _draw_line(ax, *monotone_curve(s.index, s.values), color, width=HEAVY_LINE)
        _end_dot(ax, s.index[-1], s.iloc[-1], color, size=58)
        labels.append({"y": float(s.iloc[-1]), "name": name, "value": f"{s.iloc[-1]:.2f}%", "color": color})
    ax.hlines(2.0, start, end, colors=INK_MUTED, linewidth=1.6, linestyles=(0, (4, 2.5)), zorder=2)
    labels.append({"y": 2.0, "name": "Fed target", "value": "2%", "color": INK_MUTED})

    _style_line_axes(ax, lambda v, _: f"{v:.1f}%")
    _padded_ylim(ax, [s.min() for s, _, _ in lines] + [2.0], [s.max() for s, _, _ in lines])
    _time_axis(ax, start, end, right_margin=0.24)
    _margin_labels(ax, labels, end)

    _t, _s = MACRO_TITLES["inflation"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "FRED (BLS, BEA, Federal Reserve Bank of St. Louis)")
    EconStyle.save_chart(fig, output_dir / "01_macro_inflation.png")
    print("   ✓ US Inflation Metrics")


def chart_labour(engine, output_dir, mode="dashboard"):
    """US unemployment rate and initial jobless claims: two panels on one time axis, no second y-scale."""
    unemp = engine.get_transformed("us_unemployment")
    claims = engine.get_transformed("us_claims")
    if unemp.empty or claims.empty:
        raise ValueError("US unemployment rate or initial claims missing")
    claims_4w = (claims.rolling(4).mean() / 1000).dropna()
    start = min(unemp.index[0], claims_4w.index[0])
    end = max(unemp.index[-1], claims_4w.index[-1])

    EconStyle.apply_global_style()
    fig, (ax_u, ax_c) = EconStyle.create_figure(size="wide", nrows=2, sharex=True)

    _draw_line(ax_u, *monotone_curve(unemp.index, unemp.values), LINE_BLUE)
    _end_dot(ax_u, unemp.index[-1], unemp.iloc[-1], LINE_BLUE)
    _value_label(ax_u, unemp.index[-1], unemp.iloc[-1], f"{unemp.iloc[-1]:.1f}%")
    payrolls = engine.get_transformed("us_payrolls")
    payrolls_note = (f"Payrolls, {payrolls.index[-1]:%B}: {payrolls.iloc[-1]:+,.0f}K"
                     if not payrolls.empty else None)
    _panel_title(ax_u, "Unemployment rate", badge=payrolls_note)

    _draw_line(ax_c, *monotone_curve(claims_4w.index, claims_4w.values), LINE_MAROON)
    _end_dot(ax_c, claims_4w.index[-1], claims_4w.iloc[-1], LINE_MAROON)
    _value_label(ax_c, claims_4w.index[-1], claims_4w.iloc[-1], f"{claims_4w.iloc[-1]:,.0f}K")
    _panel_title(ax_c, "Initial jobless claims, 4-week average")

    _style_line_axes(ax_u, lambda v, _: f"{v:.1f}%", nbins=8)
    _style_line_axes(ax_c, lambda v, _: f"{v:,.0f}K")
    # Headroom above each line, with no gridlines in it, keeps the panel titles clear of the data.
    _padded_ylim(ax_u, [unemp.min()], [unemp.max()], bottom=0.12, top=0.28)
    _padded_ylim(ax_c, [claims_4w.min()], [claims_4w.max()], bottom=0.12, top=0.28)
    _trim_yticks(ax_u, unemp.max())
    _trim_yticks(ax_c, claims_4w.max())
    _time_axis(ax_c, start, end, right_margin=0.07)
    ax_u.tick_params(axis="x", which="both", length=0)

    _t, _s = MACRO_TITLES["labour"][mode]
    EconStyle.set_title(ax_u, _t, _s)
    EconStyle.add_top_rule(ax_u)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    fig.subplots_adjust(hspace=0.1)
    EconStyle.add_source(fig, "FRED (BLS, US Department of Labor)")
    EconStyle.save_chart(fig, output_dir / "02_macro_labour.png")
    print("   ✓ US Labour Market Indicators")

def chart_macro_em_vulnerability(output_dir):
    fpath = output_dir / "em_macro.csv"
    if not fpath.exists(): return
    df = pd.read_csv(fpath)
    needed = ["current_account_gdp", "govt_debt_gdp", "cpi_yoy"]
    existing = [c for c in needed if c in df.columns]
    if not existing: return
    df = df.dropna(subset=existing, how="all")

    fig, axes = plt.subplots(1, 3, figsize=(15, 7.5), sharey=True)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')
    EconStyle.apply_global_style()

    df["vuln_score"] = df.get("cpi_yoy", 0) + df.get("govt_debt_gdp", 0) - df.get("current_account_gdp", 0)
    df = df.sort_values("vuln_score", ascending=True)

    panels = [
        ("current_account_gdp", "Current Account (% GDP)", -4, "below", None),
        ("govt_debt_gdp", "Govt Debt (% GDP)", 60, "above", None),
        ("cpi_yoy", "CPI Inflation (YoY %)", 6, "above", 15),
    ]

    for ax, (col, title, thresh, bad_dir, clip_at) in zip(axes, panels):
        if col not in df.columns:
            ax.axis("off")
            continue
            
        vals = df[col].values
        for i, v in enumerate(vals):
            if pd.isna(v): continue
            is_bad = (v > thresh) if bad_dir == "above" else (v < thresh)
            color = COLOR_NEGATIVE if is_bad else COLOR_G7
            disp_v = min(v, clip_at) if clip_at and v > clip_at else v
            
            ax.scatter(disp_v, i, s=100, color=color, zorder=5, edgecolors="white")
            ax.plot([0 if col != "current_account_gdp" else min(0, disp_v), disp_v], [i, i], color=color, linewidth=0.6, alpha=0.3, zorder=2)
            
            label_x = v + (abs(ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.03) if v >= 0 else v - (abs(ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.03)
            ax.text(label_x if not (clip_at and v > clip_at) else disp_v - 0.3, i, f"{v:.1f}%" + (">>" if clip_at and v > clip_at else ""), va="center", ha="left" if v >= 0 and not (clip_at and v > clip_at) else "right", fontsize=8, fontweight="bold", color=color)

        ax.axvline(x=thresh, color=COLOR_TARGET, linewidth=1, linestyle="--", alpha=0.5, zorder=1)
        if clip_at: ax.set_xlim(right=clip_at + 1)
        ax.set_title(title, fontsize=10, fontweight="bold", loc="left", fontfamily=EconStyle.FONT_FAMILY)
        for spine in ["top", "right", "left"]: ax.spines[spine].set_visible(False)
        ax.plot([0, 1], [1, 1], color="#000000", linewidth=1.2, transform=ax.transAxes, clip_on=False, zorder=10)

    axes[0].set_yticks(range(len(df)))
    axes[0].set_yticklabels(df["country"].values, fontsize=9.5)
    
    fig.text(0.02, 0.97, "EM Vulnerability Scorecard", fontsize=18, fontweight="bold")
    fig.text(0.04, 0.02, f"Source: IMF WEO + CPI via DBnomics  |  {datetime.now().strftime('%d %b %Y')}", fontsize=8, color="#666666", ha="left", va="bottom")
    fig.tight_layout(rect=[0.01, 0.06, 0.99, 0.91])
    EconStyle.save_chart(fig, output_dir / "08_macro_em_vulnerability.png")
    print(f"   ✓ EM Vulnerability Scorecard")

import matplotlib.pyplot as plt
import matplotlib.image as mpimg

def chart_bdti_branded_screenshot(output_dir, mode="dashboard"):
    """Wraps a paywalled chart screenshot in the Economics Hub branding."""
    EconStyle.apply_global_style()
    
    # 1. Load the raw screenshot
    img_path = PROJECT_ROOT / "data" / "bdti_raw_chart.png"
    if not img_path.exists():
        print("   ⚠ Missing bdti_screenshot.png in the data folder.")
        return
        
    img = mpimg.imread(img_path)
    
    # 2. Create the standard EconStyle figure
    fig, ax = EconStyle.create_figure(size=(11, 7.5)) 
    
    # 3. Plot the image directly onto the matplotlib axis
    ax.imshow(img, aspect='auto', interpolation='lanczos')
    ax.axis('off')
    
    # ─── 100% ABSOLUTE MANUAL OVERRIDE ───────────────────────────────────────
    # Bypassing all EconStyle title functions to guarantee perfect spacing
    
    # 4. Main Title (Anchored at the very top)
    _t, _s = MACRO_TITLES["bdti"][mode]
    fig.text(0.02, 0.97, _t,
             fontsize=20, fontweight="bold", ha="left", va="top", color="#000000")

    # 5. Subtitle (Anchored perfectly below the main title)
    fig.text(0.02, 0.92, _s,
             fontsize=12, color=EconStyle.TEXT_SECONDARY, ha="left", va="top")
             
    # 6. Top Rule (Draws the thick black line directly below the subtitle)
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.88, 0.88], color='black', linewidth=2.5, zorder=10, transform=fig.transFigure))
             
    # 7. Split Custom Footer
    fig.text(0.02, 0.02, "Source: Baltic Exchange and StockQ", 
             fontsize=12, color=EconStyle.TEXT_SECONDARY, ha="left", va="bottom", fontweight="bold")
    fig.text(0.98, 0.02, "The Economics Hub", 
             fontsize=14, color="#1C1C1E", ha="right", va="bottom", fontweight="bold")
    
    # 8. Lock the chart image exactly between the header line (0.88) and footer (0.02)
    fig.tight_layout(rect=[0.02, 0.06, 0.98, 0.86])
    # ─────────────────────────────────────────────────────────────────────────
    
    filepath = output_dir / "13_bdti_branded_screenshot.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ BDTI Branded Screenshot Wrapper Complete")
    return filepath

def chart_hormuz_exposure(output_dir, mode="dashboard"):
    """Generates a horizontal bar chart showing Strait of Hormuz export exposure."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    EconStyle.apply_global_style()

    # 1. Extracted Data (Exports only, excluding Softs and Grains/Oilseeds)
    # Grouped into three distinct categories for specific color targeting
    data = [
        ("Methanol", 31.6, "Petrochemicals & Refined"),
        ("Crude Oil &\nCondensates", 30.9, "Crude & LNG"),
        ("Natural Gas \nLiquids (NGLs)", 23.3, "Petrochemicals & Refined"),
        ("Liquefied Natural \nGas (LNG)", 18.6, "Crude & LNG"),  
        ("Dirty Petroleum \nProducts (DPP)", 13.0, "Petrochemicals & Refined"),
        ("Clean Petroleum \nProducts (CPP)", 12.6, "Petrochemicals & Refined"),
        ("Petcoke", 6.1, "Petrochemicals & Refined")
    ]

    # Sort by value (ascending, so the largest bar renders at the very top of the chart)
    data.sort(key=lambda x: x[1])

    labels = [item[0] for item in data]
    values = [item[1] for item in data]
    categories = [item[2] for item in data]

    # 2. Institutional Color Mapping
    color_ag = "#1E3A8A"      # Deep Blue
    color_energy = "#D97706"  # Burnt Orange
    color_petro = "#C2185B"   # Deep Magenta/Pink for Petrochemicals

    colors = []
    for cat in categories:
        if cat == "Agriculture & Minerals":
            colors.append(color_ag)
        elif cat == "Petrochemicals & Refined":
            colors.append(color_petro)
        else:
            colors.append(color_energy)

    # 3. Create Figure
    fig, ax = EconStyle.create_figure(size=(10, 7))

    # 4. Plot Horizontal Bars
    bars = ax.barh(labels, values, color=colors, height=0.6, zorder=3)

    # 5. Add Data Labels directly to the end of the bars
    for bar, val in zip(bars, values):
        ax.text(
            val + 0.5,  # Offset slightly to the right of the bar
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%",
            va='center', ha='left',
            fontsize=11, fontweight='bold', color="#1C1C1E"
        )

    # 6. Clean and Style Axes
    ax.set_xlim(0, 40)
    ax.set_xlabel("Share of Global Exports (%)", fontsize=EconStyle.FONT_SIZE_AXIS, color=EconStyle.TEXT_SECONDARY)
    
    # Remove the bounding box
    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color(EconStyle.AXIS_COLOR)

    # 7. Gridlines (Force behind bars with correct transparency)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, linestyle='-', alpha=0.3, color='#9CA3AF', zorder=0)
    ax.yaxis.grid(False) 

    # 8. Custom 3-Part Categorical Legend
    energy_patch = mpatches.Patch(color=color_energy, label='Crude & LNG')
    petro_patch = mpatches.Patch(color=color_petro, label='Petrochemicals and Refined Products')
    
    ax.legend(handles=[petro_patch, energy_patch], loc='lower right', frameon=False, fontsize=11)

    # 9. Titles and Proprietary Branding
    _t, _s = MACRO_TITLES["hormuz"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)

    # Tight layout to prevent clipping
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    # Footer with source
    EconStyle.add_source(fig, "Kpler, S&P Global, U.S. EIA")

    # 10. Save
    filepath = output_dir / "15_hormuz_exposure.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Hormuz Petrochemical Exposure Chart Complete")
    
    return filepath

# ═══════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════

def chart_fed_balance_sheet(engine, output_dir, mode="dashboard"):
    """Federal Reserve total assets (WALCL) with QE/QT era shading."""
    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size="wide")
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    bs = engine.get_transformed("fed_balance_sheet")
    if bs.empty:
        print("   ⚠ Fed balance sheet data unavailable — skipping.")
        return

    # Convert from millions to trillions for readability
    bs_t = bs / 1_000_000
    dates, vals = bs_t.index.to_pydatetime().tolist(), bs_t.values

    # Era shading
    qe_start  = pd.to_datetime("2020-03-01")
    qt_start  = pd.to_datetime("2022-06-01")
    ax.axvspan(qe_start, qt_start, alpha=0.06, color="#003366", zorder=0)
    ax.axvspan(qt_start, dates[-1], alpha=0.06, color="#B91C1C", zorder=0)
    ax.text(pd.to_datetime("2021-01-01"), 0.03, "QE Era",
            color="#003366", fontsize=9, alpha=0.7, transform=ax.get_xaxis_transform())
    ax.text(pd.to_datetime("2022-09-01"), 0.03, "QT Era",
            color="#B91C1C", fontsize=9, alpha=0.7, transform=ax.get_xaxis_transform())

    ax.plot(dates, vals, color="#003366", linewidth=2.5, solid_capstyle="round", zorder=3)
    ax.fill_between(dates, vals, min(vals), alpha=0.06, color="#003366", zorder=0)

    _add_end_label(ax, dates, vals, f"${vals[-1]:.1f}T", "#003366")
    _style_axis(ax, ylabel="Total Assets (USD Trillions)")

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.1f}T"))
    for spine in ["top", "right", "left"]: ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.set_xlim(ax.get_xlim()[0], ax.get_xlim()[1] + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.12)

    _t, _s = MACRO_TITLES["fed_balance_sheet"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    EconStyle.add_source(fig, "FRED (Federal Reserve H.4.1)")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "07_macro_balance_sheet.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Fed Balance Sheet")


# ═══════════════════════════════════════════════
# WORLD CHARTS
# ═══════════════════════════════════════════════

def _ticks_within_data(ax, last_date):
    """Drop x ticks after the last observation (the right margin holds end labels, not future dates)."""
    last = mdates.date2num(pd.Timestamp(last_date).to_pydatetime())
    ax.set_xticks([t for t in ax.get_xticks() if t <= last + 1])


def _spread_labels(values, min_gap):
    """Nudge end-label y positions apart so they don't overlap; returns positions in input order."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    placed = {}
    last = None
    for i in order:
        y = values[i] if last is None else max(values[i], last + min_gap)
        placed[i], last = y, y
    return [placed[i] for i in range(len(values))]


# Hikes red, cuts blue: the Weekly tab's diverging pair, validated on white.
RATE_HIKE, RATE_CUT = EconStyle.LOSS, EconStyle.GAIN
BANK_NAMES = {"US": "Fed", "XM": "ECB", "GB": "BoE", "JP": "BoJ", "IN": "RBI"}
# Episodes named on the chart: (month the label sits over, text, above or below
# the line, alignment). The 2022 label ends at its peak, leaving the top right
# corner to the latest month.
RATE_CYCLE_EPISODES = [
    ("2001-09", "2001 recession", "cut", "center"),
    ("2006-06", "2004–06 tightening", "hike", "center"),
    ("2008-11", "Financial crisis", "cut", "center"),
    ("2020-03", "Pandemic", "cut", "center"),
    ("2022-09", "Post-pandemic inflation", "hike", "right"),
]


def chart_rate_cycle(cycle, output_dir, mode="dashboard", today=None):
    """
    Diverging monthly bars: how many of the central banks the BIS covers
    raised their policy rate (up) and how many cut it (down) in each month
    since 2000. The latest month is marked as partial while it is still
    running or not every bank has reported it.
    """
    if not cycle or not cycle.get("hikes"):
        raise ValueError("no rate cycle in the snapshot")
    today = pd.Timestamp(today or date.today())
    months = pd.period_range(cycle["start"], periods=len(cycle["hikes"]), freq="M")
    x = months.to_timestamp() + pd.Timedelta(days=14)   # bar centred mid-month
    hikes, cuts = np.array(cycle["hikes"]), np.array(cycle["cuts"])
    reporting, banks = np.array(cycle["reporting"]), cycle["banks"]
    last = months[-1]
    partial = last >= today.to_period("M") or reporting[-1] < banks

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size=(9.5, 6.2))
    alpha = np.where(np.arange(len(months)) == len(months) - 1, 0.55 if partial else 1.0, 1.0)
    for xi, h, c, a in zip(x, hikes, cuts, alpha):
        if h:
            ax.bar(xi, h, width=24, color=RATE_HIKE, alpha=a, linewidth=0, zorder=3)
        if c:
            ax.bar(xi, -c, width=24, color=RATE_CUT, alpha=a, linewidth=0, zorder=3)
    ax.axhline(0, color=INK, linewidth=1.0, zorder=4)

    top = max(hikes.max(), cuts.max())
    lim = top * 1.28
    ax.set_ylim(-lim, lim)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=8, steps=[1, 2, 5, 10], integer=True))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{abs(v):.0f}"))
    ax.set_yticks([t for t in ax.get_yticks() if abs(t) <= top * 1.05])
    ax.grid(axis="y", color=EconStyle.GRID_COLOR, linewidth=0.5)
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=EconStyle.FONT_SIZE_TICK, pad=4)
    _time_axis(ax, months[0].to_timestamp(), x[-1], right_margin=0.02)

    side = dict(xycoords="axes fraction", fontsize=9.5, fontweight="bold", ha="left")
    ax.annotate("Raised rates", xy=(0.005, 0.965), va="top", color=RATE_HIKE, **side)
    ax.annotate("Cut rates", xy=(0.005, 0.035), va="bottom", color=RATE_CUT, **side)

    for when, text, kind, align in RATE_CYCLE_EPISODES:
        m = pd.Period(when, "M")
        if m < months[0] or m > last:
            continue
        i = months.get_loc(m)
        window = slice(max(0, i - 3), i + 4)
        y = (hikes[window].max() + 1.2) if kind == "hike" else -(cuts[window].max() + 1.2)
        ax.annotate(text, xy=(x[i], y), ha=align, va="bottom" if kind == "hike" else "top",
                    fontsize=8, color=INK_MUTED, zorder=5,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground=EconStyle.BACKGROUND)])

    def count(n, word):
        return f"{n} {word}{'' if n == 1 else 's'}"
    ax.annotate(f"{last.strftime('%b %Y')}{' so far' if partial else ''}\n{count(hikes[-1], 'hike')}, {count(cuts[-1], 'cut')}",
                xy=(x[-1], hikes[-1] + 0.5), xytext=(x[-1], lim * 0.92), ha="right", va="top",
                fontsize=9, fontweight="bold", color=INK, zorder=6,
                arrowprops=dict(arrowstyle="-", color=INK_MUTED, linewidth=0.8, shrinkA=2, shrinkB=0),
                path_effects=[pe.withStroke(linewidth=3, foreground=EconStyle.BACKGROUND)])

    extended = [BANK_NAMES[a] for a in cycle.get("extended", []) if a in BANK_NAMES]
    lines = ["Each bank counts once a month: its rate at the month's end against the month before.",
             f"A faded bar is a month in progress or not yet reported by every bank ({reporting[-1]} of {banks} so far)."]
    if extended:
        names = extended[0] if len(extended) == 1 else ", ".join(extended[:-1]) + " and " + extended[-1]
        lines.append(f"Moves since the BIS data end ({pd.Timestamp(cycle['bis_through']):%-d %b}) come from the banks' "
                     f"own announcements ({names}).")
    fig.text(0.04, 0.055, "\n".join(lines), fontsize=7.5, color=EconStyle.TEXT_MUTED, ha="left", va="bottom",
             linespacing=1.5)

    _t, _s = MACRO_TITLES["rate_cycle"][mode]
    EconStyle.set_title(ax, _t, f"{_s}, of the {banks} the BIS tracks")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.12, 0.98, 0.96])
    EconStyle.add_source(fig, f"BIS central bank policy rates, data to {pd.Timestamp(cycle['bis_through']):%-d %b %Y}"
                              f"{'; central bank announcements' if extended else ''}")
    EconStyle.save_chart(fig, output_dir / "10_macro_rate_cycle.png")
    print("   ✓ The Global Rate Cycle")


CLI_PHASE_COLORS = {"Expansion": "#1E7B45", "Recovery": "#0B8F82", "Downturn": "#C8620A", "Slowdown": "#A61B29"}


def cli_phase(series, months=1):
    """
    The OECD's four business-cycle phases, from the leading indicator's level
    (at or above 100 = above trend) and whether it has risen over the last
    `months` months. The ranked chart asks for three, a window one month's
    wobble cannot flip; a shorter series falls back to what it has.
    """
    back = min(months, len(series) - 1)
    if back < 1:
        raise ValueError("a leading indicator needs two observations before it has a direction")
    level = float(series.iloc[-1])
    rising = level > float(series.iloc[-1 - back])
    if level >= 100:
        return "Expansion" if rising else "Downturn"
    return "Recovery" if rising else "Slowdown"


def _figure_title(fig, title, subtitle):
    """The EconStyle title block (title, subtitle, heavy rule) across a multi-panel figure. Returns the rule's y."""
    h = fig.get_figheight()
    y_title = 1 - 0.1 / h
    y_subtitle = y_title - 0.36 / h
    y_rule = y_subtitle - 0.27 / h
    fig.text(0.02, y_title, title, fontproperties=EconStyle._get_font("bold"), fontsize=EconStyle.FONT_SIZE_TITLE,
             color=EconStyle.TEXT_TITLE, ha="left", va="top")
    fig.text(0.02, y_subtitle, subtitle, fontsize=EconStyle.FONT_SIZE_SUBTITLE, color=EconStyle.TEXT_SECONDARY,
             ha="left", va="top")
    fig.add_artist(plt.Line2D([0.02, 0.98], [y_rule, y_rule], color=EconStyle.RULE_HEAVY, linewidth=1.5,
                              transform=fig.transFigure))
    return y_rule


def chart_oecd_cli(cli, output_dir, mode="dashboard"):
    """
    Every economy the OECD publishes a leading indicator for, ranked. The bar
    is how far the indicator sits above or below its long-term trend; its
    colour and the name beside it are the phase that level and direction put
    the economy in, so the phase is never carried by colour alone.
    """
    missing = [name for area, name in OECD_CLI_COUNTRIES.items() if area not in cli or cli[area].empty]
    if missing:
        raise ValueError(f"no OECD leading indicator for {', '.join(missing)}")
    rows = pd.DataFrame([
        {"label": name, "level": float(cli[area].dropna().iloc[-1]),
         "phase": cli_phase(cli[area].dropna(), months=3), "period": cli[area].dropna().index[-1]}
        for area, name in OECD_CLI_COUNTRIES.items()
    ]).sort_values(["level", "label"], ascending=[True, False]).reset_index(drop=True)
    period = max(rows["period"])
    dev = rows["level"] - 100
    y = np.arange(len(rows))

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size=(11.5, 7.0))
    ax.barh(y, dev, height=0.66, color=[CLI_PHASE_COLORS[p] for p in rows["phase"]],
            edgecolor="white", linewidth=1.2, zorder=3)
    ax.axvline(0, color=INK, linewidth=1.2, zorder=4)
    for yi, (level, phase) in enumerate(zip(rows["level"], rows["phase"])):
        right = level >= 100
        ax.annotate(f"{level:.1f}", xy=(level - 100, yi), xytext=(6 if right else -6, 0),
                    textcoords="offset points", va="center", ha="left" if right else "right",
                    fontsize=9, fontweight="bold", color=INK)
        ax.annotate(phase, xy=(1, yi), xycoords=("axes fraction", "data"), ha="right", va="center",
                    fontsize=9, fontweight="bold", color=CLI_PHASE_COLORS[phase])
    ax.annotate("Cycle phase", xy=(1, len(rows) - 0.5), xycoords=("axes fraction", "data"), ha="right",
                va="bottom", fontsize=8, color=INK_MUTED)

    _style_row_axes(ax, rows["label"], lambda v, _: f"{v + 100:.0f}")
    ax.set_xlim(dev.min() - 0.35, dev.max() + (dev.max() - dev.min()) * 0.46)
    ax.set_ylim(-0.7, len(rows) + 0.35)
    # The right margin is there to hold the phase column, not more scale:
    # keep gridlines and ticks inside the range the bars actually cover.
    ax.set_xticks([t for t in ax.get_xticks() if dev.min() - 0.35 <= t <= dev.max() + 0.35])

    _t, _s = MACRO_TITLES["oecd_cli"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, f"OECD Composite Leading Indicators, amplitude-adjusted ({period:%B %Y})")
    EconStyle.save_chart(fig, output_dir / "11_macro_oecd_cli.png")
    print("   ✓ OECD Composite Leading Indicators")


def chart_cape(shiller, output_dir, mode="dashboard"):
    """Shiller CAPE and excess CAPE yield since 1881: two panels on one time axis, long-run averages dashed."""
    cape = shiller["cape"].dropna()
    ecy = shiller["excess_cape_yield"].dropna()
    if cape.empty or ecy.empty:
        raise ValueError("Shiller CAPE or excess CAPE yield missing")
    start = min(cape.index[0], ecy.index[0])
    end = max(cape.index[-1], ecy.index[-1])
    minus = lambda text: text.replace("-", "−")

    EconStyle.apply_global_style()
    fig, (ax_c, ax_y) = EconStyle.create_figure(size="wide", nrows=2, sharex=True)
    panels = [
        (ax_c, cape, LINE_BLUE, "CAPE (cyclically adjusted P/E)", lambda v: f"{v:.1f}", lambda v, _: f"{v:.0f}"),
        (ax_y, ecy, LINE_MAROON, "Excess CAPE yield, %", lambda v: minus(f"{v:.1f}%"), lambda v, _: minus(f"{v:.0f}%")),
    ]
    for ax, s, color, title, fmt_value, fmt_tick in panels:
        average = float(s.mean())
        if ax is ax_y:
            ax.axhline(0, color=INK, linewidth=0.9, zorder=2)
        ax.hlines(average, start, end, colors=INK_MUTED, linewidth=1.3, linestyles=(0, (4, 2.5)), zorder=2)
        ax.plot(s.index, s.values, color=color, linewidth=2.0, zorder=3,
                solid_joinstyle="round", solid_capstyle="round")
        _end_dot(ax, s.index[-1], s.iloc[-1], color)
        lo_, hi_ = s.min(), s.max()
        near_zero = ax is ax_y and abs(float(s.iloc[-1])) < (hi_ - lo_) * 0.06
        _value_label(ax, s.index[-1], s.iloc[-1], fmt_value(s.iloc[-1]), dy=9 if near_zero else 0)
        _panel_title(ax, title, note=f"{s.index[-1]:%b %Y}  ·  dashed = average since {s.index[0]:%Y}: "
                                     f"{fmt_value(average)}")
        _style_line_axes(ax, fmt_tick)
        _padded_ylim(ax, [s.min()], [s.max()], bottom=0.08, top=0.3)
        _trim_yticks(ax, s.max())
    peak_date = cape.idxmax()
    ax_c.annotate(f"Record {cape.max():.1f}, {peak_date:%b %Y}", xy=(peak_date, cape.max()), xytext=(-8, 0),
                  textcoords="offset points", ha="right", va="center", fontsize=8.5, color=INK_MUTED, zorder=6,
                  path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    _time_axis(ax_y, start, end, right_margin=0.07)
    ax_c.tick_params(axis="x", which="both", length=0)

    _t, _s = MACRO_TITLES["cape"][mode]
    EconStyle.set_title(ax_c, _t, _s)
    EconStyle.add_top_rule(ax_c)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    fig.subplots_adjust(hspace=0.1)
    EconStyle.add_source(fig, "Robert J. Shiller, shillerdata.com (latest month left out while provisional)")
    EconStyle.save_chart(fig, output_dir / "16_macro_cape.png")
    print("   ✓ Shiller CAPE and Excess CAPE Yield")


def chart_equity_risk_premium(erp, output_dir, mode="dashboard"):
    """Damodaran's implied S&P 500 equity risk premium, start of each month, with its average over the series."""
    s = erp["erp"].dropna()
    if len(s) < 24:
        raise ValueError(f"only {len(s)} months of implied ERP")
    average = float(s.mean())

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size="wide")
    ax.hlines(average, s.index[0], s.index[-1], colors=INK_MUTED, linewidth=1.6, linestyles=(0, (4, 2.5)), zorder=2)
    _draw_line(ax, *monotone_curve(s.index, s.values), LINE_BLUE, width=HEAVY_LINE)
    _end_dot(ax, s.index[-1], s.iloc[-1], LINE_BLUE, size=58)

    _style_line_axes(ax, lambda v, _: f"{v:.0f}%" if float(v).is_integer() else f"{v:.1f}%")
    _padded_ylim(ax, [s.min(), average], [s.max()])
    _time_axis(ax, s.index[0], s.index[-1], right_margin=0.3)
    _margin_labels(ax, [
        {"y": float(s.iloc[-1]), "name": f"{s.index[-1]:%b %Y}", "value": f"{s.iloc[-1]:.2f}%", "color": LINE_BLUE},
        {"y": average, "name": f"Average since {s.index[0]:%Y}", "value": f"{average:.2f}%", "color": INK_MUTED},
    ], s.index[-1])

    _t, _s = MACRO_TITLES["equity_risk_premium"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "Aswath Damodaran, NYU Stern (implied ERP, trailing 12-month cash yield)")
    EconStyle.save_chart(fig, output_dir / "17_macro_equity_risk_premium.png")
    print("   ✓ US Equity Risk Premium")


# ── Country risk (Damodaran's January and July updates) ──────────────────────
# G20 members as named in Damodaran's table. Russia is not in his rated table
# (no sovereign rating; he scores it on PRS, a different method), so it is not shown.
G20_COUNTRIES = {
    "Argentina": "Argentina", "Australia": "Australia", "Brazil": "Brazil", "Canada": "Canada",
    "China": "China", "France": "France", "Germany": "Germany", "India": "India", "Indonesia": "Indonesia",
    "Italy": "Italy", "Japan": "Japan", "Korea": "South Korea", "Mexico": "Mexico",
    "Saudi Arabia": "Saudi Arabia", "South Africa": "South Africa", "Turkey": "Turkey",
    "United Kingdom": "United Kingdom", "United States": "United States",
}
REGION_LABELS = {"Central and South America": "Central & South America", "Australia & New Zealand": "Australia & NZ"}
# Damodaran's regional averages table and his country table spell one region
# differently; every other name matches. Regional spelling -> country spelling.
REGION_MEMBERS = {"Eastern Europe": "Eastern Europe & Russia"}
# Countries rated C sit near 31%, three times the next tier, and stretch the
# regional chart until every other country is a smear. They are drawn at this
# edge instead and named under the chart.
ERP_AXIS_CAP = 20.0
BASE_SEGMENT = "#C9D1DC"   # the mature-market premium is the same for every country, so it is drawn neutral
RING = "#7B8594"


def _g20_rows(countries):
    missing = [name for name in G20_COUNTRIES if name not in countries.index]
    if missing:
        raise ValueError(f"G20 countries missing from Damodaran's rated table: {', '.join(missing)} — renamed?")
    rows = countries.loc[list(G20_COUNTRIES)].copy()
    rows["label"] = [G20_COUNTRIES[name] for name in rows.index]
    return rows


def _style_row_axes(ax, labels, x_format):
    """Horizontal-row chart: category labels on the left, vertical grid, no ticks."""
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=9.5, color=INK)
    ax.set_ylim(-0.7, len(labels) - 0.3)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=7, steps=[1, 2, 5, 10]))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(x_format))
    ax.grid(axis="x", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.5)
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "bottom", "left"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="both", length=0, labelsize=EconStyle.FONT_SIZE_TICK)


def _update_label(update):
    return f"{update:%B %Y} update"


def chart_country_erp(risk, output_dir, mode="dashboard"):
    """G20 total equity risk premiums, split into the mature-market premium and each country's risk premium."""
    latest = risk["latest"]
    mature = latest["mature"]
    rows = _g20_rows(latest["countries"]).sort_values(["erp", "label"], ascending=[True, False])
    y = np.arange(len(rows))

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size=(9.5, 6.0))
    ax.barh(y, mature, height=0.66, color=BASE_SEGMENT, edgecolor="white", linewidth=1.5, zorder=3,
            label=f"Mature-market premium, {mature:.2f}%")
    ax.barh(y, rows["crp"], left=mature, height=0.66, color=LINE_MAROON, edgecolor="white", linewidth=1.5, zorder=3,
            label="Country risk premium")
    for yi, erp in zip(y, rows["erp"]):
        ax.annotate(f"{erp:.2f}%", xy=(erp, yi), xytext=(5, 0), textcoords="offset points", va="center", ha="left",
                    fontsize=9, fontweight="bold", color=INK)
    _style_row_axes(ax, rows["label"], lambda v, _: f"{v:.0f}%")
    ax.set_xlim(0, rows["erp"].max() * 1.1)
    ax.legend(loc="lower right", frameon=False, fontsize=9, handlelength=1.4, handleheight=1.1)

    _t, _s = MACRO_TITLES["country_erp"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, f"Aswath Damodaran, NYU Stern (country risk premiums, {_update_label(latest['date'])}; "
                              f"Russia, unrated, not shown)")
    EconStyle.save_chart(fig, output_dir / "18_macro_country_erp.png")
    print("   ✓ Equity Risk Premiums Across the G20")


def _signed(value, digits=2):
    return f"{'+' if value > 0 else chr(0x2212) if value < 0 else ''}{abs(value):.{digits}f}"


def _swarm_offsets(values, min_gap, levels=(0.0, 0.17, -0.17, 0.30, -0.30)):
    """
    Vertical offsets that stop dots on one row from hiding each other: each
    value takes the first level on which it clears its neighbours by min_gap.
    Deterministic, so the same data always draws the same picture.
    """
    placed = {level: [] for level in levels}
    offsets = []
    for value in values:
        for level in levels:
            if all(abs(value - other) >= min_gap for other in placed[level]):
                break
        else:
            level = min(levels, key=lambda lv: len(placed[lv]))
        placed[level].append(value)
        offsets.append(level)
    return offsets


def chart_regional_erp(risk, output_dir, mode="dashboard"):
    """
    Every rated country as a dot on its region's row, with the region's
    GDP-weighted average marked. The average says where a region sits; the
    spread of dots says whether that average is worth trusting, and where
    inside a risky region the calmer places are.
    """
    now, before = risk["latest"]["regions"], risk["year_ago"]["regions"]
    countries = risk["latest"]["countries"]
    regions = [r for r in now.index if r != "Global"]
    missing = [r for r in regions + ["Global"] if r not in before.index]
    if missing:
        raise ValueError(f"regions missing from the earlier update: {', '.join(missing)}")
    members = {r: countries.loc[countries["region"] == REGION_MEMBERS.get(r, r), "erp"].dropna().sort_values()
               for r in regions}
    empty = [r for r, s in members.items() if s.empty]
    if empty:
        raise ValueError(f"no rated countries fall in {', '.join(empty)} — region names changed?")
    order = sorted(regions, key=lambda r: now[r])
    y = np.arange(len(order))
    lo = min(s.min() for s in members.values())
    span = ERP_AXIS_CAP - lo
    off_scale = countries.loc[countries["erp"] > ERP_AXIS_CAP, "erp"].sort_values()

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size=(9.5, 6.0))
    ax.axvline(now["Global"], color=INK_MUTED, linewidth=1.2, linestyle=(0, (4, 2.5)), zorder=1)
    ax.annotate(f"Global average {now['Global']:.2f}%", xy=(now["Global"], 1), xycoords=("data", "axes fraction"),
                xytext=(5, -2), textcoords="offset points", ha="left", va="top", fontsize=8.5, color=INK_MUTED)
    for yi, region in zip(y, order):
        values = members[region]
        inside = values[values <= ERP_AXIS_CAP]
        offsets = _swarm_offsets(inside, min_gap=span * 0.013)
        ax.scatter(inside, yi + np.array(offsets), s=19, color=LINE_BLUE, alpha=0.5, edgecolors="none", zorder=3)
        ax.scatter([now[region]], [yi], s=185, color=LINE_MAROON, alpha=0.85, edgecolors="white",
                   linewidths=1.4, zorder=5)
        change = now[region] - before[region]
        ax.annotate(f"{now[region]:.2f}%", xy=(1, yi), xycoords=("axes fraction", "data"), xytext=(-62, 0),
                    textcoords="offset points", ha="right", va="center", fontsize=9, fontweight="bold", color=INK)
        ax.annotate(_signed(change), xy=(1, yi), xycoords=("axes fraction", "data"), ha="right", va="center",
                    fontsize=9, fontweight="bold",
                    color=LINE_TEAL if change < 0 else LINE_MAROON if change > 0 else INK_MUTED)
    ax.annotate("Average", xy=(1, len(order) - 0.5), xycoords=("axes fraction", "data"), xytext=(-62, 0),
                textcoords="offset points", ha="right", va="bottom", fontsize=8, color=INK_MUTED)
    ax.annotate("Change", xy=(1, len(order) - 0.5), xycoords=("axes fraction", "data"), ha="right",
                va="bottom", fontsize=8, color=INK_MUTED)
    _style_row_axes(ax, [REGION_LABELS.get(r, r) for r in order], lambda v, _: f"{v:.0f}%")
    ax.set_xlim(lo - span * 0.04, ERP_AXIS_CAP + span * 0.34)
    ax.set_ylim(-0.75, len(order) + 0.2)
    ax.set_xticks([t for t in ax.get_xticks() if lo - span * 0.04 <= t <= ERP_AXIS_CAP])

    _t, _s = MACRO_TITLES["regional_erp"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    omitted = f"; {len(off_scale)} above {ERP_AXIS_CAP:.0f}% not shown" if len(off_scale) else ""
    EconStyle.add_source(fig, f"Aswath Damodaran, NYU Stern ({len(countries)} rated countries, "
                              f"{_update_label(risk['latest']['date'])}{omitted})")
    EconStyle.save_chart(fig, output_dir / "19_macro_regional_erp.png")
    print("   ✓ Equity Risk Premiums by Region")


def chart_ratings_vs_markets(risk, output_dir, mode="dashboard"):
    """
    The gap itself, one bar per country: what credit default swap markets
    charge for a country's risk minus what its Moody's rating implies. Drawn
    as a difference so the reader is never asked to subtract two dots.
    """
    latest = risk["latest"]
    rows = _g20_rows(latest["countries"])
    no_cds = rows.loc[rows["crp_cds"].isna(), "label"].tolist()
    rows = rows.dropna(subset=["crp_cds"]).assign(gap=lambda d: d["crp_cds"] - d["crp"])
    rows = rows.sort_values(["gap", "label"], ascending=[False, False]).reset_index(drop=True)
    y = np.arange(len(rows))
    minus = lambda text: text.replace("-", "−")

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size=(9.5, 6.0))
    ax.barh(y, rows["gap"], height=0.62, zorder=3, edgecolor="white", linewidth=1.2,
            color=[LINE_TEAL if g < 0 else LINE_MAROON for g in rows["gap"]])
    ax.axvline(0, color=INK, linewidth=1.2, zorder=4)
    for yi, gap in zip(y, rows["gap"]):
        ax.annotate(f"{_signed(gap)} pp", xy=(gap, yi), xytext=(6 if gap >= 0 else -6, 0),
                    textcoords="offset points", va="center", ha="left" if gap >= 0 else "right",
                    fontsize=9, fontweight="bold", color=INK)
    top = len(rows) - 0.42
    ax.annotate("◀  Markets see less risk than the rating", xy=(0, top), xytext=(-8, 0),
                textcoords="offset points", ha="right", va="center", fontsize=8.5, fontweight="bold",
                color=LINE_TEAL)
    ax.annotate("Markets see more risk  ▶", xy=(0, top), xytext=(8, 0), textcoords="offset points",
                ha="left", va="center", fontsize=8.5, fontweight="bold", color=LINE_MAROON)
    reach = max(abs(rows["gap"].min()), abs(rows["gap"].max()))
    _style_row_axes(ax, rows["label"], lambda v, _: minus(f"{v:.1f}"))
    # Both sides share one scale; the margins only hold the value labels and
    # the two captions, so they need not be symmetric.
    ax.set_xlim(rows["gap"].min() - reach * 0.32, max(rows["gap"].max() + reach * 0.32, reach * 0.95))
    ax.set_ylim(-0.7, len(rows) + 0.3)
    ax.set_xlabel("Difference in the country risk premium, percentage points",
                  fontsize=EconStyle.FONT_SIZE_AXIS, color=INK_MUTED, labelpad=6)

    _t, _s = MACRO_TITLES["ratings_vs_markets"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    note = f"; no CDS market: {', '.join(no_cds)}" if no_cds else ""
    EconStyle.add_source(fig, f"Aswath Damodaran, NYU Stern ({_update_label(latest['date'])}{note})")
    EconStyle.save_chart(fig, output_dir / "20_macro_ratings_vs_markets.png")
    print("   ✓ Country Risk: Ratings vs Markets")


def chart_em_borrowing(engine, output_dir, mode="dashboard"):
    """Yields on EM companies' dollar bonds, high yield and investment grade, against the 10-year Treasury."""
    lines = [
        ("em_hy_yield", "EM high yield", LINE_ORANGE),
        ("em_ig_yield", "EM investment grade", LINE_TEAL),
        ("us_10y", "10-year Treasury", LINE_BLUE),
    ]
    daily = {ind_id: engine.get_transformed(ind_id) for ind_id, _, _ in lines}
    missing = [ind_id for ind_id, s in daily.items() if s.empty]
    if missing:
        raise ValueError(f"no data for {', '.join(missing)}")
    start = max(s.index[0] for s in daily.values())    # ICE BofA history on FRED starts three years back
    weekly = {ind_id: weekly_average(s[s.index >= start]) for ind_id, s in daily.items()}

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size="wide")
    first = min(s.index[0] for s in weekly.values())
    end = max(s.index[-1] for s in weekly.values())
    labels = []
    for ind_id, name, color in reversed(lines):        # Treasury drawn first, underneath
        s = weekly[ind_id]
        _draw_line(ax, *monotone_curve(s.index, s.values), color, width=HEAVY_LINE)
        _end_dot(ax, s.index[-1], s.iloc[-1], color, size=58)
        labels.append({"y": float(s.iloc[-1]), "name": name, "value": f"{s.iloc[-1]:.2f}%", "color": color})

    _style_line_axes(ax, lambda v, _: f"{v:.0f}%" if float(v).is_integer() else f"{v:.1f}%")
    _padded_ylim(ax, [s.min() for s in weekly.values()], [s.max() for s in weekly.values()])
    _time_axis(ax, first, end, right_margin=0.26)
    _margin_labels(ax, labels, end)

    _t, _s = MACRO_TITLES["em_borrowing"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "FRED (ICE BofA Emerging Markets Corporate Plus indices, US Treasury)")
    EconStyle.save_chart(fig, output_dir / "14_macro_em_borrowing.png")
    print("   ✓ Emerging-Market Dollar Borrowing Costs")


def chart_em_dollar(engine, output_dir, mode="dashboard"):
    """
    The Fed's EM dollar index and the rupee, plus whichever of the other
    emerging-market currencies has moved furthest each way over the window.
    All are quoted per dollar and indexed to 100 on their first common week,
    so a line above 100 is a currency that has weakened against the dollar.
    """
    series = {"em": engine.get_transformed("em_usd_index"), "inr": engine.get_transformed("usd_inr")}
    for key in EM_FX_PEERS:
        series[key] = engine.get_transformed(key)
    frame = pd.concat(series, axis=1).dropna()        # only days every currency traded; nothing filled
    if len(frame) < 250:
        raise ValueError(f"only {len(frame)} days with the EM dollar index and all {len(series) - 1} currencies")
    weekly = pd.DataFrame({col: weekly_average(frame[col]) for col in frame})
    indexed = weekly / weekly.iloc[0] * 100
    moves = (indexed.iloc[-1] - 100).drop(["em", "inr"])
    weakest, strongest = moves.idxmax(), moves.idxmin()   # per dollar: biggest rise, biggest fall

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size="wide")
    start, end = indexed.index[0], indexed.index[-1]
    ax.hlines(100, start, end, colors=INK, linewidth=0.9, zorder=2)
    lines = [("em", "EM dollar index", LINE_BLUE), ("inr", "Indian rupee", LINE_RUPEE),
             (weakest, EM_FX_PEERS[weakest][1], LINE_MAROON), (strongest, EM_FX_PEERS[strongest][1], LINE_TEAL)]
    labels = []
    for col, name, color in lines:
        _draw_line(ax, *monotone_curve(indexed.index, indexed[col].values), color, width=HEAVY_LINE, halo=False)
        _end_dot(ax, end, indexed[col].iloc[-1], color, size=58)
        change = indexed[col].iloc[-1] - 100
        labels.append({"y": float(indexed[col].iloc[-1]), "name": name,
                       "value": f"{'+' if change >= 0 else chr(0x2212)}{abs(change):.1f}%", "color": color})

    _style_line_axes(ax, lambda v, _: f"{v:.0f}")
    _padded_ylim(ax, [indexed[[c for c, _, _ in lines]].min().min(), 100],
                 [indexed[[c for c, _, _ in lines]].max().max(), 100])
    _time_axis(ax, start, end, right_margin=0.42)
    _margin_labels(ax, labels, end)

    _t, _s = MACRO_TITLES["em_dollar"][mode]
    EconStyle.set_title(ax, _t, _s)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, f"FRED (Federal Reserve H.10: nominal EME dollar index and {len(EM_FX_PEERS) + 1} "
                              f"emerging-market currencies)")
    EconStyle.save_chart(fig, output_dir / "15_macro_em_dollar.png")
    print("   ✓ The Dollar vs Emerging-Market Currencies")


# ═══════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════

def generate_macro_dashboard(mode="dashboard"):
    """Build every World tab output. Returns the process exit code (1 if anything automatic failed)."""
    month_str = datetime.now().strftime("%Y-%m")
    output_dir = PROJECT_ROOT / "output" / "macro" / month_str
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Generating Economics Hub - World tab")
    print(f"   Output: {output_dir}")
    print(f"   Mode:   {mode}\n")

    if FRED_API_KEY == "YOUR_FRED_API_KEY":
        print("FRED_API_KEY is not set (local .env or the GitHub Actions secret). Nothing generated.")
        return 1

    problems = []
    fred = FredFetcher(api_key=FRED_API_KEY)
    engine = MacroDataEngine(fred)

    print("   Fetching US series from FRED...")
    for ind_id in MACRO_INDICATORS:
        issue = engine.freshness_problem(ind_id)
        if issue:
            problems.append(issue)
        else:
            print(f"   ✓ {MACRO_INDICATORS[ind_id]['name']}")

    print("\n   Generating US and emerging-market charts...")
    for name, draw in [
        ("US inflation", lambda: chart_inflation(engine, output_dir, mode)),
        ("US labour", lambda: chart_labour(engine, output_dir, mode)),
        ("Fed balance sheet", lambda: chart_fed_balance_sheet(engine, output_dir, mode)),
        ("EM borrowing costs", lambda: chart_em_borrowing(engine, output_dir, mode)),
        ("dollar vs EM currencies", lambda: chart_em_dollar(engine, output_dir, mode)),
    ]:
        try:
            draw()
        except Exception as exc:  # noqa: BLE001 — reported below and fails the run
            problems.append(f"{name} chart: {type(exc).__name__}: {exc}")

    print("\n   Fetching US equity valuations (Shiller, Damodaran) and drawing their charts...")
    for name, fetch, draw in [
        ("Shiller CAPE (shillerdata.com)", fetch_shiller, lambda data: chart_cape(data, output_dir, mode)),
        ("Damodaran implied ERP (NYU Stern)", fetch_damodaran_erp,
         lambda data: chart_equity_risk_premium(data, output_dir, mode)),
    ]:
        try:
            draw(fetch())
        except Exception as exc:  # noqa: BLE001 — reported below and fails the run
            problems.append(f"{name}: {type(exc).__name__}: {exc}")

    print("\n   Fetching country risk premiums (Damodaran) and drawing their charts...")
    try:
        country_risk = fetch_country_risk()
    except Exception as exc:  # noqa: BLE001 — reported below and fails the run
        problems.append(f"Damodaran country risk premiums: {type(exc).__name__}: {exc}")
        country_risk = None
    if country_risk is not None:
        for name, draw in [("G20 equity risk premiums", chart_country_erp),
                           ("regional equity risk premiums", chart_regional_erp),
                           ("ratings vs markets", chart_ratings_vs_markets)]:
            try:
                draw(country_risk, output_dir, mode)
            except Exception as exc:  # noqa: BLE001 — reported below and fails the run
                problems.append(f"{name} chart: {type(exc).__name__}: {exc}")

    print("\n   Building the World snapshot (central banks, scoreboard, rate cycle, calendar)...")
    snapshot, series, snapshot_problems = build_snapshot(
        FRED_API_KEY, RBI_SENTINEL_DB, load_world_manual_rows()
    )
    problems += snapshot_problems

    print("\n   Generating World charts...")
    for name, draw in [
        ("global rate cycle", lambda: chart_rate_cycle(snapshot["rate_cycle"], output_dir, mode)),
        ("OECD leading indicators", lambda: chart_oecd_cli(series["cli"], output_dir, mode)),
    ]:
        try:
            draw()
        except Exception as exc:  # noqa: BLE001 — reported below and fails the run
            problems.append(f"{name} chart: {type(exc).__name__}: {exc}")

    snapshot["problems"] = problems
    write_snapshot(snapshot, output_dir / "world_snapshot.json")
    print("   ✓ world_snapshot.json")

    print(f"\n{len(list(output_dir.glob('*.png')))} charts in {output_dir}")
    if problems:
        print("\nFINISHED WITH PROBLEMS (nothing should be published until these are fixed):")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("Finished: all sources current.")
    return 0

def write_snapshot(snapshot, path):
    """JSON indented one space, with each list of numbers (the rate cycle's monthly counts) kept on one line."""
    text = json.dumps(snapshot, indent=1, ensure_ascii=False)
    text = re.sub(r"\[\n\s*(-?\d+(?:,\n\s*-?\d+)*)\n\s*\]",
                  lambda m: "[" + re.sub(r",\n\s*", ", ", m.group(1)) + "]", text)
    path.write_text(text + "\n", encoding="utf-8")


def refresh_rates(mode="dashboard"):
    """
    Central bank rates only, written into the published World edition
    (assets/macro/<latest month>/): the strip, the scoreboard's policy-rate
    column and the rate cycle chart. rates.yml runs this twice every weekday,
    so a decision shows the day it is announced instead of waiting for
    Saturday's full run. Nothing is written when no rate, last move or
    monthly count has changed, so the workflow then has nothing to commit.
    Returns the process exit code.
    """
    editions = sorted(p.parent for p in (PROJECT_ROOT / "assets" / "macro").glob("*/world_snapshot.json"))
    if not editions:
        print("No published World edition (assets/macro/*/world_snapshot.json) to refresh.")
        return 1
    folder = editions[-1]
    if FRED_API_KEY == "YOUR_FRED_API_KEY":
        print("FRED_API_KEY is not set (local .env or the GitHub Actions secret). Nothing refreshed.")
        return 1
    print(f"Refreshing central bank rates in {folder.relative_to(PROJECT_ROOT)}")

    with open(folder / "world_snapshot.json") as fh:
        snapshot = json.load(fh)
    update, problems = build_rate_update(FRED_API_KEY, RBI_SENTINEL_DB)
    if problems:
        print("\nFINISHED WITH PROBLEMS (nothing written):")
        for p in problems:
            print(f"   - {p}")
        return 1

    fresh = apply_rate_update(snapshot, update, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
    for bank in update["central_banks"]:
        move = bank.get("last_move") or {}
        print(f"   {bank['id']:<5} {bank.get('display', '-'):>10}   last move {move.get('bps', 0):+d} bps "
              f"on {move.get('date', '-')}")
    if rates_fingerprint(fresh) == rates_fingerprint(snapshot):
        print("\nNo rate or monthly count has changed: nothing written.")
        return 0

    chart_rate_cycle(fresh["rate_cycle"], folder, mode)
    write_snapshot(fresh, folder / "world_snapshot.json")
    print("   ✓ world_snapshot.json")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Generate the Economics Hub World tab")
    parser.add_argument("--preview", action="store_true", help="Lower DPI for quick test")
    parser.add_argument("--rates-only", action="store_true",
                        help="Refresh only the central bank rates and rate cycle chart in the published edition")
    parser.add_argument(
        "--mode",
        choices=["dashboard", "newsletter"],
        default="dashboard",
        help="Title mode: 'dashboard' for standard titles, 'newsletter' for narrative Substack titles",
    )
    args = parser.parse_args()

    if args.preview:
        EconStyle.DPI = 120

    if args.rates_only:
        sys.exit(refresh_rates(mode=args.mode))
    sys.exit(generate_macro_dashboard(mode=args.mode))

if __name__ == "__main__":
    main()
