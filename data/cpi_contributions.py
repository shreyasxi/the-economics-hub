"""Offline CPI 2024 validation, fixed-weight contributions and source verification.

Weights: NSO Expert Group Report, Annexure 5.3a (printed page 108).
No interpolation, weight normalization, residual bucket or stale fallback.
"""
from __future__ import annotations

import calendar
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent / 'CPI' / 'contributions'
API_URL = 'https://api.mospi.gov.in/api/cpi/getCPIData'
WEIGHTS_URL = 'https://www.mospi.gov.in/uploads/documents/documents/1770882257889-Expert_Group_Report_CPI.pdf'
ROUNDING_URL = 'https://www.mospi.gov.in/uploads/release_calendar/1773312227790_Press_Release_of_CPI_February_2026.pdf'
CATALOGUE_URL = 'https://esankhyiki.mospi.gov.in/catalogue-main/catalogue?product=CPI'
GENERAL = 'CPI (General)'
DIVISIONS = (
    ('01', 'Food and beverages', '36.7531063101009000'),
    ('02', 'Paan, tobacco and intoxicants', '2.9894513474480300'),
    ('03', 'Clothing and footwear', '6.3832571477623400'),
    ('04', 'Housing, water, electricity, gas and other fuels', '17.6645726883430000'),
    ('05', 'Furnishings, household equipment and routine household maintenance', '4.4693932060393600'),
    ('06', 'Health', '6.1002633527256500'),
    ('07', 'Transport', '8.7961133915624400'),
    ('08', 'Information and communication', '3.6094384689580600'),
    ('09', 'Recreation, sport and culture', '1.5158147751142900'),
    ('10', 'Education services', '3.3333088103870400'),
    ('11', 'Restaurants and accommodation services', '3.3475203529668700'),
    ('13', 'Personal care, social protection and miscellaneous goods and services', '5.0377601485917900'),
)
BUCKETS = {
    'Food': ('01',),
    'Housing & Utilities': ('04',),
    'Transport': ('07',),
    'Household & Apparel': ('03', '05'),
    'Health & Education': ('06', '10'),
    'Other Consumption': ('02', '08', '09', '11', '13'),
}
FIELDS = ('base_year', 'series', 'year', 'month', 'state', 'sector', 'division',
          'group', 'class', 'sub_class', 'item', 'code', 'index', 'inflation', 'imputation')
HIERARCHY = ('group', 'class', 'sub_class', 'item')
EPSILON = Decimal('1e-12')


def require(condition, message):
    if not condition:
        raise ValueError('MoSPI CPI: ' + message)


def numeric(value):
    require(isinstance(value, str) and value.strip() == value and bool(value),
            f'expected exact numeric string, got {value!r}')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f'MoSPI CPI: invalid number {value!r}') from exc
    require(result.is_finite(), f'non-finite number {value!r}')
    return result


def period(row):
    require(isinstance(row['year'], str) and re.fullmatch(r'20\d{2}', row['year']), 'invalid year')
    require(row['month'] in calendar.month_name[1:], 'invalid month')
    return f"{row['year']}-{list(calendar.month_name).index(row['month']):02d}"


