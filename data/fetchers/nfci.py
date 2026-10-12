"""Official NFCI contributions; never substitute the standardised subindices."""
import hashlib
import io
import json
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.paths import DATA_CACHE, PROJECT_ROOT

PAGE = 'https://www.chicagofed.org/research/data/nfci/current-data'
BASE = 'https://api.data.chicagofed.org/NFCI/'
FILES = {'workbook': 'contributions-data-series-xlsx.xlsx',
         'aggregate': 'nfci-decomposed-csv.csv', 'index': 'nfci-data-series-csv.csv'}
STEM = '23_macro_nfci'


def _dated(frame, label):
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index, errors='raise')
    if frame.index.isna().any() or frame.index.duplicated().any():
        raise ValueError(f'NFCI: invalid or duplicate dates in {label}')
    frame = frame.sort_index().apply(pd.to_numeric, errors='raise')
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError(f'NFCI: incomplete or non-finite values in {label}')
    if not (frame.index.dayofweek == 4).all():
        raise ValueError(f'NFCI: observations must be week-ending Fridays in {label}')
    return frame


def parse_sources(raw, today=None):
    """Group every published indicator once, retaining the published NFCI line."""
    today = today or date.today()
    book = pd.ExcelFile(io.BytesIO(raw['workbook']))
    key = pd.read_excel(book, sheet_name='Key')
    contributions = _dated(pd.read_excel(book, sheet_name='NFCI', index_col=0), 'workbook')
    aggregate = _dated(pd.read_csv(io.BytesIO(raw['aggregate']), index_col=0), 'aggregate')
    index = _dated(pd.read_csv(io.BytesIO(raw['index']), index_col=0), 'index')
    if list(aggregate.columns) != ['NFCI', 'Risk', 'Credit', 'Leverage'] or 'NFCI' not in index:
        raise ValueError('NFCI: official aggregate schema changed')
    if not contributions.index.equals(aggregate.index) or not index.index.equals(aggregate.index):
        raise ValueError('NFCI: source dates or release endpoints do not match')
    if (aggregate.NFCI - index.NFCI).abs().max() > .000500001:
        raise ValueError('NFCI: aggregate differs from official index beyond rounding tolerance')
    if not {'Mnemonic', 'Subindex'}.issubset(key.columns) or key.Mnemonic.duplicated().any():
        raise ValueError('NFCI: invalid indicator classification key')
    # Compound labels denote overlapping memberships, not extra contributions.
    # HH and NFC belong to Leverage and must each be counted exactly once.
    groups = {}
    for column in contributions.columns:
        match = key.loc[key.Mnemonic == column, 'Subindex']
        if len(match) != 1 or pd.isna(match.iloc[0]):
            raise ValueError(f'NFCI: missing classification for {column}')
        tokens = {s.strip() for s in match.iloc[0].split(';')}
        primary = tokens & {'Risk', 'Credit', 'Leverage'}
        if len(primary) != 1 or tokens - {'Risk', 'Credit', 'Leverage', 'Nonfinancial Leverage'}:
            raise ValueError(f'NFCI: unrecognised classification for {column}')
        groups[column] = primary.pop()
    counts = {group: list(groups.values()).count(group) for group in ('Risk', 'Credit', 'Leverage')}
    if not all(counts.values()):
        raise ValueError('NFCI: all three contribution groups are required')
    grouped = pd.DataFrame({group: contributions[[c for c in contributions if groups[c] == group]].sum(axis=1)
                            for group in counts})
    grouped['NFCI'] = aggregate.NFCI
    latest = grouped.index[-1]
    if latest.date() > today or (today - latest.date()).days > 21:
        raise ValueError('NFCI: future or stale weekly observation')
    window_start = latest - pd.DateOffset(years=5)
    frame = grouped.loc[window_start:]
    if len(frame) < 260 or contributions.index[0] > window_start:
        raise ValueError('NFCI: insufficient five-year weekly history')
    if not (frame.index.to_series().diff().dropna() == pd.Timedelta(days=7)).all():
        raise ValueError('NFCI: missing weekly observations')
    residual = frame[['Risk', 'Credit', 'Leverage']].sum(axis=1) - frame.NFCI
    change = residual.diff().dropna()
    maximum, max_change = float(residual.abs().max()), float(change.abs().max())
    if maximum > .001:
        raise ValueError(f'NFCI: reconciliation residual exceeds publication limit ({maximum:.6f})')
    notices = []
    if maximum > .0002 or max_change > .00005:
        notices.append(f'NFCI source reconciliation warning: max residual {maximum:.6f}; max weekly change {max_change:.6f}')
    return {'source_url': PAGE, 'as_of': today.isoformat(), 'window_start': window_start.date().isoformat(),
            'latest_observation': latest.date().isoformat(), 'units': 'Index units',
            'indicator_count': len(groups), 'group_counts': counts, 'warnings': notices,
            'reconciliation': {'mean': float(residual.mean()), 'std': float(residual.std()),
                               'min': float(residual.min()), 'max': float(residual.max()),
                               'max_abs': maximum, 'max_weekly_change': max_change,
                               'latest': float(residual.iloc[-1])},
            'rows': [{'date': d.date().isoformat(), **{c: float(v) for c, v in row.items()}}
                     for d, row in frame.iterrows()]}


def generate(output_dir, raw=None, today=None):
    from charts.world_charts.nfci import draw
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        metadata = {}
        if raw is None:
            from data.processors.world_snapshot import _get
            raw = {}
            for key, filename in FILES.items():
                response = _get(BASE + filename)
                raw[key] = response.content
                metadata[key] = {'last_modified': response.headers.get('Last-Modified'),
                                 'retrieved_at': datetime.now(timezone.utc).isoformat()}
            modified = [pd.Timestamp(m['last_modified']).date() for m in metadata.values() if m['last_modified']]
            if len(set(modified)) > 1:
                raise ValueError('NFCI: source release dates do not match; retry after publication completes')
        report = parse_sources(raw, today)
        cache = DATA_CACHE / 'nfci'
        cache.mkdir(parents=True, exist_ok=True)
        report['sources'] = {}
        for key, content in raw.items():
            digest = hashlib.sha256(content).hexdigest()
            suffix = '.xlsx' if key == 'workbook' else '.csv'
            (cache / (digest + suffix)).write_bytes(content)
            report['sources'][key] = {'url': BASE + FILES[key], 'sha256': digest, **metadata.get(key, {})}
        for notice in report['warnings']:
            warnings.warn(notice, RuntimeWarning)
        draw(report, output_dir / (STEM + '.png'))
        (output_dir / (STEM + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        return report
    except Exception:
        for extension in ('png', 'json'):
            (output_dir / (STEM + '.' + extension)).unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    report = generate(PROJECT_ROOT / 'output' / 'macro' / date.today().strftime('%Y-%m'))
    print('NFCI latest:', report['rows'][-1], report['reconciliation'])
