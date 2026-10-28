"""Auditable emerging-sector source collection; no network calls in the dashboard.

python -m data.fetchers.emerging_opportunity --as-of 2026-09-30
Official broad-index membership is a verified subset, never the full sector.
Raw source files, checksums and failures are retained alongside normalized data.
"""
from __future__ import annotations

import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import hashlib
import gzip
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
import zipfile
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from config.emerging_opportunity import SECTORS, EQUITY_SECTORS, BASE_STORE, AI_CONSTITUENTS, sector_store
from lxml import etree
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / 'data/stores/india/emerging_opportunity/consumer_services'
NSDL = 'https://pilot.fpi.nsdl.co.in/StaticReports/Fortnightly_Sector_wise_FII_Investment_Data/'
NSE = 'https://www.nseindia.com/api/corporate-share-holdings-master'
SECTOR = 'Consumer Services'


def number(value):
    result = float(str(value).replace(',', '').strip())
    if not pd.notna(result) or abs(result) == float('inf'):
        raise ValueError('Non-finite source number')
    return result


def month_end(day, offset=0):
    month = day.year * 12 + day.month - 1 + offset
    year, month = divmod(month, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def previous_fortnight(day):
    return month_end(day, -1) if day.day == 15 else day.replace(day=15)


def fortnight_window(end, count=12):
    days = [end]
    for _ in range(count - 1):
        days.append(previous_fortnight(days[-1]))
    return list(reversed(days))


def latest_completed_fortnight(today):
    completed = today - timedelta(days=1)
    return month_end(completed) if completed == month_end(completed) else completed.replace(day=15) if completed.day >= 15 else month_end(completed, -1)


def nsdl_url(day):
    label = day.strftime('%b%d%Y')
    if day.month == 6:
        label = day.strftime('June%d%Y')
    return NSDL + 'FIIInvestSector_' + label + '.html'


def parse_nsdl(raw, day, sector=SECTOR):
    if sector not in EQUITY_SECTORS:
        raise ValueError('Unsupported opportunity sector')
    soup = BeautifulSoup(raw, 'html.parser')
    text = soup.get_text(' ', strip=True)
    if day.strftime('%B %d, %Y').replace(' 0', ' ') not in text and day.strftime('%B %d, %Y') not in text:
        raise ValueError('NSDL report date mismatch')
    rows = []
    for tr in soup.find_all('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'], recursive=False)]
        if len(cells) == 98 and cells[1] == sector:
            rows.append(cells)
    if len(rows) != 1:
        raise ValueError('NSDL sector row or 12-column asset layout changed')
    c = rows[0]
    previous = previous_fortnight(day)
    # Mid-month reports contain the PREVIOUS month's second half followed by
    # the current month's first half; month-end reports contain both current halves.
    headers = next(([cell.get_text(' ', strip=True) for cell in tr.find_all(['td', 'th'], recursive=False)]
                    for tr in soup.find_all('tr') if len(tr.find_all(['td', 'th'], recursive=False)) == 6), [])
    def auc_label(d):
        return 'AUC as on ' + d.strftime('%B %d, %Y')
    if len(headers) != 6 or headers[2] != auc_label(previous) or headers[5] != auc_label(day):
        raise ValueError('NSDL fortnight block dates changed')
    records = []
    for end, flow_index, auc_index in [(previous, 26, 2), (day, 50, 74)]:
        records.append(dict(date=end.isoformat(), start=(previous_fortnight(end) + timedelta(days=1)).isoformat(),
                            equity_flow_cr=number(c[flow_index]), equity_flow_usd_m=number(c[flow_index + 12]),
                            end_equity_auc_cr=number(c[auc_index]), source_url=nsdl_url(day)))
    return records


