"""Observed three-month/one-month market inputs; fetch only during preparation."""
import math
import pandas as pd

EQUITIES = {'sp500':'S&P 500','stoxx50':'Euro Stoxx 50','ftse100':'FTSE 100',
            'nikkei':'Nikkei 225','hangseng':'Hang Seng','shanghai':'Shanghai Composite',
            'nifty50':'Nifty 50','korea':'MSCI Korea ETF (USD)','taiwan':'MSCI Taiwan ETF (USD)'}
CREDIT = {'us_ig':'US investment-grade','us_hy':'US high-yield','em_corp':'EM corporate'}
COMMODITIES = {'copper':'Copper','brent':'Oil (Brent)','gold':'Gold'}


def observed(series, anchor):
    values = series.loc[series.index <= anchor]
    if values.empty or (anchor - values.index[-1]).days > 4:
        raise ValueError(f'No observation within four days of {anchor.date()}')
    value = float(values.iloc[-1])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Invalid observed price/spread/volatility level')
    return value, values.index[-1].date().isoformat()


def prepare(histories, as_of):
    end = pd.Timestamp(as_of).normalize()
    anchors = {key:end - pd.DateOffset(months=months) for key,months in [('quarter',3),('month',1)]}
    rows, missing = {}, {}
    for key, raw in histories.items():
        try:
            series = pd.to_numeric(raw, errors='coerce').dropna().copy()
            series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
            series = series.sort_index().loc[:end]
            latest, observation = observed(series,end)
            row = dict(latest=latest, observation=observation)
            if key == 'vix':
                if len(series) < 292 or len(series.loc[end-pd.Timedelta(days=40):]) < 20:
                    raise ValueError('Insufficient current/one-year volatility history')
                median = float(series.iloc[-20:].median())
                # Compare smoothed levels with smoothed historical levels.
                medians = series.rolling(20,min_periods=20).median()
                prior_year = medians.iloc[-272:-20].dropna()
                rank = float((prior_year <= median).mean() * 100)
                old = medians.loc[:anchors['month']]
                previous, _ = observed(old,anchors['month'])
                row.update(median_20d=median, percentile=rank,
                           month_change_pct=(median/previous-1)*100)
            else:
                for horizon,anchor in anchors.items():
                    previous, when = observed(series,anchor)
                    if previous <= 0 or latest <= 0:
                        raise ValueError('Non-positive price/spread')
                    row[horizon] = (latest-previous)*100 if key in CREDIT else (latest/previous-1)*100
                    row[horizon+'_anchor'] = when
            rows[key] = row
        except (ValueError, TypeError, KeyError) as exc:
            missing[key] = str(exc)
    return dict(as_of=end.date().isoformat(),rows=rows,missing=missing,
                methodology='Calendar three-month/one-month observed closes, anchors within four days; '
                            'equity/commodity price changes in percent, spread changes in basis points. '
                            'VIX: 20-session median versus preceding 252 rolling medians. '
                            'No interpolation or supply/demand causal attribution.')


def fetch_inputs(as_of):
    from config.settings import FRED_API_KEY
    from config.signals_settings import SERIES
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    from data.fetchers.fred_fetcher import FredFetcher
    if not FRED_API_KEY:
        raise ValueError('FRED_API_KEY is required for credit-spread histories')
    yahoo, fred = YFinanceFetcher(), FredFetcher(api_key=FRED_API_KEY)
    specs = {r['id']:r for r in SERIES}
    histories = {}
    for key in list(EQUITIES) + list(CREDIT) + ['vix'] + list(COMMODITIES):
        spec = specs[key]
        if spec['source'] == 'fred':
            series = fred.fetch_series(spec['code'],period_years=2)
        else:
            series = yahoo.get_close_series(spec['code'],period='2y')
        histories[key] = series
        print(f'{key}: {len(series)} observations',flush=True)
    result = prepare(histories,as_of)
    result['sources'] = {key:dict(source=specs[key]['source'],series=specs[key]['code']) for key in histories}
    return result
