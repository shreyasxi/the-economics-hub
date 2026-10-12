"""Curated candidates; only validated prepared instruments reach the UI."""
INDEX_IDS = ['nifty-50', 'nifty-next-50', 'nifty-midcap-150', 'niftysmallcap250']
ETFS = {
 'NIFTYBEES.NS': ('Nippon India ETF Nifty 50 BeES', 'Indian equities', 'INF204KB14I2'),
 'GOLDBEES.NS': ('Nippon India ETF Gold BeES', 'Domestic gold ETF', 'INF204KB17I5'),
 'GILT5YBEES.NS': ('Nippon India ETF Nifty 5yr Benchmark G-Sec', 'Medium sovereign bond ETF', 'INF204KC1030'),
 'LTGILTBEES.NS': ('Nippon India ETF Nifty 8–13yr G-Sec', 'Long sovereign bond ETF', 'INF204KB1882'),
 'LIQUIDCASE.NS': ('Zerodha Nifty 1D Rate Liquid ETF', 'Liquid ETF', 'INF0R8F01034'),
}
FOREIGN = ['SPY', 'EFA', 'EEM']
TEMPLATES = {
 'Indian equity benchmark': {'nifty-50': 1.},
 'Indian fund allocation': {'NIFTYBEES.NS': .6, 'GILT5YBEES.NS': .4},
 'India with gold': {'NIFTYBEES.NS': .5, 'GILT5YBEES.NS': .3, 'GOLDBEES.NS': .2},
 'India and international': {'NIFTYBEES.NS': .4, 'GILT5YBEES.NS': .3, 'GOLDBEES.NS': .1, 'SPY': .2},
}
EPISODES = {
 'Global Financial Crisis': ('2008-09-15', '2009-03-09'),
 'Taper tantrum / INR stress': ('2013-05-22', '2013-08-28'),
 'Demonetisation window': ('2016-11-08', '2016-12-30'),
 'Pandemic market shock': ('2020-02-19', '2020-04-30'),
 '2022 inflation and rate shock': ('2022-01-03', '2022-12-30'),
 'RBI tightening 2022–23': ('2022-05-04', '2023-02-15'),
}
