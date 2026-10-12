"""ECB daily euro-area New CISS and its official additive contributions."""
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.paths import DATA_CACHE, PROJECT_ROOT

COMPONENTS = {
    'SS_FIN': 'Financial intermediaries',
    'SS_EMN': 'Equity markets',
    'SS_MMN': 'Money markets',
    'SS_BMN': 'Bond markets',
    'SS_FXN': 'Foreign exchange markets',
    'SS_CON': 'Cross-market correlation',
}
KEYS = {'SS_CIN': 'CISS.D.U2.Z0Z.4F.EC.SS_CIN.IDX',
        **{code: f'CISS.D.U2.Z0Z.4F.EC.{code}.CON' for code in COMPONENTS}}
URL = ('https://data-api.ecb.europa.eu/service/data/CISS/'
       'D.U2.Z0Z.4F.EC.SS_CIN+SS_FIN+SS_EMN+SS_MMN+SS_BMN+SS_FXN+SS_CON.IDX+CON')
PAGE = 'https://data.ecb.europa.eu/data/datasets/CISS'
STEM = '24_macro_euro_area_ciss'
DRIVERS_STEM = STEM + '_drivers'
# Six contributions and the aggregate each published to four decimal places:
# seven half-units of rounding, with a small floating-point allowance.
TOLERANCE = .000350001


def parse_source(raw, today=None):
    today = today or date.today()
    frame = pd.read_csv(io.BytesIO(raw))
    required = {'KEY', 'TIME_PERIOD', 'OBS_VALUE', 'TITLE', 'UNIT', 'UNIT_MULT', 'DECIMALS'}
    if not required.issubset(frame) or set(frame.KEY) != set(KEYS.values()):
        raise ValueError('CISS: expected exactly the seven euro-area New CISS series')
    series = {}
    for code, key in KEYS.items():
        rows = frame.loc[frame.KEY == key]
        if (not rows.TITLE.str.startswith('NEW CISS -').all()
                or not rows.UNIT.eq('PURE_NUMB').all()
                or not rows.UNIT_MULT.eq(0).all() or not rows.DECIMALS.eq(4).all()):
            raise ValueError(f'CISS: unexpected methodology or index units for {key}')
        dates = pd.to_datetime(rows.TIME_PERIOD, errors='raise')
        values = pd.to_numeric(rows.OBS_VALUE, errors='raise')
        if dates.isna().any() or dates.duplicated().any() or not np.isfinite(values).all():
            raise ValueError(f'CISS: duplicate dates or missing/non-finite observations in {key}')
        series[code] = pd.Series(values.to_numpy(), index=dates).sort_index()
    endpoints = {s.index[-1] for s in series.values()}
    if len(endpoints) != 1:
        raise ValueError('CISS: latest release endpoints differ; retry after publication completes')
    latest = endpoints.pop()
    if latest.date() > today or (today - latest.date()).days > 21:
        raise ValueError('CISS: future or stale daily observation')
    start = latest - pd.DateOffset(years=15)
    aggregate = series['SS_CIN']
    if aggregate.index[0] > start or len(aggregate.loc[start:]) < 3500:
        raise ValueError('CISS: insufficient 15-year daily history')
    aligned = pd.concat(series, axis=1).loc[start:]
    common = aligned.dropna()
    if common.empty or common.index[-1] != latest:
        raise ValueError('CISS: no complete latest common observation')
    residual = common[list(COMPONENTS)].sum(axis=1) - common.SS_CIN
    if residual.abs().max() > TOLERANCE:
        raise ValueError(f'CISS: contributions do not reconcile ({residual.abs().max():.10f})')
    # A month must have ended on the calendar and be covered through its final
    # weekday. This also admits month-end releases before the next month's data.
    calendar_end = pd.Timestamp(today).to_period('M') - 1
    covered_end = (latest + pd.offsets.BDay(1)).to_period('M') - 1
    months = pd.period_range(end=min(calendar_end, covered_end), periods=12, freq='M')
    # Average all seven published series over the identical intersection of dates.
    daily = common.loc[months[0].start_time:months[-1].end_time]
    grouped = daily.groupby(daily.index.to_period('M'))
    monthly = grouped.mean().reindex(months)
    counts = grouped.size().reindex(months)
    if monthly.isna().any().any():
        raise ValueError('CISS: missing completed month in the 12-month decomposition')
    monthly_residual = monthly[list(COMPONENTS)].sum(axis=1) - monthly.SS_CIN
    if monthly_residual.abs().max() > TOLERANCE:
        raise ValueError('CISS: monthly contributions do not reconcile')
    available = aligned.loc[months[0].start_time:months[-1].end_time]
    available_counts = available.groupby(available.index.to_period('M')).size().reindex(months)
    history = aggregate.loc[start:]
    return {'source_url': PAGE, 'series_keys': KEYS, 'as_of': today.isoformat(),
            'window_start': start.date().isoformat(), 'latest_observation': latest.date().isoformat(),
            'units': 'CISS index units',
            'reconciliation': {'latest': float(residual.iloc[-1]),
                               'max_abs': float(residual.abs().max()), 'tolerance': TOLERANCE,
                               'observations': len(common)},
            'latest': {code: float(s.loc[latest]) for code, s in series.items()},
            'monthly': {
                'method': 'Arithmetic means over identical valid daily dates; no interpolation',
                'latest_month': str(months[-1]),
                'reconciliation': {'latest': float(monthly_residual.iloc[-1]),
                                   'max_abs': float(monthly_residual.abs().max()), 'tolerance': TOLERANCE},
                'rows': [{'month': str(month), 'observations': int(counts.loc[month]),
                          'excluded_dates': int(available_counts.loc[month] - counts.loc[month]),
                          **{code: float(row[code]) for code in KEYS}}
                         for month, row in monthly.iterrows()]},
            'rows': [{'date': d.date().isoformat(), 'CISS': float(v)} for d, v in history.items()]}


def generate(output_dir, raw=None, today=None):
    from charts.world_charts.ciss import draw, draw_drivers
    today = today or date.today()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        supplied = raw is not None
        params = {'startPeriod': (pd.Timestamp(today) - pd.DateOffset(years=16)).date().isoformat(),
                  'format': 'csvdata'}
        if raw is None:
            from data.processors.world_snapshot import _get
            raw = _get(URL, params).content
        report = parse_source(raw, today)
        digest = hashlib.sha256(raw).hexdigest()
        cache = DATA_CACHE / 'ciss'
        cache.mkdir(parents=True, exist_ok=True)
        (cache / (digest + '.csv')).write_bytes(raw)
        report['retrieval'] = {'url': URL, 'params': None if supplied else params, 'sha256': digest,
                               'supplied_bytes': supplied,
                               'validated_at': datetime.now(timezone.utc).isoformat()}
        draw(report, output_dir / (STEM + '.png'))
        draw_drivers(report, output_dir / (DRIVERS_STEM + '.png'))
        (output_dir / (STEM + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        return report
    except Exception:
        for stem in (STEM, DRIVERS_STEM):
            for extension in ('png', 'json'):
                (output_dir / (stem + '.' + extension)).unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    report = generate(PROJECT_ROOT / 'output' / 'macro' / date.today().strftime('%Y-%m'))
    print('New CISS:', report['latest_observation'], report['latest'], report['reconciliation'])
