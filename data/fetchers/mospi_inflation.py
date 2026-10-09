"""Main CPI bridge using the contribution collector's official source layer.

Published rates only. Historical CPI 2012 ends Dec 2025; CPI 2024 starts Jan
2026. A manual conflict blocks the entire DB transaction and the main chart,
but never invalidates the independent contribution chart.
"""
import argparse
import calendar
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3

import requests

from data.processors import cpi_contributions as cpi
from data.processors.india_db_manager import DB_PATH
from data.fetchers.mospi_cpi import Retrieval, fetch_pages, atomic_json, immutable

from data.paths import CPI_MAIN_DIR

ROOT = CPI_MAIN_DIR
LOG = logging.getLogger(__name__)
TARGETS = {'CPI (General)': 'india_cpi_yoy', 'Food and beverages': 'india_food_cpi_yoy'}
OLD_FIELDS = {'baseyear','year','month','state','sector','group','subgroup','index','inflation','status'}


def old_history(raw):
    selected = []
    concepts = {'General': ('General-Overall', 'india_cpi_yoy'),
                'Food and Beverages': ('Food and Beverages-Overall', 'india_food_cpi_yoy')}
    seen = set()
    for r in raw:
        cpi.require(set(r) == OLD_FIELDS, '2012 history schema changed')
        cpi.require(r['baseyear']=='2012' and r['state']=='All India' and r['sector']=='Combined', '2012 history scope changed')
        cpi.require(type(r['year']) is int and r['month'] in calendar.month_name[1:], '2012 history period changed')
        month = f"{r['year']}-{list(calendar.month_name).index(r['month']):02d}"
        cpi.require('2024-01' <= month <= '2025-12', '2012 history outside declared period')
        if r['group'] not in concepts:
            cpi.require(r['group']=='Consumer Food Price', 'unexpected old CPI concept')
            continue  # CFPI was inspected for the audit, never mapped to food.
        subgroup, column = concepts[r['group']]
        cpi.require(r['subgroup']==subgroup and r['status'] in ('F','P'), '2012 aggregate/status changed')
        cpi.require(cpi.numeric(r['index']) > 0, 'invalid historical index')
        value = cpi.numeric(r['inflation'])
        cpi.require((-5 <= value <= 25) if column=='india_cpi_yoy' else (-10 <= value <= 30), 'CPI sanity bounds')
        cpi.require((month,column) not in seen, 'duplicate old CPI aggregate')
        seen.add((month,column))
        selected.append(dict(month=month,column=column,value=float(value),base='2012',concept=r['group']))
    cpi.require(seen == {(m,col) for m in cpi.months_between('2024-01','2025-12') for col in TARGETS.values()}, 'missing old CPI history')
    return selected


def current_rates(rows):
    cpi.validate(rows)
    result = []
    for r in rows:
        month = cpi.period(r)
        if month >= '2026-01' and r['division'] in TARGETS:
            column = TARGETS[r['division']]
            value = cpi.numeric(r['inflation'])
            cpi.require((-5 <= value <= 25) if column=='india_cpi_yoy' else (-10 <= value <= 30), 'CPI sanity bounds')
            result.append(dict(month=month,column=column,value=float(value),base='2024',
                               concept=r['division'],source_retrieval=r.get('source_retrieval')))
    return result


