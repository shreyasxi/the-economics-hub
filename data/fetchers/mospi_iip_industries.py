"""Current-base IIP industries from MoSPI's monthly structured release annexure.

python -m data.fetchers.mospi_iip_industries [--dry-run] [--csv PATH]

Full current-base overlap (not merely four months) is reconciled on each run.
The annexure includes the published growth table; YoY is never recomputed from
rounded indices. Release text supplies statuses only where explicitly stated.
2022-23 releases before 29 June 2026 used a superseded WPI deflator and are
rejected. Latest annexures contain the revised Output-PPI history throughout.
"""
import argparse
import calendar
from contextlib import nullcontext
from datetime import date, datetime, timezone
import hashlib
import io
from pathlib import Path
import re

import openpyxl
import requests

from data.fetchers.mospi_dashboard import (
    ROOT, RELEASES_URL, require, month, number, official_url, listing, select_latest,
    publication_month, attachment, download, retain, atomic_json,
    read_csv, write_csv, reconcile, verify_retained,
)

from data.paths import MOSPI_IIP_CSV, mospi_sources_for

CSV = MOSPI_IIP_CSV
SHEET = 'NIC 2d, sectoral monthly'
TABLE = 'Monthly Sectoral, Sub-sectoral/NIC 2 digit indices and published YoY growth rates'
FIELDS = ('month', 'nic_code', 'industry', 'index', 'yoy_growth', 'status',
          'source_url', 'release_date', 'fetched_at', 'base_year', 'nic_version',
          'deflator_regime', 'status_source_url', 'raw_sha256')
STATUSES = {'Quick estimate', 'First revision', 'Final estimate', 'Not specified'}


def validate(rows):
    require(bool(rows), 'empty IIP history')
    seen, months, universe = set(), {}, {}
    for r in rows:
        require(r['base_year'] == '2022-23' and r['nic_version'] == 'NIC-2025'
                and r['deflator_regime'] == 'Output PPI', 'incompatible IIP regime')
        require(re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', r['month']) is not None
                and '2023-04' <= r['month'] < datetime.now(timezone.utc).strftime('%Y-%m'), 'invalid IIP month')
        require(re.fullmatch(r'\d{2}', r['nic_code']) is not None and r['industry'].strip(), 'invalid NIC label')
        key = (r['month'], r['nic_code'])
        require(key not in seen, 'duplicate IIP industry/month')
        seen.add(key)
        r['index'] = number(r['index'], nullable=True)
        r['yoy_growth'] = number(r['yoy_growth'], nullable=True)
        require(r['index'] is None or r['index'] > 0, 'invalid published index')
        require(r['status'] in STATUSES, 'unknown IIP status')
        require(r['release_date'] >= '2026-06-29', 'superseded WPI vintage')
        date.fromisoformat(r['release_date'])
        require(r['release_date'][:7] > r['month'], 'IIP publication precedes observation')
        official_url(r['source_url'])
        official_url(r['status_source_url'])
        require(re.fullmatch('[0-9a-f]{64}', r['raw_sha256']) is not None, 'missing raw source hash')
        months.setdefault(r['month'], set()).add(r['nic_code'])
        require(r['nic_code'] not in universe or universe[r['nic_code']] == r['industry'], 'industry label changed')
        universe[r['nic_code']] = r['industry']
    require(len(universe) == 23, 'expected 23 manufacturing industries')
    require(all(codes == set(universe) for codes in months.values()), 'incomplete manufacturing month')
    return rows


def release_statuses(text, latest):
    """Do not assume the old-base two-stage revision timetable still applies."""
    require(re.search(r'Base\s*:?\s*2022[–-]23\s*=\s*100', text, re.I), 'release base mismatch')
    require('NIC-2025' in text and '23 industry groups' in text, 'release universe mismatch')
    require('Quick Estimate' in text, 'quick-estimate release unidentified')
    result = {latest: 'Quick estimate'}
    pattern = (r'indices for\s+(' + '|'.join(calendar.month_name[1:]) +
               r')\s+(20\d{2})\s+have\s+undergone\s+(first|final)\s+revision')
    for name, year, stage in re.findall(pattern, text, flags=re.I):
        result[month(year, name.capitalize())] = 'First revision' if stage.lower() == 'first' else 'Final estimate'
    require(len(result) >= 2, 'official revision status missing')
    return result


