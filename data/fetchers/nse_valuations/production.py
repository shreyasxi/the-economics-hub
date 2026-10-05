"""Approved own-index percentiles and incremental refresh of the audited store.

No database imports, no filled values, and no network access during chart loading.
"""
import calendar
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .collector import ROOT, audit, collect_month, fetch, parse, sha, stamp, verify

APPROVED_METRICS = {
    'Nifty 50': 'P/E', 'Nifty Auto': 'P/E', 'Nifty FMCG': 'P/E',
    'Nifty IT': 'P/E', 'Nifty Pharma': 'P/E', 'Nifty Bank': 'P/B',
    'Nifty Metal': 'P/B', 'Nifty Realty': 'P/B', 'Nifty Oil & Gas': 'P/B',
}
SHORT_NAMES = {'Nifty 50':'NIFTY 50', **{n:n.removeprefix('Nifty ') for n in APPROVED_METRICS if n!='Nifty 50'}}
PE_START = '2021-04'
AVAILABLE_START = {'Nifty Oil & Gas':'2020-01'}
MIN_OBSERVATIONS = 60


def today_ist():
    return (datetime.now(timezone.utc)+timedelta(hours=5,minutes=30)).date()


def atomic_json(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value, indent=2)+'\n')
    pending.replace(path)


def latest_archive(cutoff, root, max_days=35):
    """Search every day; only 404/410 permits moving to an earlier date.

    Revalidate the selected current archive online even when already cached.
    A revised source, HTML, timeout or access failure cannot fall back to cache.
    """
    attempts = []
    for offset in range(max_days):
        day = cutoff-timedelta(days=offset)
        rows, source, tried = fetch(day, root, revalidate=True)
        attempts.extend(tried)
        if rows is not None:
            return dict(observation_date=str(day), source=source, rows=rows, attempts=attempts)
        if not tried or tried[-1]['outcome']!='archive_not_found':
            raise ValueError(f'Unresolved latest archive on {day}: {tried}')
    raise ValueError(f'No official archive found in {max_days} days; chart omitted')


def previous_month(day):
    return day.replace(day=1)-timedelta(days=1)


