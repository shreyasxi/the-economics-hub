"""Readable instrument labels for Portfolio Lab presentation."""
NAMES = {
    'SPY': 'S&P 500 Equities', 'EFA': 'Developed Markets ex-US & Canada',
    'EEM': 'Emerging-Market Equities', 'AGG': 'US Aggregate Bonds',
    'IEF': 'US Treasuries, 7–10 Years', 'TLT': 'US Treasuries, 20+ Years',
    'LQD': 'US Investment-Grade Corporate Bonds', 'GLD': 'Gold',
    'QQQ': 'Nasdaq-100 Equities', 'IWM': 'Russell 2000 Small-Cap Equities',
    'RSP': 'S&P 500 Equal-Weight Equities', 'INDA': 'MSCI India Equities',
    'SHY': 'US Treasuries, 1–3 Years', 'TIP': 'US Inflation-Protected Bonds',
    'HYG': 'US High-Yield Corporate Bonds', 'DBC': 'Broad Commodity Futures',
    'VNQ': 'US Real Estate Equities', 'BIL': 'US Treasury Bills, 1–3 Months',
    'XLK': 'US Technology Equities', 'XLF': 'US Financial Equities',
    'XLE': 'US Energy Equities', 'XLV': 'US Health Care Equities',
    'XLP': 'US Consumer Staples Equities', 'XLU': 'US Utilities Equities',
    'IWF': 'Russell 1000 Growth Equities', 'IWD': 'Russell 1000 Value Equities',
    'USO': 'WTI Oil Futures Fund', 'BTC': 'Bitcoin',
}


def asset_label(ticker):
    return f'{NAMES[ticker]} ({ticker})' if ticker in NAMES else ticker


SHORT_NAMES = {
    'SPY': 'US Equities', 'EFA': 'Developed Equities', 'EEM': 'Emerging Equities',
    'AGG': 'Bonds', 'IEF': 'Treasuries 7–10Y', 'TLT': 'Treasuries 20+Y',
    'LQD': 'Corporate Bonds', 'GLD': 'Gold', 'QQQ': 'Nasdaq-100',
    'IWM': 'Small-Cap Equities', 'RSP': 'Equal-Weight Equities', 'INDA': 'India Equities',
    'SHY': 'Treasuries 1–3Y', 'TIP': 'Inflation-Linked Bonds', 'HYG': 'High-Yield Bonds',
    'DBC': 'Commodities', 'VNQ': 'Real Estate', 'BIL': 'Treasury Bills',
    'XLK': 'Technology', 'XLF': 'Financials', 'XLE': 'Energy', 'XLV': 'Health Care',
    'XLP': 'Consumer Staples', 'XLU': 'Utilities', 'IWF': 'Growth Equities',
    'IWD': 'Value Equities', 'USO': 'Oil', 'BTC': 'Bitcoin',
}


SHORT_NAMES.update({
    'NIFTYBEES.NS': 'Equities', 'GOLDBEES.NS': 'Gold',
    'GILT5YBEES.NS': 'Bonds', 'LTGILTBEES.NS': 'Long-Term Bonds',
    'LIQUIDCASE.NS': 'Liquid Fund', 'nifty-50': 'Equities',
    'nifty-next-50': 'Next-50 Equities', 'nifty-midcap-150': 'Mid-Cap Equities',
    'niftysmallcap250': 'Small-Cap Equities',
})
ABBREVIATIONS = {
    'nifty-50': 'NIFTY 50', 'nifty-next-50': 'NIFTY NEXT 50',
    'nifty-midcap-150': 'NIFTY MIDCAP 150', 'niftysmallcap250': 'NIFTY SMALLCAP 250',
}


def short_asset_label(ticker):
    return f'{SHORT_NAMES[ticker]} ({ABBREVIATIONS.get(ticker,str(ticker).removesuffix(".NS"))})' if ticker in SHORT_NAMES else ticker


def asset_frame(frame):
    """Rename presentation axes only; calculation inputs retain ticker keys."""
    return frame.rename(index=short_asset_label, columns=short_asset_label)


def asset_chart_frame(frame):
    return asset_frame(frame)
