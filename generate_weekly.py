#!/usr/bin/env python3
"""
Economics Hub — Weekly Dashboard Generator
============================================
Run this script every Friday/Saturday to generate the full
weekly dashboard. Produces all charts.

Usage:
    python generate_weekly.py              # Live data (requires FRED_API_KEY)
    python generate_weekly.py --preview    # Lower DPI for quick preview

There is no mock-data mode: if a data source or the API key is missing, the
run fails instead of publishing invented numbers.

The script:
1. Fetches live data
2. Calculates weekly changes
3. Generates all dashboard charts
4. Saves everything to output/weekly/YYYY-MM-DD/
"""

import sys
import os
import math
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from charts.style import EconStyle
from charts.templates.change_bars import render_change_bars
from charts.templates.trend_line import TrendLineChart
from charts.templates.yield_curve import YieldCurveChart
from charts.templates.summary_table import SummaryTable


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

WEEKLY_TITLES: dict[str, dict[str, tuple[str, str]]] = {
    "equities_weekly": {
        "dashboard": (
            "Global Equities",
            "Weekly percentage change across major indices  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Global Equities Performance",
            "Weekly percentage change across major indices  ·  {date}",
        ),
    },
    "yield_curve": {
        "dashboard": (
            "US Treasury Yield Curve",
            "Current vs. 4 weeks ago vs. 52 weeks ago",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Bond Market Is Pricing an Immediate Shock",
            "Current US Treasury yield curve movements relative to 4 and 52 weeks ago",
        ),
    },
    "commodities_weekly": {
        "dashboard": (
            "Global Commodities",
            "Weekly percentage change  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Iran Risk Is Keeping Oil Prices Elevated",
            "The Iran shock continues to impact broader commodity markets",
        ),
    },
    "vix_trend": {
        "dashboard": (
            "VIX Volatility Index — Trailing 12 Months",
            "CBOE VIX (30-day) vs. VIX 3-Month Term Structure",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The VIX Term Structure Signals a Contained Shock",
            "The 30-day VIX rising above the 3-month VIX suggests markets view the shock as a short-term event",
        ),
    },
    "fx_weekly": {
        "dashboard": (
            "Foreign Exchange — Weekly Performance",
            "Weekly percentage change across major currency pairs  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Foreign Exchange — Weekly Performance",
            "Weekly percentage change across major currency pairs  ·  {date}",
        ),
    },
    "credit_spreads": {
        "dashboard": (
            "IG & HY Credit Spreads",
            "ICE BofA Investment Grade OAS (right) vs. High Yield OAS (left)  ·  basis points",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Credit Market Is Flashing a Warning",
            "High yield spreads widening above 400bps has historically preceded equity drawdowns",
        ),
    },
    "breakeven_inflation": {
        "dashboard": (
            "Breakeven Inflation — 5Y & 10Y",
            "Market-implied inflation expectations vs. Fed 2% target  ·  TIPS-derived",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Bond Market Doesn't Believe Inflation Is Over",
            "5Y and 10Y breakeven rates remain above the Fed's 2% target",
        ),
    },
    "real_yields": {
        "dashboard": (
            "Real Yields — 5Y & 10Y TIPS",
            "Inflation-adjusted Treasury yields  ·  positive = restrictive monetary conditions",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Real Rates at Multi-Decade Highs Are Squeezing Valuations",
            "Positive real yields compress equity multiples and strengthen the dollar",
        ),
    },
    "copper_gold_ratio": {
        "dashboard": (
            "Copper/Gold Ratio & 10Y Treasury Yield",
            "Growth expectations proxy vs. sovereign yield direction",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Copper Is Signalling a Global Growth Slowdown",
            "The Gundlach indicator: falling Copper/Gold ratio has historically led lower bond yields",
        ),
    },
    "stock_bond_correlation": {
        "dashboard": (
            "Are Bonds Still Hedging Equities?",
            "60-day rolling correlation of S&P 500 and long Treasury daily returns  ·  below zero = bonds cushion equity falls",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Are Bonds Still Hedging Equities?",
            "60-day rolling correlation of S&P 500 and long Treasury daily returns  ·  below zero = bonds cushion equity falls",
        ),
    },
    "sector_rotation_12m": {
        "dashboard": (
            "S&P 500 Sector Rotation — Trailing 12 Months",
            "Total return by sector over the past year  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Where the Year's Money Went",
            "Total return by S&P 500 sector over the past year  ·  {date}",
        ),
    },
    "india_sector_rotation_12m": {
        "dashboard": (
            "NIFTY Sector Rotation — Trailing 12 Months",
            "Price return by sector over the past year, not total return  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Where India's Money Went This Year",
            "Price return by NIFTY sector over the past year, not total return  ·  {date}",
        ),
    },
    "defensives_cyclicals": {
        "dashboard": (
            "Defensive vs. Cyclical Sectors",
            "Staples, utilities and healthcare against discretionary, technology and industrials  ·  rising = money moving to safety",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Investors Are Rotating Into Defensives",
            "Staples, utilities and healthcare against discretionary, technology and industrials  ·  rising = money moving to safety",
        ),
    },
    "risk_appetite_ratio": {
        "dashboard": (
            "SPHB/SPLV — High Beta vs. Low Volatility",
            "Equity-only risk appetite signal  ·  rising = investors chasing risk within equities",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "High-Beta Stocks Are Being Abandoned",
            "A falling SPHB/SPLV ratio signals investors rotating to defensive equities",
        ),
    },
    "market_breadth": {
        "dashboard": (
            "Market Breadth — RSP/SPY Equal vs. Cap-Weight",
            "Equal-weight S&P 500 vs. cap-weight  ·  falling ratio = rally narrowing to mega-caps",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Only the Magnificent Seven Are Holding Up the Market",
            "The equal-weight S&P 500 is at its weakest against the cap-weighted index in 20 years",
        ),
    },
    "bond_etf_returns": {
        "dashboard": (
            "Bond ETF Total Returns — Trailing 12 Months",
            "Duration, investment grade credit, and high yield indexed to 100  ·  total return",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Fixed Income Hierarchy Is Breaking Down",
            "HYG outperforming TLT despite rising rates is a paradox worth watching",
        ),
    },
    "gold_spx_ratio": {
        "dashboard": (
            "Gold/SPX Safe Haven Ratio",
            "Rotation between safe assets and growth  ·  rising = defensive positioning",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Gold Is Reclaiming Its Role as the Macro Hedge",
            "Gold/SPX ratio rising above its 52-week mean signals institutional flight from equities",
        ),
    },
    "commodities_vs_equities": {
        "dashboard": (
            "Commodities vs. Equities",
            "S&P GSCI relative to the S&P 500, log scale  ·  rising = commodities outperforming",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Commodities Are Near a 40-Year Low Against Stocks",
            "The S&P GSCI relative to the S&P 500 has rarely been lower since 1984",
        ),
    },
    "em_fx_weekly": {
        "dashboard": (
            "EM Currency Performance vs. USD — Weekly",
            "Weekly % change vs. the dollar  ·  positive = EM currency appreciated  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Dollar Strength Is Crushing EM Currencies",
            "The dollar index surge is transmitting directly into EM balance-of-payments stress",
        ),
    },
    "em_equity_weekly": {
        "dashboard": (
            "Emerging Market Equities — Weekly Performance",
            "Country ETF weekly % change  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "India Decouples as EM Peers Sell Off",
            "India's equity outperformance vs. China and Korea widening on a weekly basis",
        ),
    },
    "em_stress_monitor": {
        "dashboard": (
            "Emerging Markets Stress Monitor",
            "EM High Yield & Corporate Spreads vs. USD Strength",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Dollar Strength Tests Emerging Markets",
            "EM credit spreads react to the soaring Trade-Weighted Dollar",
        ),
    },
    "em_vix": {
        "dashboard": (
            "CBOE Emerging Markets ETF Volatility Index (VXEEM)",
            "VXEEM — implied volatility of EEM options · Higher = more EM fear · FRED: VXEEMCLS",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "EM Fear Is Spiking",
            "CBOE EM Volatility Index signals rising tail risk across emerging markets",
        ),
    },
    "india_vs_em": {
        "dashboard": (
            "India vs. EM Peers — Trailing 12 Months",
            "INDA, EEM, EWY, EWT, MCHI, EWZ indexed to 100 at start  ·  total return comparison",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "India Is the Only EM Story Worth Telling Right Now",
            "INDA's 12-month outperformance vs. EEM, China, and Korea is widening structurally",
        ),
    },
    "crude_oil_curve": {
        "dashboard": (
            "The Crude Oil Futures Curve",
            "WTI price for each delivery month  ·  falling curve = supply tight now  ·  rising = glut",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Oil Traders Are Paying a Premium for Barrels Today",
            "The futures curve has swung into steep backwardation as prompt supply tightens",
        ),
    },
    "gold_real_rates": {
        "dashboard": (
            "Gold Has Broken Free of Real Interest Rates",
            "A ten-year path, one step per quarter  ·  10-year TIPS real yield against the gold price",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Rule That No Longer Governs Gold",
            "Gold once fell whenever real yields rose; since 2022 the two have climbed together",
        ),
    },
    "commodities_breadth": {
        "dashboard": (
            "How Broad Is the Commodity Rally?",
            "Share of 13 major commodities above their own 200-day average  ·  smoothed over 3 months",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Commodity Rally Is Narrower Than It Looks",
            "Energy is carrying the complex while precious metals roll over",
        ),
    },
    "commodity_cycle": {
        "dashboard": (
            "The Long Commodity Cycle",
            "S&P GSCI adjusted for US inflation, monthly since {start}  ·  {start}–{end} average = 100",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Commodities Move in Decade-Long Cycles",
            "Inflation-adjusted commodity prices have swung between booms and busts for four decades",
        ),
    },
    "agri_weekly": {
        "dashboard": (
            "Agricultural Commodities — Weekly Performance",
            "Soft commodities weekly % change  ·  CBOT & ICE futures  ·  {date}",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Food Inflation Is Making a Comeback",
            "Wheat, corn, and coffee futures surging on supply shock signals",
        ),
    },
    "eth_btc_ratio": {
        "dashboard": (
            "ETH/BTC Ratio — Altcoin Appetite Signal",
            "Ethereum vs. Bitcoin relative strength  ·  rising = risk-on within crypto",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "ETH Is Losing Ground to Bitcoin",
            "ETH/BTC ratio breaking below its 52-week mean signals institutional capital concentrating in Bitcoin",
        ),
    },
    "btc_global_m2": {
        "dashboard": (
            "Bitcoin vs. Global M2 Money Supply",
            "BTC price (log scale, left) vs. the broad money of seven major economies in US dollars (right)",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Bitcoin vs. Global Liquidity",
            "Every spell of shrinking global M2 in dollars since 2013 came in a bitcoin bear market",
        ),
    },
    "btc_mvrv_zscore": {
        "dashboard": (
            "Bitcoin MVRV Z-Score",
            "How stretched bitcoin's price is against what holders paid  ·  every major cycle low came below zero",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Where Bitcoin Sits in Its Cycle",
            "The MVRV Z-score has fallen below zero at every bear-market low; its highs have come lower each cycle",
        ),
    },
    "btc_zscore_global_m2": {
        "dashboard": (
            "Bitcoin and Global M2: When the Link Breaks",
            "MVRV Z-score (top) and bitcoin's 12-month correlation with global M2 (bottom)",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Bitcoin Has Stopped Tracking Global Liquidity",
            "Its correlation with global M2 has broken down as the MVRV Z-score came off its cycle high",
        ),
    },
    "move_index": {
        "dashboard": (
            "ICE BofA MOVE Index — Bond Market Volatility",
            "Implied volatility of US Treasury options  ·  basis points  ·  trailing 12 months",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Bond Market's Fear Gauge Is Flashing",
            "MOVE Index surging signals institutional hedging activity in US Treasuries",
        ),
    },
    "india_vix_vs_us": {
        "dashboard": (
            "India VIX vs. US VIX — Trailing 12 Months",
            "NSE India VIX (left) vs. CBOE US VIX (right)  ·  India-specific vs. global risk",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "India's Fear Gauge Is Spiking Independently of Global Volatility",
            "India VIX diverging from US VIX signals domestic political or RBI event risk",
        ),
    },
}

# Where the long-view equity ratios (market breadth and SPHB/SPLV) start:
# early enough to take in the 2008 crisis. SPHB/SPLV starts later, at the
# ETFs' launch in May 2011.
LONG_VIEW_START = "2006-01-01"

