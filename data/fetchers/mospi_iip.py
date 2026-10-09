"""Canonical MoSPI General monthly IIP, published YoY growth, base 2022-23.

python -m data.fetchers.mospi_iip [--dry-run] [--db PATH]
Full current-base history replaces the active legacy projection; legacy values
are archived, never spliced. --iip entries are separately labelled emergency
values, rendered only with IIP_MANUAL_FALLBACK=true.
"""
import argparse
import calendar
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import sqlite3

import requests
from data.paths import archive_for_db
from data.processors.india_db_manager import DB_PATH, _SCHEMA
from data.fetchers.india_source_archive import read_connection, Archive, sha256
from data.fetchers.mospi_http import get
from data.fetchers.mospi_iip_audit import validate

BASE_YEAR = '2022-23'
URL = 'https://api.mospi.gov.in/api/iip/getIIPData'
LOG = logging.getLogger(__name__)
SCHEMA = '''CREATE TABLE IF NOT EXISTS india_iip_monthly (
 month TEXT PRIMARY KEY, growth_rate REAL NOT NULL CHECK(growth_rate BETWEEN -30 AND 30),
 index_level REAL NOT NULL CHECK(index_level > 0), base_year TEXT NOT NULL CHECK(base_year='2022-23'),
 concept TEXT NOT NULL CHECK(concept='General'), source_url TEXT NOT NULL,
 raw_sha256 TEXT NOT NULL, run_id TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS india_iip_legacy_archive (
 month TEXT PRIMARY KEY, growth_rate REAL, source_flags TEXT, fetched_at TEXT,
 archived_at TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS india_iip_manual (
 month TEXT PRIMARY KEY, growth_rate REAL NOT NULL CHECK(growth_rate BETWEEN -30 AND 30),
 base_year TEXT NOT NULL CHECK(base_year='2022-23'), concept TEXT NOT NULL CHECK(concept='General'),
 source TEXT NOT NULL, entered_at TEXT NOT NULL
);'''


def require(condition, message):
    if not condition:
        raise ValueError('MoSPI IIP: ' + message)


def validate_history(rows):
    # Shared concept/schema/finite/range checks; no legacy-overlap agreement gate.
    rates = validate(rows, BASE_YEAR)
    periods = sorted(rates)
    ids = []
    current = datetime.now(timezone.utc).strftime('%Y-%m')
    for r in rows:
        require(type(r['index']) is str and type(r['growth_rate']) is str, 'numeric field schema changed')
        require(2022 <= r['year'] <= int(current[:4]), 'invalid observation year')
    for month in periods:
        require('2022-04' <= month < current, 'invalid/future observation month')
        year, m = map(int, month.split('-'))
        ids.append(year*12+m)
    require(ids == list(range(ids[0], ids[-1]+1)), 'missing month; interpolation prohibited')
    return rates


def previous_records(db):
    if not Path(db).exists():
        return []
    with read_connection(db) as conn:
        conn.row_factory = sqlite3.Row
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='india_iip_monthly'").fetchone():
            return []
        return [dict(r) for r in conn.execute('SELECT * FROM india_iip_monthly ORDER BY month')]


