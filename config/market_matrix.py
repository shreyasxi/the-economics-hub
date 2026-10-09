"""Ordered return universe and explicit source decisions for the Weekly matrix.

Official TRI where automated; otherwise adjusted investable proxies. Bitcoin
uses underlying prices. No ticker or method is substituted on source failure.
"""
ADJUSTED_TOTAL_RETURN = 'dividend-adjusted investable total return'
OFFICIAL_TOTAL_RETURN = 'official total-return index'
DIRECT_PRICE_RETURN = 'direct price return'
RETURN_METHODS = (ADJUSTED_TOTAL_RETURN, OFFICIAL_TOTAL_RETURN, DIRECT_PRICE_RETURN)
GROUPS = [
    ('us_equities', 'US Equities'),
    ('us_sectors', 'US Sectors'),
    ('developed_markets', 'Developed Markets'),
    ('emerging_markets', 'Emerging Markets'),
    ('fixed_income', 'Fixed Income'),
    ('commodities', 'Commodities'),
    ('crypto', 'Crypto'),
]


def proxy(ticker, label, group, instrument, *, note='', methodology_url='', futures=False):
    return dict(id=ticker.lower(), label=label, group=group, currency='USD',
                source='Yahoo Finance', source_url=f'https://finance.yahoo.com/quote/{ticker}/history/',
                instrument_or_index=instrument, ticker_or_series=ticker, ticker_or_series_code=ticker,
                return_method=ADJUSTED_TOTAL_RETURN, methodology_note=note or
                'Split/dividend-adjusted market-price return; distributions reinvested; fund expenses embedded; before investor tax and trading costs.',
                methodology_url=methodology_url, futures_roll_accounted=futures)