def months_between(start, end):
    require(re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', start) is not None and
            re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', end) is not None, 'invalid period')
    y, m = map(int, start.split('-'))
    result = []
    while f'{y:04d}-{m:02d}' <= end:
        result.append(f'{y:04d}-{m:02d}')
        y, m = (y+1, 1) if m == 12 else (y, m+1)
    return result


def previous_month(month):
    y, m = map(int, month.split('-'))
    return f'{y:04d}-{m-1:02d}' if m > 1 else f'{y-1:04d}-12'


def configuration():
    codes = [code for code, _, _ in DIVISIONS]
    assigned = [code for values in BUCKETS.values() for code in values]
    require(len(codes) == len(set(codes)) == 12 and len(BUCKETS) == 6,
            'weight map must contain 12 divisions and six buckets')
    require(sorted(assigned) == sorted(codes), 'bucket omission or duplicate assignment')
    require(abs(sum(Decimal(w) for _, _, w in DIVISIONS)-100) < EPSILON, 'weights do not sum to 100')
    return dict(version=1, weights_source=WEIGHTS_URL, weights_table='Annexure 5.3a, printed page 108',
                weights_percent={code: dict(division=name, weight=w) for code, name, w in DIVISIONS},
                buckets=BUCKETS, formula='W_i * (I_i,t - I_i,t-12) / G_t-12',
                rounding_source=ROUNDING_URL, base_year='2024', series='Current',
                state_code=1, sector_code=3)


def select_aggregates(raw, expected_months=None):
    """Only literal JSON null qualifies; missing keys and empty strings never do."""
    accepted = []
    for row in raw:
        require(isinstance(row, dict) and set(row) == set(FIELDS), 'source schema changed')
        require(all(row[k] == v for k, v in [('base_year', '2024'), ('series', 'Current'),
                ('state', 'All India'), ('sector', 'Combined')]), 'wrong base/series/state/sector')
        if all(row[k] is None for k in HIERARCHY):
            accepted.append(dict(row))
    validate(accepted, expected_months)
    return sorted(accepted, key=lambda r: (period(r), r['code'] or '00'))


def validate(rows, expected_months=None):
    require(rows, 'no aggregate rows')
    expected = {GENERAL: None, **{name: code for code, name, _ in DIVISIONS}}
    seen = set()
    by_month = {}
    for row in rows:
        require(set(FIELDS).issubset(row), 'normalized schema changed')
        require(all(row[k] is None for k in HIERARCHY), 'lower-level leakage')
        require(all(row[k] == v for k, v in [('base_year', '2024'), ('series', 'Current'),
                ('state', 'All India'), ('sector', 'Combined')]), 'wrong base/series/state/sector')
        month = period(row)
        require(month >= '2025-01', 'observation predates Current series')
        name = row['division']
        require(name in expected and row['code'] == expected[name], 'division name/code changed')
        require((month, name) not in seen, f'duplicate {month} / {name}')
        seen.add((month, name))
        by_month.setdefault(month, []).append(row)
        require(numeric(row['index']) > 0, f'non-positive index: {month} / {name}')
        if month >= '2026-01':
            numeric(row['inflation'])
        elif row['inflation'] is not None:
            numeric(row['inflation'])
        require(row['imputation'] in (None, 'Y', 'N'), 'imputation schema changed')
    for month, block in by_month.items():
        require(len(block) == 13 and set(r['division'] for r in block) == set(expected),
                f'{month}: expected CPI General + exact 12 divisions, got {len(block)} rows')
    if expected_months is not None:
        require(set(by_month) == set(expected_months), 'missing/unexpected observation month')
    return by_month


def calculate(rows):
    configuration()
    by_month = validate(rows)
    latest = max(by_month)
    require(set(by_month) == set(months_between('2025-01', latest)), 'missing history month')
    require(latest >= '2026-01', 'no comparable prior-year observations')
    result = []
    with localcontext() as ctx:
        ctx.prec = 40
        for month in months_between('2026-01', latest):
            comparison = f'{int(month[:4])-1:04d}{month[4:]}'
            require(comparison in by_month, f'{month}: missing prior-year comparison')
            current = {r['division']: r for r in by_month[month]}
            prior = {r['division']: r for r in by_month[comparison]}
            g, g0 = numeric(current[GENERAL]['index']), numeric(prior[GENERAL]['index'])
            require(g0 > Decimal('.005'), f'{month}: invalid prior-year General index for rounding bound')
            published = numeric(current[GENERAL]['inflation'])
            direct = 100*(g/g0-1)
            divisions = {}
            for code, name, weight in DIVISIONS:
                i, i0 = numeric(current[name]['index']), numeric(prior[name]['index'])
                divisions[code] = dict(division=name, weight_percent=weight,
                    index_t=str(i), index_t12=str(i0), contribution_pp=str(Decimal(weight)*(i-i0)/g0))
            total = sum(Decimal(r['contribution_pp']) for r in divisions.values())
            residual_general, residual_published = total-direct, total-published
            allowed = 100*Decimal('.02')/g0
            # Rounding G_t and G_t-12 to .01 also perturbs their ratio. Add its
            # explicit bound, then .005 for the two-decimal published rate.
            ratio_rounding = 100*(Decimal('.005')/g0 + g*Decimal('.005')/(g0*(g0-Decimal('.005'))))
            allowed_published = allowed + ratio_rounding + Decimal('.005')
            require(abs(residual_general) <= allowed+EPSILON,
                    f'{month}: RECONCILIATION FAILED vs General: {residual_general} pp (bound {allowed})')
            require(abs(residual_published) <= allowed_published+EPSILON,
                    f'{month}: RECONCILIATION FAILED vs published: {residual_published} pp (bound {allowed_published})')
            buckets = {name: str(sum(Decimal(divisions[c]['contribution_pp']) for c in codes))
                       for name, codes in BUCKETS.items()}
            require(abs(sum(Decimal(v) for v in buckets.values())-total) < EPSILON, 'bucket totals differ')
            result.append(dict(month=month, comparison_month=comparison,
                headline_index=str(g), headline_index_t12=str(g0), published_headline=str(published),
                headline_from_general=str(direct), contribution_total=str(total),
                residual_general=str(residual_general), residual_published=str(residual_published),
                allowed_general_residual=str(allowed), allowed_published_residual=str(allowed_published),
                divisions=divisions, buckets=buckets))
    return result


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)+'\n').encode()


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def read_checked(path, checksum):
    blob = path.read_bytes()
    require(sha(blob) == checksum, f'checksum mismatch: {path.name}')
    return json.loads(blob)


def safe_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}', value), 'invalid snapshot ID')
    return value


