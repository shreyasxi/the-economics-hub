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
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from charts.style import EconStyle
from charts.templates.weekly_bar import WeeklyBarChart
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
            "Growth expectations proxy vs. sovereign yield direction  ·  2-year window",
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
            "SPHB/SPLV ratio below its 26-week mean signals investors rotating to defensive equities",
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
            "RSP/SPY below its 20-week average confirms the rally is concentrated, not broad-based",
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
            "INDA, EEM, MCHI, EWY indexed to 100 at start  ·  total return comparison",
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
            "Share of 13 major commodities trading above their own 200-day average",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Commodity Rally Is Narrower Than It Looks",
            "Energy is carrying the complex while precious metals roll over",
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
    "btc_gold_ratio": {
        "dashboard": (
            "Bitcoin vs. Gold Ratio — Digital vs. Monetary Safe Haven",
            "BTC/Gold price ratio  ·  rising = crypto commanding more per oz of gold",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Bitcoin Is Reclaiming Its Role as Digital Gold",
            "BTC/Gold ratio recovering above its 1-year mean signals renewed institutional bitcoin demand",
        ),
    },
    "btc_global_m2": {
        "dashboard": (
            "Bitcoin vs. US M2 Money Supply",
            "BTC price (log scale, left) vs. US M2 Supply (right)  ·  Trend since 2013",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Bitcoin vs. US Liquidity: The M2 Correlation",
            "The expansion of US M2 remains a structural driver for crypto prices",
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
                ticker = __import__('yfinance').Ticker(ind["ticker"])
                hist = ticker.history(start=start_date)
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
    print("\n   [1/8] Equities — Aesthetic Vertical Bar Chart (Weekly)")
    eq_ids = ["sp500", "dow", "nasdaq", "ftse100", "eurostoxx50", "nifty50", "shanghai", "hangseng", "nikkei225"]
    names, values, cks = build_bar_data(eq_ids)
    
    # Create the custom figure using your wide template
    fig, ax = EconStyle.create_figure(size="wide")
    
    # Premium Institutional Colors
    color_pos = "#03AF53" # Deep, authoritative Slate Blue
    color_neg = "#820E0E" # Deep, striking red for negatives
    colors = [color_pos if v >= 0 else color_neg for v in values]
    
    # Plot the vertical bars
    bars = ax.bar(names, values, color=colors, width=0.25, zorder=3)
    
    # Restore the Y-Axis and Gridlines
    ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
    ax.set_ylabel("Weekly Change (%)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight='bold', color="#1C1C1E")
    
    # Clean up the outer box spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    
    # Heavy Zero-Line anchor
    ax.axhline(0, color='#1C1C1E', linewidth=1.5, zorder=4)
    
    # Clean up the X-axis labels
    ax.xaxis.set_tick_params(length=0) 
    ax.set_xticklabels(names, fontweight='bold', fontsize=8.5, color="#1C1C1E")
    
    # Dynamic Y-Axis Logic (Fixing the gap)
    min_v = min(values) if values else 0
    max_v = max(values) if values else 0
    y_range = max_v - min_v if max_v != min_v else (max_v if max_v != 0 else 1)
    
    y_bottom = (min_v - y_range * 0.15) if min_v < 0 else 0
    y_top = (max_v + y_range * 0.15) if max_v > 0 else 0
    
    ax.set_ylim(y_bottom, y_top)
    
    for bar, v in zip(bars, values):
        yval = bar.get_height()
        offset = y_range * 0.02 
        
        if v >= 0:
            y_pos = yval + offset
            va = 'bottom'
        else:
            y_pos = yval - offset
            va = 'top'
            
        ax.text(
            bar.get_x() + bar.get_width()/2, 
            y_pos, 
            f"{v:+.1f}%", 
            ha='center', va=va, 
            fontweight='bold', fontsize=12, color=bar.get_facecolor()
        )

    # Apply Full EconStyle Branding
    _t, _s = WEEKLY_TITLES["equities_weekly"][mode]
    EconStyle.set_title(ax, _t, _s.format(date=date_label))
    EconStyle.add_top_rule(ax) 
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "Yahoo Finance")
    
    EconStyle.save_chart(fig, output_dir / "01_equities_weekly.png")

    print("   [2/8] Equities — 12-Month Trends")
    trend = TrendLineChart()
    for ind_id in ["sp500", "nifty50", "ftse100"]:
        dates, vals = get_trend(ind_id)
        if dates:
            ind = INDICATORS[ind_id]
            trend.add_series(ind["name"], dates, vals, color_key=ind["color_key"])
    trend.render(title="Major Indices — Trailing 12 Months",
                 subtitle="Indexed to 100 at start  ·  S&P 500, Nifty 50, FTSE 100",
                 source="Yahoo Finance", normalize=True, ylabel="Indexed (start = 100)")
    trend.save(output_dir / "02_equities_trend.png")

    # ── 2. FX ──

    print("   [4/8] FX — 12-Month Trends")
    trend = TrendLineChart()
    for ind_id in ["dxy", "eurusd","usdinr", "usdjpy"]:
        dates, vals = get_trend(ind_id)
        if dates:
            ind = INDICATORS[ind_id]
            trend.add_series(ind["name"], dates, vals, color_key=ind["color_key"])
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
    print("   [7/8] Commodities — Aesthetic Vertical Bar Chart (Weekly)")
    cm_ids = ["brent", "wti", "gold", "silver", "copper", "natgas", "uranium"]
    names, values, cks = build_bar_data(cm_ids)
    
    # Create the custom figure using your wide template
    fig, ax = EconStyle.create_figure(size="wide")
    
    # 1. Premium Institutional Colors
    color_pos = "#03AF53" # Deep, authoritative Slate Blue
    color_neg = "#820E0E" # Deep, striking red for negatives
    colors = [color_pos if v >= 0 else color_neg for v in values]
    
    # Plot the vertical bars
    bars = ax.bar(names, values, color=colors, width=0.4, zorder=3)
    
    # 2. Restore the Y-Axis and Gridlines
    ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
    ax.set_ylabel("Weekly Change (%)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight='bold', color="#1C1C1E")
    
    # Clean up the outer box spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    
    # Heavy Zero-Line anchor
    ax.axhline(0, color='#1C1C1E', linewidth=1.5, zorder=4)
    
    # Clean up the X-axis labels
    ax.xaxis.set_tick_params(length=0) 
    ax.set_xticklabels(names, fontweight='bold', fontsize=11, color="#1C1C1E")
    
    # 3. Dynamic Y-Axis Logic (Fixing the gap)
    min_v = min(values) if values else 0
    max_v = max(values) if values else 0
    y_range = max_v - min_v if max_v != min_v else (max_v if max_v != 0 else 1)
    
    # Only pad the bottom if there are actual negative numbers. 
    y_bottom = (min_v - y_range * 0.15) if min_v < 0 else 0
    y_top = (max_v + y_range * 0.15) if max_v > 0 else 0
    
    ax.set_ylim(y_bottom, y_top)
    
    for bar, v in zip(bars, values):
        yval = bar.get_height()
        offset = y_range * 0.02 
        
        if v >= 0:
            y_pos = yval + offset
            va = 'bottom'
        else:
            y_pos = yval - offset
            va = 'top'
            
        ax.text(
            bar.get_x() + bar.get_width()/2, 
            y_pos, 
            f"{v:+.1f}%", 
            ha='center', va=va, 
            fontweight='bold', fontsize=12, color=bar.get_facecolor()
        )

    # 4. Apply Full EconStyle Branding
    _t, _s = WEEKLY_TITLES["commodities_weekly"][mode]
    EconStyle.set_title(ax, _t, _s.format(date=date_label))
    EconStyle.add_top_rule(ax) 
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "Yahoo Finance")
    
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
    try:
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
            s_colors = [EconStyle.POSITIVE if v >= 0 else EconStyle.NEGATIVE for v in s_values]

            chart = WeeklyBarChart(names=s_names, values=s_values, color_keys=["us"] * len(s_names))
            chart.render(title="S&P 500 Sector Rotation",
                         subtitle=f"Weekly performance by sector  ·  {date_label}",
                         source="Yahoo Finance (SPDR ETFs)")
            chart.save(output_dir / "10_sector_rotation.png")
    except Exception as e:
        print(f"   ⚠ Sector rotation failed: {e}")
        
    # ── 7.NIFTY SECTOR ROTATION ──
    print("   [11/12] NIFTY Sector Rotation")
    try:
        # Sourced from NSE directly: Yahoo stopped updating most ^CNX* sector
        # indices in Jul 2026, which silently cut the chart to three sectors.
        from data.fetchers.india_fetcher import fetch_nifty_sector_weekly
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
        nse = fetch_nifty_sector_weekly(list(NIFTY_SECTORS))
        sector_data = [(label, nse[idx]["change_pct"]) for idx, label in NIFTY_SECTORS.items()]

        if sector_data:
            # Sort by performance (best to worst)
            sector_data.sort(key=lambda x: x[1], reverse=True)
            s_names = [s[0] for s in sector_data]
            s_values = [s[1] for s in sector_data]
            s_colors = [EconStyle.POSITIVE if v >= 0 else EconStyle.NEGATIVE for v in s_values]

            chart = WeeklyBarChart(names=s_names, values=s_values, color_keys=["us"] * len(s_names))
            chart.render(title="NIFTY Sector Rotation",
                         subtitle=f"Weekly performance by sector  ·  {date_label}",
                         source="NSE (allIndices)")
            chart.save(output_dir / "10b_india_sector_rotation.png")
    except Exception as e:
        print(f"   ⚠ Sector rotation failed: {e}")
        
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
            fig, ax = EconStyle.create_figure(size="wide")
            color_pos = "#03AF53"
            color_neg = "#820E0E"
            colors_fx = [color_pos if v >= 0 else color_neg for v in values_fx]
            bars = ax.bar(names_fx, values_fx, color=colors_fx, width=0.25, zorder=3)

            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.set_ylabel("Weekly Change (%)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight='bold', color="#1C1C1E")
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_visible(False)
            ax.axhline(0, color='#1C1C1E', linewidth=1.5, zorder=4)
            ax.xaxis.set_tick_params(length=0)
            ax.set_xticklabels(names_fx, fontweight='bold', fontsize=8.5, color="#1C1C1E")

            min_v = min(values_fx) if values_fx else 0
            max_v = max(values_fx) if values_fx else 0
            y_range = max_v - min_v if max_v != min_v else 1
            ax.set_ylim(
                (min_v - y_range * 0.15) if min_v < 0 else 0,
                (max_v + y_range * 0.15) if max_v > 0 else 0,
            )
            for bar, v in zip(bars, values_fx):
                offset = y_range * 0.02
                va = 'bottom' if v >= 0 else 'top'
                y_pos = bar.get_height() + offset if v >= 0 else bar.get_height() - offset
                ax.text(bar.get_x() + bar.get_width() / 2, y_pos, f"{v:+.1f}%",
                        ha='center', va=va, fontweight='bold', fontsize=11, color=bar.get_facecolor())

            _t, _s = WEEKLY_TITLES["fx_weekly"][mode]
            EconStyle.set_title(ax, _t, _s.format(date=date_label))
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance")
            EconStyle.save_chart(fig, output_dir / "03_fx_weekly.png")
    except Exception as e:
        print(f"   ⚠ FX weekly bar failed: {e}")

    # NOTE: USD/BRL is an ad-hoc narrative chart. Run: python custom/brazil_fx.py

    # ── 11. CREDIT SPREADS ──
    print("   [11] Credit Markets — IG & HY Spreads (2-Year Trend)")
    try:
        ig_s = fred_fetcher.fetch_series("BAMLC0A0CM", period_years=2)
        hy_s = fred_fetcher.fetch_series("BAMLH0A0HYM2", period_years=2)

        if len(ig_s) > 10 and len(hy_s) > 10:
            # FRED returns OAS in percentage points (e.g. 3.97 = 397 bps).
            # Multiply by 100 so values are in basis points for the axis labels.
            hy_s = hy_s * 100
            ig_s = ig_s * 100

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_hy = "#DC2626"
            color_ig = "#1D4ED8"

            hy_dates = hy_s.index.to_pydatetime()
            ig_dates = ig_s.index.to_pydatetime()

            l1, = ax1.plot(hy_dates, hy_s.values, color=color_hy, linewidth=2.5, label="HY OAS")
            l2, = ax2.plot(ig_dates, ig_s.values, color=color_ig, linewidth=2.5, linestyle="--", label="IG OAS")

            ax1.axhline(400, color=color_hy, linestyle=":", linewidth=1.2, alpha=0.6)
            ax2.axhline(150, color=color_ig, linestyle=":", linewidth=1.2, alpha=0.6)

            ax1.set_ylabel("HY OAS (bps)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color=color_hy)
            ax2.set_ylabel("IG OAS (bps)", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color=color_ig)

            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)

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
    # — whether bonds still hedge equities at all.
    print("   [15] Stock-Bond Correlation (60-Day Rolling)")
    try:
        spy_s = yf_fetcher.get_close_series("SPY", period="3y")
        tlt_s = yf_fetcher.get_close_series("TLT", period="3y")
        both = pd.concat({"spy": spy_s, "tlt": tlt_s}, axis=1).dropna()

        if len(both) > 200:
            returns = both.pct_change().dropna()
            corr_s = returns["spy"].rolling(60).corr(returns["tlt"]).dropna()

            fig, ax = EconStyle.create_figure(size="wide")
            c_dates = corr_s.index.to_pydatetime()
            zeros = [0.0] * len(corr_s)
            ax.fill_between(c_dates, corr_s.values, zeros, where=(corr_s.values > 0),
                            color="#9B1C31", alpha=0.16, interpolate=True)
            ax.fill_between(c_dates, corr_s.values, zeros, where=(corr_s.values <= 0),
                            color="#0B8F82", alpha=0.16, interpolate=True)
            ax.plot(c_dates, corr_s.values, color="#003366", linewidth=2.5, zorder=4)
            ax.axhline(0, color="#1A1A1A", linewidth=1.1, zorder=5)

            latest = float(corr_s.iloc[-1])
            ax.annotate(f"{latest:+.2f}".replace("-", "−"), xy=(c_dates[-1], latest),
                        xytext=(8, 0), textcoords="offset points", va="center", ha="left",
                        fontsize=11, fontweight="bold", color="#003366", annotation_clip=False)
            ax.annotate("Bonds and equities fall together", xy=(0.012, 0.95), xycoords="axes fraction",
                        ha="left", va="top", fontsize=9.5, fontweight="bold", color="#9B1C31")
            ax.annotate("Bonds hedge equities", xy=(0.012, 0.05), xycoords="axes fraction",
                        ha="left", va="bottom", fontsize=9.5, fontweight="bold", color="#0B8F82")

            ax.set_ylabel("Correlation of daily returns", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.set_ylim(-1.0, 1.0)
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
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
    print("   [15b] Defensives vs Cyclicals (2-Year Trend)")
    try:
        DEFENSIVE = {"XLP": "Staples", "XLU": "Utilities", "XLV": "Healthcare"}
        CYCLICAL = {"XLY": "Discretionary", "XLK": "Technology", "XLI": "Industrials"}
        legs = {t: yf_fetcher.get_close_series(t, period="2y") for t in {**DEFENSIVE, **CYCLICAL}}
        missing = [t for t, s in legs.items() if s is None or len(s) < 50]
        if missing:
            raise ValueError(f"no price history for {', '.join(missing)}")

        prices = pd.concat(legs, axis=1).dropna()
        rebased = prices / prices.iloc[0] * 100
        ratio_s = (rebased[list(DEFENSIVE)].mean(axis=1) / rebased[list(CYCLICAL)].mean(axis=1) * 100).dropna()
        mean_26w = ratio_s.rolling(130).mean()

        fig, ax = EconStyle.create_figure(size="wide")
        r_dates = ratio_s.index.to_pydatetime()
        ax.plot(r_dates, ratio_s.values, color="#C8620A", linewidth=2.5, label="Defensives / cyclicals")
        ax.plot(mean_26w.index.to_pydatetime(), mean_26w.values, color="#6B7280",
                linewidth=1.5, linestyle="--", label="26-Week Mean")
        ax.axhline(100, color="#1A1A1A", linewidth=1.1, zorder=5)

        ax.annotate(f"{ratio_s.iloc[-1]:.1f}", xy=(r_dates[-1], float(ratio_s.iloc[-1])),
                    xytext=(8, 0), textcoords="offset points", va="center", ha="left",
                    fontsize=11, fontweight="bold", color="#C8620A", annotation_clip=False)
        ax.set_ylabel("Index (both baskets = 100 two years ago)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
        ax.legend(frameon=False, fontsize=10, loc="upper left")

        _t, _s = WEEKLY_TITLES["defensives_cyclicals"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Yahoo Finance (SPDR sector ETFs: XLP, XLU, XLV vs XLY, XLK, XLI)")
        EconStyle.save_chart(fig, output_dir / "15b_defensives_cyclicals.png")
    except Exception as e:
        print(f"   ⚠ Defensives vs cyclicals failed: {e}")

    # ── 16. SPHB/SPLV RISK APPETITE ──
    print("   [16] SPHB/SPLV — High Beta vs Low Vol (2-Year Trend)")
    try:
        sphb_s = yf_fetcher.get_close_series("SPHB", period="2y")
        splv_s = yf_fetcher.get_close_series("SPLV", period="2y")

        if len(sphb_s) > 50 and len(splv_s) > 50:
            ratio_s  = (sphb_s / splv_s).dropna()
            mean_26w = ratio_s.rolling(130).mean()   # ~26 weeks (130 trading days)

            fig, ax = EconStyle.create_figure(size="wide")
            color_line = "#7C3AED"
            r_dates = ratio_s.index.to_pydatetime()

            ax.plot(r_dates, ratio_s.values, color=color_line, linewidth=2.5, label="SPHB/SPLV Ratio")
            ax.plot(mean_26w.index.to_pydatetime(), mean_26w.values, color="#6B7280",
                    linewidth=1.5, linestyle="--", label="26-Week Mean")

            ax.set_ylabel("SPHB / SPLV Ratio", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["risk_appetite_ratio"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (Invesco ETFs)")
            EconStyle.save_chart(fig, output_dir / "16_risk_appetite_ratio.png")
    except Exception as e:
        print(f"   ⚠ SPHB/SPLV ratio failed: {e}")

    # ── 17. MARKET BREADTH (RSP/SPY) ──
    print("   [17] Market Breadth — RSP/SPY Equal vs Cap-Weight (2-Year Trend)")
    try:
        rsp_s  = yf_fetcher.get_close_series("RSP", period="2y")
        spy2_s = yf_fetcher.get_close_series("SPY", period="2y")

        if len(rsp_s) > 50 and len(spy2_s) > 50:
            ratio_s = (rsp_s / spy2_s).dropna()
            ma20w   = ratio_s.rolling(100).mean()   # ~20 weeks (100 trading days)

            fig, ax = EconStyle.create_figure(size="wide")
            color_line = "#0F766E"
            r_dates = ratio_s.index.to_pydatetime()

            ax.plot(r_dates, ratio_s.values, color=color_line, linewidth=2.5, label="RSP/SPY Ratio")
            ax.plot(ma20w.index.to_pydatetime(), ma20w.values, color="#6B7280",
                    linewidth=1.5, linestyle="--", label="20-Week Moving Average")

            ax.set_ylabel("RSP / SPY Ratio", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["market_breadth"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (Invesco · SPDR ETFs)")
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

        fig, ax = EconStyle.create_figure(size="wide")
        any_plotted = False

        for ticker, (color, label) in BOND_ETFS.items():
            sr = yf_fetcher.get_close_series(ticker, period="1y")
            if len(sr) > 20:
                indexed = (sr / sr.iloc[0]) * 100
                ax.plot(indexed.index.to_pydatetime(), indexed.values,
                        color=color, linewidth=2.5, label=label)
                any_plotted = True

        if any_plotted:
            ax.axhline(100, color="#6B7280", linestyle="--", linewidth=1.2, alpha=0.7)
            ax.set_ylabel("Total Return (Indexed to 100)", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

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

        if em_fx_data:
            em_fx_data.sort(key=lambda x: x[1])
            names_emfx  = [d[0] for d in em_fx_data]
            values_emfx = [d[1] for d in em_fx_data]
            colors_emfx = ["#03AF53" if v >= 0 else "#820E0E" for v in values_emfx]

            fig, ax = EconStyle.create_figure(size=(10, 6))
            bars = ax.barh(names_emfx, values_emfx, color=colors_emfx, height=0.5, zorder=3)

            for bar, v in zip(bars, values_emfx):
                x_pos = v + 0.05 if v >= 0 else v - 0.05
                ha = 'left' if v >= 0 else 'right'
                ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                        f"{v:+.1f}%", va='center', ha=ha,
                        fontsize=11, fontweight='bold', color=bar.get_facecolor())

            ax.axvline(0, color='#1C1C1E', linewidth=1.5, zorder=4)
            ax.xaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.set_xlabel("Weekly Change vs USD (%)  ·  positive = EM currency appreciated",
                          fontsize=EconStyle.FONT_SIZE_AXIS, color=EconStyle.TEXT_SECONDARY)
            for sp in ['top', 'right', 'bottom']: ax.spines[sp].set_visible(False)
            ax.spines['left'].set_color(EconStyle.AXIS_COLOR)

            _t, _s = WEEKLY_TITLES["em_fx_weekly"][mode]
            EconStyle.set_title(ax, _t, _s.format(date=date_label))
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance")
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
            colors_emeq = ["#03AF53" if v >= 0 else "#820E0E" for v in values_emeq]

            fig, ax = EconStyle.create_figure(size=(10, 6))
            bars = ax.barh(names_emeq, values_emeq, color=colors_emeq, height=0.5, zorder=3)

            for bar, v in zip(bars, values_emeq):
                x_pos = v + 0.05 if v >= 0 else v - 0.05
                ha = 'left' if v >= 0 else 'right'
                ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                        f"{v:+.1f}%", va='center', ha=ha,
                        fontsize=11, fontweight='bold', color=bar.get_facecolor())

            ax.axvline(0, color='#1C1C1E', linewidth=1.5, zorder=4)
            ax.xaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.set_xlabel("Weekly Change (%)", fontsize=EconStyle.FONT_SIZE_AXIS, color=EconStyle.TEXT_SECONDARY)
            for sp in ['top', 'right', 'bottom']: ax.spines[sp].set_visible(False)
            ax.spines['left'].set_color(EconStyle.AXIS_COLOR)

            _t, _s = WEEKLY_TITLES["em_equity_weekly"][mode]
            EconStyle.set_title(ax, _t, _s.format(date=date_label))
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (iShares ETFs)")
            EconStyle.save_chart(fig, output_dir / "21_em_equity_weekly.png")
    except Exception as e:
        print(f"   ⚠ EM equity weekly failed: {e}")

    # ── 22. INDIA VS EM PEERS (INDEXED) ──
    print("   [22] India vs EM Peers — Indexed 1-Year Trend")
    try:
        EM_PEERS = {
            "INDA": ("India (INDA)",         "#FF6B00", 3.0),
            "EEM":  ("EM Benchmark (EEM)",   "#6B7280", 2.0),
            "MCHI": ("China (MCHI)",         "#DC2626", 2.0),
            "EWY":  ("South Korea (EWY)",    "#2563EB", 2.0),
        }

        fig, ax = EconStyle.create_figure(size="wide")
        any_plotted = False

        for ticker, (label, color, lw) in EM_PEERS.items():
            sr = yf_fetcher.get_close_series(ticker, period="1y")
            if len(sr) > 20:
                indexed = (sr / sr.iloc[0]) * 100
                ax.plot(indexed.index.to_pydatetime(), indexed.values,
                        color=color, linewidth=lw, label=label)
                any_plotted = True

        if any_plotted:
            ax.axhline(100, color="#6B7280", linestyle="--", linewidth=1.2, alpha=0.7)
            ax.set_ylabel("Total Return (Indexed to 100)", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

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
    # members are in their own uptrend can.
    print("   [23c] Commodity Breadth (share above 200-day average)")
    try:
        BREADTH_BASKET = {
            "BZ=F": "Brent", "CL=F": "WTI", "NG=F": "Natural gas",
            "GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum", "HG=F": "Copper",
            "ZW=F": "Wheat", "ZC=F": "Corn", "ZS=F": "Soybeans",
            "KC=F": "Coffee", "SB=F": "Sugar", "CC=F": "Cocoa",
        }
        # Four years of prices to show three years of breadth: the 200-day
        # average needs a warm-up before the first reading means anything.
        legs_b = {}
        for ticker, name in BREADTH_BASKET.items():
            s = yf_fetcher.get_close_series(ticker, period="4y")
            if s is None or len(s) < 250:
                raise ValueError(f"no usable history for {name} ({ticker})")
            s.index = s.index.tz_localize(None)
            legs_b[name] = s

        px_b = pd.concat(legs_b, axis=1).ffill().dropna()
        ma_b = px_b.rolling(200).mean()
        # Drop the warm-up explicitly. `price > NaN` evaluates to False rather
        # than NaN, so comparing first and dropping after would publish the
        # warm-up as a genuine reading of zero.
        ma_b = ma_b.dropna(how="any")
        above = px_b.loc[ma_b.index] > ma_b
        breadth = (above.mean(axis=1) * 100)

        cutoff = breadth.index[-1] - pd.Timedelta(days=3 * 365)
        breadth = breadth[breadth.index >= cutoff]
        above = above.loc[breadth.index]
        if len(breadth) < 400:
            raise ValueError(f"only {len(breadth)} days of breadth after the 200-day warm-up")
        n_members = above.shape[1]

        fig, ax = EconStyle.create_figure(size="wide")
        b_dates = breadth.index.to_pydatetime()
        fifty = [50.0] * len(breadth)
        ax.fill_between(b_dates, breadth.values, fifty, where=(breadth.values >= 50),
                        color="#0B8F82", alpha=0.16, interpolate=True, zorder=2)
        ax.fill_between(b_dates, breadth.values, fifty, where=(breadth.values < 50),
                        color="#9B1C31", alpha=0.16, interpolate=True, zorder=2)
        ax.plot(b_dates, breadth.values, color="#C8620A", linewidth=2.5, zorder=5)
        ax.axhline(50, color="#1A1A1A", linewidth=1.1, zorder=4)

        latest_b = float(breadth.iloc[-1])
        n_up = int(above.iloc[-1].sum())
        ax.annotate(f"{latest_b:.0f}%", xy=(b_dates[-1], latest_b), xytext=(8, 0),
                    textcoords="offset points", va="center", ha="left",
                    fontsize=11, fontweight="bold", color="#C8620A", annotation_clip=False)

        def _names(items, limit=9):
            """Keep the caption on one line however the basket splits."""
            if len(items) <= limit:
                return ", ".join(items)
            return ", ".join(items[:limit]) + f" and {len(items) - limit} more"

        rising = [n for n in above.columns if above.iloc[-1][n]]
        falling = [n for n in above.columns if not above.iloc[-1][n]]
        ax.annotate(f"Now {n_up} of {n_members} above: " + _names(rising),
                    xy=(0.012, 0.95), xycoords="axes fraction", ha="left", va="top",
                    fontsize=9, fontweight="bold", color="#0B8F82")
        ax.annotate(f"Below: " + _names(falling),
                    xy=(0.012, 0.055), xycoords="axes fraction", ha="left", va="bottom",
                    fontsize=9, fontweight="bold", color="#9B1C31")

        ax.set_ylabel("Share above 200-day average (%)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      fontweight="bold", color="#1C1C1E")
        ax.set_ylim(-2, 108)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)

        _t, _s = WEEKLY_TITLES["commodities_breadth"][mode]
        EconStyle.set_title(ax, _t, _s)
        EconStyle.add_top_rule(ax)
        fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
        EconStyle.add_source(fig, "Yahoo Finance (13 energy, metal and agricultural futures)")
        EconStyle.save_chart(fig, output_dir / "23c_commodities_breadth.png")
    except Exception as e:
        print(f"   ⚠ Commodity breadth failed: {e}")

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
            colors_ag = ["#03AF53" if v >= 0 else "#820E0E" for v in values_ag]

            fig, ax = EconStyle.create_figure(size=(10, 6))
            bars = ax.barh(names_ag, values_ag, color=colors_ag, height=0.5, zorder=3)

            for bar, v in zip(bars, values_ag):
                x_pos = v + 0.05 if v >= 0 else v - 0.05
                ha = 'left' if v >= 0 else 'right'
                ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                        f"{v:+.1f}%", va='center', ha=ha,
                        fontsize=11, fontweight='bold', color=bar.get_facecolor())

            ax.axvline(0, color='#1C1C1E', linewidth=1.5, zorder=4)
            ax.xaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.set_xlabel("Weekly Change (%)", fontsize=EconStyle.FONT_SIZE_AXIS, color=EconStyle.TEXT_SECONDARY)
            for sp in ['top', 'right', 'bottom']: ax.spines[sp].set_visible(False)
            ax.spines['left'].set_color(EconStyle.AXIS_COLOR)

            _t, _s = WEEKLY_TITLES["agri_weekly"][mode]
            EconStyle.set_title(ax, _t, _s.format(date=date_label))
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (CBOT · ICE Futures)")
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

    # ── 27. BTC VS GOLD RATIO ──
    print("   [27] Bitcoin vs. Gold Ratio (2-Year Trend)")
    try:
        btc_s  = yf_fetcher.get_close_series("BTC-USD", period="2y")
        gold_s = yf_fetcher.get_close_series("GC=F",    period="2y")

        # ── THE FIX: Strip timezones (BTC is UTC, Gold is NY) ──
        btc_s.index = btc_s.index.tz_localize(None)
        gold_s.index = gold_s.index.tz_localize(None)

        if len(btc_s) > 50 and len(gold_s) > 50:
            import pandas as pd
            # Force numeric to prevent the 'isfinite' error
            btc_s = pd.to_numeric(btc_s, errors='coerce')
            gold_s = pd.to_numeric(gold_s, errors='coerce')
            
            combined = pd.DataFrame({"btc": btc_s, "gold": gold_s}).dropna()
            ratio_s  = combined["btc"] / combined["gold"]
            mean_52w = ratio_s.rolling(252).mean()

            fig, ax = EconStyle.create_figure(size="wide")
            color_line = "#F59E0B"

            r_dates = ratio_s.index.to_pydatetime()
            ax.plot(r_dates, ratio_s.values, color=color_line, linewidth=2.5, label="BTC/Gold Ratio")
            ax.plot(mean_52w.index.to_pydatetime(), mean_52w.values,
                    color="#6B7280", linewidth=1.5, linestyle="--", label="52-Week Mean")
            ax.fill_between(r_dates, ratio_s.values, mean_52w.reindex(ratio_s.index).values,
                            where=ratio_s.values >= mean_52w.reindex(ratio_s.index).values,
                            alpha=0.07, color=color_line, interpolate=True)

            ax.set_ylabel("BTC / Gold Ratio", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color=color_line)
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["btc_gold_ratio"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance")
            EconStyle.save_chart(fig, output_dir / "27_btc_gold_ratio.png")
    except Exception as e:
        print(f"   ⚠ BTC/Gold ratio failed: {e}")

    # ── 28. BTC VS US LIQUIDITY (M2 MONEY SUPPLY - SINCE 2013) ──
    print("   [28] Bitcoin vs. US Liquidity (M2 Money Supply - Since 2013)")
    try:
        import pandas as pd
        import matplotlib.ticker as ticker
        
        # Fetch max history to go back to 2013
        btc_s  = yf_fetcher.get_close_series("BTC-USD", period="max")
        m2_s = fred_fetcher.fetch_series("M2SL", period_years=15)

        if len(btc_s) > 50 and len(m2_s) > 5:
            # ── Safe Timezone Stripping ──
            btc_s.index = pd.to_datetime(btc_s.index)
            if btc_s.index.tz is not None:
                btc_s.index = btc_s.index.tz_localize(None)
                
            m2_s.index = pd.to_datetime(m2_s.index)
            if m2_s.index.tz is not None:
                m2_s.index = m2_s.index.tz_localize(None)

            # Filter both to start from Jan 1, 2013
            btc_s = btc_s[btc_s.index >= "2013-01-01"]
            m2_s = m2_s[m2_s.index >= "2013-01-01"]

            m2_usd_t = (m2_s / 1e3).dropna()

            # ── THE FIX: Time-based Interpolation for Smoothing ──
            # Combine indexes so we don't lose the exact monthly M2 dates
            combined_idx = btc_s.index.union(m2_usd_t.index).sort_values()

            # Reindex M2 to the combined timeline and interpolate the gaps mathematically
            m2_smooth = m2_usd_t.reindex(combined_idx).interpolate(method="time")

            # Now filter back down to only the days Bitcoin actually traded
            m2_aligned = m2_smooth.reindex(btc_s.index).dropna()
            btc_aligned = btc_s.reindex(m2_aligned.index).dropna()

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_btc = "#F59E0B"
            color_m2  = "#1D4ED8"

            l1, = ax1.plot(btc_aligned.index.to_pydatetime(), btc_aligned.values,
                           color=color_btc, linewidth=2.0, label="Bitcoin (USD)")
            l2, = ax2.plot(m2_aligned.index.to_pydatetime(), m2_aligned.values,
                           color=color_m2, linewidth=2.5, linestyle="--", alpha=0.8,
                           label="US M2 Supply (Trillions)")

            # ── Mandatory Log Scale for 10+ Year Bitcoin Data ──
            ax1.set_yscale("log")
            # Format the log axis to show standard numbers (e.g., 10,000) instead of scientific notation (10^4)
            ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:,.0f}"))

            ax1.set_ylabel("Bitcoin Price (USD, Log Scale)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color=color_btc)
            ax2.set_ylabel("US M2 Supply ($ Trillions)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color=color_m2)

            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            
            # Format X-Axis for a decade-long view
            ax1.xaxis.set_major_locator(mdates.YearLocator())
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)
            
            ax1.legend(handles=[l1, l2], loc="upper left", frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["btc_global_m2"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance · FRED (M2SL)")
            EconStyle.save_chart(fig, output_dir / "28_btc_global_m2.png")
    except Exception as e:
        print(f"   ⚠ BTC vs US M2 Liquidity failed: {e}")

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

