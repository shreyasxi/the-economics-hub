"""Observed mixed return series. All percentage fields use percentage points.

No interpolation, padding, or synthetic common close. Yahoo max history is
requested; the peak is over every validated observation through the cutoff.
"""
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from config.market_matrix import (ASSETS, GROUPS, MAX_MISSING_SHARE, STALE_BUSINESS_DAYS,
                                  ADJUSTED_TOTAL_RETURN, OFFICIAL_TOTAL_RETURN,
                                  DIRECT_PRICE_RETURN, RETURN_METHODS)

SCHEMA_VERSION = 2


def validate_spec(spec):
    for field in ('id', 'label', 'group', 'source', 'source_url', 'instrument_or_index',
                  'ticker_or_series', 'return_method', 'currency'):
        if not spec.get(field):
            raise ValueError(f'missing source/methodology metadata: {field}')
    if spec['return_method'] not in RETURN_METHODS:
        raise ValueError('unknown return methodology')
    if spec['return_method'] == DIRECT_PRICE_RETURN and not spec.get('non_income_asset'):
        raise ValueError('direct price returns allowed only for documented non-income assets')
    if spec['id'] == 'nifty50_tri' and (spec['source'] != 'NSE Indices' or
                                      spec['return_method'] != OFFICIAL_TOTAL_RETURN or
                                      spec['ticker_or_series'] != 'NIFTY 50 TRI'):
        raise ValueError('Nifty row requires official NSE Nifty 50 TRI; no price-index substitution')
    if spec['id'] in ('dbc', 'uso', 'cper', 'dba') and (spec['return_method'] != ADJUSTED_TOTAL_RETURN or
                                      not spec.get('futures_roll_accounted') or
                                      not spec.get('methodology_url') or
                                      spec['ticker_or_series'] != spec['id'].upper()):
        raise ValueError('commodity investor return requires validated rolling-futures methodology')


def calculate(series, spec, cutoff):
    validate_spec(spec)
    if series.attrs.get('return_method') != spec['return_method']:
        raise ValueError('explicit matching return-method input required')
    s = series.copy()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    if s.index.has_duplicates:
        raise ValueError('duplicate observation dates')
    if s.index.hasnans or not s.index.is_monotonic_increasing:
        raise ValueError('observation dates must be valid and monotonic increasing')
    s = pd.to_numeric(s, errors='raise')
    s = s.loc[s.index <= pd.Timestamp(cutoff)]
    missing_count = int(s.isna().sum())
    s = s.dropna()  # blank Yahoo placeholder rows are not observations
    if not np.isfinite(s).all() or (s <= 0).any():
        raise ValueError('non-finite or non-positive return levels')
    if len(s) < 2:
        raise ValueError('series unresolved or insufficient valid observations')
    latest = s.index[-1]
    stale = ((pd.Timestamp(cutoff) - latest).days > 2 if spec['group'] == 'crypto' else
             np.busday_count(latest.date(), pd.Timestamp(cutoff).date()) > STALE_BUSINESS_DAYS)
    if stale:
        raise ValueError('stale instrument: latest close ' + str(latest.date()))
    required_years = spec.get('min_history_years', 5)
    if s.index[0] > latest - pd.DateOffset(years=required_years):
        raise ValueError(f'less than {required_years} years of validated history')
    anchors = {'1W': latest - pd.Timedelta(days=7), '1M': latest - pd.DateOffset(months=1),
               '3M': latest - pd.DateOffset(months=3), 'YTD': pd.Timestamp(latest.year-1, 12, 31),
               '1Y': latest - pd.DateOffset(years=1), '3Y': latest - pd.DateOffset(years=3),
               '5Y': latest - pd.DateOffset(years=5)}
    returns = {'1D': float((s.iloc[-1] / s.iloc[-2] - 1) * 100)}
    anchor_dates = {'1D': str(s.index[-2].date())}
    for key, target in anchors.items():
        base = s.loc[s.index <= target]
        # A distant pre-gap close is not a credible horizon anchor.
        if base.empty or (target - base.index[-1]).days > 7:
            returns[key], anchor_dates[key] = None, None
            continue
        ratio = s.iloc[-1] / base.iloc[-1]
        value = ratio ** (365.25 / (latest - base.index[-1]).days) - 1 if key in ('3Y', '5Y') else ratio - 1
        returns[key] = float(value * 100)
        anchor_dates[key] = str(base.index[-1].date())
    recent = s.loc[s.index >= latest - pd.Timedelta(weeks=52)]
    weekly = recent.groupby(recent.index.to_period('W-FRI')).tail(1)
    sparkline = [dict(date=str(d.date()), value=float(v / weekly.iloc[0] * 100)) for d, v in weekly.items()]
    cut = pd.Timestamp(cutoff)
    completed = cut.to_period('M') if cut.is_month_end else cut.to_period('M') - 1
    months = s.loc[s.index.to_period('M') <= completed]
    monthly = months.groupby(months.index.to_period('M')).tail(1)
    window = monthly.iloc[-10:]
    sufficient = (len(window) == 10 and window.index.to_period('M').equals(
        pd.period_range(completed-9, completed, freq='M')))
    sma = float(window.mean()) if sufficient else None
    distance = float((window.iloc[-1] / sma - 1) * 100) if sufficient else None
    state = ('uptrend' if distance > 0 else 'downtrend' if distance < 0 else 'at trend') if sufficient else 'insufficient data'
    return dict(spec, latest_date=str(latest.date()), latest_level=float(s.iloc[-1]),
                validation=dict(missing_observations_dropped=missing_count,
                                source_checks=series.attrs.get('source_checks', [])),
                history_start=str(s.index[0].date()), history_observations=len(s),
                returns=returns, anchor_dates=anchor_dates, off_high=float(min(0, (s.iloc[-1] / s.max()-1)*100)),
                high_date=str(s.idxmax().date()), trend_state=state,
                latest_month_end=str(monthly.index[-1].date()) if len(monthly) else None,
                sma_10m=sma, distance_from_sma_pct=distance, sparkline=sparkline)


