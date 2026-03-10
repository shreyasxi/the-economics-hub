"""
Economics Hub — Master Configuration
=====================================
All indicator definitions, API keys, data series mappings,
and publication settings live here. Edit this file to add
new indicators or change data sources.
"""

from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()



# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STYLE_DIR = PROJECT_ROOT / "style"
DATA_CACHE = PROJECT_ROOT / "data" / "cache"
CHART_BANK = PROJECT_ROOT / "charts" / "bank"
OUTPUT_DIR = PROJECT_ROOT / "output" / "weekly"
TEMPLATE_DIR = PROJECT_ROOT / "output" / "templates"

# ─────────────────────────────────────────────
# API KEYS (set yours here or via env vars)
# ─────────────────────────────────────────────
FRED_API_KEY = os.environ.get("FRED_API_KEY", "YOUR_FRED_API_KEY")

# ─────────────────────────────────────────────
# PUBLICATION SETTINGS
# ─────────────────────────────────────────────
PUBLICATION_NAME = "The Economics Hub"
AUTHOR = "Shreyas"
TAGLINE = "Global finance through multiple lenses"
WATERMARK_TEXT = "The Economics Hub"

# Current week label (auto-generated)
def get_week_label():
    now = datetime.now()
    week_num = now.isocalendar()[1]
    return f"Week {week_num} · {now.strftime('%d %B %Y')}"

# ─────────────────────────────────────────────
# INDICATOR DEFINITIONS
# ─────────────────────────────────────────────
# Each indicator has:
#   - name: Display name for chart titles
#   - source: "yfinance" or "fred" or "ecb" or "manual"
#   - ticker/series: The API identifier
#   - category: For grouping in the dashboard
#   - chart_type: "weekly_bar", "trend_line", "yield_curve"
#   - unit: Display unit (%, $, bps, index)
#   - change_type: "pct" (percentage change) or "abs" (absolute change)

