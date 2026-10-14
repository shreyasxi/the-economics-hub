"""Comparable-panel ownership statistics; missing data never becomes zero."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pandas as pd
from config.emerging_opportunity import SECTORS, sector_store

STORE = Path(__file__).resolve().parents[2] / 'data/stores/india/emerging_opportunity/consumer_services'

# Business buckets are editorial navigation aids, not official NSE sub-industry codes.
BUCKETS = {
    'Hotels & leisure': ['CHALET', 'EIHOTEL', 'INDHOTEL', 'ITCHOTELS', 'LEMONTREE', 'SAMHI', 'THELEELA'],
    'Restaurants': ['DEVYANI', 'JUBLFOOD', 'RBA', 'SAPPHIRE', 'WESTLIFE'],
    'Retail & distribution': ['ABFRL', 'ABLBL', 'AVL', 'ARVINDFASN', 'DMART', 'EMIL', 'ENTERO', 'MANYAVAR',
                              'MEDPLUS', 'TRENT', 'VMART', 'V2RETAIL', 'VMM', 'LENSKART'],
    'Digital platforms': ['ETERNAL', 'SWIGGY', 'NYKAA', 'FIRSTCRY', 'MEESHO', 'CARTRADE', 'INDIAMART',
                          'NAUKRI', 'JUSTDIAL'],
    'Travel services': ['IRCTC', 'IXIGO', 'TBOTEK', 'THOMASCOOK'],
    'Education & other services': ['PWL', 'JSLL', 'BLS', 'URBANCO'],
}

SECTOR_BUCKETS = {
    'Consumer Services': BUCKETS,
    'Services': {
        'Ports & marine services': ['ADANIPORTS', 'GPPL', 'JSWINFRA', 'KMEW', 'SHREEJISPG'],
        'Shipping': ['GESHIP', 'SCI'],
        'Logistics & supply chains': ['BLACKBUCK', 'CONCOR', 'DELHIVERY', 'SHADOWFAX', 'TVSSCS'],
        'Aviation & airports': ['GMRAIRPORT', 'INDIGO'],
        'Business & workplace services': ['CMSINFO', 'FSL', 'ECLERX', 'QUESS', 'WEWORK'],
        'Trading & distribution': ['MMTC', 'MSTCLTD', 'REDINGTON'],
        'Technical & certification services': ['CMPDI', 'IGIL'],
    },
    'Textiles': {
        'Textile mills': ['ARVIND', 'KPRMILL', 'VTL'],
        'Home textiles': ['ICIL', 'TRIDENT', 'WELSPUNLIV'],
        'Apparel & sourcing': ['GOKEX', 'KITEX', 'PDSL', 'PGIL', 'PAGEIND', 'RAYMONDLSL'],
    },
}


def load(store=None, sector=None):
    store = Path(store) if store is not None else sector_store(sector or 'Consumer Services')
    data = json.loads((store / 'snapshot.json').read_text())
    if data['schema_version'] != 1 or data['sector'] not in SECTORS or (sector is not None and data['sector'] != sector):
        raise ValueError('Unsupported opportunity snapshot')
    for receipt in data['sources']:
        path = store / receipt['file']
        if not path.resolve().is_relative_to(store.resolve()):
            raise ValueError('Invalid source path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['sha256']:
            raise ValueError('Source checksum mismatch: ' + receipt['file'])
    if hashlib.sha256(json.dumps({k: v for k, v in data.items() if k != 'digest'},
                                sort_keys=True, allow_nan=False).encode()).hexdigest() != data.get('digest'):
        raise ValueError('Normalized data checksum mismatch')
    days = [r['date'] for r in data['flows']]
    if len(days) != len(set(days)) or days != sorted(days):
        raise ValueError('Duplicate or unordered fortnights')
    symbols = [c['symbol'] for c in data['companies']]
    if len(symbols) != len(set(symbols)):
        raise ValueError('Duplicate company identity')
    return data


def flow_metrics(data):
    rows = data['flows']
    from data.fetchers.emerging_opportunity import fortnight_window
    from datetime import date
    cutoff = data.get('flows_as_of') or data['as_of']
    expected_days = [d.isoformat() for d in fortnight_window(date.fromisoformat(cutoff))]
    complete = [r['date'] for r in rows] == expected_days
    longest = current = 0
    cumulative = 0
    frame = []
    last_date = None
    for row in rows:
        flow = row['equity_flow_cr']
        index = expected_days.index(row['date'])
        adjacent = last_date is None or index == expected_days.index(last_date) + 1
        current = (current + 1 if adjacent else 1) if flow > 0 else 0
        longest = max(longest, current)
        cumulative += flow
        frame.append(dict(row, cumulative_cr=cumulative))
        last_date = row['date']
    return dict(net_cr=cumulative, positive=sum(r['equity_flow_cr'] > 0 for r in rows),
                count=len(rows), expected=len(expected_days), complete=complete, longest_streak=longest,
                current_streak=current, rows=frame)


def company_panel(data, quarter, investor='fpi'):
    if investor not in ('fpi', 'dii', 'mf', 'insurance'):
        raise ValueError('Unsupported ownership group')
    position = data['quarters'].index(quarter)
    if position == 0:
        raise ValueError('No prior quarter available')
    previous = data['quarters'][position - 1]
    rows = []
    for company in data['companies']:
        holdings = {h['quarter']: h for h in company['holdings']}
        now, before = holdings.get(quarter), holdings.get(previous)
        pct_key, shares_key = investor + '_pct', investor + '_shares'
        current_pct = now.get(pct_key) if now else None
        previous_pct = before.get(pct_key) if before else None
        buckets = SECTOR_BUCKETS.get(data['sector'], {})
        bucket = next((k for k, names in buckets.items() if company['symbol'] in names), company.get('industry', data['sector']))
        row = dict(symbol=company['symbol'], company=company['name'], bucket=bucket,
                   ownership_pct=current_pct, prior_ownership_pct=previous_pct,
                   fpi_pct=now['fpi_pct'] if now else None,
                   change_pp=None, addition_cr=None, status='Missing filing', streak=None,
                   source_url=now['source_url'] if now else None, capital_change=False,
                   ownership_shares=now.get(shares_key) if now else None, total_shares=now['total_shares'] if now else None,
                   investor=investor)
        for group in ('fpi', 'dii', 'mf', 'insurance'):
            value = now.get(group + '_pct') if now else None
            prior = before.get(group + '_pct') if before else None
            row[group + '_ownership_pct'] = value
            row[group + '_change_pp'] = value - prior if value is not None and prior is not None else None
        if now and before and (current_pct is None or previous_pct is None):
            row['status'] = 'Missing ownership category'
        if current_pct is not None and previous_pct is not None:
            row['change_pp'] = current_pct - previous_pct
            # No inference of buying when issuance, buybacks, splits or mergers
            # change the denominator. Retain reported ownership, exclude comparisons.
            row['capital_change'] = now['total_shares'] != before['total_shares']
            row['status'] = 'Capital change — review' if row['capital_change'] else (
                'Increase' if row['change_pp'] > .01 else 'Decrease' if row['change_pp'] < -.01 else 'Flat')
            streak = 0
            for index in range(position, 0, -1):
                a, b = holdings.get(data['quarters'][index]), holdings.get(data['quarters'][index - 1])
                if not a or not b or a.get(pct_key) is None or b.get(pct_key) is None or a['total_shares'] != b['total_shares'] or a[pct_key] - b[pct_key] <= .01:
                    break
                streak += 1
            row['streak'] = streak
            if not row['capital_change'] and company['reference_price'] is not None:
                row['addition_cr'] = (now[shares_key] - before[shares_key]) * company['reference_price'] / 1e7
        rows.append(row)
    comparable = [r for r in rows if r['status'] in ('Increase', 'Decrease', 'Flat')]
    increases = [r for r in comparable if r['status'] == 'Increase']
    additions = sorted([r for r in comparable if r['addition_cr'] is not None and r['addition_cr'] > 0],
                       key=lambda r: r['addition_cr'], reverse=True)
    total = sum(r['addition_cr'] for r in additions)
    for row in additions:
        row['share_of_additions_pct'] = row['addition_cr'] / total * 100 if total else None
    return dict(quarter=quarter, previous=previous, rows=rows, comparable=len(comparable),
                universe=len(rows), filed=sum(r['total_shares'] is not None for r in rows),
                ownership_reported=sum(r['ownership_pct'] is not None for r in rows),
                increases=len(increases), decreases=sum(r['status'] == 'Decrease' for r in comparable),
                flat=sum(r['status'] == 'Flat' for r in comparable),
                breadth_pct=100 * len(increases) / len(comparable) if comparable else None,
                exclusions=sum(r['capital_change'] for r in rows), additions=additions,
                top3_pct=100 * sum(r['addition_cr'] for r in additions[:3]) / total if total else None,
                priced_comparable=sum(r['addition_cr'] is not None for r in comparable))


def institutional_agreement(data, quarter):
    """Compare FPI and domestic changes on the exact same matched-capital panel."""
    rows = company_panel(data, quarter)['rows']
    result = []
    for row in rows:
        fpi, dii = row['fpi_change_pp'], row['dii_change_pp']
        if row['status'] not in ('Increase', 'Decrease', 'Flat') or fpi is None or dii is None:
            continue
        label = ('Both increasing' if fpi > .01 and dii > .01 else
                 'FPI increasing / DII decreasing' if fpi > .01 and dii < -.01 else
                 'DII increasing / FPI decreasing' if dii > .01 and fpi < -.01 else
                 'Both decreasing' if fpi < -.01 and dii < -.01 else 'Includes flat ownership')
        result.append(dict(row, agreement=label))
    return result
