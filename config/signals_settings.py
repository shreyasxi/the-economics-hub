"""
Signal or noise: the series the Analysis page ranks each week.

generate_signals.py takes every series below, measures its move over the week to
Friday's close, and divides that by the size of a typical week for the same
series over the past three years. A 2% week in an index that usually moves 1%
scores 2x; the same 2% in a currency that usually moves 0.3% scores nearly 7x.
Ranking by that multiple, rather than by the raw move, is what separates the
week's news from its noise.

Adding a series is one line in SERIES. Nothing is filled in for a series that
fails to download or has not printed this week: it is left out of the ranking
and named under the board instead.

Fields
    id       short key, unique
    name     what the board calls it
    group    Equities, Rates, Credit, Currencies, Commodities, Volatility or Crypto
    source   "yfinance" (Yahoo Finance ticker) or "fred" (FRED series id)
    code     the ticker or series id
    measure  "pct" (percentage change, for prices) or "bp" (change in basis
             points, for FRED series quoted in per cent: yields and spreads)
    fmt      how the latest level is written: "index", "usd", "fx2", "fx4",
             "yield" (a rate in per cent), "spread" (per cent shown as bp),
             "vol" or "eur"
"""

# A typical week: the root mean square of the series' weekly moves over this
# many weeks before the current one. Three years keeps it recent enough that a
# calm market is judged against calm, without letting one bad month set the bar.
TYPICAL_WINDOW_WEEKS = 156

# Fewer weekly moves than this and a typical week cannot be judged.
MIN_WEEKS = 52

# How much history is fetched, and so how far back "largest since" can look.
HISTORY_YEARS = 10

# A series whose last print is more than this many days before the week's
# Friday has not traded this week (a holiday, or a dead ticker) and is left out.
STALE_DAYS = 4

# If more than this share of the series cannot be measured, the run fails
# rather than publish a ranking of what happened to download.
MAX_MISSING_SHARE = 0.25

# Rows on the board before "all series".
TOP_N = 8

# Multiples at or above this count as "moved more than twice a typical week".
NOTABLE = 2.0

