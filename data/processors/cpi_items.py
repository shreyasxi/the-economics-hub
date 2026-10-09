"""Validated item-level CPI snapshots; no weights, filling, or base splicing."""
from datetime import datetime
import json
from pathlib import Path
import re
from data.processors import cpi_contributions as cpi

from data.paths import CPI_ITEMS_DIR

ROOT = CPI_ITEMS_DIR
TITLE = 'Where Are India’s Biggest Price Pressures?'


def normalize(raw, retrieval_id):
    rows = []
    seen = set()
    for r in raw:
        cpi.require(set(r) == set(cpi.FIELDS), 'item response schema changed')
        cpi.require(all(r[k] == v for k, v in [('base_year','2024'), ('series','Current'),
                    ('state','All India'), ('sector','Combined')]), 'item scope/base changed')
        month = cpi.period(r)
        if r['item'] is None:
            continue
        cpi.require(isinstance(r['item'], str) and r['item'].strip() and
                    isinstance(r['code'], str) and re.fullmatch(r'\d{2}\.\d\.\d\.\d\.\d\.\d{2}', r['code']),
                    'unsafe item identity')
        key = month, r['code']
        cpi.require(key not in seen, 'duplicate month/item code')
        seen.add(key)
        rows.append(dict(r, month_key=month, item_code=r['code'], item_name=r['item'],
                         index_level=None if r['index'] is None else float(cpi.numeric(r['index'])),
                         yoy=None if r['inflation'] is None else float(cpi.numeric(r['inflation'])),
                         yoy_method='published' if r['inflation'] is not None else 'missing',
                         source_url=cpi.API_URL, source_retrieval=retrieval_id,
                         publication_status='Not exposed by API'))
    return rows


def derive(rows):
    """Only exact same-code, same-base observations twelve months apart qualify."""
    lookup = {(r['month_key'], r['item_code']): r for r in rows}
    cpi.require(len(lookup) == len(rows), 'duplicate month/item code')
    result = []
    for r in rows:
        r = dict(r)
        previous = lookup.get((f"{int(r['month_key'][:4])-1}{r['month_key'][4:]}", r['item_code']))
        if r['yoy'] is None and previous and r['index_level'] is not None and previous['index_level'] is not None:
            cpi.require(all(r[k] == previous[k] for k in ('base_year','series','state','sector','item_name')),
                        'incompatible twelve-month item pair')
            cpi.require(previous['index_level'] > 0, 'invalid comparison index')
            r.update(yoy=(r['index_level']/previous['index_level']-1)*100, yoy_method='derived',
                     comparison_month=previous['month_key'], comparison_source_retrieval=previous['source_retrieval'])
        result.append(r)
    return result


def validate(rows, expected_codes=None, latest=None):
    cpi.require(rows, 'no item observations')
    # Rebuild every value from the preserved official fields; catches altered rates/provenance.
    rebuilt = []
    for r in rows:
        rebuilt.extend(normalize([{k:r[k] for k in cpi.FIELDS}], r['source_retrieval']))
    # A blank published YoY stays blank. Derivation is an explicit mode for
    # index-only sources, never a repair for missing published observations.
    if any(r['yoy_method'] == 'derived' for r in rows):
        calculated = derive(rebuilt)
        rebuilt = [d if original['yoy_method'] == 'derived' else r
                   for original, r, d in zip(rows, rebuilt, calculated)]
    cpi.require(rows == rebuilt, 'item values or provenance failed validation')
    codes = expected_codes or sorted({r['item_code'] for r in rows})
    cpi.require(len(codes) == len(set(codes)), 'duplicate universe code')
    for month in sorted({r['month_key'] for r in rows}):
        current = [r for r in rows if r['month_key'] == month]
        cpi.require(sorted(r['item_code'] for r in current) == sorted(codes), 'partial item universe')
        cpi.require(len({r['item_name'] for r in current}) == len(current), 'duplicate item name')
    names = {}
    for r in rows:
        cpi.require(names.setdefault(r['item_code'], r['item_name']) == r['item_name'], 'item identity changed')
    cpi.require(latest is None or max(r['month_key'] for r in rows) == latest, 'latest item month mismatch')
    return rows