def store(rows, sources, archive, db):
    rates = validate_history(rows)
    old = {r['month']:r for r in previous_records(db)}
    require(set(old) <= set(rates), 'new source drops stored official months')
    changes = [dict(month=m, before=old[m]['growth_rate'], after=float(v))
               for m,v in sorted(rates.items()) if m in old and abs(float(v)-old[m]['growth_rate']) > 1e-10]
    fetched = archive.manifest['fetched_at']
    with sqlite3.connect(db) as conn:
        conn.executescript(_SCHEMA + SCHEMA)
        legacy = conn.execute('SELECT month,india_iip_yoy,source_flags,fetched_at FROM india_monthly WHERE india_iip_yoy IS NOT NULL').fetchall()
        for m,value,flags,stamp in legacy:
            if m not in old:
                conn.execute('INSERT OR IGNORE INTO india_iip_legacy_archive VALUES (?,?,?,?,?,?)',
                             (m,value,flags,stamp,fetched,'Canonical migration; old series/base unverified, excluded from active chart'))
        for row in rows:
            m = f"{row['year']}-{list(calendar.month_name).index(row['month']):02d}"
            conn.execute('INSERT INTO india_iip_monthly VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(month) DO UPDATE SET '
                         'growth_rate=excluded.growth_rate,index_level=excluded.index_level,base_year=excluded.base_year,'
                         'concept=excluded.concept,source_url=excluded.source_url,raw_sha256=excluded.raw_sha256,'
                         'run_id=excluded.run_id,fetched_at=excluded.fetched_at',
                         (m,float(rates[m]),float(row['index']),BASE_YEAR,'General',URL,sources[m]['sha256'],archive.run_id,fetched))
        # Clear only legacy IIP values; all other observations/provenance remain intact.
        for m,value,flags,stamp in legacy:
            if m not in rates:
                parsed = json.loads(flags or '{}')
                parsed.pop('india_iip_yoy',None)
                conn.execute('UPDATE india_monthly SET india_iip_yoy=NULL, source_flags=? WHERE month=?',
                             (json.dumps(parsed),m))
        for m,v in rates.items():
            prior = conn.execute('SELECT source_flags FROM india_monthly WHERE month=?',(m,)).fetchone()
            flags = json.loads(prior[0] or '{}') if prior else {}
            flags['india_iip_yoy'] = f'mospi:General:base={BASE_YEAR}:run={archive.run_id}'
            conn.execute('INSERT INTO india_monthly (month,india_iip_yoy,source_flags) VALUES (?,?,?) '
                         'ON CONFLICT(month) DO UPDATE SET india_iip_yoy=excluded.india_iip_yoy,source_flags=excluded.source_flags',
                         (m,float(v),json.dumps(flags)))
    return changes


def fetch(dry_run=False, db=DB_PATH):
    previous = previous_records(db)
    archive = None if dry_run else Archive(archive_for_db(db, 'IIP'), previous)
    try:
        rows, sources = [], {}
        page, totals = 1, None
        with requests.Session() as session:
            while True:
                params = dict(frequency='Monthly',base_year=BASE_YEAR,type='General',limit=100,page=page,Format='JSON')
                response = get(session,URL,params=params,timeout=(15,90))
                response.raise_for_status()
                source = archive.retain(response.content,URL,params,'General IIP published growth') if archive else {'sha256':sha256(response.content)}
                payload = response.json()
                require(payload.get('statusCode') is True and isinstance(payload.get('data'),list), 'API response schema changed')
                meta = payload.get('meta_data',payload.get('metadata',{}))
                require(meta.get('page') == page and type(meta.get('totalPages')) is int
                        and 1 <= meta['totalPages'] <= 100 and type(meta.get('totalRecords')) is int,
                        'pagination schema changed')
                if totals is None:
                    totals = (meta['totalPages'],meta['totalRecords'])
                require(totals == (meta['totalPages'],meta['totalRecords']), 'API changed during pagination')
                validate(payload['data'],BASE_YEAR)
                rows.extend(payload['data'])
                for r in payload['data']:
                    m = f"{r['year']}-{list(calendar.month_name).index(r['month']):02d}"
                    sources[m] = source
                if page == totals[0]:
                    require(len(rows) == totals[1], 'incomplete official history')
                    break
                page += 1
        rates = validate_history(rows)
        require({r['month'] for r in previous} <= set(rates), 'new source drops stored official months')
        if not dry_run:
            changes = store(rows,sources,archive,db)
            archive.finish('accepted',base_year=BASE_YEAR,concept='General',measure='published growth_rate (% YoY)',
                           earliest=min(rates),latest=max(rates),count=len(rates),revisions=changes)
            for change in changes:
                LOG.warning('Accepted official IIP revision: %s', change)
        LOG.info('%s %d official General IIP months, base %s: %s–%s; latest %.1f%% YoY',
                 'Validated' if dry_run else 'Stored',len(rates),BASE_YEAR,min(rates),max(rates),rates[max(rates)])
        return rates
    except Exception as exc:
        if archive:
            archive.finish('rejected',error=str(exc))
        raise


