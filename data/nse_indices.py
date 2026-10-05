"""Offline, provenance-preserving import of official NSE Indices price CSV exports.

No network calls in chart drawing. Annual exports can be combined; conflicting
observations are rejected. A manifest is published only after both series validate.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent / 'nse_indices'
SOURCE = 'https://www.niftyindices.com/reports/historical-data'
NAMES = {'smallcap': 'NIFTY SMALLCAP 250', 'largecap': 'NIFTY 50'}
VERSION = 'smallcap250_nifty50_price_ratio_v1'
DAILY_SOURCE = 'https://nsearchives.nseindia.com/content/indices/ind_close_all_{date}.csv'


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def parse_export(payload, expected_name):
    """Parse the site's Date/Open/High/Low/Close CSV without inventing prices."""
    frame = pd.read_csv(io.BytesIO(payload), encoding='utf-8-sig')
    frame.columns = [re.sub(r'[^a-z0-9]', '', str(c).lower()) for c in frame.columns]
    if frame.columns.duplicated().any():
        raise ValueError('Duplicate CSV column names')
    if not {'indexname', 'date', 'open', 'high', 'low', 'close'}.issubset(frame.columns):
        raise ValueError('Expected NSE historical price-index OHLC export, not TRI or a quote')
    if 'indexname' in frame:
        names = frame.indexname.astype(str).str.strip().str.upper().unique()
        if list(names) != [expected_name]:
            raise ValueError(f'Wrong index: {names}; expected {expected_name}')
    dates = frame.date.astype(str).str.strip()
    parsed = pd.Series(pd.NaT, index=frame.index, dtype='datetime64[ns]')
    for fmt in ('%d %b %Y', '%d-%b-%Y', '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d'):
        candidate = pd.to_datetime(dates, format=fmt, errors='coerce')
        parsed = parsed.fillna(candidate)
    if parsed.isna().any() or parsed.duplicated().any():
        raise ValueError('Invalid or duplicate dates in export')
    prices = frame[['open', 'high', 'low', 'close']].apply(
        lambda s: pd.to_numeric(s.astype('string').str.strip()
                               .str.replace(',', '', regex=False).replace('-', pd.NA),
                               errors='raise'))
    prices = prices.astype(float)
    # Early official Smallcap 250 exports have closes but no O/H/L.
    # Closes are mandatory; optional O/H/L are validated wherever supplied.
    if (prices.close.isna().any() or np.isinf(prices.to_numpy()).any()
            or (prices <= 0).any().any()):
        raise ValueError('Missing, non-finite or non-positive index prices')
    if ((prices.high < prices[['open', 'close', 'low']].max(axis=1)) |
            (prices.low > prices[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Inconsistent index OHLC')
    if frame.empty:
        raise ValueError('Empty export')
    return pd.Series(prices.close.to_numpy(), index=pd.DatetimeIndex(parsed), name=expected_name).sort_index()


def combine_exports(series):
    combined = pd.concat(series).sort_index()
    if combined.groupby(level=0).nunique().gt(1).any():
        raise ValueError('Conflicting closes across overlapping exports; review source revisions')
    return combined[~combined.index.duplicated()]


def relative_performance(smallcap, largecap, start=None, end=None):
    for series in (smallcap, largecap):
        if series.index.has_duplicates or not isinstance(series.index, pd.DatetimeIndex):
            raise ValueError('Expected unique trading-date index')
        if not np.isfinite(series.to_numpy()).all() or (series <= 0).any():
            raise ValueError('Index levels must be finite and positive')
    # Inner join only. Never pad either leg to match the other's dates.
    panel = pd.concat([smallcap.rename('smallcap_close'), largecap.rename('nifty50_close')],
                      axis=1, join='inner').sort_index().loc[start:end]
    if len(panel) < 2:
        raise ValueError('At least two matching trading dates required')
    panel['ratio'] = panel.smallcap_close / panel.nifty50_close
    panel['relative_100'] = 100 * panel.ratio / panel.ratio.iloc[0]
    panel.index.name = 'date'
    return panel


def import_exports(smallcap_paths, largecap_paths, start, end, root=ROOT):
    root = Path(root)
    end_ts = pd.Timestamp(end)
    if end_ts > pd.Timestamp(datetime.now(timezone.utc).date()):
        raise ValueError('Cannot import a future cutoff')
    sources, series = [], {}
    for role, paths in [('smallcap', smallcap_paths), ('largecap', largecap_paths)]:
        parts = []
        for path in paths:
            payload = Path(path).read_bytes()
            part = parse_export(payload, NAMES[role])
            if part.index.max() > end_ts:
                raise ValueError('Export contains dates after requested cutoff')
            sha = digest(payload)
            relative_path = f'raw/{sha}.csv'
            (root / 'raw').mkdir(parents=True, exist_ok=True)
            (root / relative_path).write_bytes(payload)
            sources.append(dict(role=role, index=NAMES[role], path=relative_path, format='historical',
                                sha256=sha, source_url=SOURCE, original_filename=Path(path).name,
                                first_date=str(part.index.min().date()), last_date=str(part.index.max().date()),
                                rows=len(part), acquisition='official website CSV export; imported locally'))
            parts.append(part)
        series[role] = combine_exports(parts)
    return publish(root, sources, start, end)


def parse_daily(payload, expected_date):
    """Official all-index daily snapshot; select exact price-index identities."""
    frame = pd.read_csv(io.BytesIO(payload), encoding='utf-8-sig')
    frame.columns = frame.columns.str.strip()
    required = {'Index Name', 'Index Date', 'Closing Index Value'}
    if not required.issubset(frame.columns):
        raise ValueError('Not an NSE all-index daily closing report')
    result = {}
    for role, name in NAMES.items():
        selected = frame.loc[frame['Index Name'].str.strip().str.upper() == name]
        if len(selected) != 1:
            raise ValueError(f'Expected exactly one {name} row')
        date = pd.to_datetime(selected['Index Date'].iloc[0], format='%d-%m-%Y')
        if date != pd.Timestamp(expected_date):
            raise ValueError('Snapshot date does not match requested date')
        close = float(selected['Closing Index Value'].iloc[0])
        if not np.isfinite(close) or close <= 0:
            raise ValueError('Daily close must be finite and positive')
        result[role] = pd.Series([close], index=pd.DatetimeIndex([date]), name=name)
    return result


def read_sources(root, sources):
    series = {role: [] for role in NAMES}
    for entry in sources:
        payload = (Path(root) / entry['path']).read_bytes()
        if digest(payload) != entry['sha256']:
            raise ValueError('Raw NSE export checksum mismatch')
        if entry.get('format', 'historical') == 'historical':
            part = parse_export(payload, NAMES[entry['role']])
        elif entry['format'] == 'daily':
            part = parse_daily(payload, entry['date'])[entry['role']]
        else:
            raise ValueError('Unknown NSE source format')
        series[entry['role']].append(part)
    return {role: combine_exports(parts) for role, parts in series.items()}


def publish(root, sources, start, end, refresh=None):
    """Publish a complete manifest atomically only after every source validates."""
    root = Path(root)
    end_ts = pd.Timestamp(end)
    series = read_sources(root, sources)
    panel = relative_performance(series['smallcap'], series['largecap'], start, end)
    if panel.index[0] != pd.Timestamp(start):
        raise ValueError('Fixed rebasing date is missing from the inputs')
    payload = panel.to_csv(float_format='%.12g').encode()
    sha = digest(payload)
    derived = f'signals/{sha}.csv'
    (root / 'signals').mkdir(parents=True, exist_ok=True)
    (root / derived).write_bytes(payload)
    observed_union = series['smallcap'].index.union(series['largecap'].index)
    observed_union = observed_union[(observed_union >= pd.Timestamp(start)) & (observed_union <= end_ts)]
    omitted = observed_union.difference(panel.index)
    meta = dict(calculation_version=VERSION, source_url=SOURCE, index_variant='price return; excludes dividends',
                requested_start=start, requested_end=end, base_date=str(panel.index[0].date()),
                last_date=str(panel.index[-1].date()), matched_dates=len(panel),
                unmatched_dates=[str(d.date()) for d in omitted],
                imported_at=datetime.now(timezone.utc).isoformat(), sources=sources,
                refresh=refresh,
                signal_path=derived, signal_sha256=sha,
                calendar_note='Matched source dates; missing dates in both exports cannot be detected without a separate exchange calendar.')
    staging = root / 'manifest.pending.json'
    staging.write_text(json.dumps(meta, indent=2) + '\n')
    staging.replace(root / 'manifest.json')
    return panel, meta


def load_risk_appetite(root=ROOT):
    root = Path(root)
    meta = json.loads((root / 'manifest.json').read_text())
    if meta['calculation_version'] != VERSION:
        raise ValueError('Unsupported risk-appetite calculation version')
    sources = read_sources(root, meta['sources'])
    panel = relative_performance(*(sources[k] for k in NAMES),
                                 meta['requested_start'], meta['requested_end'])
    payload = (root / meta['signal_path']).read_bytes()
    if digest(payload) != meta['signal_sha256']:
        raise ValueError('Calculated signal checksum mismatch')
    saved = pd.read_csv(io.BytesIO(payload), index_col='date', parse_dates=True)
    pd.testing.assert_frame_equal(panel, saved, check_freq=False, check_dtype=False, rtol=1e-9, atol=1e-9)
    return panel, meta


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--smallcap', nargs='+', type=Path, required=True)
    p.add_argument('--nifty50', nargs='+', type=Path, required=True)
    p.add_argument('--start', required=True, help='YYYY-MM-DD; first common date is the base')
    p.add_argument('--end', required=True, help='YYYY-MM-DD')
    a = p.parse_args()
    panel, meta = import_exports(a.smallcap, a.nifty50, a.start, a.end)
    print(json.dumps({k: meta[k] for k in ('base_date', 'last_date', 'matched_dates', 'unmatched_dates')}, indent=2))
