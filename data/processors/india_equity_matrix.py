"""India equity matrix arithmetic from official gross TRI observations only.

Common latest/1Y anchor dates; no interpolating, padding or proxy substitution.
Percent returns and excess returns are stored in percentage points.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from config.india_equity_matrix import INDICES, GROUPS, HORIZONS, RETURN_METHOD, SOURCE_PAGE, ENDPOINT, METHOD_NOTE
from data.fetchers.india_equity_tri import series_digest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stale(day, cutoff):
    return np.busday_count(pd.Timestamp(day).date(), pd.Timestamp(cutoff).date()) > 3


def validate_series(entry, spec, cutoff):
    require(entry['id'] == spec['id'] and entry['code'] == spec['code'] and
            entry['label'] == spec['label'], 'Official TRI series identity mismatch')
    records = entry['records']
    require(records and entry['sha256'] == series_digest(records), 'Official history checksum mismatch')
    dates = pd.DatetimeIndex([r[0] for r in records])
    require(not dates.hasnans and not dates.has_duplicates and dates.is_monotonic_increasing
            and all(str(d.date()) == r[0] for d, r in zip(dates, records)), 'Invalid official observation dates')
    require(dates[-1] <= pd.Timestamp(cutoff), 'Official history contains future observations')
    values = np.array([r[1] for r in records], dtype=float)
    require(np.isfinite(values).all() and (values > 0).all(), 'Invalid official gross TRI levels')
    require(not stale(dates[-1], cutoff), 'Stale official index history')
    series = pd.Series(values, index=dates)
    require(len(entry['source_checks']) == 3, 'Missing independent official checks')
    for check in entry['source_checks']:
        require(pd.Timestamp(check['date']) in dates and series.loc[check['date']] == check['level'],
                'Independent source check mismatch')
    require(bool(entry['requests']), 'Missing official request receipts')
    for receipt in entry['requests']:
        require(receipt['endpoint'] == ENDPOINT and receipt['status'] == 200 and
                receipt['parameters']['name'] == spec['code'] and
                receipt['parameters']['indexName'] == spec['label'] and
                0 <= (pd.Timestamp(receipt['end'])-pd.Timestamp(receipt['start'])).days <= 365 and
                pd.Timestamp(receipt['end']) <= pd.Timestamp(cutoff), 'Invalid official request provenance')
    return series


def anchor(series, target):
    eligible = series.loc[:target]
    if eligible.empty or (pd.Timestamp(target)-eligible.index[-1]).days > 7:
        return None
    return eligible.index[-1]


def calculate(series, spec, latest, benchmark_dates, one_year_anchor):
    latest = pd.Timestamp(latest)
    s = series.loc[:latest]
    targets = {'1W': latest-pd.Timedelta(days=7), '1M': latest-pd.DateOffset(months=1),
               'YTD': pd.Timestamp(latest.year-1, 12, 31), '1Y': latest-pd.DateOffset(years=1),
               '3Y': latest-pd.DateOffset(years=3), '5Y': latest-pd.DateOffset(years=5)}
    returns, anchors = {}, {}
    for key, target in targets.items():
        day = one_year_anchor if key == '1Y' else anchor(s, target)
        if day is None or day not in s.index or (target-day).days > 7:
            returns[key], anchors[key] = None, None
            continue
        ratio = s.loc[latest] / s.loc[day]
        elapsed = (latest-day).days
        require(elapsed > 0, 'Return anchor must precede latest date')
        value = ratio ** (365.25/elapsed)-1 if key in ('3Y', '5Y') else ratio-1
        returns[key] = float(value*100)
        anchors[key] = dict(date=str(day.date()), level=float(s.loc[day]))
    start_5y = latest-pd.DateOffset(years=5)
    window = s.loc[start_5y:latest]
    expected = benchmark_dates[(benchmark_dates >= start_5y) & (benchmark_dates <= latest)]
    missing = expected.difference(window.index)
    complete = anchor(s, start_5y) is not None and not len(missing)
    peak_day = window.idxmax() if complete and not window.empty else None
    off = float(min(0, (s.loc[latest]/window.max()-1)*100)) if peak_day is not None else None
    recent = s.loc[latest-pd.Timedelta(weeks=52):latest]
    weekly = recent.groupby(recent.index.to_period('W-FRI')).tail(1)
    sparkline = [dict(date=str(d.date()), value=float(v/weekly.iloc[0]*100)) for d, v in weekly.items()] if len(weekly) else []
    return dict(spec, status='available', latest_date=str(latest.date()), latest_level=float(s.loc[latest]),
                history_start=str(s.index[0].date()), history_observations=len(s), returns=returns,
                anchor_dates=anchors, vs_nifty50_1y=None, sparkline=sparkline,
                off_5y_high=off, high_5y_date=str(peak_day.date()) if peak_day is not None else None,
                high_5y_level=float(window.max()) if peak_day is not None else None,
                high_5y_start=str(start_5y.date()), missing_5y_dates=[str(d.date()) for d in missing],
                off_5y_high_reason=None if complete else 'Incomplete five-year coverage; highest observation may be missing.')


def build(snapshot, cutoff):
    cut = pd.Timestamp(cutoff).normalize()
    require(snapshot['schema_version'] == 1 and snapshot['return_method'] == RETURN_METHOD and
            snapshot['currency'] == 'INR' and snapshot['source_url'] == SOURCE_PAGE and
            snapshot['endpoint'] == ENDPOINT, 'Official gross TRI snapshot required')
    require(pd.Timestamp(snapshot['as_of']) <= cut and not stale(snapshot['as_of'], cut), 'Stale/future official snapshot')
    specs = {s['id']:s for s in INDICES}
    require(len(snapshot['series']) == len({e['id'] for e in snapshot['series']}), 'Duplicate source series')
    entries = {e['id']:e for e in snapshot['series']}
    failures = {r['id']:r['reason'] for r in snapshot['failures']}
    require(not (entries.keys() & failures.keys()) and entries.keys() | failures.keys() == specs.keys(),
            'Official snapshot universe mismatch')
    histories = {}
    for key, entry in entries.items():
        try:
            histories[key] = validate_series(entry, specs[key], snapshot['as_of'])
        except ValueError as exc:
            # Invalid provenance is a corrupt snapshot, not an optional missing row.
            raise ValueError(specs[key]['label'] + ': ' + str(exc)) from exc
    benchmark_id = INDICES[0]['id']
    require(benchmark_id in histories, 'Nifty 50 TRI is required for relative performance')
    require(len(histories) >= math.ceil(len(INDICES)*.8), 'More than 20% of official indices unavailable')
    common = histories[benchmark_id].index
    for series in histories.values():
        common = common.intersection(series.index)
    require(len(common) > 1 and not stale(common[-1], cut), 'No fresh common official observation date')
    latest = common[-1]
    one_year_target = latest-pd.DateOffset(years=1)
    joint = pd.Series(1., index=common)
    one_year_anchor = anchor(joint, one_year_target)
    benchmark = histories[benchmark_id]
    rows = []
    for spec in INDICES:
        if spec['id'] in histories:
            row = calculate(histories[spec['id']], spec, latest, benchmark.index, one_year_anchor)
            row['source_checks'] = entries[spec['id']]['source_checks']
            row['source_sha256'] = entries[spec['id']]['sha256']
            rows.append(row)
        else:
            rows.append(dict(spec, status='unavailable', reason=failures[spec['id']],
                             returns={h:None for h in HORIZONS}, anchor_dates={h:None for h in HORIZONS},
                             latest_date=None, latest_level=None, vs_nifty50_1y=None,
                             off_5y_high=None, high_5y_date=None, sparkline=[]))
    base_return = rows[0]['returns']['1Y']
    for row in rows:
        if row['returns']['1Y'] is not None and base_return is not None:
            row['vs_nifty50_1y'] = row['returns']['1Y']-base_return
    payload = dict(schema_version=1, title='India Equity Market Performance Matrix',
                   requested_as_of=str(cut.date()), as_of=str(latest.date()),
                   generated_at=datetime.now(timezone.utc).isoformat(), source_fetched_at=snapshot['fetched_at'],
                   source_url=SOURCE_PAGE, return_method=RETURN_METHOD, currency='INR',
                   methodology_note=METHOD_NOTE, relative_unit='percentage points',
                   relative_anchor=str(one_year_anchor.date()) if one_year_anchor is not None else None,
                   off_high_definition='Latest gross TRI / highest observed gross TRI within the trailing five calendar years − 1.',
                   groups=[dict(id=g, label=label, rows=[r for r in rows if r['group']==g]) for g,label in GROUPS])
    validate_payload(payload)
    return payload


def validate_payload(payload):
    require(payload['schema_version'] == 1 and payload['return_method'] == RETURN_METHOD and
            payload['currency'] == 'INR' and payload['relative_unit'] == 'percentage points' and
            payload['source_url'] == SOURCE_PAGE and payload['methodology_note'] == METHOD_NOTE,
            'Invalid India equity matrix schema/methodology')
    require([(g['id'],g['label']) for g in payload['groups']] == GROUPS, 'Invalid matrix group order')
    require(all(r['group'] == g['id'] for g in payload['groups'] for r in g['rows']),
            'Index placed in incorrect matrix group')
    rows = [r for g in payload['groups'] for r in g['rows']]
    require([r['id'] for r in rows] == [s['id'] for s in INDICES], 'Invalid approved matrix universe/order')
    cut = pd.Timestamp(payload['requested_as_of']); latest = pd.Timestamp(payload['as_of'])
    require(latest <= cut and not stale(latest, cut), 'Invalid common cutoff')
    benchmark_return = rows[0]['returns']['1Y']
    for row, spec in zip(rows, INDICES):
        require(all(row[k] == spec[k] for k in spec), 'Matrix source identity altered')
        require(set(row['returns']) == set(HORIZONS), 'Invalid return horizons')
        require(row['status'] in ('available', 'unavailable'), 'Invalid row status')
        vals = list(row['returns'].values())+[row['vs_nifty50_1y'],row['off_5y_high']]
        require(all(v is None or isinstance(v, (int, float)) and math.isfinite(v) for v in vals), 'Nonfinite matrix value')
        if row['status'] == 'unavailable':
            require(all(v is None for v in vals) and not row['sparkline'] and row['latest_date'] is None,
                    'Unavailable index must not carry old metrics')
            continue
        require(row['latest_date'] == payload['as_of'] and math.isfinite(row['latest_level']) and
                row['latest_level'] > 0, 'Misaligned latest observation')
        targets = {'1W': latest-pd.Timedelta(days=7), '1M': latest-pd.DateOffset(months=1),
                   'YTD': pd.Timestamp(latest.year-1, 12, 31), '1Y': latest-pd.DateOffset(years=1),
                   '3Y': latest-pd.DateOffset(years=3), '5Y': latest-pd.DateOffset(years=5)}
        require(set(row['anchor_dates']) == set(HORIZONS), 'Invalid anchor horizons')
        for horizon, target in targets.items():
            a, v = row['anchor_dates'][horizon], row['returns'][horizon]
            require((a is None) == (v is None), 'Missing return/anchor mismatch')
            if a is None:
                continue
            day = pd.Timestamp(a['date'])
            require(day <= target and (target-day).days <= 7 and day < latest and
                    math.isfinite(a['level']) and a['level'] > 0, 'Invalid observed return anchor')
            ratio = row['latest_level']/a['level']
            expected_return = (ratio**(365.25/(latest-day).days)-1)*100 if horizon in ('3Y','5Y') else (ratio-1)*100
            require(math.isclose(v, expected_return, abs_tol=1e-10), 'Return/anchor arithmetic mismatch')
        require(row['returns']['1Y'] is None or row['anchor_dates']['1Y']['date'] == payload['relative_anchor'],
                'Relative returns must use common actual anchors')
        expected = row['returns']['1Y']-benchmark_return if row['returns']['1Y'] is not None and benchmark_return is not None else None
        require(row['vs_nifty50_1y'] == expected, 'Relative-return calculation mismatch')
        if row['off_5y_high'] is not None:
            require(row['off_5y_high'] <= 0 and not row['missing_5y_dates'] and
                    row['high_5y_start'] == str((latest-pd.DateOffset(years=5)).date()) and
                    math.isfinite(row['high_5y_level']) and row['high_5y_level'] >= row['latest_level'] and
                    row['high_5y_start'] <= row['high_5y_date'] <= payload['as_of'] and
                    math.isclose(row['off_5y_high'], (row['latest_level']/row['high_5y_level']-1)*100, abs_tol=1e-10),
                    'Invalid trailing-five-year high')
        points = row['sparkline']
        require([p['date'] for p in points] == sorted(set(p['date'] for p in points)) and
                all(latest-pd.Timedelta(weeks=52) <= pd.Timestamp(p['date']) <= latest and
                    math.isfinite(p['value']) and p['value'] > 0 for p in points), 'Invalid sparkline')
    require(rows[0]['status'] == 'available', 'Benchmark unavailable')
    return payload


def generate(output_dir, source_path=None, cutoff=None):
    """Generate only this edition's JSON; omit stale/failed data, never restore an older edition."""
    import os
    from config.india_equity_matrix import ARTIFACT
    from data.fetchers.india_equity_tri import DEFAULT_PATH
    destination = Path(output_dir)/ARTIFACT
    cut = pd.Timestamp(cutoff or datetime.now(timezone.utc).date())
    try:
        require(os.environ.get('NSE_EQUITY_UPDATE_FAILED') != 'true', 'Official TRI refresh failed')
        payload = build(json.loads(Path(source_path or DEFAULT_PATH).read_text()), cut)
        require(str(cut.date())[:7] == Path(output_dir).name, 'Matrix cutoff must match India edition')
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix('.pending.json')
        temp.write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n');temp.replace(destination)
        print('India equity matrix: ' + payload['as_of'] + ' · 37 official indices')
        return destination
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as exc:
        destination.unlink(missing_ok=True)
        print('India equity matrix omitted: ' + str(exc))
        return None