def snapshot(rows):
    validate(rows)
    month = max(r['month_key'] for r in rows)
    valid = [r for r in rows if r['month_key'] == month and r['yoy'] is not None]
    increases = sorted((r for r in valid if r['yoy'] > 0), key=lambda r:(-r['yoy'],r['item_code']))[:8]
    declines = sorted((r for r in valid if r['yoy'] < 0), key=lambda r:(r['yoy'],r['item_code']))[:8]
    label = datetime.fromisoformat(month+'-01').strftime('%B %Y')
    parts = []
    if increases:
        r = increases[0]; parts.append(f"{r['item_name']} recorded the strongest increase at +{r['yoy']:.1f}%")
    else:
        parts.append('no items recorded an increase')
    if declines:
        r = declines[0]; parts.append(f"{r['item_name']} fell the most at −{abs(r['yoy']):.1f}%")
    else:
        parts.append('no items recorded a decline')
    methods = {r['yoy_method'] for r in valid}
    method = ('Item-level YoY inflation (published)' if methods <= {'published'} else
              'Item-level YoY inflation · includes YoY calculated from official same-item, same-base indices')
    return dict(title=TITLE, subtitle=f'Largest year-on-year price increases and declines across CPI items · {label}',
                summary=f"Among {len(valid)} CPI items with valid YoY readings, {parts[0]}, while {parts[1]} in {label}.",
                latest_month=month, valid_count=len(valid), increases=increases, declines=declines,
                source_line='Source: MoSPI / eSankhyiki · All-India CPI Combined · '+method,
                source_url=cpi.API_URL)


def load_current(root=ROOT, ready=True):
    root = Path(root)
    pointer = json.loads((root/'current.json').read_text())
    folder = root/'runs'/pointer['run_id']
    blob = (folder/'manifest.json').read_bytes()
    cpi.require(cpi.sha(blob) == pointer['manifest_sha256'], 'item manifest checksum mismatch')
    manifest = json.loads(blob)
    if ready:
        attempt = json.loads((root/'last_attempt.json').read_text())
        cpi.require(attempt['status'] == 'success' and attempt['run_id'] == pointer['run_id'], 'item refresh not ready')
    blob = (folder/'normalized.json').read_bytes()
    cpi.require(cpi.sha(blob) == manifest['rows_sha256'], 'item data checksum mismatch')
    rows = json.loads(blob)
    validate(rows, manifest['item_codes'], manifest['latest_month'])
    # Every canonical observation must exactly match its archived official response.
    source_rows = {}
    for rid in {r['source_retrieval'] for r in rows}:
        blob = (root/'raw/retrievals'/f'{rid}.json').read_bytes()
        cpi.require(cpi.sha(blob) == manifest['source_manifest_checksums'][rid], 'item source manifest changed')
        source = json.loads(blob)
        cpi.require(source['success'], 'unsuccessful item source')
        for request in source['requests']:
            if request['url'] != cpi.API_URL: continue
            blob = (root/'raw/blobs'/f"{request['sha256']}.bin").read_bytes()
            cpi.require(cpi.sha(blob) == request['sha256'], 'item raw source changed')
            for r in json.loads(blob)['data']:
                if r['item'] is not None:
                    key = rid, cpi.period(r), r['code']
                    cpi.require(key not in source_rows or source_rows[key] == r, 'conflicting archived source')
                    source_rows[key] = r
    for r in rows:
        cpi.require(source_rows.get((r['source_retrieval'],r['month_key'],r['item_code'])) ==
                    {k:r[k] for k in cpi.FIELDS}, 'item differs from official source')
    return rows, manifest
