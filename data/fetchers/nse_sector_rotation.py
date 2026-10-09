"""India's benchmarked rotation: one official, date-validated NSE price snapshot."""
from datetime import datetime, timezone, timedelta
import math
import argparse
import json
from pathlib import Path

from data.fetchers.mospi_cpi import atomic_json
from data.processors.cpi_contributions import sha

from data.fetchers.india_fetcher import fetch_nifty_sector_changes, _NSE_ALL_INDICES_URL

INDICES = {
    "NIFTY 50": "NIFTY 50",
    "NIFTY BANK": "Bank Nifty", "NIFTY IT": "IT", "NIFTY AUTO": "Auto",
    "NIFTY FMCG": "FMCG", "NIFTY PHARMA": "Pharma", "NIFTY METAL": "Metal",
    "NIFTY REALTY": "Realty", "NIFTY ENERGY": "Energy",
    "NIFTY PSU BANK": "PSU Bank", "NIFTY INFRASTRUCTURE": "Infra",
}
from data.paths import NSE_ROTATION_DIR

ROOT = NSE_ROTATION_DIR


def today_ist():
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()


def validate_snapshot(changes, snapshot):
    """Retain the weekly helper's price-return formula and require all eleven rows.

    allIndices supplies the current snapshot timestamp. previousDay describes
    the previous-close reference, which can precede the snapshot date during
    trading. Require consistent references without treating them as as-of dates.
    """
    timestamp = datetime.strptime(snapshot['timestamp'], '%d-%b-%Y %H:%M')
    observed = timestamp.date()
    today = today_ist()
    if observed > today:
        raise ValueError('NSE snapshot is future-dated')
    if (today-observed).days > 7:
        raise ValueError('NSE snapshot is stale by more than seven calendar days')
    reference = snapshot['dates']['oneYearAgo']
    reference_date = datetime.strptime(reference, '%d-%b-%Y').date()
    if not 350 <= (observed - reference_date).days <= 380:
        raise ValueError('NSE one-year reference date is invalid')
    selected = {}
    for row in snapshot['data']:
        name = row.get('index')
        if name in INDICES:
            if name in selected:
                raise ValueError(f'Duplicate NSE index: {name}')
            selected[name] = row
    rows = []
    previous_close_date = None
    for name, label in INDICES.items():
        if name not in selected or name not in changes:
            raise ValueError(f'Missing required NSE index: {name}')
        raw, change = selected[name], changes[name]
        previous_day = datetime.strptime(raw['previousDay'], '%d-%b-%Y').date()
        if previous_day > observed:
            raise ValueError(f'Future NSE previous-close date: {name}')
        if previous_close_date is None:
            previous_close_date = previous_day
        elif previous_day != previous_close_date:
            raise ValueError(f'Mixed NSE previous-close date: {name}')
        if raw['date365dAgo'] != reference:
            raise ValueError(f'Mixed NSE one-year reference date: {name}')
        for key in ('last', 'year_ago'):
            if not math.isfinite(change[key]) or change[key] <= 0:
                raise ValueError(f'Invalid NSE price level: {name} {key}')
        value = change['change_pct_1y']
        if not math.isfinite(value):
            raise ValueError(f'Invalid NSE price return: {name}')
        rows.append(dict(index=name, label=label, return_pct=value,
                         last=change['last'], year_ago=change['year_ago'],
                         observation_date=observed.isoformat(),
                         year_ago_date=reference_date.isoformat()))
    rows = rows[:1] + sorted(rows[1:], key=lambda r: -r['return_pct'])
    return rows, dict(source_url=_NSE_ALL_INDICES_URL, timestamp=snapshot['timestamp'],
                      observation_date=observed.isoformat(),
                      previous_close_date=previous_close_date.isoformat(),
                      year_ago_date=reference_date.isoformat(),
                      methodology='round((last / oneYearAgoVal - 1) * 100, 2)',
                      return_type='price; dividends excluded')


def fetch_rotation_data():
    changes, snapshot = fetch_nifty_sector_changes(list(INDICES), include_snapshot=True)
    return validate_snapshot(changes, snapshot)


def update(root=ROOT):
    root = Path(root)
    atomic_json(root/'status.json',dict(status='running'))
    try:
        changes,snapshot=fetch_nifty_sector_changes(list(INDICES),include_snapshot=True)
        rows,meta=validate_snapshot(changes,snapshot)
        blob=json.dumps(dict(changes=changes,snapshot=snapshot),sort_keys=True).encode()
        checksum=sha(blob)
        raw=root/'raw'/f'{checksum}.json'
        raw.parent.mkdir(parents=True,exist_ok=True)
        if not raw.exists(): raw.write_bytes(blob)
        atomic_json(root/'current.json',dict(rows=rows,metadata=meta,sha256=checksum))
        atomic_json(root/'status.json',dict(status='ready',sha256=checksum,
                    checked_date=datetime.now(timezone.utc).date().isoformat()))
        return rows,meta
    except Exception as exc:
        atomic_json(root/'status.json',dict(status='failed',error=str(exc)))
        raise


def load_rotation_data(root=ROOT):
    root=Path(root)
    status=json.loads((root/'status.json').read_text())
    if status['status']!='ready' or status['checked_date']!=datetime.now(timezone.utc).date().isoformat():
        raise ValueError('No successful rotation refresh today; stale data not substituted')
    current=json.loads((root/'current.json').read_text())
    blob=(root/'raw'/f"{status['sha256']}.json").read_bytes()
    if sha(blob)!=status['sha256'] or current['sha256']!=status['sha256']:
        raise ValueError('Rotation checksum mismatch')
    raw=json.loads(blob)
    rows,meta=validate_snapshot(raw['changes'],raw['snapshot'])
    if rows!=current['rows'] or meta!=current['metadata']:
        raise ValueError('Rotation normalized snapshot mismatch')
    return rows,meta


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    try:
        _,meta=update(args.root)
        print('NSE rotation ready:',meta['timestamp'])
    except Exception as exc:
        parser.exit(1,f'NSE ROTATION FAILED: {exc}\n')