ASSETS = [
    proxy('SPY', 'S&P 500', 'us_equities', 'SPDR S&P 500 ETF Trust'),
    proxy('QQQ', 'Nasdaq 100', 'us_equities', 'Invesco QQQ Trust'),
    proxy('IWM', 'Russell 2000', 'us_equities', 'iShares Russell 2000 ETF'),
    proxy('XLE', 'Energy', 'us_sectors', 'State Street Energy Select Sector SPDR ETF',
          methodology_url='https://www.ssga.com/us/en/individual/capabilities/equities/sector-investing/select-sector-etfs'),
    proxy('XLF', 'Financials', 'us_sectors', 'State Street Financial Select Sector SPDR ETF',
          methodology_url='https://www.ssga.com/us/en/individual/capabilities/equities/sector-investing/select-sector-etfs'),
    proxy('XLK', 'Technology', 'us_sectors', 'State Street Technology Select Sector SPDR ETF',
          methodology_url='https://www.ssga.com/us/en/individual/capabilities/equities/sector-investing/select-sector-etfs'),
    proxy('VGK', 'Europe', 'developed_markets', 'Vanguard FTSE Europe ETF'),
    proxy('EWJ', 'Japan', 'developed_markets', 'iShares MSCI Japan ETF'),
    proxy('VEA', 'Developed ex-US', 'developed_markets', 'Vanguard FTSE Developed Markets ETF'),
    proxy('EEM', 'Broad Emerging Markets', 'emerging_markets', 'iShares MSCI Emerging Markets ETF'),
    proxy('INDA', 'India (MSCI proxy)', 'emerging_markets', 'iShares MSCI India ETF'),
    proxy('MCHI', 'China', 'emerging_markets', 'iShares MSCI China ETF'),
    proxy('EWY', 'South Korea', 'emerging_markets', 'iShares MSCI South Korea ETF'),
    proxy('EWT', 'Taiwan', 'emerging_markets', 'iShares MSCI Taiwan ETF'),
    proxy('EWZ', 'Brazil', 'emerging_markets', 'iShares MSCI Brazil ETF'),
    proxy('AGG', 'US Aggregate Bonds', 'fixed_income', 'iShares Core US Aggregate Bond ETF'),
    proxy('IEF', 'US 7–10Y Treasuries', 'fixed_income', 'iShares 7–10 Year Treasury Bond ETF'),
    proxy('TLT', 'US Long Treasuries', 'fixed_income', 'iShares 20+ Year Treasury Bond ETF'),
    proxy('LQD', 'US Investment Grade Credit', 'fixed_income', 'iShares iBoxx USD Investment Grade Corporate Bond ETF'),
    proxy('HYG', 'US High Yield Credit', 'fixed_income', 'iShares iBoxx USD High Yield Corporate Bond ETF'),
    proxy('EMB', 'EM Sovereign Debt', 'fixed_income', 'iShares J.P. Morgan USD Emerging Markets Bond ETF'),
    proxy('GLD', 'Gold', 'commodities', 'SPDR Gold Shares',
          note='Physically backed gold trust adjusted return, net of expenses; gold has no dividend/coupon. Chosen for stable automated full history; not a spot-price index.',
          methodology_url='https://www.spdrgoldshares.com/usa/'),
    proxy('SLV', 'Silver', 'commodities', 'iShares Silver Trust',
          note='Physically backed silver trust adjusted return, net of expenses; silver has no dividend/coupon. Chosen for stable automated full history; not a spot-price index.',
          methodology_url='https://www.ishares.com/us/products/239855/ishares-silver-trust-fund'),
    proxy('DBC', 'Broad Commodities (proxy)', 'commodities', 'Invesco DB Commodity Index Tracking Fund',
          note='Adjusted investable commodity-futures strategy return: rolling futures, collateral income and fund expenses are reflected; distributions reinvested. Not spot returns or the excess-return benchmark alone.',
          methodology_url='https://www.invesco.com/us/en/financial-products/etfs/invesco-db-commodity-index-tracking-fund.html', futures=True),
    proxy('USO', 'Oil (WTI futures proxy)', 'commodities', 'United States Oil Fund, LP',
          note='Adjusted oil-futures fund market-price total return including roll effects, collateral income, distributions and expenses. Not spot WTI; portfolio/roll strategy changed in 2020 and 2023–24.',
          methodology_url='https://www.uscfinvestments.com/uso', futures=True),
    proxy('CPER', 'Copper (futures proxy)', 'commodities', 'United States Copper Index Fund',
          note='Adjusted investable copper-futures fund return including rolling futures, collateral income, distributions and fund expenses. Not spot copper.',
          methodology_url='https://www.uscfinvestments.com/cper', futures=True),
    proxy('DBA', 'Agriculture (futures proxy)', 'commodities', 'Invesco DB Agriculture Fund',
          note='Adjusted investable agricultural-futures strategy return including roll effects, collateral income, distributions and fund expenses. Not spot crop prices or the excess-return benchmark alone.',
          methodology_url='https://www.invesco.com/content/dam/invesco/us/en/product-documents/etf/fact-sheet/dba-invesco-db-agriculture-fund-fact-sheet.pdf', futures=True),
    dict(id='bitcoin', label='Bitcoin', group='crypto', currency='USD', source='Yahoo Finance',
         source_url='https://finance.yahoo.com/quote/BTC-USD/history/', instrument_or_index='Bitcoin / US dollar',
         ticker_or_series='BTC-USD', ticker_or_series_code='BTC-USD', return_method=DIRECT_PRICE_RETURN,
         non_income_asset=True, methodology_note='Direct BTC/USD observed daily close; no dividend/coupon, so price return is the underlying asset return; not a Bitcoin ETF.'),
]
# All selected instruments are expected to support five years; no proxy swaps.
for asset in ASSETS:
    asset['min_history_years'] = 5

HORIZONS = ('1D', '1W', '1M', '3M', 'YTD', '1Y', '3Y', '5Y')
MAX_MISSING_SHARE = 0.20
STALE_BUSINESS_DAYS = 3
