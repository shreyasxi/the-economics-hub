"""Approved V1 India equity leadership universe; exact official retrieval keys.

No proxy, price-index or differently named index substitution on source failure.
"""
SOURCE_PAGE = 'https://www.niftyindices.com/reports/historical-data'
ENDPOINT = 'https://www.niftyindices.com/BackPage/getTotalReturnIndexString'
MAPPING_URL = 'https://liveindexsa.niftyindices.com/assets/json/IndexMapping.json'
RETURN_METHOD = 'official NSE gross total-return index'
ARTIFACT = 'india_equity_matrix.json'
METHOD_NOTE = ('Returns use official NSE gross total-return indices. '
               'Some newer indices include official NSE back-cast history prior to launch.')
HORIZONS = ('1W', '1M', 'YTD', '1Y', '3Y', '5Y')
GROUPS = [('broad', 'Broad Market'), ('size', 'Market Cap'), ('sectors', 'Sectors'), ('style', 'Factors & Style'), ('themes', 'Themes'), ('ownership', 'Corporate / Ownership')]

# id, official name, group, trading code, product URL, audit history start
_UNIVERSE = [
    ('nifty-50', 'Nifty 50', 'broad', 'NIFTY 50', 'https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50', '1999-06-30'),
    ('nifty-next-50', 'Nifty Next 50', 'broad', 'NIFTY NEXT 50', 'https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-next-50', '2002-11-08'),
    ('nifty-500', 'Nifty 500', 'broad', 'NIFTY 500', 'https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-500', '1995-01-01'),
    ('nifty-midcap-150', 'Nifty Midcap 150', 'size', 'NIFTY MIDCAP 150', 'https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-midcap-150', '2005-04-01'),
    ('niftysmallcap250', 'NIFTY Smallcap 250', 'size', 'NIFTY SMLCAP 250', 'https://www.niftyindices.com/indices/equity/broad-based-indices/niftysmallcap250', '2005-04-01'),
    ('nifty-microcap-250', 'Nifty Microcap 250', 'size', 'NIFTY MICROCAP250', 'https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-microcap-250', '2005-04-01'),
    ('nifty-bank', 'Nifty Bank', 'sectors', 'NIFTY BANK', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-bank', '2000-01-01'),
    ('nifty-financial-services-ex-bank', 'Nifty Financial Services Ex-Bank', 'sectors', 'NIFTY FINSEREXBNK', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-financial--services-ex-bank', '2005-04-01'),
    ('nifty-psu-bank', 'Nifty PSU Bank', 'sectors', 'NIFTY PSU BANK', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-psu-bank', '2004-01-01'),
    ('nifty-it', 'Nifty IT', 'sectors', 'NIFTY IT', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-it', '1999-06-30'),
    ('nifty-auto', 'Nifty Auto', 'sectors', 'NIFTY AUTO', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-auto', '2004-01-01'),
    ('nifty-pharma', 'Nifty Pharma', 'sectors', 'NIFTY PHARMA', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-pharma', '2001-01-01'),
    ('nifty-fmcg', 'Nifty FMCG', 'sectors', 'NIFTY FMCG', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-fmcg', '1996-01-01'),
    ('nifty-metal', 'Nifty Metal', 'sectors', 'NIFTY METAL', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-metal', '2004-01-01'),
    ('nifty-realty', 'Nifty Realty', 'sectors', 'NIFTY REALTY', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-realty', '2006-12-29'),
    ('nifty-energy', 'Nifty Energy', 'sectors', 'NIFTY ENERGY', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-energy', '2001-01-01'),
    ('nifty-consumer-durables-index', 'Nifty Consumer Durables', 'sectors', 'NIFTY CONSR DURBL', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-consumer-durables-index', '2005-04-01'),
    ('nifty-capital-goods', 'Nifty Capital Goods', 'sectors', 'NIFTY CAPITAL GOODS', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-capital-goods', '2005-04-01'),
    ('nifty-chemicals', 'Nifty Chemicals', 'sectors', 'NIFTY CHEMICALS', 'https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-chemicals', '2005-04-01'),
    ('nifty200-momentum-30', 'NIFTY200 MOMENTUM 30', 'style', 'NIFTY200MOMENTM30', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty200-momentum-30', '2005-04-01'),
    ('nifty200-value30', 'Nifty200 Value 30', 'style', 'NIFTY200 VALUE 30', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty200-value30', '2005-04-01'),
    ('nifty100-quality-30', 'Nifty100 Quality 30', 'style', 'NIFTY100 QUALTY30', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty100-quality-30', '2009-10-01'),
    ('nifty-100-low-volatility', 'Nifty100 Low Volatility 30', 'style', 'NIFTY100 LOWVOL30', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty-100-low-volatility', '2005-04-01'),
    ('nifty-alpha-50', 'Nifty Alpha 50', 'style', 'NIFTY ALPHA 50', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty-alpha-50', '2003-12-31'),
    ('nifty-alpha-low-volatility-30', 'NIFTY ALPHA LOW-VOLATILITY 30', 'style', 'NIFTY ALPHALOWVOL', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty-alpha-low-volatility-30', '2005-04-01'),
    ('nifty50-equal-weight', 'NIFTY50 Equal Weight', 'style', 'NIFTY50 EQL WGT', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty50-equal-weight', '1995-11-03'),
    ('nifty500-equal-weight', 'Nifty500 Equal Weight', 'style', 'NIFTY500 EW', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty500--equal--weight', '2005-04-01'),
    ('nifty-dividend-opportunities-50', 'Nifty Dividend Opportunities 50', 'style', 'NIFTY DIV OPPS 50', 'https://www.niftyindices.com/indices/equity/strategy-indices/nifty-dividend-opportunities-50', '2007-10-01'),
    ('nifty-infrastructure', 'Nifty Infrastructure', 'themes', 'NIFTY INFRA', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-infrastructure', '2004-01-01'),
    ('nifty-india-defence', 'Nifty India Defence', 'themes', 'NIFTY IND DEFENCE', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-india-defence', '2018-04-02'),
    ('nifty-india-manufacturing', 'Nifty India Manufacturing', 'themes', 'NIFTY INDIA MFG', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-india-manufacturing', '2005-04-01'),
    ('nifty-india-consumption', 'Nifty India Consumption', 'themes', 'NIFTY CONSUMPTION', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-india-consumption', '2006-01-02'),
    ('nifty-housing', 'Nifty Housing', 'themes', 'NIFTY HOUSING', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty--housing', '2005-04-01'),
    ('nifty-india-digital', 'Nifty India Digital', 'themes', 'NIFTY IND DIGITAL', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-india-digital', '2005-04-01'),
    ('nifty-capital-markets', 'Nifty Capital Markets', 'themes', 'NIFTY CAPITAL MKT', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-capital-markets', '2019-04-01'),
    ('nifty-pse', 'Nifty PSE', 'ownership', 'NIFTY PSE', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-pse', '2000-01-03'),
    ('nifty-mnc', 'Nifty MNC', 'ownership', 'NIFTY MNC', 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-mnc', '1995-01-02'),
]
INDICES = [dict(id=i, label=label, group=g, code=code, source_url=url,
                audit_history_start=start, currency='INR', return_method=RETURN_METHOD)
           for i, label, g, code, url, start in _UNIVERSE]
