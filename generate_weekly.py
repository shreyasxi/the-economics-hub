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


def get_output_dir():
    """Create and return the output directory for this week."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_dir = PROJECT_ROOT / "output" / "weekly" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def generate_with_mock_data(output_dir):
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
    print("   [3/8] FX — Weekly Bar Chart")
    fx = weekly["fx"]
    chart = WeeklyBarChart(
        names=fx["names"],
        values=fx["values"],
        color_keys=fx["color_keys"],
    )
    chart.render(
        title="Foreign Exchange",
        subtitle="Weekly percentage change  ·  " + datetime.now().strftime("%d %b %Y"),
        source="Yahoo Finance",
    )
    chart.save(output_dir / "03_fx_weekly.png")
    
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
    print("   [5/8] Yields — Weekly Bar Chart")
    yd = weekly["yields"]
    chart = WeeklyBarChart(
        names=yd["names"],
        values=yd["values"],
        change_type=yd.get("change_type", "abs"),
        color_keys=yd["color_keys"],
    )
    chart.render(
        title="Government Bond Yields",
        subtitle="Weekly change (percentage points)  ·  " + datetime.now().strftime("%d %b %Y"),
        source="FRED, Yahoo Finance",
    )
    chart.save(output_dir / "05_yields_weekly.png")
    
    print("   [6/8] Yields — US Treasury Yield Curve")
    yc_data = get_mock_yield_data()
    yc = YieldCurveChart()
    yc.add_curve("7 Feb 2026", yc_data["tenors"], yc_data["current"], style="current")
    yc.add_curve("10 Jan 2026", yc_data["tenors"], yc_data["4w_ago"], style="4w_ago")
    yc.add_curve("7 Feb 2025", yc_data["tenors"], yc_data["52w_ago"], style="52w_ago")
    yc.render(
        title="US Treasury Yield Curve",
        subtitle="Current vs. 4 weeks ago vs. 52 weeks ago",
        source="FRED",
    )
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
        

def generate_with_live_data(output_dir):
    """Generate dashboard with live API data from yfinance + FRED."""
    import pandas as pd
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
    print("\n   [1/8] Equities — Weekly Bar Chart")
    eq_ids = ["sp500", "ftse100", "eurostoxx50", "nifty50", "nikkei225"]
    names, values, cks = build_bar_data(eq_ids)
    chart = WeeklyBarChart(names=names, values=values, color_keys=cks)
    chart.render(title="Global Equities",
                 subtitle=f"Weekly percentage change  ·  {date_label}",
                 source="Yahoo Finance")
    chart.save(output_dir / "01_equities_weekly.png")

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
    print("   [3/8] FX — Weekly Bar Chart")
    # FIX: removed usdchf (not in INDICATORS)
    fx_ids = ["dxy", "eurusd", "gbpusd", "usdinr", "usdjpy"]
    names, values, cks = build_bar_data(fx_ids)
    chart = WeeklyBarChart(names=names, values=values, color_keys=cks)
    chart.render(title="Foreign Exchange",
                 subtitle=f"Weekly percentage change  ·  {date_label}",
                 source="Yahoo Finance")
    chart.save(output_dir / "03_fx_weekly.png")

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
    print("   [5/8] Yields — Weekly Bar Chart")
    # FIX: Only US daily yields for weekly bar (Bund/Gilt are monthly, will be auto-skipped)
    yd_ids = ["us_2y", "us_10y", "us_30y"]
    names, values, cks = build_bar_data(yd_ids, change_type="abs")
    chart = WeeklyBarChart(names=names, values=values, change_type="abs", color_keys=cks)
    chart.render(title="Government Bond Yields",
                 subtitle=f"Weekly change (basis points)  ·  {date_label}",
                 source="FRED")
    chart.save(output_dir / "05_yields_weekly.png")

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
        
        yc.render(title="US Treasury Yield Curve",
                  subtitle="Current vs. 4 weeks ago vs. 52 weeks ago", source="FRED")
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
    color_pos = "#2A4DBE" # Deep, authoritative Slate Blue
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
    EconStyle.set_title(ax, "Commodities: Weekly Performance", f"Physical market momentum  ·  {date_label}")
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
        if vix_dates:
            trend = TrendLineChart()
            trend.add_series("VIX", vix_dates, vix_vals, color_key="special_black")
            # Add reference lines for fear zones
            trend.add_reference_line(20, label="Long-term avg", color="#999999")
            trend.add_reference_line(30, label="Fear zone", color="#CC0000")
            trend.render(title="VIX — Market Fear Gauge",
                         subtitle=f"CBOE Volatility Index  ·  {date_label}",
                         source="Yahoo Finance (CBOE)", ylabel="VIX Level")
            trend.save(output_dir / "09_vix_trend.png")
    except Exception as e:
        print(f"   ⚠ VIX chart failed: {e}")

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
            EconStyle.set_title(ax, "India's IT Sector Feels the AI Threat", f"Sector benchmark hits 12-month lows as investors confront AI's threat to India's IT export model")
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
    print("   [12/12] US Real Wage Growth")
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
            combined = pd.DataFrame({"earnings_yoy": earn_yoy, "cpi_yoy": cpi_yoy}).dropna()
            combined["real_wage"] = combined["earnings_yoy"] - combined["cpi_yoy"]

            if len(combined) > 3:
                dates_rw = combined.index.to_pydatetime().tolist()
                vals_rw = combined["real_wage"].values.tolist()

                trend = TrendLineChart()
                trend.add_series("Real Wage Growth", dates_rw, vals_rw,
                                 color_key="us", linewidth=2.2)
                trend.add_reference_line(0, label="Break-even", color="#CC0000")
                trend.render(
                    title="US Real Wage Growth",
                    subtitle="Average Hourly Earnings YoY minus CPI YoY  ·  Positive = purchasing power gains",
                    source="FRED (BLS)",
                    ylabel="Real Wage Growth (%)",
                )
                trend.save(output_dir / "11_real_wage_growth.png")

                # Store latest for summary table
                real_wage_latest = float(combined["real_wage"].iloc[-1])
                if len(combined) >= 2:
                    real_wage_change = real_wage_latest - float(combined["real_wage"].iloc[-2])
    except Exception as e:
        print(f"   ⚠ Real wage growth failed: {e}")

    # ── SUMMARY TABLE ──
    print("   [+] Summary Table")
    table = SummaryTable()
    
    # Define the rows we want (Ordered list)
    row_ids = [
        "sp500", "ftse100", "eurostoxx50", "nifty50", "nikkei225", # Equities
        "btc", "eth",                                              # Crypto
        "dxy", "eurusd", "gbpusd", "usdinr", "usdjpy",             # FX
        "us_2y", "us_10y", "us_30y", "de_10y",                     # Yields
        "brent", "gold", "silver", "copper", "natgas",                        # Commodities
        "vix",                                                      # Volatility (AFTER commodities)
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
            elif ind["change_type"] == "abs": # Yields + VIX
                ytd_str = EconStyle.format_change_label(ytd_val, "abs")
            else: # Everything else (%)
                ytd_str = EconStyle.format_change_label(ytd_val * 100, "pct") # *100 for display

            # VIX: weekly change is absolute points, not percentage
            if ind_id == "vix":
                # Back-calculate absolute change from level and change_pct
                if "change_pct" in w and w["change_pct"] != 0:
                    prev_vix = w["level"] / (1 + w["change_pct"] / 100)
                    vix_abs = w["level"] - prev_vix
                    weekly_str = f"{vix_abs:+.1f} pts"
                else:
                    weekly_str = "0.0 pts"
            elif "change_pct" in w:
                weekly_str = EconStyle.format_change_label(w["change_pct"], "pct")
            else:
                weekly_str = EconStyle.format_change_label(w["change"], "abs")

            table.add_row(ind["name"], w["level"],
                          weekly_str,
                          ytd_change=ytd_str,
                          category=ind.get("category", "misc"))

    # ── Special row: Real Wage Growth (computed, not in INDICATORS) ──
    if real_wage_latest is not None:
        rw_weekly_str = f"{real_wage_change:+.2f} pp" if real_wage_change is not None else "-"
        table.add_row("Real Wage Growth", f"{real_wage_latest:.2f}%",
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
    args = parser.parse_args()
    
    if args.preview:
        EconStyle.DPI = EconStyle.DPI_PREVIEW
    
    output_dir = get_output_dir()
    
    if args.mock:
        generate_with_mock_data(output_dir)
    else:
        try:
            generate_with_live_data(output_dir)
        except ImportError as e:
            print(f"⚠ {e}")
            print("   Falling back to mock data. Install dependencies:")
            print("   pip install yfinance fredapi")
            generate_with_mock_data(output_dir)


if __name__ == "__main__":
    main()