def load(db=DB_PATH, manual_fallback=False):
    """Offline canonical chart data; emergency overlay requires explicit opt-in."""
    root = archive_for_db(db, 'IIP')
    state = root/'status.json'
    if not manual_fallback:
        require(state.exists() and json.loads(state.read_text())['status'] == 'accepted',
                'latest official update not accepted; emergency fallback requires explicit opt-in')
    records = previous_records(db)
    if manual_fallback:
        with read_connection(db) as conn:
            conn.row_factory = sqlite3.Row
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='india_iip_manual'").fetchone()
            manual = [dict(r) for r in conn.execute('SELECT * FROM india_iip_manual ORDER BY month')] if exists else []
        require(manual, 'explicit emergency fallback requested but no labelled manual IIP values')
        overlay = {r['month']:r for r in records}
        for r in manual:
            require(r['base_year'] == BASE_YEAR and r['concept'] == 'General'
                    and math.isfinite(r['growth_rate']) and -30 <= r['growth_rate'] <= 30, 'invalid manual fallback')
            overlay[r['month']] = r
        records = [overlay[m] for m in sorted(overlay)]
    else:
        require(records, 'official IIP history missing')
        current = json.loads((root/'current.json').read_text())
        require(len(records) == current['count'] and records[0]['month'] == current['earliest']
                and records[-1]['month'] == current['latest'], 'stored coverage differs from accepted source')
        blobs = {s['sha256']:s for s in current['sources']}
        for checksum,source in blobs.items():
            require(sha256((root/source['raw']).read_bytes()) == checksum, 'stored official raw checksum mismatch')
        for r in records:
            require(r['run_id'] == current['run_id'] and r['raw_sha256'] in blobs
                    and r['base_year'] == BASE_YEAR and r['concept'] == 'General', 'stored provenance mismatch')
        raw_rows = [r for source in current['sources'] for r in json.loads((root/source['raw']).read_bytes())['data']]
        rates = validate_history(raw_rows)
        require(all(r['growth_rate'] == float(rates[r['month']]) for r in records), 'stored published growth differs from raw source')
        levels = {f"{r['year']}-{list(calendar.month_name).index(r['month']):02d}":float(r['index']) for r in raw_rows}
        require(all(r['index_level'] == levels[r['month']] and r['source_url'] == URL for r in records), 'stored index/source metadata differs from raw source')
    return records


def enter_manual(conn, month, value):
    require('2022-04' <= month and math.isfinite(value) and -30 <= value <= 30, 'invalid current-base emergency value')
    conn.executescript(SCHEMA)
    official = conn.execute('SELECT growth_rate FROM india_iip_monthly WHERE month=?',(month,)).fetchone()
    if official and abs(official[0]-value) > 1e-10:
        LOG.warning('CONFLICT: emergency IIP %s %.2f vs official %.2f; official value preserved',month,value,official[0])
    conn.execute('INSERT INTO india_iip_manual VALUES (?,?,?,?,?,?) ON CONFLICT(month) DO UPDATE SET '
                 'growth_rate=excluded.growth_rate,source=excluded.source,entered_at=excluded.entered_at',
                 (month,value,BASE_YEAR,'General','manual:mospi:emergency',datetime.now(timezone.utc).isoformat()))
    print(f'  IIP {month}: stored separately as emergency General / base {BASE_YEAR}; '
          'activate chart with IIP_MANUAL_FALLBACK=true. Official data preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--db',type=Path,default=DB_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s: %(message)s')
    fetch(args.dry_run,args.db)


if __name__ == '__main__':
    main()
