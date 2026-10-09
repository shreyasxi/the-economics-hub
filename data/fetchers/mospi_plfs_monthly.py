"""Redesigned PLFS monthly Urban/Persons unemployment, officially published only.

python -m data.fetchers.mospi_plfs_monthly [--dry-run] [--csv PATH]

Monthly API frequency_code=3 is CWS by the bulletin's explicit methodology.
Each refresh verifies the latest five months against Statement 3 of the latest
bulletin. release_date identifies that corroborating release vintage; the API
does not expose per-record publication dates or revisions. Reference month is
stored separately. Only a newer official bulletin permits a changed vintage.
"""
import argparse
from contextlib import nullcontext
import calendar
from datetime import date, datetime, timezone
from pathlib import Path
import re

import requests

from data.fetchers.mospi_dashboard import (
    ROOT, BULLETINS_URL, require, month, number, official_url, listing,
    select_latest, publication_month, attachment, download, api_rows, retain,
    atomic_json, read_csv, write_csv, reconcile, verify_retained,
)

from data.paths import MOSPI_PLFS_CSV, mospi_sources_for

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


def validate(rows):
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
        raw, pages = api_rows(client, URL, PARAMS)
        import hashlib
        # Hash the exact bytes of every returned page in deterministic order.
        checksum = hashlib.sha256(b'\n'.join(pages)).hexdigest()
        fetched = datetime.now(timezone.utc).isoformat()
        incoming = parse_api(raw, release['published_year'], url, fetched, checksum)
        verified = verify_bulletin(text, incoming, reference)
        previous = read_csv(path)
        # The latest bulletin supplies revision evidence only for its own table.
        # A changed older API observation needs an explicit historical bulletin.
        old = {(r['month'], r['age_group']): r for r in previous}
        for r in incoming:
            key = (r['month'], r['age_group'])
            if key in old and float(old[key]['value_pct']) != r['value_pct']:
                require(key in verified, 'historical PLFS change lacks bulletin evidence')
        combined = reconcile(previous, incoming, ('month', 'age_group'), validate)
        if not dry_run:
            archive = mospi_sources_for(path, 'plfs')
            retain(archive, b'\n'.join(pages))
            bulletin_hash = retain(archive, bulletin)
            atomic_json(archive / 'latest.json', dict(release=release, source_url=URL,
                        request=PARAMS, table_id=TABLE, raw_sha256=checksum,
                        bulletin_sha256=bulletin_hash, fetched_at=fetched,
                        start_month=START, spot_checks=len(verified),
                        release_date_semantics='Corroborating bulletin vintage; API record dates not exposed'))
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
