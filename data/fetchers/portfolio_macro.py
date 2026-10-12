"""Offline FRED research preparation, reusing Monetaria's FredFetcher.

ICE credit history is source-limited to three years; never substitute a proxy.
All stores are private, immutable, hashed and activated only after validation.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import uuid
import numpy as np
import pandas as pd
from data.paths import PORTFOLIO_STORE_DIR

SERIES = {'DGS10': ('daily', 'percent yield', 14),
          'BAMLH0A0HYM2': ('daily', 'percent OAS', 14),
          'CPIAUCSL': ('monthly', 'seasonally adjusted index', 100),
          'CFNAIMA3': ('monthly', 'published three-month activity index', 100)}
ROOT = PORTFOLIO_STORE_DIR/'macro'


def validate_series(series, sid):
    if sid not in SERIES or not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError('Unsupported economic series/calendar.')
    if len(series) < 24 or series.index.hasnans or series.index.duplicated().any() or not series.index.is_monotonic_increasing:
        raise ValueError(sid + ': inadequate, duplicate or unordered observations')
    if series.index.tz is not None or not series.index.equals(series.index.normalize()) or not np.isfinite(series.to_numpy(dtype=float)).all():
        raise ValueError(sid + ': invalid dates or values')
    if sid in ('CPIAUCSL','BAMLH0A0HYM2') and (series <= 0).any():
        raise ValueError(sid + ': nonpositive level')
    if SERIES[sid][0] == 'monthly':
        periods = series.index.to_period('M')
        if periods.duplicated().any():
            raise ValueError(sid + ': duplicate months')
    elif series.index.to_series().diff().dt.days.max() > 7:
        raise ValueError(sid + ': material daily coverage gap')
    return series.astype(float)


def prepare(root=ROOT):
    from config.settings import FRED_API_KEY
    from data.fetchers.fred_fetcher import FredFetcher
    fetcher = FredFetcher(FRED_API_KEY)
    root = Path(root)
    bundle = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    bundle.mkdir(parents=True)
    manifest = {'schema':1, 'retrieved_utc':datetime.now(timezone.utc).isoformat(), 'series':{},
                'availability':'Ex-post latest revised observations. No release vintages; never an investable signal.',
                'credit_rights':'ICE internal use only; public distribution requires permission; three-year FRED coverage.'}
    for sid, (frequency, units, max_age) in SERIES.items():
        print('Preparing '+sid, flush=True)
        series = validate_series(fetcher.fetch_series(sid, period_years=40), sid)
        age = (pd.Timestamp.now().normalize()-series.index[-1]).days
        if age < 0 or age > max_age:
            raise ValueError(sid+': stale or future observations')
        path = bundle/(sid+'.csv')
        series.rename('value').to_csv(path, index_label='Date')
        manifest['series'][sid] = dict(frequency=frequency, units=units, max_age_days=max_age,
            first=str(series.index[0].date()), latest=str(series.index[-1].date()), observations=len(series),
            missing_months=[str(p) for p in pd.period_range(series.index[0].to_period('M'), series.index[-1].to_period('M'), freq='M').difference(series.index.to_period('M'))] if frequency=='monthly' else [],
            source_url='https://fred.stlouisfed.org/series/'+sid, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (bundle/'manifest.json').write_text(json.dumps(manifest, indent=2))
    load(bundle)
    pointer = root/('CURRENT-'+uuid.uuid4().hex+'.tmp'); pointer.write_text(bundle.name)
    os.replace(str(pointer), str(root/'CURRENT'))
    print('Validated macro snapshot: '+str(bundle), flush=True)
    return bundle


def current(root=ROOT):
    from portfolio_lab.deployment import active_root
    root = active_root(PORTFOLIO_STORE_DIR) / 'macro' if Path(root) == ROOT else Path(root)
    name = (root/'CURRENT').read_text().strip()
    if not name or Path(name).name != name or name in ('.','..'):
        raise ValueError('Invalid macro snapshot pointer')
    return root/name


def load(bundle):
    bundle = Path(bundle); manifest = json.loads((bundle/'manifest.json').read_text())
    if manifest.get('schema') != 1 or set(manifest.get('series',{})) != set(SERIES):
        raise ValueError('Invalid macro manifest')
    data = {}
    for sid, meta in manifest['series'].items():
        if meta.get('frequency')!=SERIES[sid][0] or meta.get('units')!=SERIES[sid][1]:
            raise ValueError('Macro frequency/unit mismatch: '+sid)
        path = bundle/(sid+'.csv')
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta['sha256']:
            raise ValueError('Macro checksum mismatch: '+sid)
        data[sid] = validate_series(pd.read_csv(path, index_col='Date', parse_dates=True)['value'],sid)
        s=data[sid]
        if str(s.index[0].date())!=meta['first'] or str(s.index[-1].date())!=meta['latest'] or len(s)!=meta['observations']:
            raise ValueError('Macro coverage mismatch: '+sid)
    return data, manifest

if __name__ == '__main__':
    prepare()