INDICATORS = {

    # ═══════════════════════════════════════════
    # EQUITIES
    # ═══════════════════════════════════════════
    "sp500": {
        "name": "S&P 500",
        "source": "yfinance",
        "ticker": "^GSPC",
        "category": "equities",
        "region": "US",
        "unit": "index",
        "change_type": "pct",
        "color_key": "us",
    },
    "ftse100": {
        "name": "FTSE 100",
        "source": "yfinance",
        "ticker": "^FTSE",
        "category": "equities",
        "region": "Europe",
        "unit": "index",
        "change_type": "pct",
        "color_key": "europe",
    },
    "eurostoxx50": {
        "name": "Euro Stoxx 50",
        "source": "yfinance",
        "ticker": "^STOXX50E",
        "category": "equities",
        "region": "Europe",
        "unit": "index",
        "change_type": "pct",
        "color_key": "europe",
    },
    "nifty50": {
        "name": "Nifty 50",
        "source": "yfinance",
        "ticker": "^NSEI",
        "category": "equities",
        "region": "India",
        "unit": "index",
        "change_type": "pct",
        "color_key": "india",
    },
    "nikkei225": {
        "name": "Nikkei 225",
        "source": "yfinance",
        "ticker": "^N225",
        "category": "equities",
        "region": "Asia",
        "unit": "index",
        "change_type": "pct",
        "color_key": "asia",
    },
    
    "dow": {
        "name": "Dow Jones",
        "source": "yfinance",
        "ticker": "^DJI",
        "category": "equities",
        "region": "US",
        "unit": "index",
        "change_type": "pct",
        "color_key": "us",
    },
    "nasdaq": {
        "name": "NASDAQ",
        "source": "yfinance",
        "ticker": "^IXIC",  # Use ^NDX instead if you prefer the NASDAQ-100
        "category": "equities",
        "region": "US",
        "unit": "index",
        "change_type": "pct",
        "color_key": "us",
    },
    "shanghai": {
        "name": "Shanghai Comp",
        "source": "yfinance",
        "ticker": "000001.SS",
        "category": "equities",
        "region": "Asia",
        "unit": "index",
        "change_type": "pct",
        "color_key": "asia",
    },
    "hangseng": {
        "name": "Hang Seng",
        "source": "yfinance",
        "ticker": "^HSI",
        "category": "equities",
        "region": "Asia",
        "unit": "index",
        "change_type": "pct",
        "color_key": "asia",
    },

    # ═══════════════════════════════════════════
    # FOREIGN EXCHANGE
    # ═══════════════════════════════════════════
    "dxy": {
        "name": "US Dollar Index (DXY)",
        "source": "yfinance",
        "ticker": "DX-Y.NYB",
        "category": "fx",
        "region": "US",
        "unit": "index",
        "change_type": "pct",
        "color_key": "special_black",
    },
    "eurusd": {
        "name": "EUR/USD",
        "source": "yfinance",
        "ticker": "EURUSD=X",
        "category": "fx",
        "region": "Europe",
        "unit": "",
        "change_type": "pct",
        "color_key": "europe",
    },
    "gbpusd": {
        "name": "GBP/USD",
        "source": "yfinance",
        "ticker": "GBPUSD=X",
        "category": "fx",
        "region": "Europe",
        "unit": "",
        "change_type": "pct",
        "color_key": "europe",
    },
    "usdinr": {
        "name": "USD/INR",
        "source": "yfinance",
        "ticker": "INR=X",
        "category": "fx",
        "region": "India",
        "unit": "",
        "change_type": "pct",
        "color_key": "india",
    },
    "usdjpy": {
        "name": "USD/JPY",
        "source": "yfinance",
        "ticker": "JPY=X",
        "category": "fx",
        "region": "Asia",
        "unit": "",
        "change_type": "pct",
        "color_key": "asia",
    },

    # ═══════════════════════════════════════════
    # TREASURY / GOVERNMENT BOND YIELDS
    # ═══════════════════════════════════════════
    # US Yields (FRED — daily series)
    "us_2y": {
        "name": "US 2-Year",
        "source": "fred",
        "series": "DGS2",
        "category": "yields",
        "region": "US",
        "unit": "%",
        "change_type": "abs",
        "color_key": "us",
    },
    "us_5y": {
        "name": "US 5-Year",
        "source": "fred",
        "series": "DGS5",
        "category": "yields",
        "region": "US",
        "unit": "%",
        "change_type": "abs",
        "color_key": "us",
    },
    "us_10y": {
        "name": "US 10-Year",
        "source": "fred",
        "series": "DGS10",
        "category": "yields",
        "region": "US",
        "unit": "%",
        "change_type": "abs",
        "color_key": "us",
    },
    "us_30y": {
        "name": "US 30-Year",
        "source": "fred",
        "series": "DGS30",
        "category": "yields",
        "region": "US",
        "unit": "%",
        "change_type": "abs",
        "color_key": "us",
    },
    # ── FIXED: German Bund — now FRED source (monthly series) ──
    # Works for trend charts. Will be auto-skipped for weekly bar (not enough data).
    "de_10y": {
        "name": "German Bund 10Y",
        "source": "fred",
        "series": "IRLTLT01DEM156N",
        "category": "yields",
        "region": "Europe",
        "unit": "%",
        "change_type": "abs",
        "color_key": "europe",
    },
    # UK Gilt — same situation (monthly FRED series)
    "uk_10y": {
        "name": "UK Gilt 10Y",
        "source": "fred",
        "series": "IRLTLT01GBM156N",
        "category": "yields",
        "region": "Europe",
        "unit": "%",
        "change_type": "abs",
        "color_key": "europe",
    },
    # ── REMOVED: India 10Y — ^IRTYIELD is permanently delisted on Yahoo Finance ──

    # ═══════════════════════════════════════════
    # CRYPTO (New Section)
    # ═══════════════════════════════════════════
    "btc": {
        "name": "Bitcoin",
        "source": "yfinance",
        "ticker": "BTC-USD",
        "category": "crypto",
        "unit": "USD",
        "change_type": "pct",
        "color_key": "special_black",
    },
    "eth": {
        "name": "Ethereum",
        "source": "yfinance",
        "ticker": "ETH-USD",
        "category": "crypto",
        "unit": "USD",
        "change_type": "pct",
        "color_key": "special_black",
    },

    # ═══════════════════════════════════════════
    # VOLATILITY & SENTIMENT
    # ═══════════════════════════════════════════
    "vix": {
        "name": "VIX",
        "source": "yfinance",
        "ticker": "^VIX",
        "category": "volatility",
        "unit": "index",
        "change_type": "abs",
        "color_key": "special_black",
    },
    
    "vix3m": {
        "name": "VIX 3-Month",
        "ticker": "^VIX3M",
        "source": "yfinance",
        "change_type": "abs",
        "unit": "index",
        "category": "volatility",
        "color_key": "pink",
    },

    # ═══════════════════════════════════════════
    # COMMODITIES
    # ═══════════════════════════════════════════
    "brent": {
        "name": "Brent Crude",
        "source": "yfinance",
        "ticker": "BZ=F",
        "category": "commodities",
        "unit": "$/bbl",
        "change_type": "pct",
        "color_key": "commodity_energy",
    },
    "wti": {
        "name": "WTI Crude",
        "source": "yfinance",
        "ticker": "CL=F",
        "category": "commodities",
        "unit": "$/bbl",
        "change_type": "pct",
        "color_key": "commodity_energy",
    },
    "gold": {
        "name": "Gold",
        "source": "yfinance",
        "ticker": "GC=F",
        "category": "commodities",
        "unit": "$/oz",
        "change_type": "pct",
        "color_key": "commodity_gold",
    },
    "silver": {
        "name": "Silver",
        "source": "yfinance",
        "ticker": "SI=F",
        "category": "commodities",
        "unit": "$/oz",
        "change_type": "pct",
        "color_key": "commodity_silver",
    },
    "copper": {
        "name": "Copper",
        "source": "yfinance",
        "ticker": "HG=F",
        "category": "commodities",
        "unit": "$/lb",
        "change_type": "pct",
        "color_key": "commodity_copper",
    },
    "natgas": {
        "name": "Natural Gas",
        "source": "yfinance",
        "ticker": "NG=F",
        "category": "commodities",
        "unit": "$/MMBtu",
        "change_type": "pct",
        "color_key": "commodity_energy",
    },
    
    "uranium": {
        "name": "Uranium", 
        "ticker": "SRUUF", 
        "source": "yfinance", 
        "color_key": "us",
        "category": "commodities"
    },
}