def apply_rates(db, rates, *, accept_manual_conflicts=False):
    """All-or-nothing; manual values remain manual even when confirmed.

    <=0.005 pp is equivalent at CPI's two-decimal publication precision.
    Old unflagged/FRED values may migrate, with every before/after archived.
    Official revisions may replace official values and retain an audit trail.
    Differing manual values require an explicit, audited acceptance flag.
    """
    changes, conflicts = [], []
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        for rate in rates:
            month, column, value = rate['month'],rate['column'],rate['value']
            cpi.require(column in TARGETS.values(), 'unexpected DB target')
            old = conn.execute('SELECT * FROM india_monthly WHERE month=?',(month,)).fetchone()
            flags = json.loads(old['source_flags'] or '{}') if old else {}
            before = old[column] if old else None
            manual = str(flags.get(column,'')).startswith('manual:')
            equivalent = before is not None and abs(before-value) <= .005000001
            approved = manual and not equivalent and accept_manual_conflicts
            if manual and not equivalent and not approved:
                conflict = dict(rate,stored=before,stored_source=flags[column])
                conflicts.append(conflict)
                LOG.error('MANUAL CPI CONFLICT %s %s: stored=%s official=%s (%s, base %s); NOT overwritten',
                          month,column,before,value,rate['concept'],rate['base'])
            changes.append(dict(rate,before=before,previous_source=flags.get(column),manual=manual,equivalent=equivalent,manual_conflict_approved=approved))
        if conflicts:
            return dict(status='conflict', conflicts=conflicts, changes=changes, committed=False)
        # Journal before/after inside the same SQLite transaction as values.
        # A crash after the commit cannot lose the previous manual/legacy value.
        conn.execute('''CREATE TABLE IF NOT EXISTS india_cpi_observation_audit (
            id INTEGER PRIMARY KEY, recorded_at_utc TEXT NOT NULL,
            month TEXT NOT NULL, column_name TEXT NOT NULL, payload TEXT NOT NULL)''')
        for change in changes:
            month,column,value = change['month'],change['column'],change['value']
            conn.execute('INSERT OR IGNORE INTO india_monthly (month) VALUES (?)',(month,))
            row = conn.execute('SELECT source_flags FROM india_monthly WHERE month=?',(month,)).fetchone()
            flags = json.loads(row[0] or '{}')
            flags[column+':official_confirmation'] = f"mospi_api:base{change['base']}:{change['concept']}"
            if not change['manual'] or change['manual_conflict_approved']:
                conn.execute('INSERT INTO india_cpi_observation_audit (recorded_at_utc,month,column_name,payload) VALUES (?,?,?,?)',
                             (datetime.now(timezone.utc).isoformat(),month,column,json.dumps(change)))
                flags[column] = f"official:mospi_api:base{change['base']}:{change['concept']}"
                conn.execute(f'UPDATE india_monthly SET {column}=? WHERE month=?',(value,month))
            if change['manual_conflict_approved']:
                LOG.warning('APPROVED MANUAL CPI RESOLUTION %s %s: %s -> %s; previous source archived',month,column,change['before'],value)
            if change['before'] is not None and not change['equivalent']:
                LOG.warning('CPI HISTORY/REVISION %s %s: %s -> %s; previous source %s',month,column,change['before'],value,change['previous_source'])
            conn.execute('UPDATE india_monthly SET source_flags=?,fetched_at=? WHERE month=?',
                         (json.dumps(flags),datetime.now(timezone.utc).isoformat(),month))
    return dict(status='ready',conflicts=[],changes=changes,committed=True)


def update(db=DB_PATH, root=ROOT, source_root=cpi.ROOT, session=None, *, accept_manual_conflicts=False):
    root = Path(root)
    atomic_json(root/'status.json',dict(status='running'))
    try:
        rows,_,manifest = cpi.load_current(source_root)
        history_path = root/'history_2012.json'
        if history_path.exists():
            history = json.loads(history_path.read_text())
            cpi.require(history['sha256']==cpi.sha(cpi.encoded(history['raw'])), 'old history checksum mismatch')
            raw = history['raw']
        else:
            own = session is None
            session = session or requests.Session()
            retrieval = Retrieval(root,session)
            try:
                raw = fetch_pages(retrieval,dict(base_year='2012',state_code=99,level='Group',
                     year='2024,2025',group_code='0,1,7',subgroup_code='0.99,1.99,7.99'))
                old_history(raw)  # Validate before sealing a reusable history.
                source = retrieval.seal(True,scope=dict(base_year='2012',state_code=99,sector_code=3,series='Current'))
                immutable(history_path,cpi.encoded(dict(raw=raw,sha256=cpi.sha(cpi.encoded(raw)),source_retrieval=source['retrieval_id'])))
            except Exception:
                retrieval.seal(False,scope=dict(base_year='2012',state_code=99))
                raise
            finally:
                if own: session.close()
        rates = old_history(raw)+current_rates(rows)
        # Preserve candidates before any database mutation, including conflicts.
        identifier = manifest['run_id']
        immutable(root/'candidates'/f'{identifier}.json',cpi.encoded(rates))
        result = apply_rates(db,rates,accept_manual_conflicts=accept_manual_conflicts)
        result.update(latest_month=manifest['latest_month'],source_run=identifier,
                      checked_at_utc=datetime.now(timezone.utc).isoformat(),
                      history_note='2012 through Dec 2025; 2024 from Jan 2026; food is Food and beverages, not CFPI')
        atomic_json(root/'runs'/f'{identifier}.json',result)
        atomic_json(root/'status.json',result)
        return result
    except Exception as exc:
        atomic_json(root/'status.json',dict(status='failed',error=str(exc),checked_at_utc=datetime.now(timezone.utc).isoformat()))
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,default=DB_PATH)
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--source-root',type=Path,default=cpi.ROOT)
    p.add_argument('--accept-manual-conflicts',action='store_true',
                   help='Explicitly accept validated official CPI values over conflicting manual entries, preserving an audit trail')
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:
        result=update(args.db,args.root,args.source_root,accept_manual_conflicts=args.accept_manual_conflicts)
        if result['status']!='ready': p.exit(1,f"MAIN CPI BLOCKED: {len(result['conflicts'])} manual conflicts; database unchanged\n")
        LOG.info('Main CPI ready through %s',result['latest_month'])
    except (ValueError,OSError,requests.RequestException,KeyError,TypeError) as exc:
        p.exit(1,f'MAIN CPI FAILED: {exc}\n')


if __name__=='__main__': main()