def build(fetcher, cutoff, assets=ASSETS, nse_fetcher=None):
    rows, left_out = [], []
    for spec in assets:
        try:
            validate_spec(spec)
            if spec['return_method'] == OFFICIAL_TOTAL_RETURN:
                if nse_fetcher is None:
                    from data.fetchers.nse_tri import NiftyTRIFetcher
                    nse_fetcher = NiftyTRIFetcher()
                series = nse_fetcher.get_nifty50_tri(cutoff)
            elif spec['return_method'] == DIRECT_PRICE_RETURN:
                series = fetcher.get_price_return_series(spec['ticker_or_series'], period='max')
            else:
                series = fetcher.get_total_return_series(spec['ticker_or_series'], period='max')
            rows.append(calculate(series, spec, cutoff))
        except Exception as exc:
            left_out.append(dict(id=spec['id'], ticker_or_series=spec['ticker_or_series'],
                                 label=spec['label'], group=spec['group'], source=spec['source'],
                                 return_method=spec['return_method'], reason=str(exc)))
    if not assets or len(left_out) / len(assets) > MAX_MISSING_SHARE:
        raise ValueError('More than 20% unavailable; no matrix published: ' + repr(left_out))
    return dict(schema_version=SCHEMA_VERSION, generated_at=datetime.now(timezone.utc).isoformat(),
                as_of=str(pd.Timestamp(cutoff).date()), sources=sorted({r['source'] for r in rows}),
                methodology=dict(
                return_basis='Official total-return indices or dividend-adjusted investable proxies where available; non-income assets use direct underlying price returns.',
                adjustments='Yahoo proxies use explicit Adj Close (auto_adjust=False): distributions and splits adjusted; fund costs embedded, before investor taxes/trading costs. Bitcoin uses explicit unadjusted BTC/USD Close.',
                currency='All returns are in USD; no currency conversion.',
                horizons='Latest observed level / last level on or before calendar anchor - 1. 1D uses previous observation. Anchors more than seven days old are unavailable. 3Y/5Y annualised CAGR uses 365.25 / actual elapsed days.',
                trend_rule='Latest completed calendar month observed level versus 10 consecutive monthly observed levels; equality is at trend.',
                off_high_definition='Latest / highest level of the SAME return series in all available validated history through cutoff - 1; inception/history start differs by row.',
                stale_policy='Reject more than three weekday sessions behind cutoff (two calendar days for 7-day crypto); no forward filling. Each row has its actual latest date.',
                sparkline='Last actual observation per W-FRI week within trailing 52 weeks, rebased to 100.',
                heat_scale='Visual only: per-column 80th percentile absolute magnitude, floor 0.5 percentage points; pale saturation capped, numeric values never capped.'),
                summary=summarize(rows, len(assets)),
                groups=[dict(id=g, label=label, rows=[r for r in rows if r['group']==g]) for g,label in GROUPS], left_out=left_out)


def summarize(rows, configured_markets):
    """Summarise the included rows without recalculating any market observations."""
    valid = sorted((r for r in rows if r['returns']['1Y'] is not None), key=lambda r: (r['returns']['1Y'], r['id']))
    def leader(row):
        return dict(id=row['id'], label=row['label'], return_pct=row['returns']['1Y'], currency=row['currency'])
    breadth = []
    equity_groups = {'us_equities', 'us_sectors', 'developed_markets', 'emerging_markets'}
    for name, chosen in (('Equity', [r for r in rows if r['group'] in equity_groups]),
                         ('Fixed-income', [r for r in rows if r['group'] == 'fixed_income'])):
        if chosen:
            breadth.append(dict(label=name, valid_markets=len(chosen),
                                trend_valid_count=sum(r['sma_10m'] is not None for r in chosen),
                                uptrend_count=sum(r['trend_state']=='uptrend' for r in chosen)))
    return dict(configured_markets=configured_markets, valid_markets=len(rows),
                             uptrend_count=sum(r['trend_state']=='uptrend' for r in rows),
                             trend_valid_count=sum(r['sma_10m'] is not None for r in rows), valid_1y_count=len(valid),
                             best_1y=leader(valid[-1]) if len(valid)>=2 else None,
                             worst_1y=leader(valid[0]) if len(valid)>=2 else None, breadth=breadth)