def get_output_dir():
    """
    Create and return the output directory for this week.

    Any PNG left by an earlier run on the same day is removed first. The run
    redraws the complete set every time, so anything surviving from a previous
    run is a chart that no longer exists — and charts/loader.py serves the
    newest folder across assets/ and output/, so a stale file keeps appearing
    on the dashboard (under "Other", once its keywords stop matching a section)
    long after the code that drew it was deleted.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_dir = PROJECT_ROOT / "output" / "weekly" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()
    return out_dir


def _turning_points(series, swing, log=True):
    """
    The highs and lows a series turned from by at least `swing`, measured in
    logs (0.45 is a 57% rise or a 36% fall), as [(date, value, "high"|"low")].
    With log=False the swing is in the series' own units, for one that
    crosses zero (a Z-score).

    A turn counts only once the reversal has happened, so the latest peak or
    trough is never marked while the market could still carry on past it. The
    first counts only if the series moved at least as far to reach it, so the
    first month of data is never taken for a turn.
    """
    import numpy as np

    v = series.to_numpy(dtype=float)
    if log:
        v = np.log(v)
    turns, trend, hi, lo = [], 0, 0, 0
    for i in range(1, len(v)):
        if trend >= 0:
            if v[i] > v[hi]:
                hi = i
            if v[hi] - v[i] >= swing:
                turns.append((hi, "high"))
                trend, lo = -1, i
        if trend <= 0:
            if v[i] < v[lo]:
                lo = i
            if v[i] - v[lo] >= swing:
                turns.append((lo, "low"))
                trend, hi = 1, i
    if turns and abs(v[turns[0][0]] - v[0]) < swing:
        turns = turns[1:]
    return [(series.index[i], float(series.iloc[i]), kind) for i, kind in turns]


def _mark_turns(ax, turns, color, label=lambda when, level: when.strftime("%b %Y")):
    """A dot on each turn, labelled (by default with its date) above a high and below a low."""
    for when, level, kind in turns:
        ax.plot(when, level, "o", ms=5.5, color=color, mec="white", mew=1.3, zorder=6)
        high = kind == "high"
        ax.annotate(label(when, level), xy=(when, level), xytext=(0, 8 if high else -8),
                    textcoords="offset points", ha="center", va="bottom" if high else "top",
                    fontsize=8.5, fontweight="bold", color=EconStyle.INK, zorder=6)


def _global_m2_weekly(fred_fetcher, start="2009-01"):
    """
    Global M2 in US dollar trillions, weekly on Fridays: the broad money of
    the United States, China, the euro area, Japan, the UK, Canada and
    Australia, each at that week's exchange rate. These are the economies in
    the global M2 of Lyn Alden's liquidity report that the OECD publishes;
    Russia, the eighth, is left out.

    Money supply is monthly and exchange rates daily, so each economy's
    figure is interpolated between its monthly prints and held at the latest
    one until the next; the dollar total still moves every week with the
    exchange rates, as the published composites do.
    """
    import pandas as pd
    from data.fetchers.oecd_fetcher import fetch_broad_money
    # FRED's H.10 rate for each currency, and whether it is quoted in dollars per unit.
    RATES = {"CHN": ("DEXCHUS", False), "EA20": ("DEXUSEU", True), "JPN": ("DEXJPUS", False),
             "GBR": ("DEXUSUK", True), "CAN": ("DEXCAUS", False), "AUS": ("DEXUSAL", True)}
    money = fetch_broad_money(["USA", *RATES], start=start)
    weeks = pd.date_range(money.index[0], datetime.now(), freq="W-FRI")
    local = (money.reindex(money.index.union(weeks)).interpolate(method="time", limit_area="inside")
             .reindex(weeks).ffill())
    usd = {"USA": local["USA"]}
    years = datetime.now().year - int(start[:4]) + 1
    for area, (series_id, dollars_per_unit) in RATES.items():
        rate = fred_fetcher.fetch_series(series_id, period_years=years)
        rate.index = pd.to_datetime(rate.index)
        if (datetime.now() - rate.index[-1]).days > 30:
            raise ValueError(f"{series_id} has no exchange rate since {rate.index[-1]:%d %b %Y}")
        rate = rate.resample("W-FRI").last().reindex(weeks).ffill()
        usd[area] = local[area] * rate if dollars_per_unit else local[area] / rate
    return pd.DataFrame(usd).dropna().sum(axis=1) / 1e12


def _label_returns(ax, ends, decimals=0):
    """
    Each indexed line's change since the start ("+12%"), just right of its end.

    `ends` is [{"x": last date, "y": last level on a start = 100 index,
    "color": the line's colour}]. Labels are set in ink, joined to their line
    by a thin leader in its colour, and spread apart where two would collide.
    The x-axis is widened 7% to make room, without month ticks past the data.
    """
    import matplotlib.dates as mdates
    from generate_macro import _spread_labels_centred
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x0, x1 + (x1 - x0) * 0.07)
    last = max(mdates.date2num(e["x"]) for e in ends)
    ax.set_xticks([t for t in ax.get_xticks() if x0 <= t <= last])     # a tick outside would widen the axis
    lo, hi = ax.get_ylim()
    label_ys = _spread_labels_centred([e["y"] for e in ends], (hi - lo) * 0.055)
    for e, ly in zip(ends, label_ys):
        lx = mdates.date2num(e["x"]) + (x1 - x0) * 0.015      # just right of the end dot
        ret = e["y"] - 100
        ax.annotate(f"{'+' if ret >= 0 else '−'}{abs(ret):.{decimals}f}%", xy=(e["x"], e["y"]),
                    xytext=(lx, ly), textcoords="data", va="center", ha="left", fontsize=9.5,
                    fontweight="semibold", color=EconStyle.INK, zorder=8, annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color=e["color"], linewidth=0.9,
                                    shrinkA=0, shrinkB=2, relpos=(0, 0.5)))


def _recession_bands(ax, usrec, note="Shaded: US recessions"):
    """
    Grey bands over the NBER recessions, as FRED's own charts draw them.

    `usrec` is FRED's USREC: monthly, 1 through a recession and 0 otherwise.
    The bands are read from the series rather than typed in, so a future
    recession appears by itself. Returns the number of bands drawn.

    Call this last: a band is a patch like any other, so it widens the axes to
    the 1960s if drawn on a chart that starts later. The x limits in force when
    it is called are what the chart keeps.
    """
    import pandas as pd
    import matplotlib.dates as mdates
    flag = pd.Series(usrec).astype(int)
    flag.index = pd.to_datetime(flag.index)
    edges = flag.diff().fillna(flag.iloc[0])
    x0, x1 = ax.get_xlim()
    drawn = 0
    for start in flag.index[edges == 1]:
        after = flag.index[(flag.index > start) & (edges == -1)]
        end = after[0] if len(after) else flag.index[-1]
        if mdates.date2num(end) < x0 or mdates.date2num(start) > x1:
            continue                              # outside the years on screen
        ax.axvspan(start, end, color="#4B5563", alpha=0.13, lw=0, zorder=1)
        drawn += 1
    ax.set_xlim(x0, x1)
    if note and drawn:
        ax.annotate(note, xy=(0.01, 0.03), xycoords="axes fraction", ha="left", va="bottom",
                    fontsize=8.5, color=EconStyle.INK_MUTED, zorder=6)
    return drawn


# ---------------------------------------------------------------------------
# Data-quality guardrail
# ---------------------------------------------------------------------------
# Yahoo Finance periodically rate-limits/blocks CI IP ranges. When that
# happens yfinance doesn't always raise — it can hand back a few tickers
# with implausible, near-identical values (unrelated markets don't move in
# lockstep to two decimal places). Publishing that is worse than publishing
# nothing, so every multi-ticker bar chart is checked before it's saved and
# skipped — not overwritten with garbage — if the fetch looks broken.
SKIPPED_CHARTS = []


def _bad_fetch(values, requested, min_ratio=0.5, min_ok=2):
    """True if a batch of weekly-change values looks like a fetch outage."""
    # NaN/inf can't be plotted (one NaN collapses the axis) and would slip
    # past the checks below, since NaN counts as a value and never equals itself.
    if not all(math.isfinite(v) for v in values):
        return True
    if len(values) < max(min_ok, math.ceil(requested * min_ratio)):
        return True
    if len(values) >= 3 and len({round(v, 2) for v in values}) == 1:
        return True
    return False


def _flag_skipped(chart_name, got, requested):
    msg = f"{chart_name} ({got}/{requested} tickers usable, or values looked degenerate)"
    SKIPPED_CHARTS.append(msg)
    print(f"   ⚠⚠ SKIPPED — {msg}; Yahoo Finance likely rate-limited this run")
    print(f"::warning::Weekly dashboard skipped '{chart_name}' this run — {msg}")


def generate_with_live_data(output_dir, mode="dashboard"):
    """Generate dashboard with live API data from yfinance + FRED."""
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    from data.fetchers.fred_fetcher import FredFetcher
    from config.settings import INDICATORS, FRED_API_KEY

    if not FRED_API_KEY or FRED_API_KEY == "YOUR_FRED_API_KEY":
        sys.exit(
            "FRED_API_KEY is not set. Add it to .env locally or to the GitHub Actions secrets.\n"
            "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
        )

    print("📊 Generating Economics Hub Weekly Dashboard (LIVE DATA)")
    print(f"   Output: {output_dir}\n")

    yf_fetcher = YFinanceFetcher()
    fred_fetcher = FredFetcher(api_key=FRED_API_KEY)
    date_label = datetime.now().strftime("%d %b %Y")

    # ── Helper: fetch weekly change for an indicator ──
    def get_weekly(ind_id):
        ind = INDICATORS[ind_id]
        try:
            if ind["source"] == "yfinance":
                result = yf_fetcher.weekly_change(ind["ticker"])
                if result is None:
                    return None
                return {
                    "level": result["current"],
                    "change": result["change_pct"] / 100,  # as fraction
                    "change_pct": result["change_pct"],
                }
            elif ind["source"] == "fred":
                result = fred_fetcher.weekly_change(ind["series"])
                if result is None:
                    return None
                return {
                    "level": result["current"],
                    "change": result["change_abs"],
                    "change_bps": result["change_bps"],
                }
        except Exception as e:
            print(f"   ⚠ Failed: {ind['name']} ({e})")
            return None
        
    # ── Helper: Fetch YTD change ──
    def get_ytd_change(ind_id):
        ind = INDICATORS[ind_id]
        try:
            # Start of current year
            start_date = f"{datetime.now().year}-01-01"
            
            if ind["source"] == "yfinance":
                # Fetch history since Jan 1
                hist = yf_fetcher.fetch(ind["ticker"], start=start_date)
                if hist.empty: return None
                
                start_price = hist["Close"].iloc[0]
                current_price = hist["Close"].iloc[-1]
                
                # Calculate % change
                return (current_price - start_price) / start_price

            elif ind["source"] == "fred":
                # FIX: fetch_series doesn't have start_date param
                # Fetch last 6 months, then filter to current year
                s = fred_fetcher.fetch_series(ind["series"], period_years=0.5)
                if len(s) < 2: return None
                
                # Filter to current year
                current_year = datetime.now().year
                s_ytd = s[s.index.year == current_year]
                if len(s_ytd) < 2: return None
                
                start_val = float(s_ytd.iloc[0])
                curr_val = float(s_ytd.iloc[-1])
                
                if ind["change_type"] == "abs":
                    return (curr_val - start_val) # Absolute change for yields
                else:
                    return (curr_val - start_val) / start_val

        except Exception as e:
            return None
        return None

    # ── Helper: fetch 12-month close series ──
    def get_trend(ind_id):
        ind = INDICATORS[ind_id]
        try:
            if ind["source"] == "yfinance":
                series = yf_fetcher.get_close_series(ind["ticker"], period="1y")
                if series.empty:
                    return None, None
                dates = series.index.to_pydatetime().tolist()
                values = series.values.tolist()
                return dates, values
            elif ind["source"] == "fred":
                series = fred_fetcher.fetch_series(ind["series"], period_years=1)
                if len(series) == 0:
                    return None, None
                dates = series.index.to_pydatetime().tolist()
                values = series.values.tolist()
                return dates, values
        except Exception as e:
            print(f"   ⚠ Trend failed: {ind['name']} ({e})")
            return None, None

    # ═══════════════════════════════════════════
    # FETCH ALL WEEKLY CHANGES
    # ═══════════════════════════════════════════
    print("   Fetching weekly changes...")
    weekly_data = {}
    for ind_id in INDICATORS:
        w = get_weekly(ind_id)
        if w:
            weekly_data[ind_id] = w
            print(f"   ✓ {INDICATORS[ind_id]['name']}")
        else:
            print(f"   ✗ {INDICATORS[ind_id]['name']} (skipped)")

    # ═══════════════════════════════════════════
    # BUILD CHART DATA & GENERATE
    # ═══════════════════════════════════════════

    def build_bar_data(ind_ids, change_type="pct"):
        names, values, color_keys = [], [], []
        for ind_id in ind_ids:
            if ind_id not in weekly_data:
                continue
            ind = INDICATORS[ind_id]
            w = weekly_data[ind_id]
            names.append(ind["name"])
            if change_type == "pct":
                values.append(w["change_pct"])
            else:
                values.append(w["change"])
            color_keys.append(ind.get("color_key", "us"))
        return names, values, color_keys

    # ── 1. EQUITIES ──
    # ── 1. EQUITIES ──
    print("\n   [1/8] Equities — Weekly Change Bars")
    eq_ids = ["sp500", "dow", "nasdaq", "ftse100", "eurostoxx50", "nifty50", "shanghai", "hangseng", "nikkei225"]
    names, values, cks = build_bar_data(eq_ids)

    if _bad_fetch(values, len(eq_ids)):
        _flag_skipped("Equities — Weekly Bar Chart", len(values), len(eq_ids))
    else:
        _t, _s = WEEKLY_TITLES["equities_weekly"][mode]
        fig = render_change_bars(names, values, _t, _s.format(date=date_label), "Yahoo Finance")
        EconStyle.save_chart(fig, output_dir / "01_equities_weekly.png")

    print("   [2/8] Equities — 12-Month Trends")
    trend = TrendLineChart()
    # Five markets on five continents' clocks; the Dow and NASDAQ would only add two more US lines.
    # Euro Stoxx 50 shares FTSE 100's region colour, so it gets its own.
    trend_colors = {"eurostoxx50": EconStyle.LINE_MAROON}
    for ind_id in ["sp500", "ftse100", "eurostoxx50", "nifty50", "nikkei225"]:
        dates, vals = get_trend(ind_id)
        if dates:
            ind = INDICATORS[ind_id]
            trend.add_series(ind["name"], dates, vals, color_key=ind["color_key"],
                             color=trend_colors.get(ind_id))
    trend.render(title="Major Indices — Trailing 12 Months",
                 subtitle="Indexed to 100 at start  ·  S&P 500, FTSE 100, Euro Stoxx 50, Nifty 50, Nikkei 225",
                 source="Yahoo Finance", normalize=True, ylabel="Indexed (start = 100)")
    trend.save(output_dir / "02_equities_trend.png")

    # ── 2. FX ──

    print("   [4/8] FX — 12-Month Trends")
    trend = TrendLineChart()
    for ind_id in ["dxy", "eurusd","usdinr", "usdjpy"]:
        dates, vals = get_trend(ind_id)
        if dates:
            ind = INDICATORS[ind_id]
            # "DXY", as the subtitle has it: the full name would end "(DXY) (+3.7%)".
            trend.add_series("DXY" if ind_id == "dxy" else ind["name"], dates, vals,
                             color_key=ind["color_key"])
    trend.render(title="Key FX Rates — Trailing 12 Months",
                 subtitle="Indexed to 100 at start  ·  DXY, EUR/USD, USD/INR, USD/JPY",
                 source="Yahoo Finance", normalize=True, ylabel="Indexed (start = 100)")
    trend.save(output_dir / "04_fx_trend.png")                                      # <--- Add this

    # ── 3. YIELDS ──

    print("   [6/8] Yields — US Treasury Yield Curve")
    try:
        yc = YieldCurveChart()
        
        # 1. Current Curve
        cur = fred_fetcher.fetch_yield_curve()
        yc.add_curve(datetime.now().strftime("%d %b %Y"), 
                     cur["tenors"], 
                     cur["yields"],  # Already clean floats from fixed fred_fetcher
                     style="current")

        # 2. 4 Weeks Ago
        try:
            hist_4w = fred_fetcher.fetch_yield_curve_historical(weeks_ago=4)
            w4_date = (datetime.now() - __import__('datetime').timedelta(weeks=4)).strftime("%d %b %Y")
            yc.add_curve(w4_date, 
                         hist_4w["tenors"], 
                         hist_4w["yields"],
                         style="4w_ago")
        except Exception: pass

        # 3. 52 Weeks Ago
        try:
            hist_52w = fred_fetcher.fetch_yield_curve_historical(weeks_ago=52)
            w52_date = (datetime.now() - __import__('datetime').timedelta(weeks=52)).strftime("%d %b %Y")
            yc.add_curve(w52_date, 
                         hist_52w["tenors"], 
                         hist_52w["yields"],
                         style="52w_ago")
        except Exception: pass
        
        _t, _s = WEEKLY_TITLES["yield_curve"][mode]
        yc.render(title=_t, subtitle=_s, source="FRED")
        yc.save(output_dir / "06_yield_curve.png")
    except Exception as e:
        print(f"   ⚠ Yield curve failed: {e}")

    # ── 4. COMMODITIES ──
    print("   [7/8] Commodities — Weekly Change Bars")
    cm_ids = ["brent", "wti", "gold", "silver", "copper", "natgas", "uranium"]
    names, values, cks = build_bar_data(cm_ids)

    _t, _s = WEEKLY_TITLES["commodities_weekly"][mode]
    fig = render_change_bars(names, values, _t, _s.format(date=date_label), "Yahoo Finance")
    if fig:
        EconStyle.save_chart(fig, output_dir / "07_commodities_weekly.png")

    print("   [8/8] Commodities — 12-Month Trends")
    trend = TrendLineChart()
    for ind_id in ["brent", "gold", "silver", "copper"]:
        dates, vals = get_trend(ind_id)
        if dates:
            ind = INDICATORS[ind_id]
            trend.add_series(ind["name"], dates, vals, color_key=ind["color_key"])
    trend.render(title="Key Commodities — Trailing 12 Months",
                 subtitle="Indexed to 100 at start  ·  Brent Crude, Gold, Silver, Copper",
                 source="Yahoo Finance", normalize=True, ylabel="Indexed (start = 100)")
    trend.save(output_dir / "08_commodities_trend.png")

    # ── 5. VIX — FEAR GAUGE ──
    print("   [9/11] VIX — 12-Month Trend")
    try:
        vix_dates, vix_vals = get_trend("vix")
        vix3m_dates, vix3m_vals = get_trend("vix3m")
        
        if vix_dates:
            trend = TrendLineChart()
            trend.add_series("VIX", vix_dates, vix_vals, color_key="special_black")
            trend.add_series("VIX 3-Month", vix3m_dates, vix3m_vals, color_key="pink")
            
            _t, _s = WEEKLY_TITLES["vix_trend"][mode]
            trend.render(title=_t, subtitle=_s, source="Yahoo Finance (VIX), FRED (VIX 3-Month, VXVCLS)", ylabel="VIX Level")
            trend.save(output_dir / "09_vix_trend.png")
    except Exception as e:
        print(f"   ⚠ VIX chart failed: {e}")

    # ── MOVE INDEX ──
    print("   [09b] ICE BofA MOVE Index — Bond Volatility")
    try:
        # Pull from yfinance instead of FRED
        move_s = yf_fetcher.get_close_series("^MOVE", period="1y")

        if len(move_s) > 20:
            move_s.index = move_s.index.tz_localize(None) # Strip timezone
            fig, ax = EconStyle.create_figure(size="wide")

            color_move = "#7C3AED"  # Purple

            move_dates = move_s.index.to_pydatetime()
            move_vals  = move_s.values

            ax.plot(move_dates, move_vals, color=color_move, linewidth=2.5, label="MOVE Index")
            ax.fill_between(move_dates, move_vals, move_vals.min(),
                            alpha=0.06, color=color_move)

            ax.axhline(100, color="#6B7280", linestyle="--", linewidth=1.2, alpha=0.7,
                       label="100 — Elevated vol threshold")

            ax.annotate(
                f"{move_vals[-1]:.0f}",
                xy=(move_dates[-1], move_vals[-1]),
                xytext=(8, 0), textcoords="offset points",
                fontsize=9, fontweight="bold", color=color_move,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85),
            )

            ax.set_ylabel("MOVE Index (bps)", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=9)

            _t, _s = WEEKLY_TITLES["move_index"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (ICE BofA)")
            EconStyle.save_chart(fig, output_dir / "09_move_index.png")
    except Exception as e:
        print(f"   ⚠ MOVE Index chart failed: {e}")

    # ── 6. SECTOR ROTATION ──
    print("   [10/11] S&P 500 Sector Rotation")
    # Shared with the trailing-12-month chart below, so the two always cover the same sectors.
    SECTOR_ETFS = {
        "XLK": "Technology",
        "XLF": "Financials",
        "XLE": "Energy",
        "XLV": "Healthcare",
        "XLI": "Industrials",
        "XLC": "Comms",
        "XLY": "Consumer Disc",
        "XLP": "Consumer Staples",
        "XLRE": "Real Estate",
        "XLU": "Utilities",
        "XLB": "Materials",
    }
    try:
        sector_data = []
        for ticker, name in SECTOR_ETFS.items():
            try:
                result = yf_fetcher.weekly_change(ticker)
                if result:
                    sector_data.append((name, result["change_pct"]))
            except Exception:
                pass

        if sector_data:
            # Sort by performance (best to worst)
            sector_data.sort(key=lambda x: x[1], reverse=True)
            s_names = [s[0] for s in sector_data]
            s_values = [s[1] for s in sector_data]

            if _bad_fetch(s_values, len(SECTOR_ETFS)):
                _flag_skipped("S&P 500 Sector Rotation", len(s_values), len(SECTOR_ETFS))
            else:
                fig = render_change_bars(s_names, s_values, "S&P 500 Sector Rotation",
                                         f"Weekly performance by sector  ·  {date_label}",
                                         "Yahoo Finance (SPDR ETFs)")
                EconStyle.save_chart(fig, output_dir / "10_sector_rotation.png")
    except Exception as e:
        print(f"   ⚠ Sector rotation failed: {e}")

    # ── 6b. SECTOR ROTATION, TRAILING 12 MONTHS ──
    # The weekly chart above answers "what moved this week"; this one answers "what has
    # led the year", which a single week's bars cannot show. Yahoo's history() adjusts
    # closes for dividends, so these are total returns — and that matters at this horizon:
    # utilities and staples yield around 3%, enough to change the order of the ranking.
    print("   [10b/11] S&P 500 Sector Rotation — Trailing 12 Months")
    try:
        year_data, missing = [], []
        for ticker, name in SECTOR_ETFS.items():
            try:
                closes = yf_fetcher.get_close_series(ticker, period="1y")
            except Exception:
                closes = None
            if closes is None or len(closes) < 200:      # a year is about 250 trading days
                missing.append(name)
                continue
            year_data.append((name, round((closes.iloc[-1] / closes.iloc[0] - 1) * 100, 2)))

        if missing:
            print(f"   ⚠ No 12-month history for: {', '.join(missing)} — left off the chart")
        if year_data:
            year_data.sort(key=lambda x: x[1], reverse=True)
            _t, _s = WEEKLY_TITLES["sector_rotation_12m"][mode]
            fig = render_change_bars([s[0] for s in year_data], [s[1] for s in year_data],
                                     _t, _s.format(date=date_label),
                                     "Yahoo Finance (SPDR sector ETFs, total return)")
            EconStyle.save_chart(fig, output_dir / "10a_sector_rotation_12m.png")
    except Exception as e:
        print(f"   ⚠ 12-month sector rotation failed: {e}")

    # ── 7.NIFTY SECTOR ROTATION ──
    print("   [11/12] NIFTY Sector Rotation")
    # Sourced from NSE directly: Yahoo stopped updating most ^CNX* sector
    # indices in Jul 2026, which silently cut the chart to three sectors. One
    # snapshot serves this chart and the 12-month one below, so the two always
    # cover the same sectors on the same day.
    NIFTY_SECTORS = {
        "NIFTY BANK": "Bank Nifty",
        "NIFTY IT": "IT",
        "NIFTY AUTO": "Auto",
        "NIFTY FMCG": "FMCG",
        "NIFTY PHARMA": "Pharma",
        "NIFTY METAL": "Metal",
        "NIFTY REALTY": "Realty",
        "NIFTY ENERGY": "Energy",
        "NIFTY PSU BANK": "PSU Bank",
        "NIFTY INFRASTRUCTURE": "Infra",
    }
    try:
        from data.fetchers.india_fetcher import fetch_nifty_sector_changes
        nse = fetch_nifty_sector_changes(list(NIFTY_SECTORS))
    except Exception as e:
        nse = None
        print(f"   ⚠ NSE sector snapshot failed: {e}")
    try:
        if nse is None:
            raise ValueError("no NSE sector snapshot")
        sector_data = [(label, nse[idx]["change_pct"]) for idx, label in NIFTY_SECTORS.items()]

        if sector_data:
            # Sort by performance (best to worst)
            sector_data.sort(key=lambda x: x[1], reverse=True)
            s_names = [s[0] for s in sector_data]
            s_values = [s[1] for s in sector_data]
            fig = render_change_bars(s_names, s_values, "NIFTY Sector Rotation",
                                     f"Weekly performance by sector  ·  {date_label}",
                                     "NSE (allIndices)")
            EconStyle.save_chart(fig, output_dir / "10b_india_sector_rotation.png")
    except Exception as e:
        print(f"   ⚠ Sector rotation failed: {e}")

    # ── 7b. NIFTY SECTOR ROTATION, TRAILING 12 MONTHS ──
    # India's counterpart to the S&P chart above. NSE's sector indices are price
    # indices, so unlike the SPDR ETFs these returns leave out dividends; the
    # subtitle says so, because the two charts are read side by side.
    print("   [11b/12] NIFTY Sector Rotation — Trailing 12 Months")
    try:
        if nse is None:
            raise ValueError("no NSE sector snapshot")
        year_data = sorted(((label, nse[idx]["change_pct_1y"]) for idx, label in NIFTY_SECTORS.items()),
                           key=lambda x: x[1], reverse=True)
        _t, _s = WEEKLY_TITLES["india_sector_rotation_12m"][mode]
        fig = render_change_bars([s[0] for s in year_data], [s[1] for s in year_data],
                                 _t, _s.format(date=date_label), "NSE (allIndices, price indices)")
        EconStyle.save_chart(fig, output_dir / "10c_india_sector_rotation_12m.png")
    except Exception as e:
        print(f"   ⚠ 12-month NIFTY sector rotation failed: {e}")
        
    # ── 8. REAL WAGE GROWTH ──
    print("   [12/12] US Real Wage Growth (Data only for Summary Table)")
    real_wage_latest = None
    real_wage_change = None
    try:
        # Average Hourly Earnings (All Employees, Total Private)
        earnings = fred_fetcher.fetch_series("CES0500000003", period_years=3)
        # CPI All Items
        cpi = fred_fetcher.fetch_series("CPIAUCSL", period_years=3)

        if len(earnings) > 12 and len(cpi) > 12:
            # Calculate YoY % change for both
            earn_yoy = earnings.pct_change(periods=12) * 100
            cpi_yoy = cpi.pct_change(periods=12) * 100

            # Align dates (both are monthly)
            combined = __import__('pandas').DataFrame({"earnings_yoy": earn_yoy, "cpi_yoy": cpi_yoy}).dropna()
            combined["real_wage"] = combined["earnings_yoy"] - combined["cpi_yoy"]

            if len(combined) > 3:
                # Store latest for summary table ONLY (no chart rendering)
                real_wage_latest = float(combined["real_wage"].iloc[-1])
                if len(combined) >= 2:
                    real_wage_change = real_wage_latest - float(combined["real_wage"].iloc[-2])
    except Exception as e:
        print(f"   ⚠ Real wage growth failed: {e}")
        
    # ── 8. FX WEEKLY BAR ──
    print("   [FX-bar] FX — Weekly Performance Bar Chart")
    try:
        fx_ids = ["dxy", "eurusd", "gbpusd", "usdinr", "usdjpy", "usdcny"]
        names_fx, values_fx, cks_fx = build_bar_data(fx_ids)

        if names_fx:
            _t, _s = WEEKLY_TITLES["fx_weekly"][mode]
            fig = render_change_bars(names_fx, values_fx, _t, _s.format(date=date_label), "Yahoo Finance")
            EconStyle.save_chart(fig, output_dir / "03_fx_weekly.png")
    except Exception as e:
        print(f"   ⚠ FX weekly bar failed: {e}")

    # NOTE: USD/BRL is an ad-hoc narrative chart. Run: python custom/brazil_fx.py

    # ── 11. CREDIT SPREADS ──
    # ICE BofA option-adjusted spreads. Since April 2026 FRED carries only the
    # latest three years of ICE's indices, and its archive (ALFRED) is cut the
    # same way, so three years is as far back as this chart can go. Each of
    # the widest points is labelled with the shock behind it: a new spike
    # needs a line in CREDIT_EVENTS.
    print("   [11] Credit Markets — IG & HY Spreads (3-Year Trend)")
    try:
        ig_s = fred_fetcher.fetch_series("BAMLC0A0CM", period_years=3)
        hy_s = fred_fetcher.fetch_series("BAMLH0A0HYM2", period_years=3)

        if len(ig_s) > 10 and len(hy_s) > 10:
            # FRED returns OAS in percentage points (e.g. 3.97 = 397 bps).
            # Multiply by 100 so values are in basis points for the axis labels.
            hy_s = hy_s.dropna() * 100
            ig_s = ig_s.dropna() * 100
            hy_s.index, ig_s.index = pd.to_datetime(hy_s.index), pd.to_datetime(ig_s.index)

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_hy = "#DC2626"
            color_ig = "#1D4ED8"
            HY_STRESS, IG_STRESS = 400, 150

            # Each key entry carries today's reading.
            l1, = ax1.plot(hy_s.index.to_pydatetime(), hy_s.values, color=color_hy, linewidth=2.2,
                           label=f"HY OAS, left  {hy_s.iloc[-1]:,.0f} bps")
            l2, = ax2.plot(ig_s.index.to_pydatetime(), ig_s.values, color=color_ig, linewidth=2.2, linestyle="--",
                           label=f"IG OAS, right  {ig_s.iloc[-1]:,.0f} bps")

            ax1.axhline(HY_STRESS, color=color_hy, linestyle=":", linewidth=1.2, alpha=0.6)
            ax2.axhline(IG_STRESS, color=color_ig, linestyle=":", linewidth=1.2, alpha=0.6)

            # Both lines fill the same band of the chart, so their spikes line
            # up, with room above for the labels.
            hy_lo, hy_hi = float(hy_s.min()), float(max(hy_s.max(), HY_STRESS))
            ig_lo, ig_hi = float(ig_s.min()), float(max(ig_s.max(), IG_STRESS))
            ax1.set_ylim(hy_lo - (hy_hi - hy_lo) * 0.15, hy_hi + (hy_hi - hy_lo) * 0.38)
            ax2.set_ylim(ig_lo - (ig_hi - ig_lo) * 0.15, ig_hi + (ig_hi - ig_lo) * 0.38)

            # The shock behind each of the widest points, by the month the
            # high-yield spread peaked in; each is marked at the widest reading
            # within three weeks of that month.
            CREDIT_EVENTS = {
                "2023-10": "10-year Treasury yield hits 5%",
                "2024-08": "Yen carry-trade unwind",
                "2025-04": "US tariff shock",
                "2026-03": "Iran war and oil spike",
            }
            first, span = hy_s.index[0], hy_s.index[-1] - hy_s.index[0]
            for month, event in CREDIT_EVENTS.items():
                start = pd.Timestamp(month)
                near = hy_s[start - pd.Timedelta(weeks=3): start + pd.offsets.MonthEnd(0) + pd.Timedelta(weeks=3)]
                if near.empty:
                    continue                                    # older than the three years FRED keeps
                when, peak = near.idxmax(), float(near.max())
                if when - first < pd.Timedelta(weeks=2):
                    continue                                    # the peak itself has rolled off the start
                place = (when - first) / span
                ha = "left" if place < 0.08 else "right" if place > 0.92 else "center"
                ax1.plot(when, peak, "o", ms=5, color=color_hy, mec="white", mew=1.2, zorder=6)
                ax1.annotate(f"{event}\n{peak:,.0f} bps", xy=(when, peak), xytext=(0, 7),
                             textcoords="offset points", ha=ha, va="bottom", fontsize=8.5,
                             fontweight="bold", color=EconStyle.INK, linespacing=1.25, zorder=6)

            ax1.set_ylabel("HY OAS (bps)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color=color_hy)
            ax2.set_ylabel("IG OAS (bps)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color=color_ig)

            # One set of gridlines, the high-yield axis's.
            ax1.grid(axis="x", visible=False)
            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax2.grid(False)
            ax1.margins(x=0.01)
            ax1.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 5, 9)))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for ax in (ax1, ax2):
                ax.tick_params(axis="y", length=0)
                for sp in ('top', 'left', 'right'):
                    ax.spines[sp].set_visible(False)

            ax1.legend(handles=[l1, l2], loc="upper right", frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["credit_spreads"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "FRED (ICE BofA)")
            EconStyle.save_chart(fig, output_dir / "11_credit_spreads.png")
    except Exception as e:
        print(f"   ⚠ Credit spreads failed: {e}")

    # ── 12. BREAKEVEN INFLATION ──
    print("   [12] Breakeven Inflation — 5Y & 10Y (2-Year Trend)")
    try:
        be5_s = fred_fetcher.fetch_series("T5YIE", period_years=2)
        be10_s = fred_fetcher.fetch_series("T10YIE", period_years=2)

        if len(be5_s) > 10 and len(be10_s) > 10:
            fig, ax = EconStyle.create_figure(size="wide")

            color_5y  = "#7C3AED"
            color_10y = "#2563EB"

            ax.plot(be5_s.index.to_pydatetime(), be5_s.values, color=color_5y, linewidth=2.5, label="5Y Breakeven")
            ax.plot(be10_s.index.to_pydatetime(), be10_s.values, color=color_10y, linewidth=2.5, linestyle="--", label="10Y Breakeven")
            ax.axhline(2.0, color="#6B7280", linestyle="--", linewidth=1.5, label="Fed 2% Target")

            ax.set_ylabel("Breakeven Rate (%)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["breakeven_inflation"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "FRED (Federal Reserve Bank of St. Louis)")
            EconStyle.save_chart(fig, output_dir / "12_breakeven_inflation.png")
    except Exception as e:
        print(f"   ⚠ Breakeven inflation failed: {e}")

    # ── 13. REAL YIELDS ──
    print("   [13] Real Yields — 5Y & 10Y TIPS (2-Year Trend)")
    try:
        ry5_s  = fred_fetcher.fetch_series("DFII5",  period_years=2)
        ry10_s = fred_fetcher.fetch_series("DFII10", period_years=2)

        if len(ry5_s) > 10 and len(ry10_s) > 10:
            fig, ax = EconStyle.create_figure(size="wide")

            color_5y  = "#D97706"
            color_10y = "#DC2626"

            ax.plot(ry5_s.index.to_pydatetime(), ry5_s.values, color=color_5y, linewidth=2.5, label="5Y Real Yield (TIPS)")
            ax.plot(ry10_s.index.to_pydatetime(), ry10_s.values, color=color_10y, linewidth=2.5, linestyle="--", label="10Y Real Yield (TIPS)")
            ax.axhline(0.0, color="#1C1C1E", linestyle="-", linewidth=1.5, alpha=0.7)

            ry10_vals = ry10_s.values
            ry10_dts  = ry10_s.index.to_pydatetime()
            ax.fill_between(ry10_dts, ry10_vals, 0,
                            where=[v < 0 for v in ry10_vals],
                            color=color_10y, alpha=0.08)

            ax.set_ylabel("Real Yield (%)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["real_yields"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "FRED (US Treasury — TIPS)")
            EconStyle.save_chart(fig, output_dir / "13_real_yields.png")
    except Exception as e:
        print(f"   ⚠ Real yields failed: {e}")
        
    # ── 14. COPPER/GOLD RATIO ──
    print("   [14] Copper/Gold Ratio + 10Y Yield (2-Year Trend)")
    try:
        cu_s    = yf_fetcher.get_close_series("HG=F", period="2y")
        au_s    = yf_fetcher.get_close_series("GC=F", period="2y")
        dgs10_s = fred_fetcher.fetch_series("DGS10", period_years=2)

        # ── THE FIX: Strip timezones so Pandas can do math ──
        cu_s.index = cu_s.index.tz_localize(None)
        au_s.index = au_s.index.tz_localize(None)
        dgs10_s.index = dgs10_s.index.tz_localize(None)

        if len(cu_s) > 50 and len(au_s) > 50:
            ratio_s = (cu_s / au_s).dropna().rolling(5).mean().dropna()

            # Align FRED 10Y to ratio's trading-day index
            dgs10_aligned = dgs10_s.reindex(ratio_s.index, method="ffill").dropna()

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_ratio = "#B45309"
            color_10y   = "#1D4ED8"

            l1, = ax1.plot(ratio_s.index.to_pydatetime(), ratio_s.values,
                           color=color_ratio, linewidth=2.5, label="C/G Ratio")
            l2, = ax2.plot(dgs10_aligned.index.to_pydatetime(), dgs10_aligned.values,
                           color=color_10y, linewidth=2.0, linestyle="--", alpha=0.8, label="10Y Yield (%)")

            ax1.set_ylabel("Copper/Gold Ratio (5-day smooth)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color=color_ratio)
            ax2.set_ylabel("10Y Treasury Yield (%)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color=color_10y)

            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)

            # Perfectly aligned with the subcaption sitting on the top axis
            ax1.legend(handles=[l1, l2], loc="lower right", bbox_to_anchor=(1.0, 1.00), 
                       ncol=2, frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["copper_gold_ratio"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance · FRED")
            EconStyle.save_chart(fig, output_dir / "14_copper_gold_ratio.png")
    except Exception as e:
        print(f"   ⚠ Copper/Gold ratio failed: {e}")

    # ── 15. STOCK-BOND CORRELATION ──
    # Replaced the SPY/TLT ratio, which only ever rose: because TLT is driven
    # by long rates, the ratio climbed whenever yields rose, even in an equity
    # selloff. Their correlation asks the question that ratio was gesturing at
    # — whether bonds still hedge equities at all. It runs from TLT's launch in
    # 2002, because the point is the contrast: two decades of bonds cushioning
    # equity falls, then a regime since 2021 in which they mostly have not.
    print("   [15] Stock-Bond Correlation (60-Day Rolling, since 2002)")
    try:
        spy_s = yf_fetcher.get_close_series("SPY", period="max")
        tlt_s = yf_fetcher.get_close_series("TLT", period="max")
        both = pd.concat({"spy": spy_s, "tlt": tlt_s}, axis=1).dropna()
        if len(both) < 5000:                          # TLT has traded since Jul 2002
            raise ValueError(f"only {len(both)} days of SPY/TLT history")

        returns = both.pct_change().dropna()
        corr_s = returns["spy"].rolling(60).corr(returns["tlt"]).dropna()
        corr_s.index = corr_s.index.tz_localize(None)
        regime = pd.Timestamp("2021-01-01")
        before, after = corr_s[corr_s.index < regime], corr_s[corr_s.index >= regime]
        # Shares of days are counted on every daily reading; the line shows one
        # reading a week, because 6,000 daily points at this width is a smear.
        weekly_corr = corr_s.resample("W-FRI").last().dropna()

        fig, ax = EconStyle.create_figure(size="wide")
        c_dates = weekly_corr.index.to_pydatetime()
        zeros = [0.0] * len(weekly_corr)
        ax.axvspan(regime, weekly_corr.index[-1], color="#6B7280", alpha=0.10, lw=0, zorder=0)
        ax.fill_between(c_dates, weekly_corr.values, zeros, where=(weekly_corr.values > 0),
                        color="#9B1C31", alpha=0.16, interpolate=True)
        ax.fill_between(c_dates, weekly_corr.values, zeros, where=(weekly_corr.values <= 0),
                        color="#0B8F82", alpha=0.16, interpolate=True)
        ax.plot(c_dates, weekly_corr.values, color="#003366", linewidth=2.5, zorder=4)
        ax.axhline(0, color="#1A1A1A", linewidth=1.1, zorder=5)

        latest = float(corr_s.iloc[-1])
        ax.annotate(f"{latest:+.2f}".replace("-", "−"), xy=(c_dates[-1], latest),
                    xytext=(8, 0), textcoords="offset points", va="center", ha="left",
                    fontsize=11, fontweight="bold", color="#003366", annotation_clip=False)
        ax.annotate("Bonds and equities fall together", xy=(0.012, 0.95), xycoords="axes fraction",
                    ha="left", va="top", fontsize=9.5, fontweight="bold", color="#9B1C31")
        ax.annotate("Bonds hedge equities", xy=(0.012, 0.05), xycoords="axes fraction",
                    ha="left", va="bottom", fontsize=9.5, fontweight="bold", color="#0B8F82")
        # Each period's share of days above zero, over its span. The earlier
        # label sits right of centre to clear the caption at the top left.
        for label, share, x in (
            (f"{before.index[0].year}–{regime.year - 1}", (before > 0).mean() * 100,
             before.index[0] + (regime - before.index[0]) * 0.6),
            (f"Since {regime.year}", (after > 0).mean() * 100,
             regime + (after.index[-1] - regime) / 2),
        ):
            ax.annotate(f"{label}\nabove zero on {share:.0f}% of days", xy=(x, 0.95),
                        xycoords=("data", "axes fraction"), ha="center", va="top",
                        fontsize=9, fontweight="bold", color="#1A1A1A", linespacing=1.3)

        ax.set_ylabel("Correlation of daily returns", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.set_ylim(-1.0, 1.0)
        ax.margins(x=0.01)
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)

        _t, _s = WEEKLY_TITLES["stock_bond_correlation"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Yahoo Finance (SPY, TLT daily returns)")
        EconStyle.save_chart(fig, output_dir / "15_stock_bond_correlation.png")
    except Exception as e:
        print(f"   ⚠ Stock-bond correlation failed: {e}")

    # ── 15b. DEFENSIVES VS CYCLICALS ──
    # Risk appetite read from where money actually sits inside the index, which
    # no rate move can distort. Complements SPHB/SPLV rather than repeating it.
    # Two years, unlike the long-view ratios beside it: over twenty years this
    # ratio mostly measures technology's long run, which buries the rotation
    # signal the chart is for. Each basket is equal-weighted and rebalanced
    # daily, the mean of its members' daily returns.
    print("   [15b] Defensives vs Cyclicals (2-Year Trend)")
    try:
        from generate_macro import _end_dot
        DEFENSIVE = {"XLP": "Staples", "XLU": "Utilities", "XLV": "Healthcare"}
        CYCLICAL = {"XLY": "Discretionary", "XLK": "Technology", "XLI": "Industrials"}
        legs = {t: yf_fetcher.get_close_series(t, period="2y") for t in {**DEFENSIVE, **CYCLICAL}}
        missing = [t for t, s in legs.items() if s is None or len(s) < 50]
        if missing:
            raise ValueError(f"no price history for {', '.join(missing)}")

        prices = pd.concat(legs, axis=1).dropna()
        daily = prices.pct_change().fillna(0)
        def basket(tickers):
            return (1 + daily[tickers].mean(axis=1)).cumprod()
        ratio_s = basket(list(DEFENSIVE)) / basket(list(CYCLICAL)) * 100
        mean_26w = ratio_s.rolling(130).mean()          # ~26 weeks of trading days

        fig, ax = EconStyle.create_figure(size="wide")
        color = "#C8620A"
        r_dates = ratio_s.index.to_pydatetime()
        ax.plot(r_dates, ratio_s.values, color=color, linewidth=2.5, label="Defensives / cyclicals")
        ax.plot(mean_26w.index.to_pydatetime(), mean_26w.values, color="#6B7280",
                linewidth=1.5, linestyle="--", label="26-Week Mean")
        ax.axhline(100, color="#1A1A1A", linewidth=1.1, zorder=5)
        _end_dot(ax, r_dates[-1], float(ratio_s.iloc[-1]), color, zorder=7, size=26)

        ax.set_ylabel("Index (both baskets = 100 two years ago)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.grid(axis="x", visible=False)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
        ax.legend(frameon=False, fontsize=10, loc="lower left")
        _label_returns(ax, [{"x": r_dates[-1], "y": float(ratio_s.iloc[-1]), "color": color}], decimals=1)

        _t, _s = WEEKLY_TITLES["defensives_cyclicals"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Yahoo Finance (SPDR sector ETFs: XLP, XLU, XLV vs XLY, XLK, XLI)")
        EconStyle.save_chart(fig, output_dir / "15b_defensives_cyclicals.png")
    except Exception as e:
        print(f"   ⚠ Defensives vs cyclicals failed: {e}")

    # ── 16. SPHB/SPLV RISK APPETITE ──
    # Invesco's high-beta and low-volatility S&P 500 ETFs, weekly from their
    # launch in May 2011: as far back as the pair goes, since Yahoo does not
    # carry the S&P indices behind them.
    print("   [16] SPHB/SPLV — High Beta vs Low Vol (since 2011)")
    try:
        from generate_macro import _end_dot
        sphb_s = yf_fetcher.get_close_series("SPHB", period="max")
        splv_s = yf_fetcher.get_close_series("SPLV", period="max")

        if len(sphb_s) > 50 and len(splv_s) > 50:
            both = pd.concat({"hb": sphb_s, "lv": splv_s}, axis=1).dropna()
            both.index = both.index.tz_localize(None)
            both = both[both.index >= LONG_VIEW_START]
            ratio_s = (both["hb"] / both["lv"]).resample("W-FRI").last().dropna()
            ratio_s = ratio_s / ratio_s.iloc[0] * 100

            fig, ax = EconStyle.create_figure(size="wide")
            color_line = "#7C3AED"
            r_dates = ratio_s.index.to_pydatetime()
            ax.plot(r_dates, ratio_s.values, color=color_line, linewidth=2.0, zorder=4)
            ax.axhline(100, color="#1A1A1A", linewidth=1.1, zorder=5)
            _end_dot(ax, r_dates[-1], float(ratio_s.iloc[-1]), color_line, zorder=7, size=26)

            ax.set_ylabel(f"SPHB ÷ SPLV, {both.index[0]:%b %Y} = 100", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.grid(axis="x", visible=False)
            ax.margins(x=0.01)
            ax.xaxis.set_major_locator(mdates.YearLocator(2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            _label_returns(ax, [{"x": r_dates[-1], "y": float(ratio_s.iloc[-1]), "color": color_line}])
            _recession_bands(ax, fred_fetcher.fetch_series("USREC", period_years=25))

            _t, _s = WEEKLY_TITLES["risk_appetite_ratio"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (Invesco ETFs) · recession dates NBER via FRED")
            EconStyle.save_chart(fig, output_dir / "16_risk_appetite_ratio.png")
    except Exception as e:
        print(f"   ⚠ SPHB/SPLV ratio failed: {e}")

    # ── 17. MARKET BREADTH (RSP/SPY) ──
    # Equal weight against cap weight, weekly since LONG_VIEW_START (RSP has
    # traded since 2003), indexed to 100 at the start.
    print("   [17] Market Breadth — RSP/SPY Equal vs Cap-Weight (since 2006)")
    try:
        from generate_macro import _end_dot
        rsp_s  = yf_fetcher.get_close_series("RSP", period="max")
        spy2_s = yf_fetcher.get_close_series("SPY", period="max")

        if len(rsp_s) > 50 and len(spy2_s) > 50:
            both = pd.concat({"rsp": rsp_s, "spy": spy2_s}, axis=1).dropna()
            both.index = both.index.tz_localize(None)
            both = both[both.index >= LONG_VIEW_START]
            ratio_s = (both["rsp"] / both["spy"]).resample("W-FRI").last().dropna()
            ratio_s = ratio_s / ratio_s.iloc[0] * 100

            fig, ax = EconStyle.create_figure(size="wide")
            color_line = "#0F766E"
            r_dates = ratio_s.index.to_pydatetime()
            ax.plot(r_dates, ratio_s.values, color=color_line, linewidth=2.0, zorder=4)
            ax.axhline(100, color="#1A1A1A", linewidth=1.1, zorder=5)
            _end_dot(ax, r_dates[-1], float(ratio_s.iloc[-1]), color_line, zorder=7, size=26)

            ax.set_ylabel(f"RSP ÷ SPY, {both.index[0]:%b %Y} = 100", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.grid(axis="x", visible=False)
            ax.margins(x=0.01)
            ax.xaxis.set_major_locator(mdates.YearLocator(2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            _label_returns(ax, [{"x": r_dates[-1], "y": float(ratio_s.iloc[-1]), "color": color_line}])
            _recession_bands(ax, fred_fetcher.fetch_series("USREC", period_years=25))

            _t, _s = WEEKLY_TITLES["market_breadth"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (Invesco · SPDR ETFs) · recession dates NBER via FRED")
            EconStyle.save_chart(fig, output_dir / "17_market_breadth.png")
    except Exception as e:
        print(f"   ⚠ Market breadth failed: {e}")

    # ── 18. BOND ETF TOTAL RETURNS ──
    print("   [18] Bond ETF Total Returns — TLT, LQD, HYG (1-Year Indexed)")
    try:
        BOND_ETFS = {
            "TLT": ("#1D4ED8", "TLT — Long Duration"),
            "LQD": ("#059669", "LQD — IG Credit"),
            "HYG": ("#DC2626", "HYG — High Yield"),
        }

        from generate_macro import _end_dot
        fig, ax = EconStyle.create_figure(size="wide")
        ends = []

        for ticker, (color, label) in BOND_ETFS.items():
            sr = yf_fetcher.get_close_series(ticker, period="1y")
            if len(sr) > 20:
                indexed = (sr / sr.iloc[0]) * 100
                x = indexed.index.to_pydatetime()
                ax.plot(x, indexed.values, color=color, linewidth=2.5, label=label)
                _end_dot(ax, x[-1], indexed.iloc[-1], color, zorder=7)
                ends.append({"x": x[-1], "y": float(indexed.iloc[-1]), "color": color})

        if ends:
            ax.axhline(100, color="#6B7280", linestyle="--", linewidth=1.2, alpha=0.7)
            ax.set_ylabel("Total Return (Indexed to 100)", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)
            _label_returns(ax, ends, decimals=1)      # bond returns are single digits: keep the decimal

            _t, _s = WEEKLY_TITLES["bond_etf_returns"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (iShares ETFs)")
            EconStyle.save_chart(fig, output_dir / "18_bond_etf_returns.png")
        else:
            plt.close(fig)
    except Exception as e:
        print(f"   ⚠ Bond ETF returns failed: {e}")

    # ── 19. GOLD/SPX SAFE HAVEN RATIO ──
    print("   [19] Gold/SPX Safe Haven Ratio (2-Year Trend)")
    try:
        gold_s = yf_fetcher.get_close_series("GC=F",  period="2y")
        spx_s  = yf_fetcher.get_close_series("^GSPC", period="2y")

        if len(gold_s) > 50 and len(spx_s) > 50:
            ratio_s  = (gold_s / spx_s).dropna()
            mean_52w = ratio_s.rolling(252).mean()

            fig, ax = EconStyle.create_figure(size="wide")
            color_line = "#D97706"
            r_dates = ratio_s.index.to_pydatetime()

            ax.plot(r_dates, ratio_s.values, color=color_line, linewidth=2.5, label="Gold/SPX Ratio")
            ax.plot(mean_52w.index.to_pydatetime(), mean_52w.values, color="#6B7280",
                    linewidth=1.5, linestyle="--", label="52-Week Mean")

            ax.set_ylabel("Gold / SPX Ratio", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["gold_spx_ratio"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance")
            EconStyle.save_chart(fig, output_dir / "19_gold_spx_ratio.png")
    except Exception as e:
        print(f"   ⚠ Gold/SPX ratio failed: {e}")

    # ── 19b. COMMODITIES VS EQUITIES ──
    # Four decades of commodities priced in equities. The ratio drifts down
    # over time, because shares compound earnings while commodity prices
    # mostly track inflation; the log scale lets the cycles around that drift
    # show. ^SPGSCI is the spot index, the price of the commodities themselves,
    # not the return from rolling futures.
    print("   [19b] Commodities vs Equities (S&P GSCI / S&P 500, since 1984)")
    try:
        import matplotlib.ticker as mticker
        gsci_s = yf_fetcher.get_close_series("^SPGSCI", period="max")
        spx_s = yf_fetcher.get_close_series("^GSPC", period="max")
        if len(gsci_s) < 8000 or len(spx_s) < 8000:      # both run back to the 1980s
            raise ValueError("no long S&P GSCI or S&P 500 history")
        gsci_s.index = gsci_s.index.tz_localize(None)
        spx_s.index = spx_s.index.tz_localize(None)
        # Month-end closes, so the last point is the latest close.
        ratio_s = (gsci_s.resample("MS").last() / spx_s.resample("MS").last()).dropna()
        ratio_s = ratio_s / ratio_s.iloc[0] * 100

        fig, ax = EconStyle.create_figure(size="wide")
        color = EconStyle.LINE_ORANGE
        ax.plot(ratio_s.index.to_pydatetime(), ratio_s.values, color=color, linewidth=2.5, zorder=4)
        _mark_turns(ax, _turning_points(ratio_s, 0.7), color)

        latest = float(ratio_s.iloc[-1])
        ax.annotate(f"{latest:.1f}", xy=(ratio_s.index[-1], latest), xytext=(8, 0),
                    textcoords="offset points", va="center", ha="left", fontsize=11,
                    fontweight="bold", color=color, annotation_clip=False)
        ax.annotate(f"Now lower than in {(ratio_s > latest).mean() * 100:.0f}% of months "
                    f"since {ratio_s.index[0].year}",
                    xy=(0.99, 0.95), xycoords="axes fraction", ha="right", va="top",
                    fontsize=9.5, fontweight="bold", color=color)

        ax.set_yscale("log")
        ax.set_ylim(ratio_s.min() / 1.5, ratio_s.max() * 1.15)   # room for the dated lows
        ax.yaxis.set_major_locator(mticker.FixedLocator([2, 5, 10, 20, 50, 100, 200]))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))
        ax.yaxis.set_minor_locator(mticker.NullLocator())
        ax.set_ylabel(f"{ratio_s.index[0]:%b %Y} = 100, log scale", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.margins(x=0.01)
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)

        # Last, once the years on screen are settled (see _recession_bands).
        _recession_bands(ax, fred_fetcher.fetch_series("USREC", period_years=60))

        _t, _s = WEEKLY_TITLES["commodities_vs_equities"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "S&P GSCI and S&P 500 via Yahoo Finance; recession dates NBER via FRED")
        EconStyle.save_chart(fig, output_dir / "19b_commodities_vs_equities.png")
    except Exception as e:
        print(f"   ⚠ Commodities vs equities failed: {e}")

    # ── 20. EM FX WEEKLY BAR ──
    print("   [20] EM FX — Weekly Performance Bar Chart")
    try:
        EM_FX_TICKERS = {
            "BRL=X": "Brazilian Real (BRL)",
            "MXN=X": "Mexican Peso (MXN)",
            "ZAR=X": "South African Rand (ZAR)",
            "INR=X": "Indian Rupee (INR)",
            "TRY=X": "Turkish Lira (TRY)",
            "IDR=X": "Indonesian Rupiah (IDR)",
            "KRW=X": "Korean Won (KRW)",
        }
        em_fx_data = []
        for ticker, name in EM_FX_TICKERS.items():
            try:
                result = yf_fetcher.weekly_change(ticker)
                if result:
                    # Tickers are USD/EM rates — negate to show EM currency vs USD
                    em_fx_data.append((name, -result["change_pct"]))
            except Exception:
                pass

        values_emfx_check = [d[1] for d in em_fx_data]
        if em_fx_data and _bad_fetch(values_emfx_check, len(EM_FX_TICKERS)):
            _flag_skipped("EM FX — Weekly Performance", len(values_emfx_check), len(EM_FX_TICKERS))
        elif em_fx_data:
            _t, _s = WEEKLY_TITLES["em_fx_weekly"][mode]
            fig = render_change_bars([d[0] for d in em_fx_data], [d[1] for d in em_fx_data],
                                     _t, _s.format(date=date_label), "Yahoo Finance")
            EconStyle.save_chart(fig, output_dir / "20_em_fx_weekly.png")
    except Exception as e:
        print(f"   ⚠ EM FX weekly failed: {e}")

    # ── 21. EM EQUITY ETF WEEKLY BAR ──
    print("   [21] EM Equity ETFs — Weekly Performance Bar Chart")
    try:
        EM_EQUITY_TICKERS = {
            "EWZ":  "Brazil (EWZ)",
            "EWW":  "Mexico (EWW)",
            "EZA":  "South Africa (EZA)",
            "EWT":  "Taiwan (EWT)",
            "EWY":  "South Korea (EWY)",
            "INDA": "India (INDA)",
            "MCHI": "China (MCHI)",
        }
        em_eq_data = []
        for ticker, name in EM_EQUITY_TICKERS.items():
            try:
                result = yf_fetcher.weekly_change(ticker)
                if result:
                    em_eq_data.append((name, result["change_pct"]))
            except Exception:
                pass

        if em_eq_data:
            em_eq_data.sort(key=lambda x: x[1])
            names_emeq  = [d[0] for d in em_eq_data]
            values_emeq = [d[1] for d in em_eq_data]

            if _bad_fetch(values_emeq, len(EM_EQUITY_TICKERS)):
                _flag_skipped("Emerging Market Equities — Weekly Performance", len(values_emeq), len(EM_EQUITY_TICKERS))
            else:
                _t, _s = WEEKLY_TITLES["em_equity_weekly"][mode]
                fig = render_change_bars(names_emeq, values_emeq, _t, _s.format(date=date_label),
                                         "Yahoo Finance (iShares ETFs)")
                EconStyle.save_chart(fig, output_dir / "21_em_equity_weekly.png")
    except Exception as e:
        print(f"   ⚠ EM equity weekly failed: {e}")

    # ── 22. INDIA VS EM PEERS (INDEXED) ──
    # Six lines is past what colour alone can separate, so the palette was
    # chosen with the dataviz validator over *all* pairs (any two lines can
    # cross): the house saffron for India and four hues that stay distinct
    # from each other and from it, with the EM benchmark in grey as context.
    # A legend names the lines; each line's 12-month return sits at its end.
    print("   [22] India vs EM Peers — Indexed 1-Year Trend")
    try:
        from generate_macro import _draw_line, _end_dot
        EM_PEERS = {
            "INDA": ("India (INDA)",         EconStyle.LINE_ORANGE, 3.0),
            "EEM":  ("EM benchmark (EEM)",   "#6B7280",             2.0),
            "EWY":  ("South Korea (EWY)",    "#2A78D6",             2.0),
            "EWT":  ("Taiwan (EWT)",         EconStyle.LINE_TEAL,   2.0),
            "MCHI": ("China (MCHI)",         EconStyle.LINE_MAROON, 2.0),
            "EWZ":  ("Brazil (EWZ)",         "#4A3AA7",             2.0),
        }

        fig, ax = EconStyle.create_figure(size="wide")
        ends = []
        for ticker, (label, color, lw) in EM_PEERS.items():
            sr = yf_fetcher.get_close_series(ticker, period="1y")
            if len(sr) <= 20:
                print(f"   ⚠ No 12-month history for {label} — left off the chart")
                continue
            indexed = (sr / sr.iloc[0]) * 100
            x = indexed.index.to_pydatetime()
            _draw_line(ax, x, indexed.values, color, width=lw, zorder=5 if ticker == "INDA" else 4)
            ax.plot([], [], color=color, linewidth=lw, label=label)      # legend key without the halo
            _end_dot(ax, x[-1], indexed.iloc[-1], color, zorder=7)
            ends.append({"x": x[-1], "y": float(indexed.iloc[-1]), "color": color})

        if ends:
            ax.axhline(100, color=EconStyle.INK_MUTED, linestyle="--", linewidth=1.1, zorder=2)
            ax.set_ylabel("Total return, indexed to 100", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=9.5, loc="upper left", ncol=2,
                      handlelength=1.8, columnspacing=1.6)
            _label_returns(ax, ends)

            _t, _s = WEEKLY_TITLES["india_vs_em"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (iShares ETFs)")
            EconStyle.save_chart(fig, output_dir / "22_india_vs_em_peers.png")
        else:
            plt.close(fig)
    except Exception as e:
        print(f"   ⚠ India vs EM peers failed: {e}")
        
    # ── 22b. EM STRESS MONITOR ──
    print("   [22b] Emerging Markets Stress Monitor")
    try:
        import pandas as pd
        
        # Fetch the exact series from your macro_settings.py
        em_hy_s = fred_fetcher.fetch_series("BAMLEMHBHYCRPIOAS", period_years=3)
        em_corp_s = fred_fetcher.fetch_series("BAMLEMCBPIOAS", period_years=3)
        usd_em_s = fred_fetcher.fetch_series("DTWEXEMEGS", period_years=3)

        if len(em_hy_s) > 10 and len(usd_em_s) > 10:
            # Strip timezones safely
            for s in [em_hy_s, em_corp_s, usd_em_s]:
                s.index = pd.to_datetime(s.index)
                if s.index.tz is not None:
                    s.index = s.index.tz_localize(None)

            # Multiply spreads by 100 to convert to basis points (bps)
            em_hy_bps = (em_hy_s * 100).dropna()
            em_corp_bps = (em_corp_s * 100).dropna()
            usd_em = usd_em_s.dropna()

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            # Institutional Colors mapped directly from macro_settings.py
            color_hy = "#FF9933"   # Saffron/EM
            color_corp = "#CC0066" # Magenta
            color_usd = "#003366"  # Navy

            # Plot Spreads (Left Axis)
            l1, = ax1.plot(em_hy_bps.index.to_pydatetime(), em_hy_bps.values,
                           color=color_hy, linewidth=2.5, solid_capstyle="round", label="EM HY Credit Spread")
            l2, = ax1.plot(em_corp_bps.index.to_pydatetime(), em_corp_bps.values,
                           color=color_corp, linewidth=2.5, solid_capstyle="round", label="EM Corporate Spread")
            
            # Plot USD Index (Right Axis)
            l3, = ax2.plot(usd_em.index.to_pydatetime(), usd_em.values,
                           color=color_usd, linewidth=2.0, linestyle="--", alpha=0.8, solid_capstyle="round",
                           label="USD Index (vs EM)")

            ax1.set_ylabel("Credit Spread (bps)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color="#1C1C1E")
            ax2.set_ylabel("USD Index (vs EM)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color=color_usd)

            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)

            # ── END-OF-LINE LABELS, SPACED SO NONE OVERLAP ACROSS THE TWO AXES ──
            last_date = em_hy_bps.index[-1].to_pydatetime()
            labels = [  # (axis, text, value, colour)
                (ax1, "EM HY Spread", em_hy_bps.values[-1], color_hy),
                (ax1, "EM Corp Spread", em_corp_bps.values[-1], color_corp),
                (ax2, "USD Index", usd_em.values[-1], color_usd),
            ]
            # Put every label on a shared 0-1 height scale, push neighbours apart,
            # then draw it just right of the line ends (x in data, y in axes units).
            def _height(ax, v):
                lo, hi = ax.get_ylim()
                return (v - lo) / (hi - lo)
            order = sorted(range(len(labels)), key=lambda i: _height(labels[i][0], labels[i][2]))
            heights = [_height(labels[i][0], labels[i][2]) for i in order]
            min_gap = 0.065
            for k in range(1, len(heights)):
                heights[k] = max(heights[k], heights[k - 1] + min_gap)
            overflow = heights[-1] - 0.98
            if overflow > 0:
                heights = [h - overflow for h in heights]
            import matplotlib.transforms as mtransforms
            label_tf = mtransforms.offset_copy(
                mtransforms.blended_transform_factory(ax1.transData, ax1.transAxes),
                fig=fig, x=8, units="points",
            )
            for h, i in zip(heights, order):
                _, text, _, colour = labels[i]
                ax1.text(mdates.date2num(last_date), h, text, transform=label_tf,
                         va="center", ha="left", fontsize=10, fontweight="bold",
                         color=colour, clip_on=False)

            # Room on the right for the labels, but date ticks only where there is data:
            # every January and July, so the labels never collide.
            x0, x1 = ax1.get_xlim()
            ax1.set_xlim(x0, x1 + (x1 - x0) * 0.18)
            first_date = min(em_hy_bps.index[0], em_corp_bps.index[0], usd_em.index[0])
            months = pd.date_range(first_date, em_hy_bps.index[-1], freq="MS")
            ax1.set_xticks([d.to_pydatetime() for d in months if d.month in (1, 7)])
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))

            _t, _s = WEEKLY_TITLES["em_stress_monitor"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "FRED (ICE BofA, Federal Reserve)")
            
            # Save chart
            EconStyle.save_chart(fig, output_dir / "22b_em_stress_monitor.png")
    except Exception as e:
        print(f"   ⚠ EM Stress Monitor failed: {e}")

    # ── 22c. CBOE EM VOLATILITY INDEX (VXEEM) ──
    print("   [22c] CBOE EM Volatility Index (VXEEM)")
    try:
        vxeem_s = fred_fetcher.fetch_series("VXEEMCLS", period_years=3)
        if len(vxeem_s) > 20:
            fig, ax = EconStyle.create_figure(size="wide")
            dates = vxeem_s.index.to_pydatetime()
            vals  = vxeem_s.values

            color_vxeem = EconStyle.get_color("asia")   # Purple — EM fear
            mean_52w = vxeem_s.rolling(252).mean()

            ax.plot(dates, vals, color=color_vxeem, lw=2.0, zorder=4, label="VXEEM")
            ax.plot(
                mean_52w.index.to_pydatetime(), mean_52w.values,
                color="#808080", lw=1.2, ls="--", alpha=0.7, zorder=3, label="52-Week Avg",
            )
            ax.fill_between(dates, vals, mean_52w.reindex(vxeem_s.index).values,
                            where=(vals > mean_52w.reindex(vxeem_s.index).values),
                            color=color_vxeem, alpha=0.12, zorder=2)

            ax.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.5, alpha=0.6, zorder=0)
            ax.xaxis.grid(False)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax.set_ylabel("VXEEM Level", fontsize=EconStyle.FONT_SIZE_AXIS, color="#404040")
            ax.tick_params(axis="x", rotation=30, labelsize=8)
            for spine in ["top", "right", "left"]:
                ax.spines[spine].set_visible(False)
            ax.legend(loc="upper left", fontsize=8.5, frameon=False)

            _t, _s = WEEKLY_TITLES["em_vix"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "FRED (CBOE / ICE)")
            EconStyle.save_chart(fig, output_dir / "22c_em_vix.png")
    except Exception as e:
        print(f"   ⚠ VXEEM chart failed: {e}")

    # ── 23. CRUDE OIL FUTURES CURVE ──
    # Replaced the Brent–WTI spread, which was not a signal: Brent is waterborne
    # and WTI is landlocked at Cushing, so Brent sits structurally above WTI and
    # the spread spent ~90% of two years in a $2–5 band. The futures curve asks
    # the question that spread could not: is physical crude tight right now?
    # A falling curve (backwardation) means buyers pay up for prompt barrels;
    # a rising curve (contango) means the market is paying to store a glut.
    print("   [23] Crude Oil Futures Curve (WTI, NYMEX contract ladder)")
    try:
        import contextlib, io

        MONTH_CODES = "FGHJKMNQUVXZ"          # Jan..Dec, CME convention
        today = datetime.now()

        # Walk forward from the current month and keep every contract Yahoo
        # still quotes. The front contract expires mid-month, so the nearest
        # month is often already delisted — that is expected, not an error.
        ladder = []
        for i in range(18):
            mm = today.month + i
            yy = today.year + (mm - 1) // 12
            mm = (mm - 1) % 12 + 1
            ticker = f"CL{MONTH_CODES[mm - 1]}{str(yy)[-2:]}.NYM"
            try:
                # A delisted contract is the normal case here, not a fault, so
                # the fetcher's warning is swallowed rather than logged.
                with contextlib.redirect_stdout(io.StringIO()):
                    s = yf_fetcher.get_close_series(ticker, period="3mo")
                if s is None or len(s) < 20:
                    continue
                s.index = s.index.tz_localize(None)
                ladder.append((f"{datetime(yy, mm, 1):%b '%y}", s))
            except Exception:
                continue
            if len(ladder) >= 15:
                break

        if len(ladder) < 6:
            raise ValueError(f"only {len(ladder)} live WTI contracts found")
        print(f"        {len(ladder)} live contracts: {ladder[0][0]} to {ladder[-1][0]}")

        labels  = [lab for lab, _ in ladder]
        now_px  = [float(s.iloc[-1]) for _, s in ladder]
        ago_ts  = ladder[0][1].index[-1] - pd.Timedelta(days=30)
        ago_px  = [float(s.asof(ago_ts)) for _, s in ladder]
        xs      = list(range(len(ladder)))

        front, back = now_px[0], now_px[-1]
        spread = front - back
        backwardated = spread > 0
        shade = "#0B8F82" if backwardated else "#C8620A"

        fig, ax = EconStyle.create_figure(size="wide")

        # The gap between the curve and the front-month price IS the signal, so
        # draw it rather than asking the reader to subtract two points.
        ax.fill_between(xs, now_px, front, color=shade, alpha=0.14, zorder=2)
        ax.axhline(front, color="#6B7280", linewidth=1.1, linestyle=":", zorder=3)

        l_ago, = ax.plot(xs, ago_px, color="#9AA3B0", linewidth=1.6, linestyle="--",
                         marker="o", markersize=4, zorder=4, label="One month ago")
        l_now, = ax.plot(xs, now_px, color="#1F5596", linewidth=2.5,
                         marker="o", markersize=6, zorder=5, label="Today")

        # Both end labels are pushed into the shaded band, away from the
        # subtitle above the first point and the axis below the last.
        ax.annotate(f"${front:,.0f}", xy=(xs[0], front), xytext=(18, -9),
                    textcoords="offset points", ha="left", va="top",
                    fontsize=11, fontweight="bold", color="#1F5596")
        ax.annotate(f"${back:,.0f}", xy=(xs[-1], back), xytext=(-4, 11),
                    textcoords="offset points", ha="right", va="bottom",
                    fontsize=11, fontweight="bold", color="#1F5596")

        verdict = (
            f"Backwardation — the far contract is ${spread:,.0f} below the front month"
            if backwardated else
            f"Contango — the far contract is ${abs(spread):,.0f} above the front month"
        )
        # Anchored inside the shaded band rather than at a fixed corner, so the
        # label follows the band if the curve flips into contango.
        mid = len(xs) // 2
        ax.annotate(verdict, xy=(xs[mid], (now_px[mid] + front) / 2), ha="center", va="center",
                    fontsize=10.5, fontweight="bold", color=shade, zorder=6)

        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=8.5, rotation=30, ha="right")
        ax.set_ylabel("WTI futures price ($/barrel)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.set_xlabel("Delivery month", fontsize=EconStyle.FONT_SIZE_AXIS, color="#4B5563")
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.xaxis.grid(False)
        ax.margins(x=0.04)
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
        ax.legend(handles=[l_now, l_ago], frameon=False, fontsize=10, loc="upper right")

        _t, _s = WEEKLY_TITLES["crude_oil_curve"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Yahoo Finance (NYMEX WTI monthly contracts)")
        EconStyle.save_chart(fig, output_dir / "23_crude_oil_curve.png")
    except Exception as e:
        print(f"   ⚠ Crude oil futures curve failed: {e}")

    # ── 23b. GOLD VS REAL YIELDS ──
    # Gold's textbook anchor is the real yield: when inflation-protected
    # Treasuries pay more, non-yielding gold should fall. That held tightly for
    # decades and then stopped. Plotted as a path through time on one pair of
    # axes (no second y-axis), the break is the shape of the line itself.
    print("   [23b] Gold vs Real Yields (10-Year Path)")
    try:
        gold_s = yf_fetcher.get_close_series("GC=F", period="10y")
        gold_s.index = gold_s.index.tz_localize(None)
        ry_s = fred_fetcher.fetch_series("DFII10", period_years=10)
        ry_s.index = ry_s.index.tz_localize(None)

        joint = pd.concat({"gold": gold_s, "ry": ry_s}, axis=1).dropna()
        # Quarterly, not monthly: real yields have been range-bound since 2023
        # while gold doubled, so monthly points pile up as horizontal noise on
        # a near-vertical path. Quarterly averages leave the shape and drop it.
        monthly = joint.resample("QE").mean().dropna()

        if len(monthly) < 20:
            raise ValueError(f"only {len(monthly)} quarterly observations")

        SPLIT = "2022-01-01"
        old = monthly[monthly.index < SPLIT]
        new = monthly[monthly.index >= SPLIT]
        # One month of overlap so the two coloured segments join up.
        bridge = pd.concat([old.tail(1), new])

        corr_old = old.corr().iloc[0, 1]
        corr_new = new.corr().iloc[0, 1]

        fig, ax = EconStyle.create_figure(size="wide")
        ax.plot(old["ry"], old["gold"], color="#1F5596", linewidth=2.5,
                solid_capstyle="round", zorder=4, label=f"2016–2021  (correlation {corr_old:+.2f})".replace("-", "−"))
        ax.plot(bridge["ry"], bridge["gold"], color="#9B1C31", linewidth=2.5,
                solid_capstyle="round", zorder=5, label=f"2022–today  (correlation {corr_new:+.2f})".replace("-", "−"))

        start, end = monthly.iloc[0], monthly.iloc[-1]
        ax.scatter([start["ry"]], [start["gold"]], s=70, color="#1F5596",
                   edgecolors="white", linewidths=1.4, zorder=6)
        ax.scatter([end["ry"]], [end["gold"]], s=140, color="#9B1C31",
                   edgecolors="white", linewidths=1.6, zorder=7)

        # Labelled by quarter, so the last point is not misread as a spot price.
        def _q(ts):
            return f"Q{ts.quarter} {ts.year}"

        ax.annotate(_q(monthly.index[0]), xy=(start["ry"], start["gold"]),
                    xytext=(10, -9), textcoords="offset points", ha="left", va="top",
                    fontsize=9.5, fontweight="bold", color="#1F5596")
        ax.annotate(f"{_q(monthly.index[-1])}\n${end['gold']:,.0f}",
                    xy=(end["ry"], end["gold"]), xytext=(-6, -12), textcoords="offset points",
                    ha="right", va="top", fontsize=10.5, fontweight="bold", color="#9B1C31")

        # The pivot: gold's cheapest real-yield point, where the old rule ended.
        trough = old["ry"].idxmin()
        ax.annotate(_q(trough), xy=(old.loc[trough, "ry"], old.loc[trough, "gold"]),
                    xytext=(10, -9), textcoords="offset points", ha="left", va="top",
                    fontsize=9.5, fontweight="bold", color="#1F5596")

        ax.axvline(0, color="#1A1A1A", linewidth=1.1, alpha=0.6, zorder=3)
        ax.annotate("Real yields\nturn positive", xy=(0, 0.62), xycoords=("data", "axes fraction"),
                    xytext=(7, 0), textcoords="offset points", ha="left", va="center",
                    fontsize=9, color="#4B5563")

        ax.set_xlabel("10-year US real yield, % (TIPS)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.set_ylabel("Gold price ($/ounce)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.1f}%".replace("-", "−")))
        ax.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
        ax.legend(frameon=False, fontsize=10, loc="upper left")

        _t, _s = WEEKLY_TITLES["gold_real_rates"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Yahoo Finance (COMEX gold) · FRED (DFII10)")
        EconStyle.save_chart(fig, output_dir / "23b_gold_real_rates.png")
    except Exception as e:
        print(f"   ⚠ Gold vs real yields failed: {e}")

    # ── 23c. COMMODITY BREADTH ──
    # Whether a commodity move is a global demand impulse or one squeezed
    # market. A headline index cannot separate the two; counting how many
    # members are in their own uptrend can. It runs from 2008, when all 13 have
    # history on Yahoo (Brent is the last to start), so that more than one
    # commodity cycle is on the chart.
    print("   [23c] Commodity Breadth (share above 200-day average, since 2008)")
    try:
        BREADTH_BASKET = {
            "BZ=F": "Brent", "CL=F": "WTI", "NG=F": "Natural gas",
            "GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum", "HG=F": "Copper",
            "ZW=F": "Wheat", "ZC=F": "Corn", "ZS=F": "Soybeans",
            "KC=F": "Coffee", "SB=F": "Sugar", "CC=F": "Cocoa",
        }
        status = {}
        for ticker, name in BREADTH_BASKET.items():
            s = yf_fetcher.get_close_series(ticker, period="max")
            if s is None or len(s) < 250:
                raise ValueError(f"no usable history for {name} ({ticker})")
            s.index = s.index.tz_localize(None)
            ma = s.rolling(200).mean()
            # 1 above its own 200-day average, 0 below, and NaN until the
            # average has 200 closes behind it: `price > NaN` is False, so
            # without the mask the warm-up would be published as a zero.
            status[name] = (s > ma).astype(float).where(ma.notna())

        # A reading is carried across a holiday or two, never further. Yahoo's
        # platinum series has two-month holes in 2008–09, and bridging them
        # would publish readings no market printed; on those days the share is
        # of the commodities that did trade, and never of fewer than 12.
        above = pd.concat(status, axis=1).sort_index().ffill(limit=5)
        above = above.loc[above.apply(lambda c: c.first_valid_index()).max():]
        above = above[above.notna().sum(axis=1) >= len(BREADTH_BASKET) - 1]
        breadth = above.mean(axis=1) * 100
        if breadth.index[0] > pd.Timestamp("2009-01-01"):
            raise ValueError(f"breadth starts in {breadth.index[0]:%b %Y}: a member's history was cut short")
        # Thirteen members move the share in steps of eight points, so the
        # daily reading is drawn faintly and its 3-month average carries the line.
        smooth = breadth.rolling(63).mean().dropna()

        fig, ax = EconStyle.create_figure(size="wide")
        s_dates = smooth.index.to_pydatetime()
        fifty = [50.0] * len(smooth)
        ax.fill_between(s_dates, smooth.values, fifty, where=(smooth.values >= 50),
                        color="#0B8F82", alpha=0.16, interpolate=True, zorder=2)
        ax.fill_between(s_dates, smooth.values, fifty, where=(smooth.values < 50),
                        color="#9B1C31", alpha=0.16, interpolate=True, zorder=2)
        ax.plot(breadth.index.to_pydatetime(), breadth.values, color="#C8620A",
                linewidth=0.7, alpha=0.3, zorder=3)
        ax.plot(s_dates, smooth.values, color="#C8620A", linewidth=2.5, zorder=5)
        ax.axhline(50, color="#1A1A1A", linewidth=1.1, zorder=4)

        latest_b = float(smooth.iloc[-1])
        ax.annotate(f"{latest_b:.0f}%", xy=(s_dates[-1], latest_b), xytext=(8, 0),
                    textcoords="offset points", va="center", ha="left",
                    fontsize=11, fontweight="bold", color="#C8620A", annotation_clip=False)

        def _names(items, limit=9):
            """Keep the caption on one line however the basket splits."""
            if len(items) <= limit:
                return ", ".join(items)
            return ", ".join(items[:limit]) + f" and {len(items) - limit} more"

        # Today's split, from the daily reading. The bands above 100 and below
        # 0 are the captions' own, so they never sit on the line.
        today = above.iloc[-1]
        rising = [n for n in above.columns if today[n] == 1]
        falling = [n for n in above.columns if today[n] == 0]
        ax.annotate(f"Now {len(rising)} of {len(rising) + len(falling)} above: " + _names(rising),
                    xy=(0.012, 0.97), xycoords="axes fraction", ha="left", va="top",
                    fontsize=9, fontweight="bold", color="#0B8F82")
        ax.annotate(f"Below: " + _names(falling),
                    xy=(0.012, 0.03), xycoords="axes fraction", ha="left", va="bottom",
                    fontsize=9, fontweight="bold", color="#9B1C31")

        ax.set_ylabel("Share above 200-day average (%)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.set_ylim(-22, 124)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.margins(x=0.01)
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)

        _t, _s = WEEKLY_TITLES["commodities_breadth"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Yahoo Finance (13 energy, metal and agricultural futures)")
        EconStyle.save_chart(fig, output_dir / "23c_commodities_breadth.png")
    except Exception as e:
        print(f"   ⚠ Commodity breadth failed: {e}")

    # ── 23d. THE LONG COMMODITY CYCLE ──
    # Breadth says how wide today's move is; this says where it sits in the
    # long cycle. The S&P GSCI spot index, deflated by US CPI so that the
    # 1980s and today are in the same money, with each high marked once prices
    # fell 36% from it and each low once they rose 57% (a log swing of 0.45).
    # Monthly averages on both sides, as CPI is an average over the
    # month: a month enters only once its CPI is published, so no price level
    # is carried into a month it did not measure.
    print("   [23d] The Long Commodity Cycle (real S&P GSCI, since 1984)")
    try:
        gsci_s = yf_fetcher.get_close_series("^SPGSCI", period="max")
        if len(gsci_s) < 8000:
            raise ValueError("no long S&P GSCI history")
        gsci_s.index = gsci_s.index.tz_localize(None)
        cpi_s = fred_fetcher.fetch_series("CPIAUCSL", period_years=50)
        real_s = (gsci_s.resample("MS").mean() / cpi_s).dropna()
        real_s = real_s / real_s.mean() * 100
        first, last = real_s.index[0].year, real_s.index[-1].year

        fig, ax = EconStyle.create_figure(size="wide")
        color = EconStyle.LINE_ORANGE
        ax.plot(real_s.index.to_pydatetime(), real_s.values, color=color, linewidth=2.5, zorder=4)
        ax.axhline(100, color=EconStyle.INK_MUTED, linewidth=1.1, linestyle="--", zorder=3)
        # Over the 1990s, when the line runs well below the average.
        ax.annotate(f"{first}–{last} average", xy=(pd.Timestamp("1993-01-01"), 100),
                    xytext=(0, 4), textcoords="offset points", ha="left", va="bottom",
                    fontsize=8.5, color=EconStyle.INK_MUTED)
        _mark_turns(ax, _turning_points(real_s, 0.45), color)

        latest = float(real_s.iloc[-1])
        ax.annotate(f"{latest:.0f}", xy=(real_s.index[-1], latest), xytext=(8, 0),
                    textcoords="offset points", va="center", ha="left", fontsize=11,
                    fontweight="bold", color=color, annotation_clip=False)

        ax.set_ylim(real_s.min() * 0.6, real_s.max() * 1.1)      # room for the dated turns
        ax.set_ylabel("Index, average = 100", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.margins(x=0.01)
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)

        # Last, once the years on screen are settled (see _recession_bands).
        _recession_bands(ax, fred_fetcher.fetch_series("USREC", period_years=60))

        _t, _s = WEEKLY_TITLES["commodity_cycle"][mode]
        EconStyle.set_title(ax, _t, _s.format(start=first, end=last))
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "S&P GSCI via Yahoo Finance · US CPI via FRED; recession dates NBER via FRED")
        EconStyle.save_chart(fig, output_dir / "23d_commodity_cycle.png")
    except Exception as e:
        print(f"   ⚠ Long commodity cycle failed: {e}")

    # ── 24. AGRICULTURAL COMMODITIES ──
    print("   [24] Agricultural Commodities — Weekly Bar Chart")
    try:
        AGRI_TICKERS = {
            "ZW=F": "Wheat",
            "ZC=F": "Corn",
            "ZS=F": "Soybeans",
            "KC=F": "Coffee",
            "SB=F": "Sugar",
            "CC=F": "Cocoa",
        }
        agri_data = []
        for ticker, name in AGRI_TICKERS.items():
            try:
                result = yf_fetcher.weekly_change(ticker)
                if result:
                    agri_data.append((name, result["change_pct"]))
            except Exception:
                pass

        if agri_data:
            agri_data.sort(key=lambda x: x[1])
            names_ag  = [d[0] for d in agri_data]
            values_ag = [d[1] for d in agri_data]

            if _bad_fetch(values_ag, len(AGRI_TICKERS)):
                _flag_skipped("Agricultural Commodities — Weekly", len(values_ag), len(AGRI_TICKERS))
            else:
                _t, _s = WEEKLY_TITLES["agri_weekly"][mode]
                fig = render_change_bars(names_ag, values_ag, _t, _s.format(date=date_label),
                                         "Yahoo Finance (CBOT · ICE Futures)")
                EconStyle.save_chart(fig, output_dir / "24_agri_weekly.png")
    except Exception as e:
        print(f"   ⚠ Agricultural commodities failed: {e}")

    # ── 25. INDIA VIX VS US VIX ──
    print("   [25] India VIX vs US VIX (1-Year Trend)")
    try:
        india_vix_dates, india_vix_vals = get_trend("india_vix")
        us_vix_dates, us_vix_vals       = get_trend("vix")

        if india_vix_dates and us_vix_dates:
            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_india = "#FF6B00"
            color_us    = "#1C1C1E"

            l1, = ax1.plot(india_vix_dates, india_vix_vals, color=color_india,
                           linewidth=2.5, label="India VIX")
            l2, = ax2.plot(us_vix_dates, us_vix_vals, color=color_us,
                           linewidth=2.0, linestyle="--", alpha=0.8, label="US VIX")

            ax1.set_ylabel("India VIX", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color=color_india)
            ax2.set_ylabel("US VIX",   fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color=color_us)

            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)

            ax1.legend(handles=[l1, l2], loc="upper right", frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["india_vix_vs_us"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (NSE · CBOE)")
            EconStyle.save_chart(fig, output_dir / "25_india_vix_vs_us.png")
    except Exception as e:
        print(f"   ⚠ India VIX vs US VIX failed: {e}")

    # ── 26. ETH/BTC RATIO ──
    print("   [26] ETH/BTC Ratio + BTC & ETH Indexed Trend")
    try:
        btc_s = yf_fetcher.get_close_series("BTC-USD", period="2y")
        eth_s = yf_fetcher.get_close_series("ETH-USD", period="2y")

        if len(btc_s) > 50 and len(eth_s) > 50:
            # Align on common dates
            import pandas as pd
            combined = pd.DataFrame({"btc": btc_s, "eth": eth_s}).dropna()
            ratio_s  = combined["eth"] / combined["btc"]
            mean_52w = ratio_s.rolling(252).mean()

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_ratio = "#7C3AED"
            color_btc   = "#F59E0B"
            color_eth   = "#3B82F6"

            r_dates = ratio_s.index.to_pydatetime()
            l1, = ax1.plot(r_dates, ratio_s.values, color=color_ratio, linewidth=2.5, label="ETH/BTC Ratio")
            ax1.plot(mean_52w.index.to_pydatetime(), mean_52w.values,
                     color="#6B7280", linewidth=1.2, linestyle="--", alpha=0.7, label="52-Week Mean")

            # Secondary axis: BTC & ETH indexed to 100 (faint)
            btc_idx = (combined["btc"] / combined["btc"].iloc[0]) * 100
            eth_idx = (combined["eth"] / combined["eth"].iloc[0]) * 100
            l2, = ax2.plot(combined.index.to_pydatetime(), btc_idx.values,
                           color=color_btc, linewidth=1.5, alpha=0.45, linestyle="-", label="BTC (indexed)")
            l3, = ax2.plot(combined.index.to_pydatetime(), eth_idx.values,
                           color=color_eth, linewidth=1.5, alpha=0.45, linestyle="-", label="ETH (indexed)")

            ax1.set_ylabel("ETH/BTC Ratio", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color=color_ratio)
            ax2.set_ylabel("Indexed to 100 (2Y start)", fontsize=EconStyle.FONT_SIZE_AXIS, color="#9CA3AF")

            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)
            
            # Floating in the empty bottom-left corner with a premium white background
            handles = [l1] + ax1.lines[1:2] + [l2, l3]
            ax1.legend(handles=handles, loc="lower left", ncol=1, 
                       frameon=True, facecolor="white", edgecolor="none", framealpha=0.85, fontsize=9.5)

            _t, _s = WEEKLY_TITLES["eth_btc_ratio"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance")
            EconStyle.save_chart(fig, output_dir / "26_eth_btc_ratio.png")
    except Exception as e:
        print(f"   ⚠ ETH/BTC ratio failed: {e}")

    # ── 28. BITCOIN VS GLOBAL M2 ──
    # Bitcoin against the broad money of seven major economies in dollars
    # (_global_m2_weekly), since 2013. The price is Coin Metrics', as Yahoo's
    # BTC-USD starts only in September 2014. Shaded: each spell of two months
    # or more with global M2 below its level a year earlier. There have been
    # three (2015, early 2019, 2022–23), all when a strong dollar shrank the
    # non-US money in dollar terms (at fixed exchange rates it grew 5–8% a
    # year throughout), and all with bitcoin in a bear market. Coin Metrics
    # and global M2 are fetched once, here, and reused by charts 29 and 30.
    print("   [28] Bitcoin vs. Global M2 (since 2013)")
    cm = gm2 = None
    try:
        import pandas as pd
        import matplotlib.ticker as mticker
        from generate_macro import _end_dot
        from data.fetchers.coinmetrics_fetcher import fetch_btc_mvrv, mvrv_zscore
        cm = fetch_btc_mvrv()
        cm["z"] = mvrv_zscore(cm)
        gm2 = _global_m2_weekly(fred_fetcher)
        btc = cm["price"][cm.index >= "2013-01-01"].dropna()
        m2 = gm2[gm2.index >= "2013-01-01"]
        if len(btc) < 3000 or len(m2) < 500:
            raise ValueError(f"only {len(btc)} days of price and {len(m2)} weeks of global M2")

        # Weeks with global M2 below a year earlier, joined across gaps of
        # under eight weeks; spells shorter than eight weeks are left out.
        spells = []
        for week in m2.index[m2.pct_change(52) < 0]:
            if spells and (week - spells[-1][1]).days < 56:
                spells[-1][1] = week
            else:
                spells.append([week, week])
        spells = [(a, b) for a, b in spells if (b - a).days >= 56]

        c_btc, c_m2 = "#F59E0B", "#1D4ED8"
        fig, ax1 = EconStyle.create_figure(size="wide")
        ax2 = ax1.twinx()
        for a, b in spells:
            ax1.axvspan(a, b, color="#4B5563", alpha=0.12, lw=0, zorder=0)
        ax1.plot(btc.index.to_pydatetime(), btc.values, color=c_btc, linewidth=1.8, zorder=3)
        ax2.plot(m2.index.to_pydatetime(), m2.values, color=c_m2, linewidth=2.2, linestyle="--",
                 alpha=0.85, zorder=3)
        _end_dot(ax1, btc.index[-1].to_pydatetime(), float(btc.iloc[-1]), c_btc, zorder=7, size=26)
        _end_dot(ax2, m2.index[-1].to_pydatetime(), float(m2.iloc[-1]), c_m2, zorder=7, size=26)
        if spells:
            ax1.annotate("Shaded: global M2 below its level a year earlier", xy=(0.99, 0.03),
                         xycoords="axes fraction", ha="right", va="bottom", fontsize=8.5,
                         color=EconStyle.INK_MUTED, zorder=6)

        ax1.set_yscale("log")
        ax1.yaxis.set_major_locator(mticker.LogLocator(base=10))
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda v, _: f"${v / 1000:,.0f}k" if v >= 1000 else f"${v:,.0f}"))
        ax1.yaxis.set_minor_locator(mticker.NullLocator())
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}tn"))
        ax1.set_ylabel("Bitcoin price, log scale", fontsize=EconStyle.FONT_SIZE_AXIS,
                       fontweight="bold", color="#1C1C1E")
        ax2.set_ylabel("Global M2, US dollars", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold",
                       color="#1C1C1E", rotation=270, labelpad=14)
        # One set of gridlines, bitcoin's: a second set for global M2 would not line up with it.
        ax2.grid(False)
        ax1.grid(axis="x", visible=False)
        ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax1.margins(x=0.01)
        ax1.xaxis.set_major_locator(mdates.YearLocator(2))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for ax in (ax1, ax2):
            ax.tick_params(axis="y", length=0)
            for sp in ['top', 'right', 'left']:
                ax.spines[sp].set_visible(False)

        # Each entry carries today's reading.
        handles = [
            plt.Line2D([], [], color=c_btc, linewidth=2, label=f"Bitcoin, left axis  ${btc.iloc[-1]:,.0f}"),
            plt.Line2D([], [], color=c_m2, linewidth=2, linestyle="--",
                       label=f"Global M2, right axis  ${m2.iloc[-1]:,.1f}tn"),
        ]
        ax1.legend(handles=handles, loc="upper left", frameon=False, fontsize=9.5)

        _t, _s = WEEKLY_TITLES["btc_global_m2"][mode]
        EconStyle.set_title(ax1, _t, _s)
        EconStyle.add_top_rule(ax1)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Coin Metrics  ·  OECD broad money of 7 economies in US dollars (FRED exchange rates)")
        EconStyle.save_chart(fig, output_dir / "28_btc_global_m2.png")
    except Exception as e:
        print(f"   ⚠ Bitcoin vs. global M2 failed: {e}")

    # ── 29. BITCOIN MVRV Z-SCORE ──
    # Where bitcoin sits in its own cycle: market value against realised value,
    # roughly what holders paid for their coins, and the Z-score of the gap,
    # (market value − realised value) ÷ the spread of market value to date.
    # From Coin Metrics' free API, which carries MVRV but not realised value,
    # so realised value is derived from the two (see coinmetrics_fetcher).
    # Two y-axes, as the metric is always drawn: dollars on a log scale (left)
    # and the Z-score (right). Above 7 (red) marked the tops up to early 2021;
    # below 0 (green), market value is under realised value, which has marked
    # every bear-market low. Each cycle has peaked lower (10.7 in 2013, 7.2 in
    # 2021, 3.4 in 2024), so the peaks are labelled and the last reading in
    # the red band is dated, rather than the band promising a top.
    print("   [29] Bitcoin MVRV Z-Score (since 2011)")
    try:
        import pandas as pd
        import matplotlib.ticker as mticker
        from matplotlib.patches import Rectangle
        from matplotlib.transforms import blended_transform_factory
        from generate_macro import _end_dot
        from data.fetchers.coinmetrics_fetcher import fetch_btc_mvrv, mvrv_zscore
        if cm is None:                                  # chart 28 could not fetch it
            cm = fetch_btc_mvrv()
            cm["z"] = mvrv_zscore(cm)
        d = cm[cm.index >= "2011-01-01"]
        HOT, COLD = 7.0, 0.0
        # Validated as a set, every pair, since the lines cross: violet, blue, orange.
        c_mv, c_rv, c_z = "#4A3AA7", "#2A78D6", EconStyle.LINE_ORANGE
        RED, GREEN = "#E34948", "#22A06B"

        def usd(v, _=None):
            for size, unit in ((1e12, "tn"), (1e9, "bn"), (1e6, "m")):
                if v >= size:
                    n = v / size
                    return f"${n:,.{0 if n >= 100 or n == round(n) else 2}f}{unit}"
            return f"${v:,.0f}"

        fig, ax1 = EconStyle.create_figure(size=(EconStyle.SIZE_WIDE[0], 5.4))
        ax2 = ax1.twinx()
        x = d.index.to_pydatetime()

        # The bands belong to the Z-score but sit on the dollar axes, behind
        # every line, so the market-value lines are never tinted by them.
        z_top = max(HOT + 3, float(d["z"].max()) * 1.18)       # room for the peak labels
        z_bot = -2.6                                           # room for the lows' labels
        ax2.set_ylim(z_bot, z_top)
        on_z = blended_transform_factory(ax1.transAxes, ax2.transData)
        ax1.add_patch(Rectangle((0, HOT), 1, z_top - HOT, transform=on_z, color=RED, alpha=0.10, lw=0, zorder=0))
        ax1.add_patch(Rectangle((0, z_bot), 1, COLD - z_bot, transform=on_z, color=GREEN, alpha=0.13, lw=0, zorder=0))

        ax1.plot(x, d["mcap"].values, color=c_mv, linewidth=1.5, zorder=3)
        ax1.plot(x, d["rcap"].values, color=c_rv, linewidth=1.5, zorder=3)
        ax2.plot(x, d["z"].values, color=c_z, linewidth=1.8, zorder=4)
        for ax, col, val in ((ax1, c_mv, d["mcap"].iloc[-1]), (ax1, c_rv, d["rcap"].iloc[-1]),
                             (ax2, c_z, d["z"].iloc[-1])):
            _end_dot(ax, x[-1], val, col, zorder=7, size=26)

        # Each cycle's peak, labelled with its value: the turns the weekly
        # Z-score fell at least 3 from, each placed on the highest day within
        # six weeks of it (a daily peak can fall between two weekly closes).
        z_week = d["z"].resample("W-FRI").last().dropna()
        for when, _, kind in _turning_points(z_week, 3.0, log=False):
            if kind != "high":
                continue
            near = d["z"][when - pd.Timedelta(weeks=6): when + pd.Timedelta(weeks=6)]
            peak_day, peak = near.idxmax(), float(near.max())
            ax2.plot(peak_day, peak, "o", ms=5, color=c_z, mec="white", mew=1.2, zorder=6)
            ax2.annotate(f"{peak:.1f}", xy=(peak_day, peak), xytext=(0, 7), textcoords="offset points",
                         ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=EconStyle.INK, zorder=6)

        # Every spell below zero, dated at its lowest day (spells under six
        # months apart count as one). A date within 18 months of the one
        # before drops a line, so the two never overlap.
        below = d["z"][d["z"] < COLD]
        spell = (below.index.to_series().diff() > pd.Timedelta(days=183)).cumsum()
        prev = None
        for _, s in below.groupby(spell.values):
            low_day, low = s.idxmin(), float(s.min())
            drop = prev is not None and (low_day - prev).days < 548
            ax2.plot(low_day, low, "o", ms=5, color=c_z, mec="white", mew=1.2, zorder=6)
            ax2.annotate(f"{low_day:%b %Y}", xy=(low_day, low), xytext=(0, -19 if drop else -7),
                         textcoords="offset points", ha="center", va="top", fontsize=8.5,
                         fontweight="bold", color="#0F6B45", zorder=6)
            prev = low_day

        last_hot = d.index[d["z"] > HOT].max()
        ax2.annotate(f"Above {HOT:g}: overheated  ·  last reached {last_hot:%b %Y}", xy=(0.99, z_top - 0.35),
                     xycoords=("axes fraction", "data"), ha="right", va="top",
                     fontsize=9, fontweight="bold", color="#B42318", zorder=6)
        ax2.annotate("Below 0: market value\nunder realised value", xy=(0.99, z_bot + 0.3),
                     xycoords=("axes fraction", "data"), ha="right", va="bottom", linespacing=1.15,
                     fontsize=9, fontweight="bold", color="#0F6B45", zorder=6)

        # Room past the last day for the end dots; no year ticks past the data.
        ax1.margins(x=0.01)
        x0, x1 = ax1.get_xlim()
        ax1.set_xlim(x0, x1 + (x1 - x0) * 0.015)
        ax1.set_yscale("log")
        ax1.set_ylim(d[["mcap", "rcap"]].min().min() / 3, d["mcap"].max() * 6)
        ax1.yaxis.set_major_locator(mticker.FixedLocator([1e6, 1e8, 1e10, 1e12]))
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(usd))
        ax1.yaxis.set_minor_locator(mticker.NullLocator())
        ax1.set_ylabel("Market and realised value, log scale", fontsize=EconStyle.FONT_SIZE_AXIS,
                       fontweight="bold", color="#1C1C1E")
        ax2.set_ylabel("MVRV Z-score", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold",
                       color="#1C1C1E", rotation=270, labelpad=14)
        ax2.yaxis.set_major_locator(mticker.MultipleLocator(2))
        # One set of gridlines, the Z-score's: a second set for the dollar axis would not line up with it.
        ax1.grid(False)
        ax2.grid(axis="x", visible=False)
        ax2.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax1.xaxis.set_major_locator(mdates.YearLocator(2))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for ax in (ax1, ax2):
            ax.tick_params(axis="y", length=0)
            for sp in ['top', 'right', 'left']:
                ax.spines[sp].set_visible(False)

        # The key sits under the plot, where it covers no data; each entry carries today's reading.
        handles = [
            plt.Line2D([], [], color=c_mv, linewidth=2, label=f"Market value (MV)  {usd(d['mcap'].iloc[-1])}"),
            plt.Line2D([], [], color=c_rv, linewidth=2, label=f"Realised value (RV)  {usd(d['rcap'].iloc[-1])}"),
            plt.Line2D([], [], color=c_z, linewidth=2.4, label=f"Z-score, right axis  {d['z'].iloc[-1]:.2f}"),
        ]
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.045), ncol=3,
                   frameon=False, fontsize=9, handlelength=1.8, columnspacing=2.2)

        _t, _s = WEEKLY_TITLES["btc_mvrv_zscore"][mode]
        EconStyle.set_title(ax1, _t, _s.format(start=d.index[0].year))
        EconStyle.add_top_rule(ax1)
        fig.tight_layout(rect=[0.02, 0.085, 0.98, 0.96])
        EconStyle.add_source(fig, "Coin Metrics Community API  ·  Z-score = (MV − RV) ÷ standard deviation of MV to date")
        EconStyle.save_chart(fig, output_dir / "29_btc_mvrv_zscore.png")
    except Exception as e:
        print(f"   ⚠ Bitcoin MVRV Z-score failed: {e}")

    # ── 30. BITCOIN, GLOBAL M2 AND THE Z-SCORE ──
    # Inspired by "Bitcoin: A Global Liquidity Barometer" (Sam Callahan for Lyn
    # Alden, Sep 2024), which found bitcoin moving with global M2 more often
    # than any other major asset, and its 12-month correlation with it breaking
    # down as the MVRV Z-score fell from its cycle highs. Global M2 is OECD
    # broad money in dollars (_global_m2_weekly); the correlation is over 52
    # weekly closes, in logs. Shaded: each fall of the Z-score from a cycle
    # high (a turn it fell at least 3 from) to its low, or to today while no
    # low has formed. The Z-score's overheated and undervalued bands are left
    # to chart 29, which sits beside this one.
    print("   [30] Bitcoin's correlation with global M2 vs. the MVRV Z-score")
    try:
        import numpy as np
        import pandas as pd
        import matplotlib.ticker as mticker
        from data.fetchers.coinmetrics_fetcher import fetch_btc_mvrv, mvrv_zscore
        if cm is None:
            cm = fetch_btc_mvrv()
            cm["z"] = mvrv_zscore(cm)
        if gm2 is None:
            gm2 = _global_m2_weekly(fred_fetcher)
        wk = pd.DataFrame({"btc": cm["price"].resample("W-FRI").last(), "z": cm["z"].resample("W-FRI").last(),
                           "m2": gm2}).dropna()
        wk["corr"] = np.log(wk["btc"]).rolling(52).corr(np.log(wk["m2"]))
        wk = wk[wk.index >= "2012-01-01"].dropna()
        if len(wk) < 300:
            raise ValueError("too little overlapping history")

        falls, turns = [], _turning_points(cm["z"][cm.index >= "2011-01-01"].resample("W-FRI").last().dropna(),
                                           3.0, log=False)
        for i, (when, _, kind) in enumerate(turns):
            if kind == "high":
                end = next((w for w, _, k in turns[i + 1:] if k == "low"), wk.index[-1])
                if end > wk.index[0]:                        # not a fall over before the chart starts
                    falls.append((max(when, wk.index[0]), end))
        falling = pd.Series(False, index=wk.index)
        for a, b in falls:
            falling |= (wk.index >= a) & (wk.index <= b)

        c_z, c_corr = EconStyle.LINE_ORANGE, EconStyle.LINE_BLUE
        fig, (ax1, ax2) = EconStyle.create_figure(
            size=(EconStyle.SIZE_WIDE[0], 6.2), nrows=2, sharex=True,
            gridspec_kw={"height_ratios": [1, 1.1], "hspace": 0.14})
        x = wk.index.to_pydatetime()
        for ax in (ax1, ax2):
            for a, b in falls:
                ax.axvspan(a, b, color="#4B5563", alpha=0.10, lw=0, zorder=0)

        z_top = max(10.0, float(wk["z"].max()) * 1.15)
        ax1.plot(x, wk["z"].values, color=c_z, linewidth=1.9, zorder=4)
        ax1.axhline(0, color=EconStyle.INK_MUTED, linewidth=0.9, zorder=3)
        ax1.set_ylim(-1.5, z_top)
        ax1.set_ylabel("MVRV Z-score", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color="#1C1C1E")
        ax1.annotate("Shaded: from each cycle high of the Z-score to the low that followed", xy=(0.99, 0.95),
                     xycoords="axes fraction", ha="right", va="top", fontsize=8.5,
                     color=EconStyle.INK_MUTED, zorder=6)

        corr = wk["corr"].values
        ax2.fill_between(x, corr, 0, where=corr >= 0, interpolate=True, color=EconStyle.GAIN, alpha=0.16, lw=0, zorder=1)
        ax2.fill_between(x, corr, 0, where=corr < 0, interpolate=True, color=EconStyle.LOSS, alpha=0.20, lw=0, zorder=1)
        ax2.plot(x, corr, color=c_corr, linewidth=1.7, zorder=4)
        ax2.axhline(0, color=EconStyle.INK_MUTED, linewidth=0.9, zorder=3)
        ax2.set_ylim(-1.05, 1.05)
        ax2.yaxis.set_major_locator(mticker.MultipleLocator(0.5))
        ax2.set_ylabel("Correlation with global M2", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold",
                       color="#1C1C1E")
        now = float(wk["corr"].iloc[-1])
        ax2.annotate(f"{'−' if now < 0 else ''}{abs(now):.2f}", xy=(x[-1], now), xytext=(6, 0),
                     textcoords="offset points", va="center", ha="left", fontsize=10.5,
                     fontweight="bold", color=EconStyle.INK, annotation_clip=False)
        # The weakest the link has been, labelled on the side with room.
        low_week, low = wk["corr"].idxmin(), float(wk["corr"].min())
        right_half = low_week > wk.index[0] + (wk.index[-1] - wk.index[0]) / 2
        ax2.plot(low_week, low, "o", ms=5, color=c_corr, mec="white", mew=1.2, zorder=6)
        ax2.annotate(f"Lowest since {wk.index[0].year}: −{abs(low):.2f}, {low_week:%b %Y}" if low < 0 else
                     f"Lowest since {wk.index[0].year}: {low:.2f}, {low_week:%b %Y}",
                     xy=(low_week, low), xytext=(-12 if right_half else 12, 30), textcoords="offset points",
                     ha="right" if right_half else "left", va="bottom", fontsize=8.5, fontweight="bold",
                     color=EconStyle.INK, zorder=6,
                     arrowprops=dict(arrowstyle="-", color=c_corr, linewidth=0.8, shrinkA=2, shrinkB=3))
        in_fall, other = wk["corr"][falling].mean(), wk["corr"][~falling].mean()
        ax2.annotate(f"Average correlation while the Z-score falls from a cycle high: {in_fall:.2f}  ·  "
                     f"at other times: {other:.2f}",
                     xy=(0.01, 0.04), xycoords="axes fraction", ha="left", va="bottom", fontsize=8.5,
                     fontweight="bold", color=EconStyle.INK, zorder=6)

        ax2.xaxis.set_major_locator(mdates.YearLocator(2))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        for ax in (ax1, ax2):
            ax.margins(x=0.01)
            ax.grid(axis="x", visible=False)
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.tick_params(axis="y", length=0)
            for sp in ['top', 'right', 'left']:
                ax.spines[sp].set_visible(False)

        _t, _s = WEEKLY_TITLES["btc_zscore_global_m2"][mode]
        EconStyle.set_title(ax1, _t, _s.format(start=wk.index[0].year))
        EconStyle.add_top_rule(ax1)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Coin Metrics  ·  OECD broad money of 7 economies in US dollars (FRED exchange rates)")
        EconStyle.save_chart(fig, output_dir / "30_btc_zscore_global_m2.png")
    except Exception as e:
        print(f"   ⚠ Bitcoin vs. global M2 correlation failed: {e}")

    # ── SUMMARY TABLE ──
    print("   [+] Summary Table")
    table = SummaryTable()
    
    # Define the rows we want (Ordered list)
    row_ids = [
        "sp500", "ftse100", "eurostoxx50", "nifty50", "nikkei225", # Equities
        "brent", "gold", "silver", "copper", "natgas",             # Commodities
        "dxy", "eurusd", "gbpusd", "usdinr", "usdjpy",             # FX
        "us_2y", "us_10y", "us_30y", "de_10y",                     # Yields
        "btc", "eth",                                              # Crypto Assets
        "vix", "india_vix", "move_index",                          # Volatility
    ]
    
    for ind_id in row_ids:
        if ind_id in weekly_data:
            ind = INDICATORS[ind_id]
            w = weekly_data[ind_id]
            
            # CALCULATE YTD
            ytd_val = get_ytd_change(ind_id)
            
            # Format YTD based on type
            if ytd_val is None:
                ytd_str = "-"
            elif ind_id in ["vix", "india_vix", "move_index"]:
                ytd_str = f"{ytd_val:+.1f} pts"
            elif ind["change_type"] == "abs":
                ytd_str = EconStyle.format_change_label(ytd_val, "abs")
            else: # Everything else (%)
                ytd_str = EconStyle.format_change_label(ytd_val * 100, "pct") # *100 for display

            # VIX / MOVE: weekly change is absolute points, not percentage
            if ind_id in ["vix", "india_vix"]:
                # Back-calculate absolute change from level and change_pct
                if "change_pct" in w and w["change_pct"] != 0:
                    prev_level = w["level"] / (1 + w["change_pct"] / 100)
                    points_abs = w["level"] - prev_level
                    weekly_str = f"{points_abs:+.1f} pts"
                else:
                    weekly_str = "0.0 pts"
            elif ind_id == "move_index":
                # MOVE index: level is in bps, change_abs is raw bps change
                chg = w.get("change_abs", 0)
                weekly_str = f"{chg:+.1f} pts"
            elif "change_pct" in w:
                weekly_str = EconStyle.format_change_label(w["change_pct"], "pct")
            else:
                weekly_str = EconStyle.format_change_label(w["change"], "abs")

            table.add_row(ind["name"], f"{w['level']:,.2f}",
                          weekly_str,
                          ytd_change=ytd_str,
                          category=ind.get("category", "misc"))

    # ── Special row: Real Wage Growth (computed, not in INDICATORS) ──
    if real_wage_latest is not None:
        rw_weekly_str = f"{real_wage_change:+.2f} pp" if real_wage_change is not None else "-"
        table.add_row("US Real Wage Growth", f"{real_wage_latest:.2f}%",
                      rw_weekly_str, ytd_change="-", category="volatility")

    table.render(title="Market Snapshot",
                 subtitle=f"Week ending {datetime.now().strftime('%d %B %Y')}",
                 source="Yahoo Finance, FRED")
    table.save(output_dir / "00_summary_table.png")

    print(f"\n✅ Dashboard complete! {len(list(output_dir.glob('*.png')))} charts saved to:")
    print(f"   {output_dir}")

    if SKIPPED_CHARTS:
        print(f"\n⚠ {len(SKIPPED_CHARTS)} chart(s) skipped this run — Yahoo Finance data looked incomplete or degenerate:")
        for m in SKIPPED_CHARTS:
            print(f"   - {m}")

        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a") as f:
                f.write("### ⚠ Weekly dashboard — charts skipped this run\n")
                f.write("Likely Yahoo Finance rate-limiting; the rest of the dashboard still published.\n\n")
                for m in SKIPPED_CHARTS:
                    f.write(f"- {m}\n")

        # One or two isolated tickers flaking is normal and fine to skip
        # quietly-ish; this many failing at once means Yahoo is down for
        # this whole run, not just one series — worth failing the job so a
        # half-broken edition doesn't get committed and published unnoticed.
        if len(SKIPPED_CHARTS) >= 3:
            sys.exit(
                f"\n❌ {len(SKIPPED_CHARTS)} charts skipped — treating this as a Yahoo Finance "
                "outage rather than publishing a half-broken edition. Re-run the workflow later."
            )


def main():
    parser = argparse.ArgumentParser(description="Generate Economics Hub Weekly Dashboard")
    parser.add_argument("--preview", action="store_true", help="Generate at lower DPI")
    parser.add_argument(
        "--mode",
        choices=["dashboard", "newsletter"],
        default="dashboard",
        help="Title mode: 'dashboard' for standard titles, 'newsletter' for narrative Substack titles",
    )
    args = parser.parse_args()

    if args.preview:
        EconStyle.DPI = EconStyle.DPI_PREVIEW

    output_dir = get_output_dir()

    generate_with_live_data(output_dir, mode=args.mode)


if __name__ == "__main__":
    main()

