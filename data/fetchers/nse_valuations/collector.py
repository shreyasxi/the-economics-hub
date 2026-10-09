"""Official NSE valuation archives: historical audit and incremental production update."""
import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import statistics
import time
import requests

from data.paths import NSE_VALUATIONS_DIR

ROOT = NSE_VALUATIONS_DIR
URL = 'https://archives.nseindia.com/content/indices/ind_close_all_{date}.csv'
NAMES = ['Nifty 50', 'Nifty Auto', 'Nifty Bank', 'Nifty Financial Services', 'Nifty FMCG', 'Nifty IT', 'Nifty Metal', 'Nifty Pharma', 'Nifty PSU Bank', 'Nifty Realty', 'Nifty Private Bank', 'Nifty Oil & Gas', 'Nifty Healthcare Index', 'Nifty Consumer Durables']
SCHEMA = ['Index Name', 'Index Date', 'Open Index Value', 'High Index Value', 'Low Index Value', 'Closing Index Value', 'Points Change', 'Change(%)', 'Volume', 'Turnover (Rs. Cr.)', 'P/E', 'P/B', 'Div Yield']
METRICS = ['P/E', 'P/B', 'Div Yield']
PROVISIONAL = {'Nifty Auto':'P/E', 'Nifty FMCG':'P/E', 'Nifty IT':'P/E', 'Nifty Pharma':'P/E', 'Nifty Bank':'P/B', 'Nifty Private Bank':'P/B', 'Nifty PSU Bank':'P/B', 'Nifty Financial Services':'P/B'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def parse(payload, expected_date):
    text = payload.decode('utf-8-sig')
    if '<html' in text.lower() or '<!doctype' in text.lower():
        raise ValueError('HTML/error content is not CSV')
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != SCHEMA:
        raise ValueError('Expected exact NSE schema: ' + repr(reader.fieldnames))
    result, seen = {}, set()
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Malformed CSV row')
        name = row['Index Name']
        if name in seen:
            raise ValueError('Duplicate index: ' + name)
        seen.add(name)
        if datetime.strptime(row['Index Date'], '%d-%m-%Y').date() != expected_date:
            raise ValueError('Index Date differs from requested source date')
        # Exact identity only: no case folding, fuzzy matching, or aliases.
        if name not in NAMES:
            continue
        for metric in METRICS:
            value = row[metric].strip()
            if value in ('', '-'):
                # Official missing markers remain exact in extracted.csv/raw.csv.
                continue
            try:
                number = Decimal(value)
            except InvalidOperation:
                raise ValueError(f'Invalid {metric} for {name}: {value!r}')
            if not number.is_finite():
                raise ValueError('Non-finite valuation')
        result[name] = {k: row[k] for k in ['Index Name', 'Index Date'] + METRICS}
    if not seen or 'Nifty 50' not in result:
        raise ValueError('Empty archive or missing exact Nifty 50 identity')
    return result


def fetch(day, root, revalidate=False):
    folder = root / 'sources' / day.isoformat()
    meta_path = folder / 'manifest.json'
    cached = None
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        payload = (folder / 'raw.csv').read_bytes()
        if sha(payload) != meta['sha256'] or meta['observation_date'] != day.isoformat() or meta['source_url'] != URL.format(date=day.strftime('%d%m%Y')):
            raise ValueError('Cached provenance/checksum mismatch')
        cached = (parse(payload, day), meta)
        if not revalidate:
            return cached[0], cached[1], []
    url = URL.format(date=day.strftime('%d%m%Y'))
    attempts = []
    for retry in range(3):
        item = {'source_url':url, 'requested_date':day.isoformat(), 'retrieved_at':stamp()}
        try:
            response = requests.get(url, timeout=30, headers={'User-Agent':'EconomicsHub NSE historical valuation audit'})
            item.update(http_status=response.status_code, content_type=response.headers.get('Content-Type'), sha256=sha(response.content))
            if response.status_code in (404, 410):
                item['outcome'] = 'archive_not_found'
                attempts.append(item)
                return None, None, attempts
            response.raise_for_status()
            rows = parse(response.content, day)
            if 'html' in response.headers.get('Content-Type', '').lower():
                raise ValueError('HTML Content-Type')
            item['outcome'] = 'validated_csv'
            attempts.append(item)
            if cached is not None:
                if sha(response.content) != cached[1]['sha256']:
                    raise ValueError('Official archive changed; immutable source retained for review')
                return rows, cached[1], attempts
            folder.mkdir(parents=True, exist_ok=True)
            meta = dict(source_url=url, observation_date=day.isoformat(), retrieved_at=item['retrieved_at'], sha256=item['sha256'], bytes=len(response.content), content_type=item['content_type'], exact_target_names=list(rows))
            # Exclusive creation preserves source bytes and original retrieval time.
            with (folder / 'raw.csv').open('xb') as out:
                out.write(response.content)
            with meta_path.open('x') as out:
                json.dump(meta, out, indent=2)
            return rows, meta, attempts
        except (requests.RequestException, ValueError) as exc:
            item.update(outcome='unresolved_error', error=str(exc))
            attempts.append(item)
            if retry < 2:
                time.sleep(1 + retry)
    return None, None, attempts


def collect_month(month, cutoff, root):
    y, m = map(int, month.split('-'))
    day = min(date(y, m, calendar.monthrange(y, m)[1]), cutoff)
    attempts = []
    while day.month == m:
        rows, meta, tried = fetch(day, root)
        attempts.extend(tried)
        if rows is not None:
            return dict(month=month, status='validated', source=meta, rows=rows, attempts=attempts, partial_month=cutoff < date(y,m,calendar.monthrange(y,m)[1]))
        if tried and tried[-1]['outcome'] != 'archive_not_found':
            return dict(month=month, status='unresolved', rows={}, attempts=attempts)
        day -= timedelta(days=1)
    return dict(month=month, status='no_archive_found', rows={}, attempts=attempts)


def months_to(cutoff):
    y, m = 2016, 10
    result = []
    while (y,m) <= (cutoff.year, cutoff.month):
        result.append(f'{y:04d}-{m:02d}')
        y, m = (y+1,1) if m == 12 else (y,m+1)
    return result


def longest(flags):
    best = run = 0
    for missing in flags:
        run = run+1 if missing else 0
        best = max(best, run)
    return best


def write_csv(path, rows, fields):
    with path.open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit(results, root, cutoff, start_month="2016-10"):
    normalized, coverage, extracted = [], [], []
    seen = set()
    for entry in results:
        for name in NAMES:
            key = (entry['month'], name)
            if key in seen:
                raise ValueError('Duplicate month/index')
            seen.add(key)
            row = entry['rows'].get(name)
            meta = entry.get('source', {})
            if row:
                extracted.append(dict(month=entry['month'], **row, **{k:meta.get(k,'') for k in ['observation_date','retrieved_at','source_url','sha256']}))
            normalized.append(dict(month=entry['month'], **{'Index Name':name, 'Index Date':row['Index Date'] if row else '', **{k:row[k].strip() if row and row[k].strip() not in ('', '-') else '' for k in METRICS}}, index_present=bool(row), archive_status=entry['status'], partial_month=entry.get('partial_month',False), observation_date=meta.get('observation_date',''), retrieved_at=meta.get('retrieved_at',''), source_url=meta.get('source_url',''), sha256=meta.get('sha256','')))
    write_csv(root/'extracted.csv', extracted, ['month', 'Index Name', 'Index Date']+METRICS+['observation_date','retrieved_at','source_url','sha256'])
    write_csv(root/'monthly.csv', normalized, list(normalized[0]))
    details = {}
    for name in NAMES:
        panel = [r for r in normalized if r['Index Name']==name]
        present = [r for r in panel if r['index_present']]
        record = dict(index=name, first_available_month=present[0]['month'] if present else '', last_available_month=present[-1]['month'] if present else '', expected_months=len(panel), months_present=len(present))
        details[name] = {}
        for metric, tag in [('P/E','pe'), ('P/B','pb')]:
            values = [float(r[metric]) for r in panel if r[metric]!='']
            missing = [r['month'] for r in panel if r[metric]=='']
            full_window = [r for r in panel if '2016-10' <= r['month'] <= '2026-09']
            record.update({tag+'_valid':len(values),tag+'_missing':len(missing),tag+'_longest_gap':longest([r[metric]=='' for r in panel]),tag+'_coverage_pct':round(100*len(values)/len(panel),2),tag+'_coverage_since_first_pct':round(100*len(values)/len([r for r in panel if present and r['month']>=present[0]['month']]),2) if present else 0,tag+'_at_least_60':len(values)>=60,tag+'_full_10_years':len(full_window)==120 and all(r[metric]!='' for r in full_window)})
            details[name][metric] = dict(first_valid_month=next((r['month'] for r in panel if r[metric]!=''),None), last_valid_month=next((r['month'] for r in reversed(panel) if r[metric]!=''),None), valid_complete_months=sum(r[metric]!='' and not r['partial_month'] for r in panel), missing_months=missing, missing_while_present=[r['month'] for r in panel if r['index_present'] and r[metric]==''], min=min(values) if values else None, median=statistics.median(values) if values else None, max=max(values) if values else None, nonpositive_months=[r['month'] for r in panel if r[metric]!='' and float(r[metric])<=0], largest_changes=sorted([dict(month=b['month'], previous_month=a['month'], ratio=float(b[metric])/float(a[metric])) for a,b in zip(panel,panel[1:]) if a[metric]!='' and b[metric]!='' and float(a[metric])>0],key=lambda r:abs(r['ratio']-1),reverse=True)[:5])
        coverage.append(record)
    write_csv(root/'coverage.csv',coverage,list(coverage[0]))
    (root/'metric_details.json').write_text(json.dumps(details,indent=2)+'\n')
    manifest = dict(audit_only=True, cutoff=cutoff.isoformat(), generated_at=stamp(), start_month=start_month, expected_months=len(results), validated_months=sum(r['status']=='validated' for r in results), partial_month_note='Current month is latest available as of cutoff, not a completed month-end.', full_10_year_definition='120 complete monthly observations October 2016–September 2026; evaluated separately for each metric', provisional_metric_choices=PROVISIONAL, sources=[dict(month=r['month'],status=r['status'],source=r.get('source'),attempts=r['attempts']) for r in results], outputs={p.name:sha(p.read_bytes()) for p in [root/'monthly.csv',root/'extracted.csv',root/'coverage.csv',root/'metric_details.json']})
    payload = (json.dumps(manifest,indent=2)+'\n').encode()
    (root/'runs').mkdir(exist_ok=True)
    run_path = root/'runs'/(sha(payload)+'.json')
    if not run_path.exists():
        with run_path.open('xb') as out:
            out.write(payload)
    (root/'manifest.json').write_bytes(payload)
    return coverage


def investigate_starts(root):
    evidence = []
    for names, begin, end in [(['Nifty Oil & Gas','Nifty Consumer Durables'],date(2019,12,31),date(2020,1,31)), (['Nifty Healthcare Index'],date(2020,10,30),date(2020,11,30))]:
        remaining = set(names)
        day = begin
        while day <= end and remaining:
            rows, meta, attempts = fetch(day,root)
            evidence.append(dict(requested_date=str(day), source=meta, attempts=attempts, target_presence={n:n in rows for n in names} if rows is not None else None))
            if rows is None and attempts and attempts[-1]['outcome']!='archive_not_found':
                raise ValueError('Unresolved boundary archive; cannot infer first appearance')
            if rows is not None:
                remaining -= set(rows)
            day += timedelta(days=1)
    rows, meta, attempts = fetch(date(2016,10,4),root)
    evidence.append(dict(requested_date='2016-10-04', source=meta, attempts=attempts, target_rows=rows))
    (root/'start_investigation.json').write_text(json.dumps(evidence,indent=2)+'\n')


def verify(root):
    manifest = json.loads((root/'manifest.json').read_text())
    for filename, expected in manifest['outputs'].items():
        if sha((root/filename).read_bytes()) != expected:
            raise ValueError('Derived checksum mismatch: '+filename)
    sources = {}
    for path in sorted((root/'sources').glob('*/manifest.json')):
        meta = json.loads(path.read_text())
        payload = (path.parent/'raw.csv').read_bytes()
        day = date.fromisoformat(meta['observation_date'])
        if sha(payload)!=meta['sha256'] or meta['source_url']!=URL.format(date=day.strftime('%d%m%Y')):
            raise ValueError('Source provenance mismatch: '+str(path))
        sources[meta['observation_date']] = parse(payload,day)
    with (root/'monthly.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    keys = set()
    for row in rows:
        key = (row['month'],row['Index Name'])
        if key in keys:
            raise ValueError('Duplicate month/index in output')
        keys.add(key)
        source = sources.get(row['observation_date'],{}).get(row['Index Name'])
        if (source is not None)!=(row['index_present']=='True'):
            raise ValueError('Index presence mismatch')
        for metric in METRICS:
            expected = source[metric].strip() if source and source[metric].strip() not in ('','-') else ''
            if row[metric]!=expected:
                raise ValueError('Normalized value does not match exact source')
    if len(keys)!=manifest['expected_months']*len(NAMES):
        raise ValueError('Incomplete normalized grid')
    print(f'Verified {len(sources)} raw archives and {len(rows)} normalized rows; all checksums and exact-source values match.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cutoff',type=date.fromisoformat,default=(datetime.now(timezone.utc)+timedelta(hours=5,minutes=30)).date())
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--update',action='store_true',help='Incremental production refresh; no full historical download')
    parser.add_argument('--verify',action='store_true',help='Offline checksum and normalization verification')
    parser.add_argument('--investigate-starts',action='store_true')
    parser.add_argument('--workers',type=int,default=4)
    args = parser.parse_args()
    if args.cutoff > (datetime.now(timezone.utc)+timedelta(hours=5,minutes=30)).date():
        raise ValueError('Future cutoff forbidden')
    args.root.mkdir(parents=True,exist_ok=True)
    if args.update:
        # Also works when invoked as a script rather than a module.
        import sys
        sys.path.insert(0, str(ROOT.parents[1]))
        from data.fetchers.nse_valuations.production import update
        try:
            update(args.root, args.cutoff)
        except Exception as exc:
            print(f'ERROR: NSE valuation update failed; valuation chart must be omitted: {exc}', file=sys.stderr)
            raise SystemExit(1)
        return
    if args.verify:
        verify(args.root)
        return
    if args.investigate_starts:
        investigate_starts(args.root)
        return
    months = months_to(args.cutoff)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(lambda m:collect_month(m,args.cutoff,args.root),months):
            results.append(result)
            print(result['month'],result['status'],result.get('source',{}).get('observation_date',''),flush=True)
    audit(results,args.root,args.cutoff)

if __name__ == '__main__':
    main()
