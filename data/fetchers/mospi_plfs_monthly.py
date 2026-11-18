"""Redesigned PLFS monthly unemployment, officially published only.

The urban age-band history feeds the dedicated India labour chart. The
all-India, persons-15+ rate from the same bulletin feeds the overview database.

python -m data.fetchers.mospi_plfs_monthly [--dry-run] [--csv PATH]

The official monthly bulletin's Statement 3 is the canonical source for the
latest five months. It supplies both the urban age bands and the all-India
persons-15+ rate, avoiding a lag between the PDF release and the separate API.
"""
import argparse
from contextlib import nullcontext
import calendar
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import requests

from data.fetchers.mospi_dashboard import (
    ROOT, BULLETINS_URL, require, month, number, official_url, listing,
    select_latest, publication_month, attachment, download, api_rows, retain,
    atomic_json, read_csv, write_csv, reconcile, verify_retained,
)

from data.paths import MOSPI_PLFS_CSV, mospi_sources_for
from data.processors.india_db_manager import init_db, upsert_monthly

CSV = MOSPI_PLFS_CSV
URL = 'https://api.mospi.gov.in/api/plfs/getData'
START = '2025-04'
TABLE = 'Statement 3: Unemployment Rate (in per cent) in CWS'
INDICATOR = 'UR (Unemployment Rate, in per cent)'
PARAMS = dict(frequency_code=3, indicator_code=3, gender_code=3, sector_code=2,
              limit=100, Format='JSON')
AGES = {'15-29 years': '15–29', '15 years and above': '15+'}
FIELDS = ('month', 'geography', 'sector', 'age_group', 'gender', 'indicator',
          'value_pct', 'source_url', 'table_id', 'release_date', 'fetched_at',
          'frequency', 'activity_status', 'methodology', 'bulletin_url', 'raw_sha256')


def validate(rows, require_start=True):
    require(bool(rows), 'empty PLFS history')
    seen, periods = set(), {}
    for r in rows:
        require(re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', r['month']) is not None
                and START <= r['month'] < datetime.now(timezone.utc).strftime('%Y-%m'),
                'PLFS month precedes first published comparable monthly observation')
        require(r['geography'] == 'All India' and r['sector'] == 'Urban'
                and r['gender'] == 'Persons' and r['indicator'] == 'UR'
                and r['age_group'] in AGES.values(), 'wrong PLFS dimensions')
        require(r['frequency'] == 'Monthly' and r['activity_status'] == 'CWS'
                and r['methodology'] == 'Redesigned January 2025', 'quarterly/usual-status/old-methodology splice')
        require(r['table_id'] == TABLE, 'wrong PLFS table')
        key = (r['month'], r['age_group'])
        require(key not in seen, 'duplicate PLFS month/dimensions')
        seen.add(key)
        periods.setdefault(r['month'], set()).add(r['age_group'])
        r['value_pct'] = number(r['value_pct'])
        require(0 <= r['value_pct'] <= 100, 'invalid UR percentage')
        date.fromisoformat(r['release_date'])
        require(r['release_date'][:7] > r['month'], 'PLFS release precedes observation')
        official_url(r['source_url'])
        official_url(r['bulletin_url'])
        require(re.fullmatch('[0-9a-f]{64}', r['raw_sha256']) is not None, 'missing PLFS raw hash')
    require(all(ages == set(AGES.values()) for ages in periods.values()), 'incomplete PLFS month')
    if require_start:
        require(min(periods) == START, 'first published PLFS month missing')
    return rows


def parse_api(rows, release_date, bulletin_url, fetched_at, checksum):
    require(bool(rows), 'empty monthly PLFS table')
    output, seen = [], set()
    for r in rows:
        require(r['frequency'] == 'Monthly' and r['indicator'] == INDICATOR
                and r['unit'] == '%', 'wrong frequency/indicator/unit in monthly API')
        # Older API rows omit activity status. Monthly CWS is established by the
        # official bulletin; reject contradictory fields if MoSPI adds them.
        require(r.get('weekly_status', 'CWS') in ('CWS', 'Current Weekly Status')
                and r.get('activity_status', 'CWS') == 'CWS', 'non-CWS response')
        period = month(r['year'], r['month'])
        require(period >= START, 'monthly source includes pre-publication regime')
        raw_key = (period, r['state'], r['sector'], r['AgeGroup'], r['gender'])
        require(raw_key not in seen, 'duplicate source PLFS observation')
        seen.add(raw_key)
        if (r['state'], r['sector'], r['gender']) != ('All India', 'urban', 'person'):
            continue
        if r['AgeGroup'] not in AGES:
            continue
        output.append(dict(month=period, geography='All India', sector='Urban',
                    age_group=AGES[r['AgeGroup']], gender='Persons', indicator='UR',
                    value_pct=number(r['value']), source_url=URL, table_id=TABLE,
                    release_date=release_date, fetched_at=fetched_at, frequency='Monthly',
                    activity_status='CWS', methodology='Redesigned January 2025',
                    bulletin_url=bulletin_url, raw_sha256=checksum))
    return validate(sorted(output, key=lambda r: (r['month'], r['age_group'])))


