"""Refresh official NSE price indices; no network access in chart rendering.

Run: python -m data.fetchers.nse_risk_appetite
One-time seed: add --bootstrap to import the supplied annual CSV exports.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data.nse_indices import (ROOT, NAMES, DAILY_SOURCE, digest, import_exports,
                              load_risk_appetite, parse_daily, publish)


def bootstrap(root=ROOT):
    """Never replace an existing validated store with the seed history."""
    root = Path(root)
    if (root / 'manifest.json').exists():
        return load_risk_appetite(root)
    data = Path(__file__).resolve().parents[1]
    small = sorted((data / 'NIFTY Small Cap 250').glob('*.csv'))
    large = sorted((data / 'NIFTY 50').glob('*.csv'))
    if not small or not large:
        raise ValueError('Missing seed exports; bootstrap requires both supplied folders')
    return import_exports(small, large, '2016-10-04',
                          datetime.now(timezone.utc).date().isoformat(), root)


def session():
    client = requests.Session()
    client.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept': 'text/csv,*/*'})
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    client.mount('https://', HTTPAdapter(max_retries=retry))
    return client


def refresh(root=ROOT, end=None, start=None, client=None):
    """Recheck 14 days and catch up from last valid close, including weekends.

    A 404 is recorded as an unavailable report, never labelled a holiday.
    Other HTTP errors, schema changes or conflicting closes abort publication.
    --start permits explicit rechecks of older unavailable reports.
    """
    root = Path(root)
    _, previous = load_risk_appetite(root)
    today_ist = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    end = pd.Timestamp(end or today_ist - timedelta(days=1)).normalize()
    if end.date() >= today_ist:
        raise ValueError('Only completed calendar days may be fetched')
    start = pd.Timestamp(start or (pd.Timestamp(previous['last_date']) - pd.Timedelta(days=14)))
    start = max(start, pd.Timestamp(previous['base_date']))
    if end < start:
        raise ValueError('End precedes requested start')
    if (end - start).days > 370:
        raise ValueError('Catch-up exceeds 370 days; use explicit smaller date windows')
    sources = list(previous['sources'])
    seen = {(s['role'], s['sha256']) for s in sources}
    client = client or session()
    audit = {'started_at': datetime.now(timezone.utc).isoformat(),
             'requested_start': str(start.date()), 'requested_end': str(end.date()),
             'received_dates': [], 'unavailable_dates': [], 'status': 'running'}
    try:
        for day in pd.date_range(start, end, freq='D'):
            url = DAILY_SOURCE.format(date=day.strftime('%d%m%Y'))
            response = client.get(url, timeout=(10, 25))
            if response.status_code == 404:
                audit['unavailable_dates'].append(str(day.date()))
                continue
            response.raise_for_status()
            payload = response.content
            parse_daily(payload, day)
            sha = digest(payload)
            relative = f'raw/{sha}.csv'
            (root / 'raw').mkdir(parents=True, exist_ok=True)
            (root / relative).write_bytes(payload)
            for role, name in NAMES.items():
                if (role, sha) not in seen:
                    sources.append(dict(role=role, index=name, path=relative,
                                        sha256=sha, source_url=url, format='daily',
                                        date=str(day.date()), rows=1,
                                        retrieved_at=datetime.now(timezone.utc).isoformat()))
                    seen.add((role, sha))
            audit['received_dates'].append(str(day.date()))
        if not audit['received_dates']:
            raise ValueError('No valid daily reports returned; previous manifest retained')
        audit['status'] = 'validated_with_unavailable_reports' if audit['unavailable_dates'] else 'validated'
        # Keep previously recorded missing reports until an explicit successful recheck.
        old_missing = set((previous.get('refresh') or {}).get('unresolved_report_dates', []))
        audit['unresolved_report_dates'] = sorted(
            (old_missing | set(audit['unavailable_dates'])) - set(audit['received_dates']))
        panel, meta = publish(root, sources, previous['base_date'],
                              max(previous['requested_end'], str(end.date())), audit)
        audit['last_source_date'] = meta['last_date']
        audit['matched_dates'] = len(panel)
        return panel, meta
    except Exception as exc:
        audit.update(status='failed_previous_manifest_retained', error=str(exc))
        raise
    finally:
        (root / 'runs').mkdir(parents=True, exist_ok=True)
        audit['finished_at'] = datetime.now(timezone.utc).isoformat()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (root / 'runs' / f'{stamp}.json').write_text(json.dumps(audit, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--seed-only', action='store_true')
    parser.add_argument('--start')
    parser.add_argument('--end')
    args = parser.parse_args()
    try:
        if args.bootstrap:
            bootstrap(args.root)
        if not args.seed_only:
            panel, meta = refresh(args.root, args.end, args.start)
        else:
            panel, meta = load_risk_appetite(args.root)
        print(f"NSE Risk Appetite: {len(panel)} dates; through {meta['last_date']}; "
              f"latest {panel.relative_100.iloc[-1]:.1f}")
        missing = (meta.get('refresh') or {}).get('unresolved_report_dates', [])
        if missing:
            print(f'WARNING: {len(missing)} unavailable report dates recorded (may include holidays/weekends).')
    except Exception as exc:
        print(f'NSE refresh failed; previous validated data retained: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