def parse_annexure(content, source_url, release_date, statuses, status_source_url, fetched_at):
    require(content.startswith(b'PK'), 'IIP attachment is not an Excel workbook')
    require(release_date >= '2026-06-29', 'superseded WPI vintage')
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    require(SHEET in workbook.sheetnames, 'official monthly NIC table missing')
    table = list(workbook[SHEET].values)
    require('(Base 2022-23)' in str(table[:5]), 'Excel base mismatch')
    headers = [i for i, r in enumerate(table) if r[:3] == ('NIC 2025', 'Description', 'Weights')]
    require(len(headers) == 2, 'index/published-growth table detection failed')
    require('growth rates' in str(table[headers[1]-2][0]).lower()
            and 'previous year' in str(table[headers[1]-2][0]).lower(), 'published YoY table missing')
    monthly = {}
    labels = {}
    for block, start in enumerate(headers):
        stop = headers[1]-2 if block == 0 else len(table)
        columns = [(j, v.strftime('%Y-%m')) for j, v in enumerate(table[start]) if isinstance(v, datetime)]
        require(len(columns) >= 4 and len(set(m for j, m in columns)) == len(columns), 'invalid monthly columns')
        # Manufacturing is an explicit subtotal; derive its constituent rows from
        # that block, not from a hand-written industry list or inferred codes.
        end = next((i for i in range(start+1, stop) if table[i][0] == 'Manufacturing'), None)
        require(end is not None, 'manufacturing subtotal missing')
        begin = next((i for i in range(start+1, end) if table[i][0] == 'Mining & Quarrying'), None)
        require(begin is not None, 'manufacturing boundary missing')
        industries = table[begin+1:end]
        require(len(industries) == 23, 'expected 23 official manufacturing rows')
        for row in industries:
            require(type(row[0]) is int and 10 <= row[0] <= 32 and isinstance(row[1], str), 'invalid two-digit NIC row')
            code = str(row[0])
            require(code not in labels or labels[code] == row[1], 'index/growth label mismatch')
            labels[code] = row[1]
            for column, period in columns:
                key = (period, code)
                if block == 0:
                    require(key not in monthly, 'duplicate Excel industry/month')
                    monthly[key] = dict(month=period, nic_code=code, industry=row[1], index=number(row[column], True))
                else:
                    require(key in monthly and 'yoy_growth' not in monthly[key], 'growth/index coverage mismatch')
                    monthly[key]['yoy_growth'] = number(row[column], True)
    latest = max(m for m, c in monthly)
    require(latest in statuses, 'annexure and release reference month differ')
    checksum = hashlib.sha256(content).hexdigest()
    rows = []
    for key in sorted(monthly):
        r = monthly[key]
        require('yoy_growth' in r, 'missing official growth row')
        r.update(status=statuses.get(r['month'], 'Not specified'), source_url=source_url,
                 release_date=release_date, fetched_at=fetched_at, base_year='2022-23',
                 nic_version='NIC-2025', deflator_regime='Output PPI',
                 status_source_url=status_source_url, raw_sha256=checksum)
        rows.append(r)
    return validate(rows)


def load(path=CSV):
    rows = validate(read_csv(path))
    verify_retained(mospi_sources_for(path, 'iip'), rows)
    return rows


def fetch(path=CSV, dry_run=False, session=None):
    import fitz
    path = Path(path)
    with (nullcontext(session) if session is not None else requests.Session()) as client:
        publications = listing(client, RELEASES_URL, 'Industrial Production')
        release = select_latest(publications, lambda r: '2022-23' in r['title']
                                and 'Quick Estimates' in r['title'])
        reference = publication_month(release['title'])
        url = attachment(release, '.xlsx')
        note_url = attachment(release, '.pdf')
        # The PDF is used only for vintage/status and breadth verification;
        # every economic observation comes from the structured Excel annexure.
        note = download(client, note_url)
        with fitz.open(stream=note, filetype='pdf') as document:
            text = '\n'.join(p.get_text() for p in document)
        statuses = release_statuses(text, reference)
        content = download(client, url)
        fetched = datetime.now(timezone.utc).isoformat()
        incoming = parse_annexure(content, url, release['published_year'], statuses, note_url, fetched)
        require(max(r['month'] for r in incoming) == reference, 'Excel is stale relative to release')
        latest = [r for r in incoming if r['month'] == reference]
        match = re.search(r'(\d+)\s+out of\s+23 industry groups', text)
        require(match and sum(r['yoy_growth'] > 0 for r in latest if r['yoy_growth'] is not None)
                == int(match[1]), 'breadth differs from official release')
        combined = reconcile(read_csv(path), incoming, ('month', 'nic_code'), validate)
        if not dry_run:
            archive = mospi_sources_for(path, 'iip')
            retain(archive, content)
            retain(archive, note)
            atomic_json(archive / 'latest.json', dict(release=release, table=SHEET, fetched_at=fetched,
                        source_url=url, raw_sha256=incoming[0]['raw_sha256'], statuses=statuses,
                        overlap_months=len({r['month'] for r in incoming})))
            write_csv(path, combined, FIELDS)
        return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=CSV)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    rows = fetch(args.csv, args.dry_run)
    print(f"Validated {len(rows)} industry/month rows: {rows[0]['month']}–{rows[-1]['month']}")


if __name__ == '__main__':
    main()