# ─────────────────────────────────────────────
# YIELD CURVE CONFIGURATION
# ─────────────────────────────────────────────
US_YIELD_CURVE_TENORS = {
    "1M": "DGS1MO",
    "3M": "DGS3MO",
    "6M": "DGS6MO",
    "1Y": "DGS1",
    "2Y": "DGS2",
    "5Y": "DGS5",
    "7Y": "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}

# ─────────────────────────────────────────────
# DASHBOARD SECTION ORDER
# ─────────────────────────────────────────────
DASHBOARD_SECTIONS = [
    {
        "id": "equities",
        "title": "Global Equities",
        "subtitle": "Weekly performance",
        "indicators": ["sp500", "ftse100", "eurostoxx50", "nifty50", "nikkei225"], 
        "chart_types": ["weekly_bar", "trend_line"],
    },
    {
        "id": "fx",
        "title": "Foreign Exchange",
        "subtitle": "Key currency moves",
        "indicators": ["dxy", "eurusd", "gbpusd", "usdinr", "usdjpy"], 
        "chart_types": ["weekly_bar", "trend_line"],
    },
    {
        "id": "crypto",
        "title": "Crypto Assets",
        "subtitle": "Digital assets performance",
        "indicators": ["btc", "eth"], 
        "chart_types": ["weekly_bar"],
    },
    {
        "id": "yields",
        "title": "Government Bond Yields",
        "subtitle": "Sovereign debt markets across regions",
        "indicators": ["us_2y", "us_5y", "us_10y", "us_30y", "de_10y", "uk_10y"],
        "chart_types": ["yield_curve", "weekly_bar"],
    },
    {
        "id": "commodities",
        "title": "Commodities",
        "subtitle": "Energy and metals",
        "indicators": ["brent", "wti", "gold", "silver", "copper", "natgas"],
        "chart_types": ["weekly_bar", "trend_line"],
    },
]

# ─────────────────────────────────────────────
# CATEGORY DISPLAY NAMES
# ─────────────────────────────────────────────
CATEGORY_NAMES = {
    "equities": "Global Equities",
    "fx": "Foreign Exchange",
    "yields": "Government Bond Yields",
    "commodities": "Commodities",
    "volatility": "Volatility & Sentiment",
}
