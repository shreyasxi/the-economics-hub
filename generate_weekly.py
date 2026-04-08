#!/usr/bin/env python3
"""
Economics Hub — Weekly Dashboard Generator
============================================
Run this script every Friday/Saturday to generate the full
weekly dashboard. Produces all charts.

Usage:
    python generate_weekly.py              # Live data (requires API keys)
    python generate_weekly.py --mock       # Mock data (for testing)
    python generate_weekly.py --preview    # Lower DPI for quick preview

The script:
1. Fetches data (live or mock)
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

from style.economics_hub_style import EconStyle
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
    "nifty_it_trend": {
        "dashboard": (
            "NIFTY IT Index — Trailing 12 Months",
            "NSE IT sector benchmark index level",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "India's IT Sector Feels the AI Threat",
            "Sector benchmark continues to hit 12-month lows as investors confront AI's threat to India's IT export model",
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
            "IG & HY Credit Spreads — 2-Year Trend",
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
            "Breakeven Inflation — 5Y & 10Y (2-Year Trend)",
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
            "Real Yields — 5Y & 10Y TIPS (2-Year Trend)",
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
    "spy_tlt_ratio": {
        "dashboard": (
            "SPY/TLT Risk Appetite Ratio — 2-Year Trend",
            "Equities vs. long-duration Treasuries  ·  rising = risk-on, falling = flight to safety",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Risk-On / Risk-Off Switch Just Flipped",
            "SPY/TLT ratio breaking below its 52-week range signals institutional rotation to safety",
        ),
    },
    "risk_appetite_ratio": {
        "dashboard": (
            "SPHB/SPLV — High Beta vs. Low Volatility (2-Year Trend)",
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
            "Market Breadth — RSP/SPY Equal vs. Cap-Weight (2-Year Trend)",
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
            "Bond ETF Total Returns — TLT, LQD, HYG (Trailing 12 Months)",
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
            "Gold/SPX Safe Haven Ratio — 2-Year Trend",
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
    "brent_wti_spread": {
        "dashboard": (
            "Brent–WTI Crude Spread — 2-Year Trend",
            "International vs. US crude oil price differential  ·  $/barrel  ·  5-day smooth",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "The Geopolitical Risk Premium in Oil Is Back",
            "Brent-WTI spread widening signals Middle East supply disruption fears re-entering the market",
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
            "ETH/BTC Ratio — Altcoin Appetite Signal (2-Year Trend)",
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
            "Bitcoin vs. Global Central Bank Liquidity",
            "BTC price (left) vs. Fed + ECB blended balance sheet in USD (right)  ·  2-year trend",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Bitcoin Tracks Global Liquidity — And Liquidity Is Tightening",
            "The Fed + ECB balance sheet contraction is the single biggest macro headwind for crypto",
        ),
    },
    "stablecoin_mcap": {
        "dashboard": (
            "Stablecoin Market Cap — Crypto Liquidity Proxy",
            "USDT + USDC combined market cap  ·  USD billions  ·  2-year trend",
        ),
        "newsletter": (
            # ── EDIT for each Substack issue ──────────────────────────────
            "Stablecoin Supply Is Contracting — A Crypto Liquidity Warning",
            "Declining USDT + USDC combined supply signals capital is leaving crypto ecosystems",
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

# NOTE: USD/BRL and Hormuz exposure are ad-hoc narrative charts.
# Run them independently: python custom/brazil_fx.py
#                         python custom/hormuz_exposure.py


def get_output_dir():
    """Create and return the output directory for this week."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_dir = PROJECT_ROOT / "output" / "weekly" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def generate_with_mock_data(output_dir, mode="dashboard"):
    """Generate full dashboard using mock data."""
    from data.mock_data import (
        get_mock_weekly_changes,
        get_mock_equity_data,
        get_mock_fx_data,
        get_mock_yield_data,
        get_mock_yield_trend,
        get_mock_commodity_data,
    )
    
    print("📊 Generating Economics Hub Weekly Dashboard (Mock Data)")
    print(f"   Output: {output_dir}\n")
    
    weekly = get_mock_weekly_changes()
    
    # ─────────────────────────────────────────
    # 1. EQUITIES
    # ─────────────────────────────────────────
    print("   [1/8] Equities — Weekly Bar Chart")
    eq = weekly["equities"]
    chart = WeeklyBarChart(
        names=eq["names"],
        values=eq["values"],
        color_keys=eq["color_keys"],
    )
    chart.render(
        title="Global Equities",
        subtitle="Weekly percentage change  ·  " + datetime.now().strftime("%d %b %Y"),
        source="Yahoo Finance",
    )
    chart.save(output_dir / "01_equities_weekly.png")
    
    print("   [2/8] Equities — 12-Month Trends")
    equity_data = get_mock_equity_data()
    trend = TrendLineChart()
    for key in ["sp500", "nifty50", "ftse100"]:
        d = equity_data[key]
        trend.add_series(d["name"], d["dates"], d["values"], color_key=d["color_key"])
    trend.render(
        title="Major Indices — Trailing 12 Months",
        subtitle="Indexed to 100 at start  ·  S&P 500, Nifty 50, FTSE 100",
        source="Yahoo Finance",
        normalize=True,
        ylabel="Indexed (start = 100)",
    )
    trend.save(output_dir / "02_equities_trend.png")
    
    # ─────────────────────────────────────────
    # 2. FOREIGN EXCHANGE
    # ─────────────────────────────────────────
    
    print("   [4/8] FX — 12-Month Trends")
    fx_data = get_mock_fx_data()
    trend = TrendLineChart()
    for key in ["dxy", "eurusd", "gbpusd", "usdinr"]:
        d = fx_data[key]
        trend.add_series(d["name"], d["dates"], d["values"], color_key=d["color_key"])
    trend.render(
        title="Key FX Rates — Trailing 12 Months",
        subtitle="Indexed to 100 at start  ·  DXY, EUR/USD, GBP/USD, USD/INR",
        source="Yahoo Finance",
        normalize=True,
        ylabel="Indexed (start = 100)",
    )
    trend.save(output_dir / "04_fx_trend.png")
    
    # ─────────────────────────────────────────
    # 3. GOVERNMENT BOND YIELDS
    # ─────────────────────────────────────────
    
    print("   [6/8] Yields — US Treasury Yield Curve")
    yc_data = get_mock_yield_data()
    yc = YieldCurveChart()
    yc.add_curve("7 Feb 2026", yc_data["tenors"], yc_data["current"], style="current")
    yc.add_curve("10 Jan 2026", yc_data["tenors"], yc_data["4w_ago"], style="4w_ago")
    yc.add_curve("7 Feb 2025", yc_data["tenors"], yc_data["52w_ago"], style="52w_ago")
    _t, _s = WEEKLY_TITLES["yield_curve"][mode]
    yc.render(title=_t, subtitle=_s, source="FRED")
    yc.save(output_dir / "06_yield_curve.png")

    # ─────────────────────────────────────────
    # 4. COMMODITIES
    # ─────────────────────────────────────────
    print("   [7/8] Commodities — Weekly Bar Chart")
    cm = weekly["commodities"]
    chart = WeeklyBarChart(
        names=cm["names"],
        values=cm["values"],
        color_keys=cm["color_keys"],
    )
    chart.render(
        title="Commodities",
        subtitle="Weekly percentage change  ·  " + datetime.now().strftime("%d %b %Y"),
        source="Yahoo Finance",
    )
    chart.save(output_dir / "07_commodities_weekly.png")
    
    print("   [8/8] Commodities — 12-Month Trends")
    commodity_data = get_mock_commodity_data()
    trend = TrendLineChart()
    for key in ["brent", "gold", "copper"]:
        d = commodity_data[key]
        trend.add_series(d["name"], d["dates"], d["values"], color_key=d["color_key"])
    trend.render(
        title="Key Commodities — Trailing 12 Months",
        subtitle="Indexed to 100 at start  ·  Brent Crude, Gold, Copper",
        source="Yahoo Finance",
        normalize=True,
        ylabel="Indexed (start = 100)",
    )
    trend.save(output_dir / "08_commodities_trend.png")
    
    # ─────────────────────────────────────────
    # SUMMARY TABLE
    # ─────────────────────────────────────────
    print("   [+] Summary Table")
    table = SummaryTable()
    
    # Equities
    eq_levels = [6142, 7632, 4587, 23412, 38920, 3095]
    eq_ytds =   ["+4.8%", "+2.1%", "+5.2%", "-1.3%", "+6.4%", "-2.8%"]
    for name, val, level, ytd, ck in zip(eq["names"], eq["values"], eq_levels, eq_ytds, eq["color_keys"]):
        table.add_row(name, level, EconStyle.format_change_label(val, "pct"), ytd, "equities")
    
    # FX
    fx_levels = [104.2, 1.082, 1.268, 84.12, 147.3, 0.875]
    fx_ytds =   ["+1.2%", "-0.8%", "+0.3%", "+1.8%", "-2.1%", "-0.5%"]
    for name, val, level, ytd, ck in zip(fx["names"], fx["values"], fx_levels, fx_ytds, fx["color_keys"]):
        table.add_row(name, level, EconStyle.format_change_label(val, "pct"), ytd, "fx")
    
    # Yields
    yd_levels = [4.35, 4.38, 4.55, 2.55, 4.45, 7.05]
    yd_ytds =   ["+15bps", "+25bps", "+18bps", "+12bps", "+22bps", "-10bps"]
    for name, val, level, ytd, ck in zip(yd["names"], yd["values"], yd_levels, yd_ytds, yd["color_keys"]):
        table.add_row(name, f"{level:.2f}%", EconStyle.format_change_label(val, "abs"), ytd, "yields")
    
    # Commodities
    cm_levels = [78.40, 74.20, 2890, 31.50, 4.18, 2.65]
    cm_ytds =   ["-5.2%", "-5.8%", "+8.1%", "+12.3%", "+7.5%", "-15.2%"]
    for name, val, level, ytd, ck in zip(cm["names"], cm["values"], cm_levels, cm_ytds, cm["color_keys"]):
        table.add_row(name, level, EconStyle.format_change_label(val, "pct"), ytd, "commodities")
    
    table.render(
        title="Market Snapshot",
        subtitle=f"Week ending {datetime.now().strftime('%d %B %Y')}",
        source="Yahoo Finance, FRED",
    )
    table.save(output_dir / "00_summary_table.png")
        