def parse_shareholding(raw, symbol, quarter):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(raw, parser)
    ns = {'x': 'http://www.xbrl.org/2003/instance', 'd': 'http://xbrl.org/2006/xbrldi'}
    declared_symbols = [e.text for e in root if etree.QName(e).localname == 'Symbol']
    if declared_symbols != [symbol]:
        raise ValueError('Filing symbol mismatch')
    contexts = {}
    for c in root.findall('x:context', ns):
        instant = c.findtext('x:period/x:instant', namespaces=ns)
        identity = c.findtext('x:entity/x:identifier', namespaces=ns)
        members = c.findall('.//d:explicitMember', ns)
        if instant != quarter:
            continue
        # Named investor contexts carry extra dimensions and must never be summed
        # with their category aggregate.
        if len(members) == 1 and not c.findall('.//d:typedMember', ns):
            contexts[c.get('id')] = (members[0].text or '').split(':')[-1]
    facts = {}
    for e in root:
        ctx = e.get('contextRef')
        if ctx in contexts:
            facts.setdefault(contexts[ctx], {})[etree.QName(e).localname] = e.text
    groups = [(k, v) for k, v in facts.items() if ('ForeignPortfolioInvestor' in k or 'ForeignInstitutionalInvestor' in k)]
    # Prefer the aggregate over its category I/II children when both exist.
    aggregates = [(k, v) for k, v in groups if not re.search('Category(One|Two|I|II)', k)]
    if aggregates:
        groups = aggregates
    def shares(v):
        for key in ('NumberOfShares', 'TotalNumberOfShares', 'NumberOfFullyPaidUpEquityShares'):
            if key in v:
                return number(v[key])
        raise ValueError('Missing share count')
    fpi_shares = sum(shares(v) for _, v in groups) if groups else None
    total_candidates = [v for k, v in facts.items() if k in ('TotalMember', 'ShareholdingPatternTotalMember',
                                                            'TotalShareholdingMember', 'TotalShareholdingAsPerSCRRMember')]
    if not total_candidates:
        total_candidates = [v for k, v in facts.items() if k.lower().startswith('total') and 'NumberOfShares' in v]
    if not total_candidates:
        # Sum mutually exclusive top-level promoter/public/non-public categories.
        top = ('ShareholdingOfPromoterAndPromoterGroupMember', 'PublicShareholdingMember',
               'SharesHeldByNonPromoterNonPublicShareholdersMember')
        available = [facts[k] for k in top if k in facts]
        if not available or 'PublicShareholdingMember' not in facts:
            raise ValueError('Total shares context not found')
        # SCRR ownership percentages use A+B+C2. C1 custodians/DR shares
        # are excluded; adding their underlying receipts again inflates the denominator.
        total = sum(shares(facts[k]) for k in top[:2] if k in facts)
        nonpublic = facts.get(top[2], {})
        if nonpublic:
            total += shares(nonpublic) - number(nonpublic.get('NumberOfSharesUnderlyingOutstandingDepositoryReceipts', 0))
        for v in available:
            reported = v.get('ShareholdingAsAPercentageOfTotalNumberOfShares')
            numerator = shares(v) - number(v.get('NumberOfSharesUnderlyingOutstandingDepositoryReceipts', 0)) if v is nonpublic else shares(v)
            if reported is not None and abs(number(reported) - numerator / total) > .00015:
                raise ValueError('Total shares do not reconcile to reported category percentages')
    else:
        if len(total_candidates) != 1:
            raise ValueError('Ambiguous total shares')
        total = shares(total_candidates[0])
    if total <= 0 or (fpi_shares is not None and not 0 <= fpi_shares <= total):
        raise ValueError('Invalid FPI or total share count')
    result = dict(symbol=symbol, quarter=quarter, fpi_shares=int(fpi_shares) if fpi_shares is not None else None, total_shares=int(total),
                  fpi_pct=100 * fpi_shares / total if fpi_shares is not None else None)
    for prefix, member in [('dii', 'InstitutionsDomesticMember'), ('mf', 'MutualFundsOrUTIMember'),
                           ('insurance', 'InsuranceCompaniesMember')]:
        count = shares(facts[member]) if member in facts else None
        if count is not None and not 0 <= count <= total:
            raise ValueError('Invalid domestic institutional share count')
        result[prefix + '_shares'] = int(count) if count is not None else None
        result[prefix + '_pct'] = 100 * count / total if count is not None else None
    if result['dii_shares'] is not None:
        components = [result[k + '_shares'] for k in ('mf', 'insurance')]
        if sum(v for v in components if v is not None) > result['dii_shares']:
            raise ValueError('Domestic component counts exceed domestic aggregate')
    return result