SERIES: list[dict] = [
    # ── Equities ────────────────────────────────────────────────────────────
    {"id": "sp500",    "name": "S&P 500",                 "group": "Equities", "source": "yfinance", "code": "^GSPC",     "measure": "pct", "fmt": "index"},
    {"id": "nasdaq",   "name": "Nasdaq Composite",        "group": "Equities", "source": "yfinance", "code": "^IXIC",     "measure": "pct", "fmt": "index"},
    {"id": "sox",      "name": "Philadelphia Semiconductor", "group": "Equities", "source": "yfinance", "code": "^SOX",  "measure": "pct", "fmt": "index"},
    {"id": "stoxx50",  "name": "Euro Stoxx 50",           "group": "Equities", "source": "yfinance", "code": "^STOXX50E", "measure": "pct", "fmt": "index"},
    {"id": "ftse100",  "name": "FTSE 100",                "group": "Equities", "source": "yfinance", "code": "^FTSE",     "measure": "pct", "fmt": "index"},
    {"id": "nikkei",   "name": "Nikkei 225",              "group": "Equities", "source": "yfinance", "code": "^N225",     "measure": "pct", "fmt": "index"},
    {"id": "hangseng", "name": "Hang Seng",               "group": "Equities", "source": "yfinance", "code": "^HSI",      "measure": "pct", "fmt": "index"},
    {"id": "shanghai", "name": "Shanghai Composite",      "group": "Equities", "source": "yfinance", "code": "000001.SS", "measure": "pct", "fmt": "index"},
    {"id": "nifty50",  "name": "Nifty 50",                "group": "Equities", "source": "yfinance", "code": "^NSEI",     "measure": "pct", "fmt": "index"},
    {"id": "korea",    "name": "MSCI Korea (EWY, $)",     "group": "Equities", "source": "yfinance", "code": "EWY",       "measure": "pct", "fmt": "usd"},
    {"id": "taiwan",   "name": "MSCI Taiwan (EWT, $)",    "group": "Equities", "source": "yfinance", "code": "EWT",       "measure": "pct", "fmt": "usd"},
    {"id": "em_eq",    "name": "MSCI Emerging Markets (EEM, $)", "group": "Equities", "source": "yfinance", "code": "EEM", "measure": "pct", "fmt": "usd"},

    # ── Rates (FRED, per cent; moves in basis points) ───────────────────────
    {"id": "us_3m",    "name": "US 3-month bill",         "group": "Rates", "source": "fred", "code": "DGS3MO", "measure": "bp", "fmt": "yield"},
    {"id": "us_2y",    "name": "US 2-year Treasury",      "group": "Rates", "source": "fred", "code": "DGS2",   "measure": "bp", "fmt": "yield"},
    {"id": "us_10y",   "name": "US 10-year Treasury",     "group": "Rates", "source": "fred", "code": "DGS10",  "measure": "bp", "fmt": "yield"},
    {"id": "us_30y",   "name": "US 30-year Treasury",     "group": "Rates", "source": "fred", "code": "DGS30",  "measure": "bp", "fmt": "yield"},
    {"id": "us_real10", "name": "US 10-year real yield (TIPS)", "group": "Rates", "source": "fred", "code": "DFII10", "measure": "bp", "fmt": "yield"},
    {"id": "us_be10",  "name": "US 10-year breakeven inflation", "group": "Rates", "source": "fred", "code": "T10YIE", "measure": "bp", "fmt": "yield"},

    # ── Credit (ICE BofA option-adjusted spreads; FRED keeps three years) ───
    {"id": "us_ig",    "name": "US investment-grade spread", "group": "Credit", "source": "fred", "code": "BAMLC0A0CM",    "measure": "bp", "fmt": "spread"},
    {"id": "us_hy",    "name": "US high-yield spread",    "group": "Credit", "source": "fred", "code": "BAMLH0A0HYM2",  "measure": "bp", "fmt": "spread"},
    {"id": "em_corp",  "name": "EM corporate spread",     "group": "Credit", "source": "fred", "code": "BAMLEMCBPIOAS", "measure": "bp", "fmt": "spread"},

    # ── Currencies (USD/XXX up = dollar stronger) ───────────────────────────
    {"id": "dxy",      "name": "US dollar index (DXY)",   "group": "Currencies", "source": "yfinance", "code": "DX-Y.NYB", "measure": "pct", "fmt": "fx2"},
    {"id": "eurusd",   "name": "EUR/USD",                 "group": "Currencies", "source": "yfinance", "code": "EURUSD=X", "measure": "pct", "fmt": "fx4"},
    {"id": "gbpusd",   "name": "GBP/USD",                 "group": "Currencies", "source": "yfinance", "code": "GBPUSD=X", "measure": "pct", "fmt": "fx4"},
    {"id": "usdjpy",   "name": "USD/JPY",                 "group": "Currencies", "source": "yfinance", "code": "JPY=X",    "measure": "pct", "fmt": "fx2"},
    {"id": "usdcny",   "name": "USD/CNY",                 "group": "Currencies", "source": "yfinance", "code": "CNY=X",    "measure": "pct", "fmt": "fx4"},
    {"id": "usdinr",   "name": "USD/INR",                 "group": "Currencies", "source": "yfinance", "code": "INR=X",    "measure": "pct", "fmt": "fx2"},
    {"id": "usdkrw",   "name": "USD/KRW",                 "group": "Currencies", "source": "yfinance", "code": "KRW=X",    "measure": "pct", "fmt": "fx2"},
    {"id": "usdidr",   "name": "USD/IDR",                 "group": "Currencies", "source": "yfinance", "code": "IDR=X",    "measure": "pct", "fmt": "fx2"},
    {"id": "usdbrl",   "name": "USD/BRL",                 "group": "Currencies", "source": "yfinance", "code": "BRL=X",    "measure": "pct", "fmt": "fx4"},
    {"id": "usdmxn",   "name": "USD/MXN",                 "group": "Currencies", "source": "yfinance", "code": "MXN=X",    "measure": "pct", "fmt": "fx4"},
    {"id": "usdzar",   "name": "USD/ZAR",                 "group": "Currencies", "source": "yfinance", "code": "ZAR=X",    "measure": "pct", "fmt": "fx4"},
    {"id": "usdtry",   "name": "USD/TRY",                 "group": "Currencies", "source": "yfinance", "code": "TRY=X",    "measure": "pct", "fmt": "fx4"},

    # ── Commodities (front-month futures) ───────────────────────────────────
    {"id": "brent",    "name": "Brent crude",             "group": "Commodities", "source": "yfinance", "code": "BZ=F",  "measure": "pct", "fmt": "usd"},
    {"id": "wti",      "name": "WTI crude",               "group": "Commodities", "source": "yfinance", "code": "CL=F",  "measure": "pct", "fmt": "usd"},
    {"id": "natgas",   "name": "US natural gas (Henry Hub)", "group": "Commodities", "source": "yfinance", "code": "NG=F", "measure": "pct", "fmt": "usd"},
    {"id": "ttf",      "name": "European gas (TTF)",      "group": "Commodities", "source": "yfinance", "code": "TTF=F", "measure": "pct", "fmt": "eur"},
    {"id": "gold",     "name": "Gold",                    "group": "Commodities", "source": "yfinance", "code": "GC=F",  "measure": "pct", "fmt": "usd"},
    {"id": "silver",   "name": "Silver",                  "group": "Commodities", "source": "yfinance", "code": "SI=F",  "measure": "pct", "fmt": "usd"},
    {"id": "platinum", "name": "Platinum",                "group": "Commodities", "source": "yfinance", "code": "PL=F",  "measure": "pct", "fmt": "usd"},
    {"id": "copper",   "name": "Copper",                  "group": "Commodities", "source": "yfinance", "code": "HG=F",  "measure": "pct", "fmt": "usd"},
    {"id": "wheat",    "name": "Wheat",                   "group": "Commodities", "source": "yfinance", "code": "ZW=F",  "measure": "pct", "fmt": "usd"},
    {"id": "corn",     "name": "Corn",                    "group": "Commodities", "source": "yfinance", "code": "ZC=F",  "measure": "pct", "fmt": "usd"},
    {"id": "soybeans", "name": "Soybeans",                "group": "Commodities", "source": "yfinance", "code": "ZS=F",  "measure": "pct", "fmt": "usd"},
    {"id": "coffee",   "name": "Coffee",                  "group": "Commodities", "source": "yfinance", "code": "KC=F",  "measure": "pct", "fmt": "usd"},
    {"id": "cocoa",    "name": "Cocoa",                   "group": "Commodities", "source": "yfinance", "code": "CC=F",  "measure": "pct", "fmt": "usd"},
    {"id": "sugar",    "name": "Sugar",                   "group": "Commodities", "source": "yfinance", "code": "SB=F",  "measure": "pct", "fmt": "usd"},

    # ── Volatility (moves in per cent: a 4-point jump means more from 12 than from 30) ──
    {"id": "vix",      "name": "VIX (S&P 500 volatility)", "group": "Volatility", "source": "yfinance", "code": "^VIX",      "measure": "pct", "fmt": "vol"},
    {"id": "move",     "name": "MOVE (Treasury volatility)", "group": "Volatility", "source": "yfinance", "code": "^MOVE",  "measure": "pct", "fmt": "vol"},
    {"id": "india_vix", "name": "India VIX",              "group": "Volatility", "source": "yfinance", "code": "^INDIAVIX", "measure": "pct", "fmt": "vol"},

    # ── Crypto ──────────────────────────────────────────────────────────────
    {"id": "btc",      "name": "Bitcoin",                 "group": "Crypto", "source": "yfinance", "code": "BTC-USD", "measure": "pct", "fmt": "usd"},
    {"id": "eth",      "name": "Ether",                   "group": "Crypto", "source": "yfinance", "code": "ETH-USD", "measure": "pct", "fmt": "usd"},
]
