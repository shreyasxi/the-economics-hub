"""Official item collector, sharing the CPI HTTP, pagination and raw archive architecture.

PYTHONPATH=. python -m data.fetchers.mospi_cpi_items --update
"""
import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import uuid
import requests
from data.processors import cpi_items as items, cpi_contributions as cpi
from data.fetchers.mospi_cpi import Retrieval, discover_latest, fetch_pages, immutable, atomic_json, utc_now


def update(root=items.ROOT, session=None):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    lock = root/'.update.lock'
    with lock.open('x') as f: f.write('updating')
    own = session is None; session = session or requests.Session()
    retrieval = Retrieval(root, session); sealed = False
    try:
        atomic_json(root/'last_attempt.json', dict(status='running', source_retrieval=retrieval.id))
        previous = items.load_current(root, ready=False)[0] if (root/'current.json').exists() else []
        latest = discover_latest(retrieval)
        cpi.require(latest <= datetime.now(timezone.utc).strftime('%Y-%m'), 'future item month')
        cpi.require(not previous or latest >= max(r['month_key'] for r in previous), 'item latest month regressed')
        # Full item history is only twenty months at initial release. Incremental
        # updates refresh three recent months, comparison months and any gaps.
        months = cpi.months_between('2025-01', latest)
        targets = months if not previous else sorted(set(months[-3:]) |
            {f"{int(m[:4])-1}{m[4:]}" for m in months[-3:] if int(m[:4]) > 2025} |
            (set(months)-{r['month_key'] for r in previous}))
        refreshed = []
        expected = set(r['item_code'] for r in previous)
        for month in targets:
            raw = fetch_pages(retrieval, dict(year=month[:4], month_code=int(month[5:])))
            rows = items.normalize(raw, retrieval.id)
            cpi.require(all(r['month_key'] == month for r in rows), 'API returned wrong item month')
            codes = {r['item_code'] for r in rows}
            cpi.require(len(rows) == len(codes) and len(codes) == 358, 'official 2024 item universe changed/incomplete')
            cpi.require(not expected or codes == expected, 'item universe changed')
            expected = codes; refreshed.extend(rows)
            logging.info('Validated %s: %s official items', month, len(rows))
        rows = [{k:v for k,v in r.items() if k not in ('comparison_month','comparison_source_retrieval')} for r in previous if r['month_key'] not in targets]
        # Rebuild previous observations before recalculating any derived values.
        rows = [items.normalize([{k:r[k] for k in cpi.FIELDS}],r['source_retrieval'])[0] for r in rows]+refreshed
        rows = sorted(rows, key=lambda r:(r['month_key'],r['item_code']))
        items.validate(rows, sorted(expected), latest)
        source = retrieval.seal(True); sealed = True
        run_id = uuid.uuid4().hex; folder = root/'runs'/run_id
        blob = cpi.encoded(rows); immutable(folder/'normalized.json', blob)
        manifest = dict(run_id=run_id, latest_month=latest, coverage_start=months[0],
                        item_codes=sorted(expected), row_count=len(rows), rows_sha256=cpi.sha(blob),
                        source_retrieval=retrieval.id, refreshed_months=targets,
                        source_manifest_checksums={rid:cpi.sha((root/'raw/retrievals'/f'{rid}.json').read_bytes()) for rid in {r['source_retrieval'] for r in rows}})
        immutable(folder/'manifest.json', cpi.encoded(manifest))
        atomic_json(root/'current.json', dict(run_id=run_id,manifest_sha256=cpi.sha(cpi.encoded(manifest))))
        atomic_json(root/'last_attempt.json', dict(status='success',run_id=run_id,completed_at_utc=utc_now(),latest_month=latest))
        return manifest
    except Exception as exc:
        if not sealed: retrieval.seal(False)
        atomic_json(root/'last_attempt.json', dict(status='failed',error=str(exc),completed_at_utc=utc_now()))
        raise
    finally:
        if own: session.close()
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update', action='store_true', required=True)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    update()
