"""Timestamp-preserving Coin Metrics data and explicit asynchronous valuation.

Reuse the repository's Community API endpoint, but retain UTC times rather
than the date-only MVRV chart transformation. PriceUSD daily labels denote the
UTC day; its closing fixing is conservatively effective at next midnight.
"""
import numpy as np
import pandas as pd
import requests
from data.fetchers.coinmetrics_fetcher import _URL

CONVENTION = 'ETF observed session close / BTC prior UTC-day end; valuation at 16:00 America/New_York'
DISCLOSURE = ('BTC uses the preceding UTC day’s closing PriceUSD fixing, available by the '
              '16:00 New York valuation checkpoint (20:00/21:00 UTC). ETF prices are observed '
              'exchange-session closes, including earlier holiday closes. This is asynchronous '
              'reference valuation, not simultaneous executable prices. Weekend BTC changes '
              'accumulate into the next ETF-session interval. No weekend portfolio marks: '
              'volatility uses 252 evaluation intervals and drawdown misses intrainterval/weekend '
              'extremes. Rebalances are hypothetical transfers at these reference marks, with '
              'fixed target weights and optional turnover costs; no claim of achievable BTC '
              'execution at the stale fixing. Custody, spreads, slippage and tax excluded. '
              'Historical revised data establish fixing-time alignment, not historical API '
              'publication latency or point-in-time data availability.')


def validate_bitcoin(frame):
    frame = frame.copy()
    if frame.empty or frame['time'].map(lambda value: pd.Timestamp(value).tzinfo is None).any():
        raise ValueError('BTC: explicit timezone-bearing source timestamps required')
    times = pd.to_datetime(frame['time'], utc=True, errors='raise')
    if times.isna().any() or times.duplicated().any() or not times.is_monotonic_increasing:
        raise ValueError('BTC: invalid, duplicate or unordered UTC timestamps')
    if not times.equals(times.dt.normalize()):
        raise ValueError('BTC: daily observations must be UTC midnight labels')
    if 'asset' in frame and not frame.asset.eq('btc').all():
        raise ValueError('BTC: wrong source asset')
    values = pd.to_numeric(frame.PriceUSD, errors='raise')
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('BTC: prices must be positive and finite')
    if not times.diff().iloc[1:].eq(pd.Timedelta(days=1)).all():
        raise ValueError('BTC: missing daily fixing; weekends must be retained')
    frame['time'] = times
    frame['PriceUSD'] = values
    frame['fixing_utc'] = times + pd.Timedelta(days=1)
    return frame


def fetch_bitcoin():
    rows, url = [], _URL
    params = dict(assets='btc', metrics='PriceUSD', frequency='1d', page_size=10000)
    while url:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        body = response.json()
        rows.extend(body.get('data', []))
        url, params = body.get('next_page_url'), None
        if url and not url.startswith(_URL + '?'):
            raise ValueError('BTC: unexpected pagination endpoint')
    if not rows:
        raise ValueError('BTC: no observations')
    frame = validate_bitcoin(pd.DataFrame(rows))
    frame = frame.loc[frame.fixing_utc <= pd.Timestamp.now(tz='UTC')]
    if frame.empty or (pd.Timestamp.now(tz='UTC') - frame.fixing_utc.iloc[-1]).days > 7:
        raise ValueError('BTC: stale or unfinished history')
    return frame


def align_bitcoin(frame, sessions):
    """Exact prior-day fixing, never unlimited forward filling or future joins.

    Calendar is SPY's observed sessions. Raw seven-day history is preserved in
    the bundle; the latest fixing <= checkpoint must also equal UTC midnight
    of that session date. A missing source fixing is an error, not carried.
    """
    frame = validate_bitcoin(frame)
    sessions = pd.DatetimeIndex(sessions)
    if sessions.tz is not None or not sessions.equals(sessions.normalize()) or sessions.duplicated().any():
        raise ValueError('BTC: expected unique timezone-free session dates')
    checkpoints = (sessions + pd.Timedelta(hours=16)).tz_localize('America/New_York').tz_convert('UTC')
    fixings = pd.DatetimeIndex(frame.fixing_utc)
    expected = sessions.tz_localize('UTC')
    indexed = pd.Series(frame.PriceUSD.to_numpy(), index=fixings)
    values = indexed.reindex(expected)
    covered = (expected >= fixings[0]) & (expected <= fixings[-1])
    if values.loc[covered].isna().any():
        raise ValueError('BTC: missing required fixing inside coverage')
    if (expected > checkpoints).any():
        raise ValueError('BTC: look-ahead fixing')
    evidence = pd.DataFrame({'valuation_utc': checkpoints, 'fixing_utc': expected,
                             'PriceUSD': values.to_numpy()}, index=sessions)
    return pd.Series(values.to_numpy(), index=sessions, name='BTC'), evidence