class Collector:
    run_failures = {}
    run_cache = {}  # Reuse a freshly fetched URL across the weekly all-sector run.

    def __init__(self, store=None, refresh=False, sector=SECTOR):
        self.sector = sector
        self.store, self.refresh = Path(store) if store is not None else sector_store(sector), refresh
        (self.store / 'sources').mkdir(parents=True, exist_ok=True)
        self.receipts, self.failures = [], []

    def get(self, url, name):
        path = self.store / 'sources' / name
        if url in self.run_failures:
            raise ValueError(self.run_failures[url])
        if url in self.run_cache:
            raw = self.run_cache[url]
            if name.endswith('.xml'):
                path = path.with_suffix(path.suffix + '.gz')
                path.write_bytes(gzip.compress(raw, mtime=0))
            else:
                path.write_bytes(raw)
            self.receipts.append(dict(url=url, file='sources/' + path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            return raw
        zipped = path.with_suffix(path.suffix + '.gz') if name.endswith('.xml') else None
        if zipped and zipped.exists() and not self.refresh:
            raw = gzip.decompress(zipped.read_bytes())
        elif path.exists() and not self.refresh:
            raw = path.read_bytes()
        elif not self.refresh and (shared := next((candidate for folder in BASE_STORE.iterdir()
                if folder.is_dir() and (candidate := folder / 'sources' / (name + '.gz' if zipped else name)).exists()), None)):
            raw = gzip.decompress(shared.read_bytes()) if zipped else shared.read_bytes()
            if not zipped:
                path.write_bytes(raw)
        else:
            try:
                r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.nseindia.com/'}, timeout=45)
                r.raise_for_status()
            except requests.RequestException as exc:
                self.run_failures[url] = str(exc)
                raise
            raw = r.content
            if b'Access Denied' in raw or b'captcha' in raw[:5000].lower():
                raise ValueError('Source access denied')
            if not zipped:
                path.write_bytes(raw)
        if zipped:
            zipped.write_bytes(gzip.compress(raw, mtime=0))
            if path.exists():
                path.unlink()  # replace only our own generated raw archive with lossless gzip
            path = zipped
        self.receipts.append(dict(url=url, file='sources/' + path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        self.run_cache[url] = raw
        return raw

    def collect_flows(self, target, previous=None):
        previous = previous or {}
        observations = {r['date']: dict(r) for r in previous.get('flows', []) if r['date'] <= target.isoformat()}
        # Month-end archives each contain two periods; add the latest mid-month
        # report explicitly, so a new first half does not wait for month-end.
        reports = sorted(set([month_end(target, i) for i in range(-6, 1) if month_end(target, i) <= target] + [target]))
        for day in reports:
            name = 'nsdl-' + day.isoformat() + '.html'
            try:
                raw = self.get(nsdl_url(day), name)
            except Exception as exc:
                self.failures.append(dict(stage='sector_flows', identity=day.isoformat(), error=str(exc)))
                cached = self.store / 'sources' / name
                if not cached.exists():
                    continue
                raw = cached.read_bytes()
                self.receipts.append(dict(url=nsdl_url(day), file='sources/' + name, sha256=hashlib.sha256(raw).hexdigest()))
            try:
                for row in parse_nsdl(raw, day, self.sector):
                    if row['date'] <= target.isoformat():
                        observations[row['date']] = row
            except Exception as exc:
                self.failures.append(dict(stage='sector_flows', identity=day.isoformat(), error=str(exc)))
        # Publish only a complete contiguous window. A delayed report or outage
        # must not move the cutoff forward while erasing history or making gaps zero.
        for end in sorted(observations, reverse=True):
            expected = [d.isoformat() for d in fortnight_window(date.fromisoformat(end))]
            if all(d in observations for d in expected):
                flows = [observations[d] for d in expected]
                break
        else:
            raise ValueError('No complete validated FPI window; retaining the previous snapshot')
        for row in flows:
            prior = observations.get(previous_fortnight(date.fromisoformat(row['date'])).isoformat(), {}).get('end_equity_auc_cr')
            if prior is None:
                prior = next((r.get('opening_equity_auc_cr') for r in previous.get('flows', []) if r['date'] == row['date']), None)
            row['opening_equity_auc_cr'] = prior
            row['flow_pct_opening_auc'] = 100 * row['equity_flow_cr'] / prior if prior else None
        for url in {r['source_url'] for r in flows}:
            if not any(r['url'] == url for r in self.receipts):
                old = next(r for r in previous['sources'] if r['url'] == url)
                self.receipts.append(old)
        return flows, previous_fortnight(date.fromisoformat(flows[0]['date']))

    def collect(self, cutoff, flow_cutoff=None):
        from data.processors.emerging_opportunity import load
        previous = load(self.store, sector=self.sector) if (self.store / 'snapshot.json').exists() else {}
        target = flow_cutoff or cutoff
        flows, start = self.collect_flows(target, previous) if self.sector in EQUITY_SECTORS else ([], month_end(cutoff, -6))
        universe = {}
        expected_constituents = None
        baskets = [('ai_catalysts', AI_CONSTITUENTS)] if self.sector == 'AI Catalysts' else [
            (basket, 'https://nsearchives.nseindia.com/content/indices/ind_' + basket + '_list.csv')
            for basket in ('niftytotalmarket', 'niftymicrocap250')]
        for basket, url in baskets:
            try:
                frame = pd.read_csv(BytesIO(self.get(url, basket + '.csv')))
                # Source constituent files omit punctuation used in NSDL sector names.
                if self.sector == 'AI Catalysts':
                    expected_constituents = len(frame)
                industry = frame.Industry.str.replace(',', '', regex=False)
                selected = frame if self.sector == 'AI Catalysts' else frame[industry == self.sector.replace(',', '')]
                selected = selected[selected['ISIN Code'].str.startswith('INE', na=False) & selected.Series.isin(['EQ', 'BE'])]
                for _, row in selected.iterrows():
                    universe[row.Symbol] = dict(symbol=row.Symbol, name=row['Company Name'], sector=self.sector,
                                               industry=row.Industry, classification_url=url,
                                               baskets=sorted(set(universe.get(row.Symbol, {}).get('baskets', []) + [basket])))
            except Exception as exc:
                self.failures.append(dict(stage='universe', identity=basket, error=str(exc)))
        quarters = [month_end(cutoff, -i * 3).isoformat() for i in range(4, -1, -1)]
        fetched_at = datetime.now(timezone.utc).isoformat()
        previous_companies = {c['symbol']: c for c in previous.get('companies', [])}
        def company(item):
            symbol, entry = item
            holdings = [dict(h) for h in previous_companies.get(symbol, {}).get('holdings', []) if h['quarter'] in quarters]
            try:
                url = NSE + '?' + urlencode({'index': 'equities', 'symbol': symbol})
                filings = json.loads(self.get(url, 'filings-' + symbol + '.json'))
                if not isinstance(filings, list):
                    raise ValueError('Filings source is not an array')
                for quarter in quarters:
                    relevant = [f for f in filings if f.get('symbol') == symbol and
                                datetime.strptime(f['date'], '%d-%b-%Y').date().isoformat() == quarter and f.get('xbrl')]
                    if not relevant:
                        continue
                    filing = max(relevant, key=lambda f: datetime.strptime(f['broadcastDate'], '%d-%b-%Y %H:%M:%S'))
                    try:
                        raw = self.get(filing['xbrl'], symbol + '-' + quarter + '.xml')
                        row = parse_shareholding(raw, symbol, quarter)
                        row.update(source_url=filing['xbrl'], filed_at=filing['broadcastDate'])
                        holdings = [h for h in holdings if h['quarter'] != quarter] + [row]
                    except Exception as exc:
                        self.failures.append(dict(stage='holding', identity=symbol + ':' + quarter, error=str(exc)))
            except Exception as exc:
                self.failures.append(dict(stage='filings', identity=symbol, error=str(exc)))
            print(symbol, len(holdings), 'quarters', flush=True)
            return dict(entry, holdings=sorted(holdings, key=lambda h: h['quarter']))
        with ThreadPoolExecutor(max_workers=3) as pool:
            companies = list(pool.map(company, sorted(universe.items())))
        prices = {}
        url = 'https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_' + cutoff.strftime('%Y%m%d') + '_F_0000.csv.zip'
        try:
            raw = self.get(url, 'prices-' + cutoff.isoformat() + '.zip')
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                frame = pd.read_csv(archive.open(archive.namelist()[0]))
            for _, row in frame.iterrows():
                if row.get('TckrSymb') in universe and row.get('SctySrs') == 'EQ':
                    prices[row.TckrSymb] = float(row.ClsPric)
        except Exception as exc:
            self.failures.append(dict(stage='prices', identity=cutoff.isoformat(), error=str(exc)))
        for company in companies:
            company['reference_price'] = prices.get(company['symbol'])
        # Retained valid observations still need their original source receipts.
        for url in {h['source_url'] for c in companies for h in c['holdings']}:
            if not any(r['url'] == url for r in self.receipts):
                self.receipts.append(next(r for r in previous['sources'] if r['url'] == url))
        # Validate before publishing; a parser failure after a source revision must
        # not pair an old observation with changed source bytes.
        for receipt in self.receipts:
            if hashlib.sha256((self.store / receipt['file']).read_bytes()).hexdigest() != receipt['sha256']:
                raise ValueError('Retained source changed; refusing to publish an inconsistent snapshot')
        receipt_by_url = {r['url']: r for r in self.receipts}
        for company in companies:
            for holding in company['holdings']:
                receipt = receipt_by_url[holding['source_url']]
                raw = gzip.decompress((self.store / receipt['file']).read_bytes())
                actual = parse_shareholding(raw, company['symbol'], holding['quarter'])
                if any(holding[k] != value for k, value in actual.items()):
                    raise ValueError('Retained holding does not reconcile to its archive')
        snapshot = dict(schema_version=1, sector=self.sector, as_of=cutoff.isoformat(), collected_at=fetched_at,
                        window_start=start.isoformat(), ownership_as_of=cutoff.isoformat(),
                        flows_as_of=flows[-1]['date'] if flows else None, flows_checked_through=target.isoformat() if flows else None,
                        universe_scope='Current official Nifty AI Catalysts constituents; membership as collected, not historical membership.' if self.sector == 'AI Catalysts' else self.sector + ' members of NIFTY Total Market and NIFTY Microcap 250; verified subset of NSE listings. BSE-only and other non-members are excluded.',
                        universe_complete=self.sector == 'AI Catalysts' and len(companies) == expected_constituents and not any(f['stage'] == 'universe' for f in self.failures),
                        kind='theme' if self.sector == 'AI Catalysts' else 'sector', quarters=quarters, flows=flows, companies=companies,
                        price_date=cutoff.isoformat(), failures=self.failures, sources=sorted(self.receipts, key=lambda r: r['file']))
        snapshot['digest'] = hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()).hexdigest()
        (self.store / 'snapshot.json').write_text(json.dumps(snapshot, indent=2, allow_nan=False) + '\n')
        pd.DataFrame(flows).to_csv(self.store / 'fortnightly.csv', index=False)
        pd.DataFrame([dict(c, holdings=None) for c in companies]).drop(columns=['holdings'], errors='ignore').to_csv(self.store / 'universe.csv', index=False)
        pd.DataFrame([h for c in companies for h in c['holdings']]).to_csv(self.store / 'ownership.csv', index=False)
        print('Published', len(flows), 'fortnights;', len(companies), 'companies;', len(self.failures), 'source gaps', flush=True)
        return snapshot


def validate_datasets(sectors):
    from data.processors.emerging_opportunity import load, flow_metrics
    flow_cutoffs = set()
    datasets = {}
    for sector in sectors:
        data = load(sector=sector)
        datasets[sector] = data
        if not data['companies'] or any(f['stage'] == 'universe' for f in data['failures']):
            raise ValueError('Incomplete constituent sources: ' + sector)
        if sector in EQUITY_SECTORS:
            if not flow_metrics(data)['complete']:
                raise ValueError('Incomplete FPI window: ' + sector)
            flow_cutoffs.add(data.get('flows_as_of') or data['as_of'])
        elif not data['universe_complete']:
            raise ValueError('Incomplete AI constituents')
        print(sector, 'FPI:', data.get('flows_as_of') or (data['as_of'] if sector in EQUITY_SECTORS else 'not applicable'),
              'ownership:', data.get('ownership_as_of') or data['as_of'],
              'filings:', sum(len(c['holdings']) for c in data['companies']), 'source gaps:', len(data['failures']), flush=True)
    if len(flow_cutoffs) > 1:
        raise ValueError('Sector FPI cutoffs differ; refusing to publish mismatched rankings')
    return datasets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    today = datetime.now(ZoneInfo('Asia/Kolkata')).date()
    quarter_month = ((today.month - 1) // 3) * 3
    default = date(today.year, quarter_month, calendar.monthrange(today.year, quarter_month)[1]) if quarter_month else date(today.year - 1, 12, 31)
    parser.add_argument('--as-of', default=default.isoformat())
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--validate-only', action='store_true', help='Validate audited datasets without fetching sources')
    parser.add_argument('--latest-flows', action='store_true', help='Check the latest completed fortnight independently of ownership quarter')
    parser.add_argument('--sector', choices=[*SECTORS, 'all'], default=SECTOR)
    args = parser.parse_args()
    sectors = list(SECTORS) if args.sector == 'all' else [args.sector]
    if args.validate_only:
        validate_datasets(sectors)
        return
    cutoff = date.fromisoformat(args.as_of)
    if cutoff != month_end(cutoff) or cutoff.month % 3:
        parser.error('--as-of must be a completed quarter end')
    for sector in sectors:
        Collector(refresh=args.refresh, sector=sector).collect(cutoff, latest_completed_fortnight(today) if args.latest_flows else cutoff)


if __name__ == '__main__':
    main()
