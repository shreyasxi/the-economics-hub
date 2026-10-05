"""India's benchmarked rotation: one official, date-validated NSE price snapshot."""
from datetime import datetime, timezone, timedelta
import math

from data.fetchers.india_fetcher import fetch_nifty_sector_changes, _NSE_ALL_INDICES_URL

INDICES = {
    "NIFTY 50": "NIFTY 50",
    "NIFTY BANK": "Bank Nifty", "NIFTY IT": "IT", "NIFTY AUTO": "Auto",
    "NIFTY FMCG": "FMCG", "NIFTY PHARMA": "Pharma", "NIFTY METAL": "Metal",
    "NIFTY REALTY": "Realty", "NIFTY ENERGY": "Energy",
    "NIFTY PSU BANK": "PSU Bank", "NIFTY INFRASTRUCTURE": "Infra",
}


def validate_snapshot(changes, snapshot):
    """Retain the weekly helper's price-return formula and require all eleven rows.

    allIndices supplies one current timestamp for its snapshot. The published
    daily reference date on each row must agree too; an intraday/unfinalized or
    mixed-date snapshot is omitted rather than substituting earlier prices.
    """
    timestamp = datetime.strptime(snapshot['timestamp'], '%d-%b-%Y %H:%M')
    observed = timestamp.date()
    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    if observed > today:
        raise ValueError('NSE snapshot is future-dated')
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
    for name, label in INDICES.items():
        if name not in selected or name not in changes:
            raise ValueError(f'Missing required NSE index: {name}')
        raw, change = selected[name], changes[name]
        if datetime.strptime(raw['previousDay'], '%d-%b-%Y').date() != observed:
            raise ValueError(f'Mixed/unfinalized NSE observation date: {name}')
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
                      year_ago_date=reference_date.isoformat(),
                      methodology='round((last / oneYearAgoVal - 1) * 100, 2)',
                      return_type='price; dividends excluded')


def load_rotation_data():
    changes, snapshot = fetch_nifty_sector_changes(list(INDICES), include_snapshot=True)
    return validate_snapshot(changes, snapshot)