def update(root=ROOT, cutoff=None):
    """Revalidate latest daily archive and finalize only missing/partial months.

    Catch-up handles multiple missed runs. The audited historical months are
    checksum-checked locally, never downloaded again merely for a weekly run.
    A readiness marker gates rendering, so retained files cannot masquerade as
    a successful refresh. Raw files remain immutable on both success and failure.
    """
    root = Path(root)
    cutoff = cutoff or today_ist()
    if cutoff > today_ist():
        raise ValueError('Future cutoff forbidden')
    status = dict(status='updating', requested_cutoff=str(cutoff), started_at=stamp())
    atomic_json(root/'update_status.json', status)
    try:
        verify(root)
        previous = json.loads((root/'manifest.json').read_text())
        current = latest_archive(cutoff, root)
        end = previous_month(cutoff)
        entries = {e['month']:e for e in previous['sources']}
        # Begin at the audit start but only request absent or unresolved months.
        y, m = map(int, previous['start_month'].split('-'))
        changed = []
        while (y,m) <= (end.year,end.month):
            month = f'{y:04d}-{m:02d}'
            old = entries.get(month)
            month_end = date(y,m,calendar.monthrange(y,m)[1])
            incomplete = previous['cutoff'] < month_end.isoformat()
            if old is None or old['status']!='validated' or incomplete:
                result = collect_month(month, month_end, root)
                if result['status']!='validated':
                    raise ValueError(f'Cannot finalize completed month {month}: {result}')
                entries[month] = result
                changed.append(month)
            y, m = (y+1,1) if m==12 else (y,m+1)
        # The audit grid retains the current observation but marks it partial.
        current_month = current['observation_date'][:7]
        entries[current_month] = dict(month=current_month, status='validated',
                                     source=current['source'], rows=current['rows'],
                                     attempts=current['attempts'])
        results = []
        for month, entry in sorted(entries.items()):
            if month>current_month:
                continue
            source = entry.get('source')
            if source:
                rows = parse((root/'sources'/source['observation_date']/'raw.csv').read_bytes(), date.fromisoformat(source['observation_date']))
            else:
                rows = {}
            # Month containing CURRENT source date is ALWAYS outside reference.
            results.append(dict(month=month, status=entry['status'], source=source or {}, rows=rows,
                                attempts=entry.get('attempts',[]), partial_month=month==current_month))
        # Build summaries in staging; mark success only after all hashes validate.
        with TemporaryDirectory(prefix='update-',dir=root) as staging:
            staged = Path(staging)
            audit(results, staged, cutoff, start_month=previous["start_month"])
            for filename in ['monthly.csv','extracted.csv','coverage.csv','metric_details.json','manifest.json']:
                (staged/filename).replace(root/filename)
            for run in (staged/'runs').glob('*.json'):
                target = root/'runs'/run.name
                if not target.exists():
                    run.replace(target)
        atomic_json(root/'current.json', current)
        verify(root)
        status.update(status='ready', observation_date=current['observation_date'],
                      finalized_months=changed, current_sha256=sha((root/'current.json').read_bytes()),
                      monthly_sha256=sha((root/'monthly.csv').read_bytes()), finished_at=stamp())
        atomic_json(root/'update_status.json', status)
        print(f'NSE valuations ready: current {current["observation_date"]}; finalized months {changed or "none"}')
        return current, status
    except Exception as exc:
        status.update(status='failed_chart_must_be_omitted',error=str(exc),finished_at=stamp())
        atomic_json(root/'update_status.json', status)
        raise
    finally:
        # Keep failure/readiness evidence across future updates.
        folder = root/'runs'
        folder.mkdir(exist_ok=True)
        run = folder/('production-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        with run.open('x') as stream:
            json.dump(status, stream, indent=2)
            stream.write('\n')


def metric_value(token):
    if token is None or str(token).strip() in ('','-'):
        return None
    value = Decimal(str(token).strip())
    if not value.is_finite():
        raise ValueError('Non-finite production metric')
    return value


def calculate(monthly, current_rows, observation_date, min_observations=MIN_OBSERVATIONS):
    """Return approved rows, explicit omissions and exact reference metadata."""
    day = date.fromisoformat(observation_date)
    current_month = day.strftime('%Y-%m')
    pb_start = f'{day.year-10:04d}-{day.month:02d}'
    keys = set()
    for r in monthly:
        key = (r['month'],r['Index Name'])
        if key in keys:
            raise ValueError('Duplicate month/index')
        keys.add(key)
        if r.get('observation_date') and r['observation_date'][:7]!=r['month']:
            raise ValueError('Monthly observation date does not belong to month')
    output, warnings = [], []
    for name, metric in APPROVED_METRICS.items():
        raw = metric_value(current_rows.get(name,{}).get(metric))
        if raw is None:
            warnings.append(f'{name} omitted: current {metric} missing in official archive {day}')
            continue
        start = PE_START if metric=='P/E' else max(pb_start, AVAILABLE_START.get(name, pb_start))
        selected = []
        for row in sorted(monthly,key=lambda r:r['month']):
            if row['Index Name']!=name or not (start <= row['month'] < current_month):
                continue
            if str(row.get('partial_month',False)).lower()=='true':
                continue
            value = metric_value(row.get(metric))
            if value is not None:
                selected.append((row['month'],value))
        if len(selected)<min_observations:
            warnings.append(f'{name} omitted: {len(selected)} valid completed {metric} months; minimum {min_observations}')
            continue
        percentile = 100*sum(value<=raw for _,value in selected)/len(selected)
        output.append(dict(index=name, label=SHORT_NAMES[name], metric=metric, current_multiple=float(raw),
                           percentile=percentile, historical_count=len(selected),
                           history_start=selected[0][0], history_end=selected[-1][0],
                           reference_months=[m for m,_ in selected], observation_date=observation_date))
    benchmark = [r for r in output if r['index']=='Nifty 50']
    sectors = sorted([r for r in output if r['index']!='Nifty 50'],key=lambda r:(-r['percentile'],r['label']))
    return benchmark+sectors, warnings


def load_chart_data(root=ROOT, as_of=None):
    root = Path(root)
    status = json.loads((root/'update_status.json').read_text())
    if status['status']!='ready' or status['requested_cutoff']!=str(as_of or today_ist()):
        raise ValueError('No successful NSE valuation refresh for this run date; stale snapshot not substituted')
    for name in ['current','monthly']:
        path = root/(name+'.json' if name=='current' else name+'.csv')
        if sha(path.read_bytes())!=status[name+'_sha256']:
            raise ValueError(name+' production checksum mismatch')
    verify(root)
    current = json.loads((root/'current.json').read_text())
    source = current['source']
    raw_path = root/'sources'/source['observation_date']/'raw.csv'
    if sha(raw_path.read_bytes())!=source['sha256']:
        raise ValueError('Current raw source checksum mismatch')
    exact_rows = parse(raw_path.read_bytes(),date.fromisoformat(current['observation_date']))
    if current['rows']!=exact_rows:
        raise ValueError('Current normalized rows do not match raw archive')
    with (root/'monthly.csv').open() as stream:
        monthly = list(csv.DictReader(stream))
    rows, warnings = calculate(monthly, exact_rows, current['observation_date'])
    return rows, dict(source=source, update=status, warnings=warnings,
                     percentile_method='count(valid historical values <= current) / count(valid historical values) * 100',
                     current_month_excluded=True, pe_history_start=PE_START, pb_max_months=120)