def parse_statement(text):
    """Verification only: data storage is sourced from the structured API."""
    match = re.search(re.escape(TABLE), text)
    require(match is not None, 'exact monthly Statement 3 missing')
    lines = [s.strip() for s in text[match.end():].splitlines() if s.strip()]
    require(lines[:5] == ['sector', 'survey month', 'male', 'female', 'person'],
            'Statement 3 gender column order changed')
    result, sector, age = {}, None, None
    for i, line in enumerate(lines):
        if line in ('rural', 'urban', 'rural + urban'):
            sector = line
            age = None
        elif line.startswith('age group:'):
            age = line.split(':', 1)[1].strip()
        else:
            m = re.fullmatch(r'(' + '|'.join(calendar.month_name[1:]) + r'),\s*(20\d{2})', line)
            if m and sector == 'urban' and age in AGES:
                require(i+3 < len(lines), 'truncated Statement 3')
                values = [number(v) for v in lines[i+1:i+4]]
                key = (month(m[2], m[1]), AGES[age])
                require(key not in result, 'duplicate Statement 3 month')
                result[key] = values[2]  # male / female / person in official table
    require(len(result) >= 10, 'five months of both official urban age groups required')
    return result


def parse_all_india_ur_statement(text):
    """Read the official all-India, age-15+, person UR from Statement 3."""
    match = re.search(re.escape(TABLE), text)
    require(match is not None, 'exact monthly Statement 3 missing')
    lines = [s.strip() for s in text[match.end():].splitlines() if s.strip()]
    require([s.casefold() for s in lines[:5]] ==
            ['sector', 'survey month', 'male', 'female', 'person'],
            'Statement 3 gender column order changed')

    result = {}
    sector = age = None
    month_re = re.compile(r'(' + '|'.join(calendar.month_name[1:]) + r'),\s*(20\d{2})', re.I)
    for i, line in enumerate(lines):
        normalized = line.casefold()
        if normalized in ('rural', 'urban', 'rural + urban'):
            sector, age = normalized, None
            continue
        if normalized.startswith('age group:'):
            age = normalized.split(':', 1)[1].strip()
            continue
        m = month_re.fullmatch(line)
        if m and sector == 'rural + urban' and age == '15 years and above':
            require(i + 3 < len(lines), 'truncated all-India unemployment row')
            values = [number(v) for v in lines[i + 1:i + 4]]
            period = month(m[2], m[1].capitalize())
            require(period not in result, 'duplicate all-India unemployment month')
            result[period] = values[2]  # male / female / person

    require(len(result) >= 5, 'five months of all-India 15+ unemployment required')
    require(all(0 <= value <= 30 for value in result.values()),
            'all-India unemployment outside plausible range')
    return result


def persist_all_india_ur(values, release_date, bulletin_url, bulletin_hash, archive,
                         dry_run=False, persist_database=True):
    """Update the India overview series independently of the urban-only API feed."""
    if dry_run or not persist_database:
        return
    init_db()
    for period, value in sorted(values.items()):
        upsert_monthly(period, {
            'india_unemployment': value,
            'source_flags': json.dumps({
                'india_unemployment': f'mospi_plfs_bulletin:published={release_date}'
            }),
        })
    atomic_json(archive / 'headline_unemployment_latest.json', {
        'reference_month': max(values),
        'release_date': release_date,
        'source_url': bulletin_url,
        'table_id': TABLE,
        'age_group': '15 years and above',
        'sector': 'rural + urban',
        'gender': 'Persons',
        'value_pct': values[max(values)],
        'bulletin_sha256': bulletin_hash,
    })


