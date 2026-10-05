"""Official CPI 2024 collector; render separately from validated local snapshots.

PYTHONPATH=. python -m data.fetchers.mospi_cpi --update
Use --backfill to explicitly refresh all history, --verify for offline checks,
or --file official.xlsx for an explicit, validated manual import.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import datetime, timezone
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import uuid

import openpyxl
import requests

from data import cpi_contributions as cpi
from data.fetchers import mospi_http

LOG = logging.getLogger(__name__)
FILTER_URL = 'https://api.mospi.gov.in/api/cpi/getCpiFilterByLevelAndBaseYear'
FILTERS = dict(base_year='2024', series='Current', state_code=1, sector_code=3)
PAGE_SIZE = 100


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def immutable(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as f:
            f.write(blob)
    except FileExistsError:
        cpi.require(path.read_bytes() == blob, f'immutable source collision: {path}')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(cpi.encoded(value))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Retrieval:
    def __init__(self, root, session):
        self.root, self.session = Path(root), session
        self.id = uuid.uuid4().hex
        self.started = utc_now()
        self.requests = []

    def capture(self, url, params, blob, http_status=200, kind='api'):
        checksum = cpi.sha(blob)
        immutable(self.root/'raw'/'blobs'/f'{checksum}.bin', blob)
        months = []
        try:
            payload = json.loads(blob) if kind != 'manual_workbook' else None
            records = payload.get('data', []) if isinstance(payload, dict) else payload
            if isinstance(records, list):
                months = sorted({cpi.period(dict(r,year=str(r['year']))) for r in records
                                 if isinstance(r, dict) and 'year' in r and 'month' in r})
        except (ValueError, TypeError, KeyError):
            pass  # Failed/schema-changing responses still retain their exact bytes.
        record = dict(url=url, query=params, retrieved_at_utc=utc_now(),
            sha256=checksum, http_status=http_status, kind=kind, observation_months=months)
        # Preserve query provenance immediately, even if the process is interrupted
        # before the final retrieval manifest can be sealed.
        immutable(self.root/'raw'/'request_records'/self.id/f'{len(self.requests)+1:04d}.json', cpi.encoded(record))
        self.requests.append(record)

    def get(self, url, params):
        response = mospi_http.get(self.session, url, params=params, timeout=45)
        self.capture(url, params, response.content, response.status_code)
        response.raise_for_status()
        return response.json()

    def seal(self, success, scope=None):
        manifest = dict(retrieval_id=self.id, started_at_utc=self.started,
            completed_at_utc=utc_now(), success=success, base_year='2024', series='Current',
            state_code=1, sector_code=3, requests=self.requests,
            request_record_count=len(self.requests),
            api_request_count=sum(r['kind']=='api' for r in self.requests),
            data_page_count=sum(r['url']==cpi.API_URL for r in self.requests),
            observation_months=sorted({m for r in self.requests for m in r['observation_months']}),
            status_note='API exposes no provisional/final or vintage field')
        if scope:
            manifest.update(scope)
            manifest['status_note'] = 'Official historical API snapshot; vintage/status retained in raw observations'
        path = self.root/'raw'/'retrievals'/f'{self.id}.json'
        immutable(path, cpi.encoded(manifest))
        return manifest


def fetch_pages(retrieval, filters):
    raw = []
    expected_total = expected_pages = None
    page = 1
    while True:
        params = dict(FILTERS, **filters, limit=PAGE_SIZE, page=page, Format='JSON')
        payload = retrieval.get(cpi.API_URL, params)
        cpi.require(isinstance(payload, dict) and payload.get('statusCode') is True,
                    'API returned unsuccessful data response')
        cpi.require(isinstance(payload.get('data'), list), 'API data schema changed')
        meta = payload.get('meta_data', {})
        total, pages = meta.get('totalRecords'), meta.get('totalPages')
        cpi.require(type(total) is int and type(pages) is int and total > 0 and
                    pages == (total+PAGE_SIZE-1)//PAGE_SIZE and meta.get('page') == page and
                    meta.get('recordPerPage') == PAGE_SIZE, 'pagination schema/limit changed')
        if expected_total is None:
            expected_total, expected_pages = total, pages
        cpi.require((total, pages) == (expected_total, expected_pages),
                    'dataset changed during pagination; retry complete retrieval')
        expected_count = min(PAGE_SIZE, total-(page-1)*PAGE_SIZE)
        cpi.require(len(payload['data']) == expected_count, 'truncated/incomplete API page')
        raw.extend(payload['data'])
        if page == pages:
            break
        if page % 20 == 0:
            LOG.info('CPI fetched %s / %s pages', page, pages)
        page += 1
    cpi.require(len(raw) == expected_total, 'incomplete API retrieval')
    return raw


def discover_latest(retrieval):
    payload = retrieval.get(FILTER_URL, dict(base_year='2024', level='Group', series_code='Current'))
    while isinstance(payload, list) or (isinstance(payload, dict) and 'state' not in payload):
        if isinstance(payload, list):
            cpi.require(len(payload)==1, 'metadata response changed')
            payload = payload[0]
        else:
            cpi.require('data' in payload, 'metadata response changed')
            payload = payload['data']
    cpi.require(any(r.get('state_code')==1 and r.get('state_name')=='All India' for r in payload['state']), 'All India metadata code changed')
    cpi.require(any(r.get('sector_code')==3 and r.get('sector_name')=='Combined' for r in payload['sector']), 'Combined metadata code changed')
    expected = {0:cpi.GENERAL, **{i:name for i, (_, name, _) in enumerate(cpi.DIVISIONS,1)}}
    cpi.require({r['division_code']:r['division_name'] for r in payload['division']} == expected, 'official division metadata changed')
    cpi.require({r['month_code']:r['month_name'] for r in payload['month']} ==
                {i:calendar.month_name[i] for i in range(1,13)}, 'month metadata changed')
    years = [int(r['year']) for r in payload['year'] if r.get('series')=='Current']
    cpi.require(years, 'no Current-series years')
    year = max(years)
    raw = fetch_pages(retrieval, dict(year=str(year), division_code='0'))
    general = [r for r in raw if set(r)==set(cpi.FIELDS) and
               all(r[k] is None for k in cpi.HIERARCHY) and r['division']==cpi.GENERAL]
    cpi.require(general and len({cpi.period(r) for r in general})==len(general), 'invalid latest-month discovery')
    for r in general:
        cpi.require(all(r[k]==v for k,v in [('base_year','2024'),('series','Current'),
                    ('state','All India'),('sector','Combined'),('year',str(year))]), 'discovery scope changed')
        cpi.numeric(r['index'])
    return max(cpi.period(r) for r in general)


def import_workbook(path, retrieval):
    blob = Path(path).read_bytes()
    retrieval.capture(Path(path).resolve().as_uri(), {}, blob, kind='manual_workbook')
    book = openpyxl.load_workbook(BytesIO(blob), read_only=True, data_only=True)
    try:
        cpi.require(book.sheetnames == ['CPI Data'], 'manual export sheet changed')
        values = iter(book.active.values)
        headers = next(values)
        cpi.require(tuple(headers)==cpi.FIELDS, 'manual export schema changed')
        raw = [dict(zip(headers, row)) for row in values if any(v is not None for v in row)]
    finally:
        book.close()
    retrieval.capture(Path(path).resolve().as_uri(), {}, cpi.encoded(raw), kind='manual')
    return cpi.select_aggregates(raw)


def store(root, rows, derived, retrieval, previous, mode):
    root = Path(root)
    run_id = uuid.uuid4().hex
    run = root/'runs'/run_id
    old = {(cpi.period(r),r['division']):r for r in previous}
    revisions = []
    for row in rows:
        key = cpi.period(row), row['division']
        if key in old:
            changes = {k:dict(before=old[key][k], after=row[k]) for k in cpi.FIELDS if old[key][k]!=row[k]}
            if changes:
                revisions.append(dict(month=key[0], division=key[1], changes=changes,
                    previous_source_retrieval=old[key]['source_retrieval'], source_retrieval=row['source_retrieval']))
                LOG.warning('CPI REVISION %s / %s: %s', *key, changes)
    files = {'normalized.json':rows, 'derived.json':derived,
             'weights.json':cpi.configuration(), 'revisions.json':revisions}
    checksums = {}
    for name, content in files.items():
        blob = cpi.encoded(content)
        immutable(run/name, blob)
        checksums[name] = cpi.sha(blob)
    source_ids = {r['source_retrieval'] for r in rows}
    manifest = dict(run_id=run_id, created_at_utc=utc_now(), mode=mode, latest_month=derived[-1]['month'],
        normalized_row_count=len(rows), contribution_month_count=len(derived),
        source_retrieval=retrieval['retrieval_id'], api_request_count=retrieval['api_request_count'],
        data_page_count=retrieval['data_page_count'], revision_count=len(revisions), checksums=checksums,
        source_manifest_checksums={rid:cpi.sha((root/'raw'/'retrievals'/f'{rid}.json').read_bytes()) for rid in source_ids})
    immutable(run/'manifest.json', cpi.encoded(manifest))
    atomic_json(root/'current.json', dict(run_id=run_id, manifest_sha256=cpi.sha(cpi.encoded(manifest))))
    atomic_json(root/'last_attempt.json', dict(status='success', run_id=run_id,
        source_retrieval=retrieval['retrieval_id'], completed_at_utc=utc_now(), latest_month=derived[-1]['month']))
    return manifest


def update(root=cpi.ROOT, backfill=False, file=None, session=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root/'.update.lock'
    # A competing updater does not invalidate another update's readiness.
    with lock.open('x') as f:
        f.write(str(os.getpid()))
    own_session = session is None
    session = session or requests.Session()
    retrieval = Retrieval(root, session)
    sealed = False
    try:
        atomic_json(root/'last_attempt.json', dict(status='running', source_retrieval=retrieval.id, started_at_utc=utc_now()))
        previous = cpi.load_current(root, ready=False)[0] if (root/'current.json').exists() else []
        if file:
            rows = import_workbook(file, retrieval)
            latest = max(cpi.period(r) for r in rows)
            mode = 'explicit_manual_import'
        else:
            latest = discover_latest(retrieval)
            cpi.require(latest <= datetime.now(timezone.utc).strftime('%Y-%m'), 'future source month')
            cpi.require(not previous or latest >= max(cpi.period(r) for r in previous), 'source latest month regressed')
            if backfill or not previous:
                years = ','.join(str(y) for y in range(2025,int(latest[:4])+1))
                raw = fetch_pages(retrieval, dict(year=years, division_code=','.join(map(str,range(13)))))
                rows = cpi.select_aggregates(raw, cpi.months_between('2025-01',latest))
                mode = 'backfill'
            else:
                existing = {cpi.period(r) for r in previous}
                targets = sorted({latest,cpi.previous_month(latest)} | (set(cpi.months_between('2025-01',latest))-existing))
                refreshed = []
                for target in targets:
                    raw = fetch_pages(retrieval, dict(year=target[:4], month_code=int(target[5:]), division_code=','.join(map(str,range(13)))))
                    refreshed.extend(cpi.select_aggregates(raw,[target]))
                rows = [r for r in previous if cpi.period(r) not in targets]+refreshed
                mode = 'incremental'
        for row in rows:
            row.setdefault('source_retrieval', retrieval.id)
        rows = sorted(rows, key=lambda r:(cpi.period(r),r['code'] or '00'))
        derived = cpi.calculate(rows)
        source = retrieval.seal(True)
        sealed = True
        manifest = store(root, rows, derived, source, previous, mode)
        LOG.info('CPI READY through %s: %s rows, %s API requests, %s revisions',
                 latest,len(rows),manifest['api_request_count'],manifest['revision_count'])
        LOG.info('Latest: headline=%s%%; contributions=%s pp; residual=%s pp; buckets=%s',
                 derived[-1]['published_headline'],derived[-1]['contribution_total'],
                 derived[-1]['residual_published'],derived[-1]['buckets'])
        return manifest
    except Exception as exc:
        if not sealed:
            retrieval.seal(False)
        atomic_json(root/'last_attempt.json', dict(status='failed', source_retrieval=retrieval.id,
            completed_at_utc=utc_now(), error=str(exc)))
        LOG.error('CPI UPDATE FAILED; contribution chart must be omitted: %s',exc)
        raise
    finally:
        if own_session:
            session.close()
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--update', action='store_true')
    modes.add_argument('--backfill', action='store_true')
    modes.add_argument('--verify', action='store_true')
    modes.add_argument('--file', type=Path)
    parser.add_argument('--root', type=Path, default=cpi.ROOT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        if args.verify:
            audit = cpi.verify_archive(args.root)
            LOG.info('CPI current and historical provenance/checksums/reconciliation verified: %s',audit)
        else:
            update(args.root,backfill=args.backfill,file=args.file)
    except (ValueError, OSError, requests.RequestException, KeyError, TypeError) as exc:
        parser.exit(1, f'CPI FAILED: {exc}\n')


if __name__ == '__main__':
    main()
