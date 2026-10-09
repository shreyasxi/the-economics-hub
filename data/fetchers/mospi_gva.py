"""Discover official NAS history and quarterly releases; accept validated revisions.

Run: python -m data.fetchers.mospi_gva [--dry-run] [--db PATH]
Raw sources, previous observations and exact revision journals live beside the DB
in gva/. A changed base, hierarchy, units, workbook contract or official Sources
and Methods document requires review. Rendering remains offline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import logging
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote, urljoin, urlsplit
import html

from data.paths import archive_for_db
from data.fetchers.india_source_archive import read_connection, Archive

import openpyxl
import requests

from data.processors.india_db_manager import DB_PATH

CATALOGUE_URL = 'https://api.mospi.gov.in/api/esankhyiki/cms/golden-sheet/list'
DOWNLOAD_ROOT = 'https://api.mospi.gov.in/api/esankhyiki/file/download/'
PUBLICATIONS_ROOT = 'https://www.mospi.gov.in/api/publications-reports/'
PUBLICATIONS_URL = PUBLICATIONS_ROOT + 'get-web-publications-report-list'
CHAPTERS_URL = PUBLICATIONS_ROOT + 'get-web-chapter-data'
BASE_YEAR = '2022-23'
SECTORS = ('Primary Sector', 'Secondary Sector', 'Tertiary Sector')
LEVEL_KEYS = ('primary', 'secondary', 'tertiary', 'gva')
PP_TOLERANCE = 1e-8
LEVEL_TOLERANCE = 1e-6  # ₹ crore; Excel contains unrounded levels
# Strict production-side schema, including the published hierarchy.
LABELS = (
    '1. Primary Sector', '1.1 Agriculture, Livestock, Forestry & Fishing',
    '1.2. Mining & Quarrying', '2. Secondary Sector', '2.1. Manufacturing',
    '2.2. Electricity, Gas, Water Supply & Other Utility Services', '2.3. Construction',
    '3. Tertiary Sector',
    '3.1 Trade, Hotels, Transport, Communication & Services related to Broadcasting, Storage',
    '3.2 Financial, Real Estate, Ownership of dwelling, IT & Professional Services',
    '3.3 Public Administration, Defence & Other Services', 'GVA at Basic Prices',
)
BROAD_ROWS = (0, 3, 7, 11)
LOG = logging.getLogger(__name__)


def clean(value):
    return ' '.join(str(value or '').split())


def require(condition, message):
    if not condition:
        raise ValueError('MoSPI GVA: ' + message)


def number(value):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), f'missing/non-numeric observation: {value!r}')
    return float(value)


def fiscal_period(year, quarter):
    require(re.fullmatch(r'20\d{2}-\d{2}', str(year)) is not None, f'invalid FY {year!r}')
    y = int(year[:4])
    require(int(year[-2:]) == (y + 1) % 100 and y >= 2022, f'invalid/new-base FY {year}')
    require(quarter in (1, 2, 3, 4), f'invalid quarter {quarter}')
    # Calendar quarter-end, so Q4 is Jan–Mar of the following calendar year.
    return f'{y + (quarter == 4):04d}-{[6, 9, 12, 3][quarter-1]:02d}-' + ('31' if quarter in (3, 4) else '30')


def read_sheet(blob):
    book = openpyxl.load_workbook(BytesIO(blob), data_only=True, read_only=True)
    require(len(book.sheetnames) == 1, 'unexpected workbook sheets')
    try:
        return [list(row) for row in book.active.values]
    finally:
        book.close()


def sector_block(rows, col):
    starts = [i for i, row in enumerate(rows) if clean(row[col]) == LABELS[0]]
    require(starts, 'missing Primary Sector row')
    start = starts[0]
    block = rows[start:start + len(LABELS)]
    require(tuple(clean(row[col]) for row in block) == LABELS,
            'official sector hierarchy changed or required sector missing')
    return block


def observation(block, col, year, quarter, url, release):
    values = [number(row[col]) for row in block]
    require(all(v > 0 for v in values), 'non-positive GVA level')
    for total, children in ((0, (1, 2)), (3, (4, 5, 6)), (7, (8, 9, 10)), (11, (0, 3, 7))):
        require(abs(values[total] - sum(values[j] for j in children)) <= LEVEL_TOLERANCE,
                f'sector levels do not reconcile: FY{year} Q{quarter}')
    return dict(quarter=fiscal_period(year, quarter), fiscal_year=year, fiscal_quarter=quarter,
                **dict(zip(LEVEL_KEYS, (values[i] for i in BROAD_ROWS))),
                base_year=BASE_YEAR, unit='INR crore', source='MoSPI / NSO',
                source_url=url, release_date=release)


def parse_history(blob, url, release):
    rows = read_sheet(blob)
    require(clean(rows[1][0]) == ('Statement 8.18.1: QUARTERLY ESTIMATES OF GDP ALONG WITH '
            'EXPENDITURE COMPONENTS AT CONSTANT PRICES, 2022-23 Series'),
            'history title/base/methodology changed; review required')
    require(any(clean(v) == '(values in ₹ crore)' for v in rows[3]), 'history unit changed')
    require(clean(rows[4][0]) == 'Sector', 'history schema changed')
    # Annual NAS vintages may add complete fiscal years; do not pin their column count.
    columns = [i for i,v in enumerate(rows[6]) if clean(v)]
    require(columns == list(range(1, len(columns)+1)) and len(columns) >= 8
            and len(columns) % 4 == 0, 'history quarter schema changed')
    block = sector_block(rows, 0)
    result = []
    for col in columns:
        year = clean(rows[4][1 + ((col - 1) // 4) * 4])
        q = (col - 1) % 4 + 1
        require(clean(rows[6][col]) == f'Q{q}', 'history quarter header changed')
        result.append(observation(block, col, year, q, url, release))
    growth_headers = [i for i,row in enumerate(rows) if clean(row[0]) == 'Sector'
                      and clean(row[1]) == 'Percentage Change Over Previous Year']
    require(len(growth_headers) == 1, 'history growth schema changed')
    h = growth_headers[0]
    growth = sector_block(rows[h+4:], 0)
    for i,r in enumerate(result[4:]):
        col = i+1
        require(clean(rows[h+1][1+(i//4)*4]) == r['fiscal_year']
                and clean(rows[h+3][col]) == f"Q{r['fiscal_quarter']}", 'history growth alignment changed')
        for row,key in zip(BROAD_ROWS, LEVEL_KEYS):
            expected = 100 * (r[key] / result[i][key] - 1)
            require(abs(expected - number(growth[row][col])) <= PP_TOLERANCE, 'history YoY alignment failed')
    return calculate(result)


def parse_latest(blob, entry, url):
    rows = read_sheet(blob)
    title = clean(rows[2][0])
    match = re.fullmatch(r'Statement 1: Quarterly Estimates of GVA at Basic Prices for Q([1-4]), (20\d{2}-\d{2}) \(Constant Prices\)', title)
    require(match is not None, 'latest workbook title/schema changed')
    q, latest_year = int(match[1]), match[2]
    require(latest_year == entry['ref_period'], 'catalogue/workbook reference period mismatch')
    require([clean(x) for x in rows[3][1:6]] == ['Sector', 'Quarterly Levels', '', '', 'Percentage Change Over Previous Year'], 'latest headers changed')
    require(any('Values are (in ₹ Crore)' in clean(v) for row in rows for v in row), 'latest unit missing')
    block = sector_block(rows, 1)
    release = datetime.strptime(entry['release_date'], '%d %b %Y').date().isoformat()
    result = [observation(block, col, clean(rows[4][col]), q, url, release) for col in (2, 3, 4)]
    require([int(r['fiscal_year'][:4]) for r in result] == list(range(int(latest_year[:4])-2, int(latest_year[:4])+1)), 'latest years misaligned')
    for i in (1, 2):
        require(clean(rows[4][4+i]) == result[i]['fiscal_year'], 'growth year header mismatch')
        for row, key in zip(BROAD_ROWS, LEVEL_KEYS):
            expected = 100 * (result[i][key] / result[i-1][key] - 1)
            require(abs(expected - number(block[row][4+i])) <= PP_TOLERANCE, 'latest published growth does not match levels')
    return result


def calculate(records):
    records = sorted(records, key=lambda r: r['quarter'])
    by_period = {(r['fiscal_year'], r['fiscal_quarter']): r for r in records}
    require(len(by_period) == len(records), 'duplicate quarters')
    require(records and records[0]['quarter'] == '2022-06-30', 'missing base-year starting quarter')
    previous_id = None
    for r in records:
        y, q = int(r['fiscal_year'][:4]), r['fiscal_quarter']
        require(r['quarter'] == fiscal_period(r['fiscal_year'], q), 'quarter-end misaligned')
        period_id = y * 4 + q
        require(previous_id is None or period_id == previous_id + 1, 'missing quarter; interpolation prohibited')
        previous_id = period_id
        require(r['base_year'] == BASE_YEAR, 'mixed base years')
        require(r['unit'] == 'INR crore' and r['source'] == 'MoSPI / NSO', 'source/unit metadata changed')
        datetime.strptime(r['release_date'], '%Y-%m-%d')
        require(all(math.isfinite(r[k]) and r[k] > 0 for k in LEVEL_KEYS), 'invalid levels')
        require(abs(sum(r[k] for k in LEVEL_KEYS[:3]) - r['gva']) <= LEVEL_TOLERANCE, 'level reconciliation failed')
        prior = by_period.get((f'{y-1}-{y % 100:02d}', q))
        require(prior is not None or y == 2022, 'missing exact year-earlier quarter')
        r['comparison_quarter'] = prior['quarter'] if prior else None
        r['comparison_release_date'] = prior['release_date'] if prior else None
        r['headline_yoy'] = 100 * (r['gva'] / prior['gva'] - 1) if prior else None
        for key in LEVEL_KEYS[:3]:
            r[key + '_pp'] = 100 * (r[key] - prior[key]) / prior['gva'] if prior else None
        if prior:
            require(abs(sum(r[k+'_pp'] for k in LEVEL_KEYS[:3]) - r['headline_yoy']) <= PP_TOLERANCE,
                    'contributions do not reconcile to headline growth')
    return records


def combine(history, latest, previous=()):
    records = {r['quarter']: dict(r) for r in previous}
    records.update({r['quarter']: dict(r) for r in history})
    for row in latest:
        old = records.get(row['quarter'])
        if old:
            if row['release_date'] < old['release_date']:
                continue  # A newer full NAS vintage supersedes an older quarterly workbook.
            if row['release_date'] == old['release_date']:
                require(all(abs(old[k]-row[k]) <= LEVEL_TOLERANCE for k in LEVEL_KEYS),
                        'same-vintage official workbooks disagree; review required')
        records[row['quarter']] = dict(row)
    return calculate(list(records.values()))


def revisions(previous, records):
    old = {r['quarter']:r for r in previous}
    return [dict(quarter=r['quarter'], changes={k:dict(before=old[r['quarter']][k], after=r[k])
                 for k in LEVEL_KEYS if abs(old[r['quarter']][k]-r[k]) > LEVEL_TOLERANCE})
            for r in records if r['quarter'] in old and
            any(abs(old[r['quarter']][k]-r[k]) > LEVEL_TOLERANCE for k in LEVEL_KEYS)]


def derived_revisions(previous, records):
    old = {r['quarter']:r for r in previous}
    fields = ('headline_yoy','primary_pp','secondary_pp','tertiary_pp')
    result = []
    for r in records:
        if r['quarter'] not in old:
            continue
        changes = {}
        for key in fields:
            before, after = old[r['quarter']][key], r[key]
            if ((before is None) != (after is None) or
                    (before is not None and after is not None and abs(before-after) > PP_TOLERANCE)):
                changes[key] = dict(before=before, after=after)
        if changes:
            result.append(dict(quarter=r['quarter'],changes=changes))
    return result


SCHEMA = '''CREATE TABLE IF NOT EXISTS india_gva_quarterly (
 quarter TEXT PRIMARY KEY, fiscal_year TEXT NOT NULL, fiscal_quarter INTEGER NOT NULL,
 "primary" REAL NOT NULL, secondary REAL NOT NULL, tertiary REAL NOT NULL, gva REAL NOT NULL,
 primary_pp REAL, secondary_pp REAL, tertiary_pp REAL, headline_yoy REAL,
 comparison_quarter TEXT, comparison_release_date TEXT,
 base_year TEXT NOT NULL CHECK(base_year = '2022-23'), unit TEXT NOT NULL,
 source TEXT NOT NULL, source_url TEXT NOT NULL, release_date TEXT NOT NULL,
 fetched_at TEXT NOT NULL
)'''


def store(records, db=DB_PATH):
    records = calculate([dict(r) for r in records])  # validate before opening a write transaction
    fetched_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(SCHEMA)
        existing = {r[0] for r in conn.execute('SELECT quarter FROM india_gva_quarterly')}
        require(existing <= {r['quarter'] for r in records}, 'new fetch drops previously stored quarters')
        for r in records:
            r['fetched_at'] = fetched_at
            columns = list(r)
            sql = ('INSERT INTO india_gva_quarterly (' + ','.join('"'+c+'"' for c in columns) + ') VALUES ('
                   + ','.join('?' for _ in columns) + ') ON CONFLICT(quarter) DO UPDATE SET '
                   + ','.join(f'"{c}"=excluded."{c}"' for c in columns if c != 'quarter'))
            conn.execute(sql, [r[c] for c in columns])


def load(db=DB_PATH, check_status=True):
    """Offline, read-only; revalidate stored contributions before plotting."""
    manifest = None
    if check_status:
        import json
        from data.fetchers.india_source_archive import sha256
        root = archive_for_db(db, 'gva')
        if (root/'status.json').exists():
            require(json.loads((root/'status.json').read_text())['status'] == 'accepted',
                    'latest GVA update rejected/pending; review required')
        path = root/'current.json' if (root/'current.json').exists() else root/'bootstrap.json'
        if path.exists():
            manifest = json.loads(path.read_text())
            for source in manifest['sources']:
                require(sha256((root/source['raw']).read_bytes()) == source['sha256'], 'archived GVA checksum mismatch')
    with read_connection(db) as conn:
        conn.row_factory = sqlite3.Row
        records = [dict(r) for r in conn.execute('SELECT * FROM india_gva_quarterly ORDER BY quarter')]
    if manifest:
        accepted = {r['quarter']:r for r in manifest['records']}
        require(set(accepted) == {r['quarter'] for r in records}, 'stored GVA coverage differs from accepted source')
        for r in records:
            require(all(r[k] == v for k,v in accepted[r['quarter']].items() if k != 'fetched_at'),
                    'stored GVA differs from accepted source')
    expected = calculate([dict(r) for r in records])
    for original, checked in zip(records, expected):
        for k in ('headline_yoy', 'primary_pp', 'secondary_pp', 'tertiary_pp', 'comparison_quarter', 'comparison_release_date'):
            if checked[k] is None or isinstance(checked[k], str):
                require(original[k] == checked[k], f'stored {k} mismatch')
            else:
                require(original[k] is not None and math.isfinite(original[k]) and abs(original[k]-checked[k]) <= PP_TOLERANCE, f'stored {k} mismatch')
    return records


def methodology_fingerprint(blob):
    """Ignore PDF metadata/whitespace changes, but review changed methodology text."""
    import fitz
    from data.fetchers.india_source_archive import sha256
    require(blob.startswith(b'%PDF-'), 'official methodology is not a PDF; review required')
    with fitz.open(stream=blob, filetype='pdf') as book:
        text = clean(' '.join(page.get_text() for page in book))
    require(len(text) >= 100 and ('2022-23' in text or '2022–23' in text),
            'methodology text/base cannot be verified; review required')
    return sha256(text.encode('utf-8'))


def official_url(path):
    url = urljoin('https://www.mospi.gov.in/', path)
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname in ('www.mospi.gov.in', 'mospi.gov.in')
            and parsed.port in (None,443) and '..' not in parsed.path, 'untrusted official publication link')
    return url


def publication_pages(post, endpoint, **filters):
    rows = []
    page, total = 1, None
    while True:
        payload = post(endpoint, dict(lang='en', page_no=page, page_size=100,
                       sort_field='published_year' if endpoint == PUBLICATIONS_URL else 'id',
                       sort_order='DESC' if endpoint == PUBLICATIONS_URL else 'ASC',
                       data_source='web', **filters)).json()
        require(payload.get('status') == 'success' and isinstance(payload.get('data'), list),
                'publication catalogue schema changed')
        meta = payload.get('pagination', {})
        require(meta.get('currentPage') == page and type(meta.get('totalPages')) is int
                and 1 <= meta['totalPages'] <= 100 and type(meta.get('totalItems')) is int,
                'publication pagination changed')
        if total is None:
            total = (meta['totalPages'], meta['totalItems'])
        require(total == (meta['totalPages'], meta['totalItems']), 'publication listing changed mid-fetch')
        rows.extend(payload['data'])
        if page == total[0]:
            require(len(rows) == total[1], 'incomplete publication listing')
            return rows
        page += 1


def discover_history(post):
    publications = publication_pages(post, PUBLICATIONS_URL, search_term='National Accounts Statistics')
    def title(row):
        return clean(html.unescape(re.sub(r'<[^>]+>', '', row['title'])))
    candidates = [r for r in publications if r.get('is_active') is True
                  and re.fullmatch(r'National Accounts Statistics 20\d{2}', title(r))]
    require(candidates, 'no official historical NAS publication discovered')
    publication = max(candidates, key=lambda r: (r['published_year'], title(r)))
    release = datetime.strptime(publication['published_year'], '%Y-%m-%d').date().isoformat()
    chapters = publication_pages(post, CHAPTERS_URL, publication_id=publication['id'])
    statements = [r for c in chapters for r in [c]+c.get('sub_chapters', [])
                  if re.match(r'^Statement 8\.18\.1:', clean(r.get('sub_chapter_title', r.get('chapter_title'))))]
    require(len(statements) == 1, 'newest NAS quarterly history statement changed/missing; review required')
    statement = statements[0]
    require('constant prices' in statement['sub_chapter_title'].lower(), 'NAS history concept changed')
    files = [statement[k] for k in ('file_one','file_two','file_three') if statement.get(k)]
    require(len(files) == 1, 'ambiguous NAS history files')
    url = official_url(files[0]['path'])
    require(urlsplit(url).path.endswith('.xlsx'), 'NAS workbook format changed; review required')
    methods = [r for r in publications if r.get('is_active') is True
               and title(r) == 'Sources and Methods for Compilation of National Accounts Statistics']
    require(methods, 'official methodology publication missing; review required')
    method = max(methods, key=lambda r:r['published_year'])
    method_url = official_url(method['file_one']['path'])
    return dict(url=url, release=release, publication=publication, statement=statement,
                methodology_url=method_url, methodology_publication=method)


def discover_latest(get):
    entries = []
    page, totals = 1, None
    while True:
        payload = get(CATALOGUE_URL, params={'product':'NAS','page':page,'limit':100}).json()
        require(payload.get('statusCode') is True and isinstance(payload.get('data'), list), 'NAS catalogue response changed')
        meta = payload.get('meta_data', payload.get('metadata', {}))
        require(meta.get('page') == page and type(meta.get('totalPages')) is int
                and 1 <= meta['totalPages'] <= 100 and type(meta.get('totalRecords')) is int,
                'NAS catalogue pagination changed')
        if totals is None:
            totals = (meta['totalPages'], meta['totalRecords'])
        require(totals == (meta['totalPages'],meta['totalRecords']), 'NAS catalogue changed mid-fetch')
        entries.extend(payload['data'])
        if page == totals[0]:
            require(len(entries) == totals[1], 'incomplete NAS catalogue')
            break
        page += 1
    candidates = [e for e in entries if e['frequency'] == 'Quarterly'
                  and 'quarterly estimates of gdp' in e['table_name'].lower()
                  and 'constant prices' in e['table_name'].lower() and e['status'] == 'Active']
    require(candidates, 'no current quarterly constant-price release in catalogue')
    entry = max(candidates, key=lambda e:datetime.strptime(e['release_date'], '%d %b %Y'))
    require(re.search(r'(?<!\d)(2022-23|20122-23)\s+SERIES', entry['table_name'], re.I),
            'catalogue base/methodology changed; review required')
    require(entry['product'] == 'NAS' and entry['geography'] == 'All India', 'catalogue scope changed')
    path = entry['file_path'].lstrip('/') + entry['file_name']
    require(path.startswith('datacatalogue/NASdata/AEQE/') and path.endswith('.xlsx') and '..' not in path,
            'download path changed')
    return entry, DOWNLOAD_ROOT + quote(path, safe='/')


def fetch(dry_run=False, db=DB_PATH):
    from data.fetchers.mospi_http import get as verified_get
    previous = []
    if Path(db).exists():
        with read_connection(db) as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='india_gva_quarterly'").fetchone():
                previous = load(db, check_status=False)
    import json
    current_path = archive_for_db(db, 'gva')/'current.json'
    if not current_path.exists():
        current_path = archive_for_db(db, 'gva')/'bootstrap.json'
    previous_manifest = json.loads(current_path.read_text()) if current_path.exists() else None
    archive = None if dry_run else Archive(archive_for_db(db, 'gva'), previous)
    try:
        with requests.Session() as session:
            def retain(response, url, request, role):
                response.raise_for_status()
                if archive:
                    archive.retain(response.content, url, request, role)
                return response
            def get(url, **kwargs):
                return retain(verified_get(session, url, timeout=(15,90), **kwargs), url, kwargs.get('params'), 'official')
            def post(url, body):
                return retain(session.post(url, json=body, timeout=(15,90)), url, body, 'discovery')
            history = discover_history(post)
            methods = get(history['methodology_url']).content
            from data.fetchers.india_source_archive import sha256
            contract = dict(base_year=BASE_YEAR, methodology_text_sha256=methodology_fingerprint(methods),
                            hierarchy=list(LABELS), unit='INR crore', concept='GVA at Basic Prices / constant prices')
            if previous_manifest:
                require(previous_manifest.get('contract') == contract,
                        'base/schema/official methodology changed; review required')
                require(history['release'] >= previous_manifest['history_release'], 'NAS history vintage regressed')
            entry, url = discover_latest(get)
            records = combine(parse_history(get(history['url']).content, history['url'], history['release']),
                              parse_latest(get(url).content, entry, url), previous)
            require({r['quarter'] for r in previous} <= {r['quarter'] for r in records}, 'new fetch drops stored quarters')
            old = {r['quarter']:r for r in previous}
            require(all(r['quarter'] not in old or r['release_date'] >= old[r['quarter']]['release_date'] for r in records),
                    'official observation vintage regressed')
        changed = revisions(previous, records)
        derived = derived_revisions(previous, records)
        for change in changed:
            LOG.warning('Accepted official GVA revision %s: %s', change['quarter'], change['changes'])
        for change in derived:
            LOG.warning('Recalculated GVA growth/contributions %s: %s', change['quarter'], change['changes'])
        if not dry_run:
            store(records, db)
            archive.finish('accepted', contract=contract, history_release=history['release'],
                           history=history, revisions=changed, derived_revisions=derived, records=records)
        latest = records[-1]
        LOG.info('%s: %d quarters; %d revised; latest FY%s Q%d, %.6f%% YoY; release %s; base %s',
                 'Validated' if dry_run else 'Stored', len(records), len(changed), latest['fiscal_year'],
                 latest['fiscal_quarter'], latest['headline_yoy'], latest['release_date'], BASE_YEAR)
        return records
    except Exception as exc:
        if archive:
            archive.finish('rejected', error=str(exc))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--db', type=Path, default=DB_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    fetch(args.dry_run, args.db)


if __name__ == '__main__':
    main()