def rows_from_bulletin(urban_values, release_date, bulletin_url, fetched_at, checksum):
    """Convert the latest official Statement 3 rows into the urban chart schema."""
    return validate([
        dict(month=period, geography='All India', sector='Urban',
             age_group=age_group, gender='Persons', indicator='UR', value_pct=value,
             source_url=bulletin_url, table_id=TABLE, release_date=release_date,
             fetched_at=fetched_at, frequency='Monthly', activity_status='CWS',
             methodology='Redesigned January 2025', bulletin_url=bulletin_url,
             raw_sha256=checksum)
        for (period, age_group), value in sorted(urban_values.items())
    ], require_start=False)


def merge_bulletin_rows(previous, incoming, reference):
    """Replace only periods verified by the newest bulletin; retain older history."""
    if previous:
        validate(previous)
    validate(incoming, require_start=False)
    require(max(r['month'] for r in incoming) == reference,
            'bulletin urban UR reference month mismatch')

    merged = {(r['month'], r['age_group']): r for r in previous}
    for row in incoming:
        key = (row['month'], row['age_group'])
        old = merged.get(key)
        if old and row['release_date'] < old['release_date']:
            continue
        if old and row['release_date'] == old['release_date']:
            require(float(old['value_pct']) == float(row['value_pct']),
                    'conflicting PLFS value within the same official bulletin vintage')
        merged[key] = row

    return validate([merged[key] for key in sorted(merged)])


def verify_bulletin(text, rows, reference):
    require(re.search(r'January,?\s*2025', text) and re.search(r'April,?\s*2025', text)
            and 'Current Weekly Status' in text and 'Monthly Bulletin' in text,
            'redesigned monthly CWS methodology missing')
    official = parse_statement(text)
    values = {(r['month'], r['age_group']): r['value_pct'] for r in rows}
    require(max(m for m, a in official) == reference, 'bulletin reference month mismatch')
    require(max(r['month'] for r in rows) == reference, 'API is stale relative to monthly publication')
    for key, value in official.items():
        require(key in values and values[key] == value, 'API differs from official Statement 3')
    return official


def load(path=CSV):
    rows = validate(read_csv(path))
    verify_retained(mospi_sources_for(path, 'plfs'), rows)
    return rows


def fetch(path=CSV, dry_run=False, session=None):
    import fitz
    path = Path(path)
    with (nullcontext(session) if session is not None else requests.Session()) as client:
        publications = listing(client, BULLETINS_URL, 'Monthly Bulletin')
        release = select_latest(publications, lambda r: 'Labour Force Survey' in r['title']
                                and 'Monthly Bulletin' in r['title'])
        reference = publication_month(release['title'])
        url = attachment(release, '.pdf')
        bulletin = download(client, url)
        with fitz.open(stream=bulletin, filetype='pdf') as document:
            text = '\n'.join(p.get_text() for p in document)
        urban_values = parse_statement(text)
        require(max(period for period, _ in urban_values) == reference,
                'urban PLFS reference month differs from bulletin')
        headline_ur = parse_all_india_ur_statement(text)
        require(max(headline_ur) == reference, 'all-India UR reference month differs from bulletin')
        archive = mospi_sources_for(path, 'plfs')
        bulletin_hash = (hashlib.sha256(bulletin).hexdigest() if dry_run
                         else retain(archive, bulletin))
        fetched = datetime.now(timezone.utc).isoformat()
        incoming = rows_from_bulletin(urban_values, release['published_year'],
                                      url, fetched, bulletin_hash)
        previous = read_csv(path)
        combined = merge_bulletin_rows(previous, incoming, reference)
        persist_all_india_ur(headline_ur, release['published_year'], url,
                             bulletin_hash, archive, dry_run=dry_run,
                             persist_database=path.resolve() == Path(CSV).resolve())
        if not dry_run:
            atomic_json(archive / 'latest.json', dict(release=release, source_url=url,
                        table_id=TABLE, raw_sha256=bulletin_hash,
                        bulletin_sha256=bulletin_hash, fetched_at=fetched,
                        start_month=START, spot_checks=len(urban_values),
                        source_method='Official monthly bulletin Statement 3'))
            write_csv(path, combined, FIELDS)
        return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=CSV)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    rows = fetch(args.csv, args.dry_run)
    print(f"Validated {len(rows)} PLFS rows: {rows[0]['month']}–{rows[-1]['month']}")


if __name__ == '__main__':
    main()
