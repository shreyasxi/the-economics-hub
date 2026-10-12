"""Prepare the four overview cards before rendering.

Default: local preview, using cached market inputs. --refresh-market downloads
market histories. --publish writes assets/macro_cards.json; --only selects the
workflow's domain. Failed sources retain previously validated, dated cards and
emit Actions warnings. No database writes or inference during page rendering.
"""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from data.paths import INDIA_DB
from data.processors.macro_cards import (
    answer, market_risk, global_inflation, india_activity, india_inflation,
)

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / 'output/card_preview/macro_cards.json'
PUBLISHED = ROOT / 'assets/macro_cards.json'
MARKET_INPUTS = PREVIEW.parent / 'market_inputs.json'


def read(folder, filename):
    return json.loads((folder / filename).read_text())


def latest(domain):
    editions = sorted(p for p in (ROOT / 'assets' / domain).iterdir() if p.is_dir())
    if not editions:
        raise ValueError(f'No published {domain} edition')
    return editions[-1]


def activity_card(folder):
    from data.fetchers.mospi_iip import load as load_iip
    from charts.india_charts.india_mospi_activity import validate_heatmap
    industries = read(folder, 'india_iip_industry_heatmap.json')
    validate_heatmap(industries)
    with sqlite3.connect(f'file:{INDIA_DB}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        monthly = [dict(r) for r in conn.execute('SELECT * FROM india_monthly ORDER BY month')]
    return india_activity(monthly, load_iip(INDIA_DB), industries)


def inflation_card(folder):
    from data.processors import cpi_contributions, cpi_items
    _, derived, contributions_manifest = cpi_contributions.load_current()
    items, items_manifest = cpi_items.load_current()
    if read(folder, '24_india_cpi_contributions.json')['run_id'] != contributions_manifest['run_id']:
        raise ValueError('CPI contribution edition differs from accepted run')
    if read(folder, '06b_india_cpi_items.json')['run_id'] != items_manifest['run_id']:
        raise ValueError('CPI item edition differs from accepted run')
    return india_inflation(derived, items)


def generate(destination=PREVIEW, scope='all', refresh_market=False):
    destination = Path(destination)
    payload = json.loads(destination.read_text()) if destination.exists() else dict(schema_version=1, cards={}, editions={})
    if payload.get('schema_version') != 1:
        raise ValueError('Unknown overview schema')
    updates, errors = {}, {}
    domains = ['markets','world','india'] if scope == 'all' else [scope]
    for domain in domains:
        try:
            folder = latest({'markets':'weekly','world':'macro','india':'india'}[domain])
            if domain == 'markets':
                if refresh_market:
                    from data.processors.market_regime import fetch_inputs
                    signals = read(folder, 'signals.json')
                    inputs = fetch_inputs(signals['week']['to'])
                elif MARKET_INPUTS.exists():
                    inputs = json.loads(MARKET_INPUTS.read_text())
                else:
                    inputs = payload['market_inputs']
                candidates = {'risk':market_risk(inputs)}
            elif domain == 'world':
                candidates = {'global_inflation':global_inflation(read(folder, 'world_snapshot.json'))}
            else:
                # These two independently sourced cards must not block each other.
                candidates = {}
                for key, build in [('india_activity',activity_card),('india_inflation',inflation_card)]:
                    try:
                        candidates[key] = build(folder)
                    except Exception as exc:
                        errors[key] = type(exc).__name__
            for key, card in candidates.items():
                if card['state'] == 'Awaiting data' and key in payload['cards']:
                    errors[key] = 'Insufficient comparable observations'
                    continue
                updates[key] = card
            if domain == 'markets' and 'risk' in updates:
                payload['market_inputs'] = inputs
                if not refresh_market:
                    # Do not claim the cached regime belongs to a newer weekly edition.
                    folder = ROOT / payload.get('editions',{}).get('weekly',str(folder.relative_to(ROOT)))
            if any(key in updates for key in candidates):
                payload.setdefault('editions',{})[{'markets':'weekly','world':'macro','india':'india'}[domain]] = str(folder.relative_to(ROOT))
        except Exception as exc:
            errors[domain] = type(exc).__name__
    payload['cards'].update(updates)
    for key in ('risk','global_inflation','india_activity','india_inflation'):
        payload['cards'].setdefault(key, answer('Awaiting data','A validated dated snapshot is unavailable.'))
    payload['generated_at'] = datetime.now(timezone.utc).isoformat()
    payload['refresh_errors'] = errors
    payload['methodology'] = ('Three-month market environment; one-month momentum; sustained VIX; commodity context. '
                              'Two-thirds agreement within breadth pillars; 80% matched inflation coverage; '
                              '±0.05 pp = little changed. Unweighted counts; no GDP/GVA.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,indent=2)+'\n')
    temporary.replace(destination)
    for key, error in errors.items():
        print(f'::warning title=Overview card refresh incomplete::{key}: {error}; retained the last validated card and its original dates where available.')
    for key, card in updates.items():
        print(f"{key}: {card['state']} — {card['evidence']}")
    print(f'Overview written to {destination}')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--refresh-market',action='store_true')
    parser.add_argument('--only',choices=['all','markets','world','india'],default='all')
    args = parser.parse_args()
    errors = generate(PUBLISHED if args.publish else PREVIEW,args.only,args.refresh_market)
    raise SystemExit(1 if errors else 0)