def load_current(root=ROOT, ready=True):
    """Recompute all derived values and verify immutable source bytes offline."""
    root = Path(root)
    pointer = json.loads((root/'current.json').read_bytes())
    run_id = safe_id(pointer['run_id'])
    if ready:
        status = json.loads((root/'last_attempt.json').read_bytes())
        require(status['status'] == 'success' and status['run_id'] == run_id,
                'latest source update failed or is incomplete; stale chart prohibited')
    run = root/'runs'/run_id
    manifest = read_checked(run/'manifest.json', pointer['manifest_sha256'])
    require(manifest['run_id'] == run_id, 'run ID mismatch')
    rows = read_checked(run/'normalized.json', manifest['checksums']['normalized.json'])
    derived = read_checked(run/'derived.json', manifest['checksums']['derived.json'])
    weights = read_checked(run/'weights.json', manifest['checksums']['weights.json'])
    read_checked(run/'revisions.json', manifest['checksums']['revisions.json'])
    require(weights == json.loads(encoded(configuration())), 'weights/methodology changed; refresh required')
    require(calculate(rows) == derived, 'derived values differ from validated source calculation')
    require(manifest['latest_month'] == derived[-1]['month'], 'latest-month mismatch')
    require(manifest['normalized_row_count'] == len(rows) and
            manifest['contribution_month_count'] == len(derived), 'manifest row/month count mismatch')
    for retrieval_id in set(r['source_retrieval'] for r in rows):
        rid = safe_id(retrieval_id)
        retrieval = read_checked(root/'raw'/'retrievals'/f'{rid}.json',
                                 manifest['source_manifest_checksums'][rid])
        require(retrieval['retrieval_id'] == rid, 'retrieval ID mismatch')
        source_rows = []
        for number, req in enumerate(retrieval['requests'], 1):
            if 'request_record_count' in retrieval:
                require(retrieval['request_record_count'] == len(retrieval['requests']), 'request journal count mismatch')
                journal = root/'raw'/'request_records'/rid/f'{number:04d}.json'
                require(journal.read_bytes() == encoded(req), 'request journal differs from sealed provenance')
            checksum = req['sha256']
            require(re.fullmatch(r'[0-9a-f]{64}', checksum), 'invalid raw checksum')
            blob = (root/'raw'/'blobs'/f'{checksum}.bin').read_bytes()
            require(sha(blob) == checksum, 'raw response checksum mismatch')
            if req['url'] == API_URL and req['http_status'] == 200:
                payload = json.loads(blob)
                source_rows.extend(payload['data'])
            elif req['kind'] == 'manual':
                source_rows.extend(json.loads(blob))
        exact = {encoded({k:r[k] for k in FIELDS}) for r in source_rows}
        for row in rows:
            if row['source_retrieval'] == rid:
                require(encoded({k:row[k] for k in FIELDS}) in exact,
                        'normalized observation not found in immutable source snapshot')
    return rows, derived, manifest


def verify_archive(root=ROOT):
    """Verify historical snapshots too, including failed/unreferenced retrievals."""
    root = Path(root)
    _, derived, current = load_current(root)
    blobs = list((root/'raw'/'blobs').glob('*.bin'))
    for path in blobs:
        require(re.fullmatch(r'[0-9a-f]{64}', path.stem), 'invalid archive blob name')
        require(sha(path.read_bytes()) == path.stem, 'historical raw response checksum mismatch')
    retrievals = list((root/'raw'/'retrievals').glob('*.json'))
    for path in retrievals:
        source = json.loads(path.read_bytes())
        require(safe_id(source['retrieval_id']) == path.stem, 'historical retrieval ID mismatch')
        for number, request in enumerate(source['requests'], 1):
            checksum = request['sha256']
            require(re.fullmatch(r'[0-9a-f]{64}', checksum), 'invalid historical raw checksum')
            require((root/'raw'/'blobs'/f'{checksum}.bin').exists(), 'historical source blob missing')
            if 'request_record_count' in source:
                require(source['request_record_count'] == len(source['requests']), 'historical journal count mismatch')
                require((root/'raw'/'request_records'/path.stem/f'{number:04d}.json').read_bytes()==encoded(request),
                        'historical request provenance mismatch')
    runs = list((root/'runs').glob('*/manifest.json'))
    for path in runs:
        manifest = json.loads(path.read_bytes())
        require(safe_id(manifest['run_id']) == path.parent.name, 'historical run ID mismatch')
        values = {name:read_checked(path.parent/name, manifest['checksums'][name])
                  for name in ('normalized.json','derived.json','weights.json','revisions.json')}
        require(values['derived.json']==calculate(values['normalized.json']), 'historical contribution mismatch')
        require(values['weights.json']==json.loads(encoded(configuration())), 'historical weights mismatch')
        for rid, checksum in manifest['source_manifest_checksums'].items():
            read_checked(root/'raw'/'retrievals'/f'{safe_id(rid)}.json', checksum)
    return dict(latest_month=current['latest_month'], contribution_months=len(derived),
                raw_blobs=len(blobs), retrievals=len(retrievals), validated_runs=len(runs))
