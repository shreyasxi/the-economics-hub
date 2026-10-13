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


# Same basket as the existing weekly commodity-breadth research chart.
COMMODITY_BASKET = {
    'BZ=F': 'Brent', 'CL=F': 'WTI', 'NG=F': 'Natural gas',
    'GC=F': 'Gold', 'SI=F': 'Silver', 'PL=F': 'Platinum', 'HG=F': 'Copper',
    'ZW=F': 'Wheat', 'ZC=F': 'Corn', 'ZS=F': 'Soybeans',
    'KC=F': 'Coffee', 'SB=F': 'Sugar', 'CC=F': 'Cocoa',
}


def prepare_commodities(histories, as_of):
    """Dated price changes and breadth; observed futures closes, no interpolation."""
    end = pd.Timestamp(as_of).normalize()
    baseline = end - pd.DateOffset(months=1)
    members, missing = [], {}
    for ticker, label in COMMODITY_BASKET.items():
        try:
            raw = pd.to_numeric(histories[ticker], errors='coerce').dropna().copy()
            raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
            raw = raw.sort_index().loc[:end]
            if raw.index.has_duplicates or (raw <= 0).any():
                raise ValueError('Duplicate dates or non-positive prices')
            level, observation = observed(raw, end)
            averages = raw.rolling(200, min_periods=200).mean().dropna()
            average, _ = observed(averages, end)
            old_level, old_date = observed(raw, baseline)
            old_average, _ = observed(averages, baseline)
            members.append(dict(ticker=ticker, label=label, observation=observation,
                                above_200d=level > average, previous_above_200d=old_level > old_average,
                                previous_observation=old_date))
        except (ValueError, TypeError, KeyError) as exc:
            missing[ticker] = str(exc)
    prices = prepare({key: histories[ticker] for key, ticker in
                      [('brent','BZ=F'),('copper','HG=F'),('gold','GC=F')] if ticker in histories}, as_of)
    return dict(as_of=as_of, rows=prices['rows'], members=members, missing=missing,
                methodology='13-futures research basket; matched current/prior-month members above their own '
                            '200-session average; at least 12 valid members. Observations within four calendar days; '
                            'no interpolation. Three-month/one-month futures price changes; Brent price pressure; WTI near–six-month curve for prompt tightness.',
                sources={ticker:dict(source='Yahoo Finance', series=ticker) for ticker in COMMODITY_BASKET})


def fetch_commodities(as_of):
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    yahoo = YFinanceFetcher()
    histories = {}
    for ticker in COMMODITY_BASKET:
        histories[ticker] = yahoo.get_close_series(ticker, period='2y')
        print(f'Commodity {ticker}: {len(histories[ticker])} observations', flush=True)
    result = prepare_commodities(histories, as_of)
    result['oil_curve'] = fetch_oil_curve(as_of)
    return result


def oil_curve_contracts(as_of):
    """Next delivery month and six months beyond it; exact NYMEX contracts."""
    end = pd.Timestamp(as_of)
    near = end.to_period('M') + 1
    far = near + 6
    codes = 'FGHJKMNQUVXZ'
    return [dict(maturity=str(month), ticker=f"CL{codes[month.month-1]}{str(month.year)[-2:]}.NYM")
            for month in (near, far)]


def prepare_oil_curve(histories, as_of):
    """Compare identical contracts on common observed dates at both cutoffs."""
    specs = oil_curve_contracts(as_of)
    end = pd.Timestamp(as_of).normalize()
    series = {}
    try:
        for spec in specs:
            raw = pd.to_numeric(histories[spec['ticker']], errors='coerce').dropna().copy()
            raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
            raw = raw.sort_index().loc[:end]
            if raw.index.has_duplicates or (raw <= 0).any():
                raise ValueError('Invalid contract prices or duplicate dates')
            series[spec['ticker']] = raw
        common = pd.concat(series, axis=1).dropna()
        now = common.loc[:end]
        old_cutoff = end - pd.DateOffset(months=1)
        old = common.loc[:old_cutoff]
        if now.empty or old.empty or (end-now.index[-1]).days > 4 or (old_cutoff-old.index[-1]).days > 4:
            raise ValueError('Current/prior-month common-date contract coverage is unavailable')
        near, far = (s['ticker'] for s in specs)
        spread = float(now.iloc[-1][near] - now.iloc[-1][far])
        previous = float(old.iloc[-1][near] - old.iloc[-1][far])
        state = 'Backwardation' if spread > .25 else 'Contango' if spread < -.25 else 'Flat'
        return dict(as_of=as_of, benchmark='WTI', contracts=specs, observation=now.index[-1].date().isoformat(),
                    comparison_date=old.index[-1].date().isoformat(), near_price=float(now.iloc[-1][near]),
                    far_price=float(now.iloc[-1][far]), spread=spread, previous_spread=previous,
                    change=spread-previous, state=state, source='Yahoo Finance / NYMEX monthly contracts',
                    methodology='Near-month minus six-month-deferred WTI; same contracts and common observed dates '
                                'at current/prior-month cutoffs, within four calendar days; ±$0.25/bbl = flat. '
                                'A prompt premium is consistent with near-term tightness, not proof of its cause.')
    except (KeyError, TypeError, ValueError) as exc:
        return dict(as_of=as_of, state='Unavailable', error=str(exc), contracts=specs)


def fetch_oil_curve(as_of):
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    yahoo = YFinanceFetcher()
    histories = {}
    for spec in oil_curve_contracts(as_of):
        ticker = spec['ticker']
        histories[ticker] = yahoo.get_close_series(ticker, period='3mo')
        print(f'Oil curve {ticker}: {len(histories[ticker])} observations', flush=True)
    return prepare_oil_curve(histories, as_of)
