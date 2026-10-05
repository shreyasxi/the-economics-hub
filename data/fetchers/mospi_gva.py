"""Official 2022-23-base quarterly real GVA; fetch separately from rendering.

Run: python -m data.fetchers.mospi_gva [--dry-run] [--db PATH]

Sources discovered through the eSankhyiki NAS catalogue and the 31 Aug 2026
NSO release. NAS 2026 statement 8.18.1 is the revised Q1 FY2022-23–Q4
FY2025-26 history (NOT the superseded June estimates). Catalogue workbooks
use file/download/{file_path}/{file_name}; discover the newest release each run.
Reject inconsistent overlapping vintages rather than mixing unrevised history
with a new revision. A new historical revision requires reviewing the new NAS
statement and updating HISTORY_URL / HISTORY_RELEASE.
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
from urllib.parse import quote

import openpyxl
import requests

from data.india_db_manager import DB_PATH

CATALOGUE_URL = 'https://api.mospi.gov.in/api/esankhyiki/cms/golden-sheet/list'
DOWNLOAD_ROOT = 'https://api.mospi.gov.in/api/esankhyiki/file/download/'
HISTORY_URL = 'https://www.mospi.gov.in/uploads/publications_reports/NAS-2026-Statements/8.18.1.xlsx'
HISTORY_RELEASE = '2026-08-31'
RELEASE_URL = ('https://www.mospi.gov.in/uploads/latestreleasesfiles/'
               '1788174301107-Press%20Note%20on%20GDP%20Estimates%20for%20Q1%202026-27.pdf')
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
    return [list(row) for row in book.active.values]


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


def parse_history(blob):
    rows = read_sheet(blob)
    require(clean(rows[1][0]) == ('Statement 8.18.1: QUARTERLY ESTIMATES OF GDP ALONG WITH '
            'EXPENDITURE COMPONENTS AT CONSTANT PRICES, 2022-23 Series'), 'history title/base year changed')
    require(clean(rows[3][15]) == '(values in ₹ crore)', 'history unit changed')
    require(clean(rows[4][0]) == 'Sector' and len(rows[4]) == 17, 'history schema changed')
    block = sector_block(rows, 0)
    result = []
    for col in range(1, 17):
        year = clean(rows[4][1 + ((col - 1) // 4) * 4])
        q = (col - 1) % 4 + 1
        require(clean(rows[6][col]) == f'Q{q}', 'history quarter header changed')
        result.append(observation(block, col, year, q, HISTORY_URL, HISTORY_RELEASE))
    # Check independently published headline rates, not used to compute contributions.
    require(clean(rows[49][0]) == 'GVA at Basic Prices', 'history growth table changed')
    for i, r in enumerate(result[4:]):
        expected = 100 * (r['gva'] / result[i]['gva'] - 1)
        require(abs(expected - number(rows[49][i + 1])) <= PP_TOLERANCE, 'history YoY alignment failed')
    return result


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


def combine(history, latest):
    records = {r['quarter']: dict(r) for r in history}
    for row in latest:
        old = records.get(row['quarter'])
        if old:
            require(all(abs(old[k]-row[k]) <= LEVEL_TOLERANCE for k in LEVEL_KEYS),
                    'latest release revises historical levels; refresh the official historical statement before publishing')
        records[row['quarter']] = dict(row)
    return calculate(list(records.values()))


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


def load(db=DB_PATH):
    """Offline, read-only; revalidate stored contributions before plotting."""
    with sqlite3.connect(f'file:{Path(db).resolve()}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        records = [dict(r) for r in conn.execute('SELECT * FROM india_gva_quarterly ORDER BY quarter')]
    expected = calculate([dict(r) for r in records])
    for original, checked in zip(records, expected):
        for k in ('headline_yoy', 'primary_pp', 'secondary_pp', 'tertiary_pp', 'comparison_quarter', 'comparison_release_date'):
            if checked[k] is None or isinstance(checked[k], str):
                require(original[k] == checked[k], f'stored {k} mismatch')
            else:
                require(original[k] is not None and math.isfinite(original[k]) and abs(original[k]-checked[k]) <= PP_TOLERANCE, f'stored {k} mismatch')
    return records


def fetch(dry_run=False, db=DB_PATH):
    from data.fetchers.mospi_http import get as verified_get
    with requests.Session() as session:
        def get(url, **kwargs):
            response = verified_get(session, url, timeout=(15, 90), **kwargs)
            response.raise_for_status()
            return response
        # Newest catalogue records come first. Reject pagination uncertainty instead of
        # silently using an old quarterly release if the catalogue order changes.
        payload = get(CATALOGUE_URL, params={'product': 'NAS', 'page': 1, 'limit': 100}).json()
        require(payload.get('statusCode') is True and isinstance(payload.get('data'), list), 'catalogue response changed')
        candidates = [e for e in payload['data'] if e['frequency'] == 'Quarterly'
                      and 'quarterly estimates of gdp' in e['table_name'].lower()
                      and 'constant prices' in e['table_name'].lower()
                      and datetime.strptime(e['release_date'], '%d %b %Y').date().isoformat() >= HISTORY_RELEASE]
        require(candidates, 'no current quarterly constant-price release in catalogue')
        entry = max(candidates, key=lambda e: datetime.strptime(e['release_date'], '%d %b %Y'))
        # The August catalogue title has an official typo: "20122-23 SERIES".
        # Base year is independently verified in NAS statement 8.18.1 and release.
        require(re.search(r'(?<!\d)(2022-23|20122-23)\s+SERIES', entry['table_name'], re.I), 'catalogue base year changed')
        require(entry['product'] == 'NAS' and entry['geography'] == 'All India' and entry['status'] == 'Active', 'catalogue scope changed')
        path = entry['file_path'].lstrip('/') + entry['file_name']
        require(path.startswith('datacatalogue/NASdata/AEQE/') and path.endswith('.xlsx') and '..' not in path, 'download path changed')
        url = DOWNLOAD_ROOT + quote(path, safe='/')
        records = combine(parse_history(get(HISTORY_URL).content), parse_latest(get(url).content, entry, url))
    if not dry_run:
        store(records, db)
    latest = records[-1]
    LOG.info('%s: %d quarters; latest FY%s Q%d, %.6f%% YoY; release %s; base %s',
             'Validated' if dry_run else 'Stored', len(records), latest['fiscal_year'],
             latest['fiscal_quarter'], latest['headline_yoy'], latest['release_date'], BASE_YEAR)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--db', type=Path, default=DB_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    fetch(args.dry_run, args.db)


if __name__ == '__main__':
    main()