def generate_with_live_data(output_dir, mode="dashboard"):
    """Generate dashboard with live API data from yfinance + FRED."""
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    from data.fetchers.fred_fetcher import FredFetcher
    from config.settings import INDICATORS, FRED_API_KEY

    if FRED_API_KEY == "YOUR_FRED_API_KEY":
        print("⚠  FRED API key not set!")
        print("   Open config/settings.py and replace YOUR_FRED_API_KEY")
        print("   Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        print("   Falling back to mock data...\n")
        generate_with_mock_data(output_dir)
        return

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
    for ind_id in ["dxy", "eurusd", "gbpusd", "usdinr", "usdjpy"]:
        dates, vals = get_trend(ind_id)
        if dates:
            ind = INDICATORS[ind_id]
            trend.add_series(ind["name"], dates, vals, color_key=ind["color_key"])
    trend.render(title="Key FX Rates — Trailing 12 Months",
                 subtitle="Indexed to 100 at start  ·  DXY, EUR/USD, GBP/USD, USD/INR, USD/JPY",
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
            trend.render(title=_t, subtitle=_s, source="Yahoo Finance (CBOE)", ylabel="VIX Level")
            trend.save(output_dir / "09_vix_trend.png")
    except Exception as e:
        print(f"   ⚠ VIX chart failed: {e}")

    # ── MOVE INDEX ──
    print("   [09b] ICE BofA MOVE Index — Bond Volatility")
    try:
        move_s = fred_fetcher.fetch_series("BAMLMOVE", period_years=1)

        if len(move_s) > 20:
            # FRED BAMLMOVE is already in basis points — no scaling needed
            fig, ax = EconStyle.create_figure(size="wide")

            color_move = "#7C3AED"  # Purple — distinct from VIX orange

            move_dates = move_s.index.to_pydatetime()
            move_vals  = move_s.values

            ax.plot(move_dates, move_vals, color=color_move, linewidth=2.5, label="MOVE Index")
            ax.fill_between(move_dates, move_vals, move_vals.min(),
                            alpha=0.06, color=color_move)

            # Alert threshold at 100 (elevated bond vol regime)
            ax.axhline(100, color="#6B7280", linestyle="--", linewidth=1.2, alpha=0.7,
                       label="100 — Elevated vol threshold")

            # Annotate the latest value
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
            EconStyle.add_source(fig, "FRED (ICE BofA)")
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
        NIFTY_SECTORS = {
            "^NSEBANK": "Bank Nifty",
            "^CNXIT": "IT",
            "^CNXAUTO": "Auto",
            "^CNXFMCG": "FMCG",
            "^CNXPHARMA": "Pharma",
            "^CNXMETAL": "Metal",
            "^CNXREALTY": "Realty",
            "^CNXENERGY": "Energy",
            "^CNXPSUBANK": "PSU Bank",
            "^CNXINFRA": "Infra"
        }
        sector_data = []
        for ticker, name in NIFTY_SECTORS.items():
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
            chart.render(title="NIFTY Sector Rotation",
                         subtitle=f"Weekly performance by sector  ·  {date_label}",
                         source="Yahoo Finance (NSE)")
            chart.save(output_dir / "10b_india_sector_rotation.png")
    except Exception as e:
        print(f"   ⚠ Sector rotation failed: {e}")
        
    # ── CUSTOM NARRATIVE CHART: NIFTY IT INDEX 1-YEAR TREND (ECONSTYLE BRANDED) ──
    print("   [Custom] Generating NIFTY IT 1-Year Trend...")
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        
        custom_series = yf_fetcher.get_close_series("^CNXIT", period="1y")
        
        if not custom_series.empty:
            dates = custom_series.index.to_pydatetime()
            vals = custom_series.values
            
            # Use YOUR custom styling framework for the figure
            fig, ax = EconStyle.create_figure(size="wide")
            
            # Plot the line (using your official India color if defined, otherwise a deep red)
            ax.plot(dates, vals, color="#B91C1C", linewidth=2.5, solid_capstyle="round")
            # Add a subtle shadow for depth (standard in your other charts)
            ax.plot(dates, vals, color="#B91C1C", linewidth=3.7, alpha=0.07, solid_capstyle="round")
            
            # THE Y-AXIS FIX: Force it to crop tightly around the data
            min_val = min(vals)
            max_val = max(vals)
            padding = (max_val - min_val) * 0.1
            ax.set_ylim(min_val - padding, max_val + padding)
            
            # Date formatting
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.set_ylabel("Index Level", fontsize=EconStyle.FONT_SIZE_AXIS)
            
            # Highlight the selloff at the very end
            if len(dates) > 5:
                ax.axvspan(dates[-6], dates[-1], color='#DC2626', alpha=0.1)
                # Add an end label for maximum impact
                ax.annotate(
                    f"{vals[-1]:,.0f}",
                    xy=(dates[-1], vals[-1]),
                    xytext=(8, 0), textcoords="offset points",
                    fontsize=9, fontweight="bold", color="#B91C1C",
                    fontfamily=EconStyle.FONT_FAMILY,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85),
                    zorder=10
                )

            # Apply YOUR custom titles, rules, and sources
            _t, _s = WEEKLY_TITLES["nifty_it_trend"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (NSE)")
            
            # Save using your custom saver
            chart_path = output_dir / "10c_nifty_it_trend_custom.png"
            EconStyle.save_chart(fig, chart_path)
            
            print(f"      ✓ Saved Custom NIFTY IT chart (Perfectly branded)")
        else:
            print("   ⚠ Custom chart data returned empty.")
            
    except Exception as e:
        print(f"   ⚠ Custom chart generation failed: {e}")

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

        if len(cu_s) > 50 and len(au_s) > 50:
            ratio_s = (cu_s / au_s).dropna().rolling(5).mean().dropna()

            # Align FRED 10Y to ratio's trading-day index
            dgs10_aligned = dgs10_s.reindex(ratio_s.index, method="ffill").dropna()

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_ratio = "#B45309"
            color_10y   = "#1D4ED8"

            l1, = ax1.plot(ratio_s.index.to_pydatetime(), ratio_s.values,
                           color=color_ratio, linewidth=2.5, label="Copper/Gold Ratio")
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

            ax1.legend(handles=[l1, l2], loc="upper left", frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["copper_gold_ratio"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance · FRED")
            EconStyle.save_chart(fig, output_dir / "14_copper_gold_ratio.png")
    except Exception as e:
        print(f"   ⚠ Copper/Gold ratio failed: {e}")

    # ── 15. SPY/TLT RATIO ──
    print("   [15] SPY/TLT Risk Appetite Ratio (2-Year Trend)")
    try:
        spy_s = yf_fetcher.get_close_series("SPY", period="2y")
        tlt_s = yf_fetcher.get_close_series("TLT", period="2y")

        if len(spy_s) > 50 and len(tlt_s) > 50:
            ratio_s = (spy_s / tlt_s).dropna()
            r52_high = ratio_s.rolling(252).max()
            r52_low  = ratio_s.rolling(252).min()

            fig, ax = EconStyle.create_figure(size="wide")
            color_line = "#003366"
            r_dates = ratio_s.index.to_pydatetime()

            ax.fill_between(r_dates, r52_high.values, r52_low.values,
                            color="#003366", alpha=0.08, label="52-Week Range")
            ax.plot(r_dates, ratio_s.values, color=color_line, linewidth=2.5, label="SPY/TLT Ratio")

            ax.set_ylabel("SPY / TLT Ratio", fontsize=EconStyle.FONT_SIZE_AXIS, fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["spy_tlt_ratio"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (SPDR ETFs)")
            EconStyle.save_chart(fig, output_dir / "15_spy_tlt_ratio.png")
    except Exception as e:
        print(f"   ⚠ SPY/TLT ratio failed: {e}")

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

    # ── 23. BRENT–WTI SPREAD ──
    print("   [23] Brent–WTI Spread (2-Year Trend)")
    try:
        brent_s = yf_fetcher.get_close_series("BZ=F", period="2y")
        wti2_s  = yf_fetcher.get_close_series("CL=F", period="2y")

        if len(brent_s) > 50 and len(wti2_s) > 50:
            spread_s = (brent_s - wti2_s).dropna().rolling(5).mean().dropna()

            fig, ax = EconStyle.create_figure(size="wide")
            color_pos = "#D97706"
            color_neg = "#1D4ED8"
            sp_dates = spread_s.index.to_pydatetime()
            sp_vals  = spread_s.values

            ax.fill_between(sp_dates, sp_vals, 0,
                            where=[v >= 0 for v in sp_vals], color=color_pos, alpha=0.3, label="Brent Premium")
            ax.fill_between(sp_dates, sp_vals, 0,
                            where=[v < 0  for v in sp_vals], color=color_neg, alpha=0.3, label="WTI Premium")
            ax.plot(sp_dates, sp_vals, color="#1C1C1E", linewidth=1.8)
            ax.axhline(0, color="#1C1C1E", linewidth=1.5)

            ax.set_ylabel("Brent minus WTI ($/bbl)", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["brent_wti_spread"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance (NYMEX · ICE)")
            EconStyle.save_chart(fig, output_dir / "23_brent_wti_spread.png")
    except Exception as e:
        print(f"   ⚠ Brent-WTI spread failed: {e}")

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

            handles = [l1] + ax1.lines[1:2] + [l2, l3]
            ax1.legend(handles=handles, loc="upper left", frameon=False, fontsize=9)

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

        if len(btc_s) > 50 and len(gold_s) > 50:
            import pandas as pd
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

    # ── 28. BTC VS GLOBAL CENTRAL BANK BALANCE SHEETS (FED + ECB) ──
    print("   [28] Bitcoin vs. Global Liquidity (Fed + ECB Balance Sheets)")
    try:
        import pandas as pd
        btc_s  = yf_fetcher.get_close_series("BTC-USD", period="2y")
        # Fed total assets: USD millions (WALCL)
        walcl_s = fred_fetcher.fetch_series("WALCL", period_years=2)
        # ECB total assets: EUR millions (ECBASSETS) → convert to USD
        ecb_s   = fred_fetcher.fetch_series("ECBASSETS", period_years=2)
        eurusd_s = yf_fetcher.get_close_series("EURUSD=X", period="2y")

        if len(btc_s) > 50 and len(walcl_s) > 10 and len(ecb_s) > 10:
            # ECB EUR millions → USD millions using EURUSD
            ecb_usd = ecb_s * eurusd_s.reindex(ecb_s.index, method="ffill")
            # Combined Fed + ECB in USD billions
            fed_usd_b = walcl_s / 1e3
            ecb_usd_b = ecb_usd / 1e3
            combined_bs = (fed_usd_b + ecb_usd_b.reindex(fed_usd_b.index, method="ffill")).dropna()
            # Align BTC to balance sheet dates
            btc_aligned = btc_s.reindex(combined_bs.index, method="ffill").dropna()
            combined_bs = combined_bs.reindex(btc_aligned.index).dropna()

            fig, ax1 = EconStyle.create_figure(size="wide")
            ax2 = ax1.twinx()

            color_btc = "#F59E0B"
            color_bs  = "#1D4ED8"

            l1, = ax1.plot(btc_aligned.index.to_pydatetime(), btc_aligned.values,
                           color=color_btc, linewidth=2.5, label="Bitcoin (USD)")
            l2, = ax2.plot(combined_bs.index.to_pydatetime(), combined_bs.values,
                           color=color_bs, linewidth=2.0, linestyle="--", alpha=0.8,
                           label="Fed + ECB Assets (USD B)")

            ax1.set_ylabel("Bitcoin Price (USD)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color=color_btc)
            ax2.set_ylabel("Fed + ECB Balance Sheet (USD Billions)", fontsize=EconStyle.FONT_SIZE_AXIS,
                           fontweight="bold", color=color_bs)

            ax1.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)
            ax1.legend(handles=[l1, l2], loc="upper left", frameon=False, fontsize=10)

            _t, _s = WEEKLY_TITLES["btc_global_m2"][mode]
            EconStyle.set_title(ax1, _t, _s)
            EconStyle.add_top_rule(ax1)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "Yahoo Finance · FRED (Fed WALCL + ECB ECBASSETS)")
            EconStyle.save_chart(fig, output_dir / "28_btc_global_m2.png")
    except Exception as e:
        print(f"   ⚠ BTC vs Global M2 failed: {e}")

    # ── 29. STABLECOIN MARKET CAP (USDT + USDC) ──
    print("   [29] Stablecoin Market Cap — USDT + USDC (2-Year Trend)")
    try:
        import json
        import urllib.request

        def _fetch_cg_mcap(coin_id, days=730):
            url = (
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
                f"?vs_currency=usd&days={days}&interval=daily"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "EconHub/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            raw = data["market_caps"]  # [[epoch_ms, value], ...]
            import pandas as pd
            s = pd.Series(
                {pd.Timestamp(ts_ms, unit="ms"): val for ts_ms, val in raw}
            )
            return s / 1e9  # → USD billions

        usdt_s = _fetch_cg_mcap("tether",   days=730)
        usdc_s = _fetch_cg_mcap("usd-coin", days=730)

        if len(usdt_s) > 30 and len(usdc_s) > 30:
            import pandas as pd
            combined_sc = (usdt_s + usdc_s.reindex(usdt_s.index, method="ffill")).dropna()

            fig, ax = EconStyle.create_figure(size="wide")
            color_usdt  = "#26A17B"  # Tether green
            color_usdc  = "#2775CA"  # Circle blue
            color_total = "#1C1C1E"

            sc_dates = combined_sc.index.to_pydatetime()
            ax.plot(sc_dates, combined_sc.values, color=color_total, linewidth=2.5,
                    label="USDT + USDC (Combined)")
            ax.fill_between(sc_dates, combined_sc.values, combined_sc.min(),
                            alpha=0.07, color=color_total)

            # Show individual components as faint fills
            usdt_al = usdt_s.reindex(combined_sc.index, method="ffill")
            usdc_al = usdc_s.reindex(combined_sc.index, method="ffill")
            ax.fill_between(sc_dates, usdt_al.values, combined_sc.min(),
                            alpha=0.12, color=color_usdt, label="USDT")
            ax.fill_between(sc_dates, combined_sc.values, usdt_al.values,
                            alpha=0.12, color=color_usdc, label="USDC (incremental)")

            ax.set_ylabel("Market Cap (USD Billions)", fontsize=EconStyle.FONT_SIZE_AXIS,
                          fontweight="bold", color="#1C1C1E")
            ax.yaxis.grid(True, linestyle='-', alpha=0.15, color='#9CA3AF', zorder=0)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            for sp in ['top', 'right', 'left']: ax.spines[sp].set_visible(False)
            ax.legend(frameon=False, fontsize=9)

            _t, _s = WEEKLY_TITLES["stablecoin_mcap"][mode]
            EconStyle.set_title(ax, _t, _s)
            EconStyle.add_top_rule(ax)
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
            EconStyle.add_source(fig, "CoinGecko (USDT · USDC)")
            EconStyle.save_chart(fig, output_dir / "29_stablecoin_mcap.png")
    except Exception as e:
        print(f"   ⚠ Stablecoin market cap failed: {e}")

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
    parser.add_argument("--mock", action="store_true", help="Use mock data for testing")
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

    if args.mock:
        generate_with_mock_data(output_dir, mode=args.mode)
    else:
        try:
            generate_with_live_data(output_dir, mode=args.mode)
        except ImportError as e:
            print(f"⚠ {e}")
            print("   Falling back to mock data. Install dependencies:")
            print("   pip install yfinance fredapi")
            generate_with_mock_data(output_dir, mode=args.mode)


if __name__ == "__main__":
    main()

