"""Publish audited research once; serve small, immutable files without archive I/O.

Build offline: python -m data.processors.emerging_publication
The full source validators run before CURRENT can advance. Runtime readers never
fall back to source archives or collection, including when a release is missing.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from config.emerging_opportunity import SECTORS, EQUITY_SECTORS
from data.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT / 'data/published/india_research'


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _immutable(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(blob)
    except FileExistsError:
        if path.read_bytes() != blob:
            raise ValueError('Published research collision')


def publish(root=ROOT):
    # Import collection dependencies only in the publishing command.
    from data.fetchers.emerging_opportunity import validate_datasets
    from data.processors.emerging_opportunity import flow_metrics
    datasets = validate_datasets(list(SECTORS))
    files, rows, blobs = {}, [], {}
    for sector in SECTORS:
        data = datasets[sector]
        filename = SECTORS[sector] + '.json'
        blob = _encoded(data)
        blobs[filename] = blob
        files[sector] = dict(file=filename, sha256=_sha(blob), source_digest=data['digest'])
        if sector in EQUITY_SECTORS:
            metrics = flow_metrics(data)
            latest = data['flows'][-1] if data['flows'] else {}
            opening = data['flows'][0].get('opening_equity_auc_cr') if data['flows'] else None
            rows.append({'Sector': sector,
                         'Six-month net (₹ cr)': metrics['net_cr'] if metrics['complete'] else None,
                         'Net / opening FPI holdings (%)': 100 * metrics['net_cr'] / opening if metrics['complete'] and opening else None,
                         'Latest fortnight (₹ cr)': latest.get('equity_flow_cr'),
                         'Buying streak (fortnights)': metrics['current_streak'],
                         'Cutoff': data.get('flows_as_of') or data['as_of']})
    manifest = _encoded(dict(schema_version=1, sectors=files, ranking=rows))
    release = _sha(manifest)
    folder = Path(root) / release
    for name, blob in blobs.items():
        _immutable(folder / name, blob)
    _immutable(folder / 'manifest.json', manifest)
    # An interrupted or rejected build leaves the previous release readable.
    pointer = Path(root) / ('CURRENT.' + uuid.uuid4().hex + '.tmp')
    try:
        pointer.write_text(release + '\n', encoding='ascii')
        os.replace(pointer, Path(root) / 'CURRENT')
    finally:
        pointer.unlink(missing_ok=True)
    return release


def read_manifest(root=ROOT):
    release = (Path(root) / 'CURRENT').read_text(encoding='ascii').strip()
    if not re.fullmatch('[a-f0-9]{64}', release):
        raise ValueError('Invalid research release identity')
    folder = Path(root) / release
    blob = (folder / 'manifest.json').read_bytes()
    if _sha(blob) != release:
        raise ValueError('Research manifest checksum mismatch')
    manifest = json.loads(blob)
    if manifest['schema_version'] != 1 or set(manifest['sectors']) != set(SECTORS):
        raise ValueError('Unsupported research publication')
    if [row['Sector'] for row in manifest['ranking']] != EQUITY_SECTORS:
        raise ValueError('Incomplete research ranking')
    return folder, manifest


def load_sector(sector, folder, manifest):
    if sector not in SECTORS:
        raise ValueError('Unsupported research sector')
    receipt = manifest['sectors'][sector]
    if receipt['file'] != SECTORS[sector] + '.json':
        raise ValueError('Invalid published research path')
    blob = (Path(folder) / receipt['file']).read_bytes()
    if _sha(blob) != receipt['sha256']:
        raise ValueError('Research snapshot checksum mismatch')
    data = json.loads(blob)
    if data['schema_version'] != 1 or data['sector'] != sector or data['digest'] != receipt['source_digest']:
        raise ValueError('Research snapshot identity mismatch')
    return data


if __name__ == '__main__':
    print('Published research release:', publish())
