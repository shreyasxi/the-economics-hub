"""Curated USD ETF universe; first-observation dates are verified at preparation."""
ASSETS = {
    "SPY": {"name": "SPDR S&P 500 ETF", "asset_class": "U.S. large-cap equities"},
    "EFA": {"name": "iShares MSCI EAFE ETF", "asset_class": "Developed equities outside U.S./Canada"},
    "EEM": {"name": "iShares MSCI Emerging Markets ETF", "asset_class": "Emerging-market equities"},
    "AGG": {"name": "iShares Core U.S. Aggregate Bond ETF", "asset_class": "U.S. investment-grade bonds"},
    "IEF": {"name": "iShares 7–10 Year Treasury ETF", "asset_class": "Intermediate U.S. Treasuries"},
    "TLT": {"name": "iShares 20+ Year Treasury ETF", "asset_class": "Long U.S. Treasuries"},
    "LQD": {"name": "iShares iBoxx Investment Grade Corporate Bond ETF", "asset_class": "U.S. investment-grade credit"},
    "GLD": {"name": "SPDR Gold Shares", "asset_class": "Gold"},
}
ASSETS.update({'QQQ': {'name': 'Invesco QQQ Trust', 'asset_class': 'U.S. growth equities'},
 'IWM': {'name': 'iShares Russell 2000 ETF', 'asset_class': 'U.S. small-cap equities'},
 'RSP': {'name': 'Invesco S&P 500 Equal Weight ETF', 'asset_class': 'U.S. equal-weight equities'},
 'INDA': {'name': 'iShares MSCI India ETF', 'asset_class': 'India equities (unhedged USD listing)'},
 'SHY': {'name': 'iShares 1–3 Year Treasury Bond ETF', 'asset_class': 'Short U.S. Treasuries'},
 'TIP': {'name': 'iShares TIPS Bond ETF', 'asset_class': 'U.S. inflation-linked Treasuries'},
 'HYG': {'name': 'iShares iBoxx High Yield Corporate Bond ETF',
         'asset_class': 'U.S. high-yield credit'},
 'DBC': {'name': 'Invesco DB Commodity Index Tracking Fund', 'asset_class': 'Commodity futures'},
 'VNQ': {'name': 'Vanguard Real Estate ETF', 'asset_class': 'U.S. real estate equities'},
 'BIL': {'name': 'SPDR Bloomberg 1–3 Month T-Bill ETF', 'asset_class': 'U.S. Treasury bills'},
 'XLK': {'name': 'Technology Select Sector SPDR Fund', 'asset_class': 'U.S. technology equities'},
 'XLF': {'name': 'Financial Select Sector SPDR Fund', 'asset_class': 'U.S. financial equities'},
 'XLE': {'name': 'Energy Select Sector SPDR Fund', 'asset_class': 'U.S. energy equities'},
 'XLV': {'name': 'Health Care Select Sector SPDR Fund', 'asset_class': 'U.S. healthcare equities'},
 'XLP': {'name': 'Consumer Staples Select Sector SPDR Fund',
         'asset_class': 'U.S. consumer staples equities'},
 'XLU': {'name': 'Utilities Select Sector SPDR Fund', 'asset_class': 'U.S. utilities equities'},
 'IWF': {'name': 'iShares Russell 1000 Growth ETF', 'asset_class': 'U.S. growth equities'},
 'IWD': {'name': 'iShares Russell 1000 Value ETF', 'asset_class': 'U.S. value equities'}})
for _asset in ASSETS.values():
    _asset.update(currency="USD", source="Yahoo Finance via yfinance",
                  adjustment="Explicit Adj Close: split and distribution adjusted")
ASSETS['USO'] = dict(name='United States Oil Fund', asset_class='Crude-oil futures fund',
                    currency='USD', source='Yahoo Finance via yfinance',
                    adjustment='Explicit Adj Close: split and distribution adjusted',
                    instrument='Exchange-traded commodity pool; not WTI spot')
ASSETS['BTC'] = dict(name='Bitcoin · direct reference-price exposure', asset_class='Digital asset',
                    currency='USD', source='Coin Metrics Community API · PriceUSD',
                    adjustment='No yield or distributions; timestamp-aligned USD reference price',
                    instrument='Direct digital asset reference-price research proxy')
TEMPLATES = {
    "Traditional 60/40": {"SPY": .6, "AGG": .4},
    "Diversified allocation": {"SPY": .5, "AGG": .3, "GLD": .2},
    "Multi-asset research": {"SPY": .35, "EFA": .10, "IEF": .20, "LQD": .15, "GLD": .15, "VNQ": .05},
    "Equity-only benchmark": {"SPY": 1.0},
    "Bitcoin & oil research": {"SPY": .45, "AGG": .30, "GLD": .10, "BTC": .05, "USO": .10},
}
EPISODES = {
    "Global Financial Crisis": ("2007-10-09", "2009-03-09"),
    "COVID-19 Market Shock": ("2020-02-19", "2020-04-30"),
    "2022 Equity and Bond Sell-Off": ("2022-01-03", "2022-12-30"),
}
REBALANCING = {"Buy and hold": None, "Monthly": "M", "Quarterly": "Q", "Annual": "Y"}
INITIAL_WEALTH = 10000.0
TRADING_DAYS = 252
MIN_ANNUAL_OBSERVATIONS = 126
RISK_WINDOW = 252
