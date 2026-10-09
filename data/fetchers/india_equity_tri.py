"""Official gross TRI snapshot for the India matrix; bounded five-year backfill.

python -m data.fetchers.india_equity_tri [--as-of YYYY-MM-DD] [--output PATH]
Uses the official website contract, no CAPTCHA bypass or price/NTR fallback.
Every refresh retrieves a fresh backfill; failed refreshes cannot publish old data.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import numpy as np
import pandas as pd
from config.india_equity_matrix import INDICES, ENDPOINT, MAPPING_URL, SOURCE_PAGE, RETURN_METHOD

from data.paths import INDIA_EQUITY_TRI

DEFAULT_PATH = INDIA_EQUITY_TRI


def normalized(name):
    return re.sub(r'[^A-Z0-9]', '', str(name).upper())


def series_digest(records):
    return hashlib.sha256(json.dumps(records, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def parse_response(payload, spec, start, end):
    if isinstance(payload, dict) and 'd' in payload:
        payload = payload['d']
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, list):
        raise ValueError('Official TRI response is not a record array')
    values = {}
    for row in payload:
        if normalized(row.get('Index Name')) not in (normalized(spec['label']), normalized(spec['code'])):
            raise ValueError('Official TRI identity mismatch')
        if 'TotalReturnsIndex' not in row:
            raise ValueError('Gross TotalReturnsIndex required; price/NTR fallback forbidden')
        day = pd.Timestamp(datetime.strptime(row['Date'], '%d %b %Y'))
        value = float(row['TotalReturnsIndex'])
        if not pd.Timestamp(start) <= day <= pd.Timestamp(end) or not np.isfinite(value) or value <= 0:
            raise ValueError('Invalid official TRI observation')
        if day in values:
            raise ValueError('Duplicate official TRI date')
        values[day] = value
    return pd.Series(values, dtype=float).sort_index()


class IndiaTRIFetcher:
    def __init__(self, client=None, pause=.25):
        if client is None:
            from curl_cffi import requests
            client = requests.Session()
            client.headers.update({'Referer': SOURCE_PAGE, 'X-Requested-With': 'XMLHttpRequest',
                                   'Accept': 'application/json, text/javascript, */*; q=0.01'})
        self.client, self.pause = client, pause

    def mapping(self):
        response = self.client.get(MAPPING_URL, timeout=30)
        response.raise_for_status()
        mapping = response.json()
        if not isinstance(mapping, list):
            raise ValueError('Official index mapping is not an array')
        for spec in INDICES:
            if not any(normalized(m.get('Index_long_name')) == normalized(spec['label']) and
                       str(m.get('Trading_Index_Name', '')).upper() == spec['code'] for m in mapping):
                raise ValueError('Official retrieval key changed: ' + spec['label'])
        return hashlib.sha256(response.content).hexdigest()

    def window(self, spec, start, end):
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        if not 0 <= (end-start).days <= 365:
            raise ValueError('Official TRI windows must be at most 365 elapsed days')
        info = dict(name=spec['code'], indexName=spec['label'],
                    startDate=start.strftime('%d-%b-%Y'), endDate=end.strftime('%d-%b-%Y'))
        for attempt in range(3):
            time.sleep(self.pause)
            try:
                response = self.client.post(ENDPOINT, json={'cinfo': json.dumps(info)}, timeout=30)
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
                continue
            # A challenge is not a transient data error to work around.
            if response.status_code in (401, 403):
                raise ValueError('Official NSE source requires access approval; refresh stopped')
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2 ** (attempt+1))
                    continue
            response.raise_for_status()
            break
        result = parse_response(response.json(), spec, start, end)
        receipt = dict(start=str(start.date()), end=str(end.date()), rows=len(result),
                       sha256=hashlib.sha256(response.content).hexdigest(), parameters=info,
                       endpoint=ENDPOINT, status=response.status_code)
        return result, receipt

    def history(self, spec, cutoff):
        end = pd.Timestamp(cutoff).normalize()
        start = end - pd.DateOffset(years=5) - pd.Timedelta(days=14)
        parts, receipts = [], []
        while start <= end:
            stop = min(start + pd.Timedelta(days=365), end)
            part, receipt = self.window(spec, start, stop)
            if part.empty:
                raise ValueError('Empty official history window; no stale/price substitution')
            parts.append(part); receipts.append(receipt)
            start = stop + pd.Timedelta(days=1)
        series = pd.concat(parts).sort_index()
        if series.index.has_duplicates:
            raise ValueError('Overlapping official history')
        checks = []
        for day in (series.index[0], series.index[len(series)//2], series.index[-1]):
            check, receipt = self.window(spec, day, day)
            if len(check) != 1 or check.iloc[0] != series.loc[day]:
                raise ValueError('Independent official single-date check failed')
            receipts.append(receipt)
            checks.append(dict(date=str(day.date()), level=float(check.iloc[0])))
        records = [[str(day.date()), float(value)] for day, value in series.items()]
        return dict(id=spec['id'], code=spec['code'], label=spec['label'], records=records,
                    sha256=series_digest(records), requests=receipts, source_checks=checks)

    def fetch(self, cutoff):
        mapping_sha = self.mapping()
        series, failures = [], []
        for spec in INDICES:
            try:
                series.append(self.history(spec, cutoff))
                print('Validated ' + spec['label'], flush=True)
            except Exception as exc:
                failures.append(dict(id=spec['id'], reason=str(exc)))
                print('Unavailable ' + spec['label'] + ': ' + str(exc), flush=True)
                if 'access approval' in str(exc) or getattr(getattr(exc, 'response', None), 'status_code', None) == 429:
                    raise
        result = dict(schema_version=1, as_of=str(pd.Timestamp(cutoff).date()),
                      fetched_at=datetime.now(timezone.utc).isoformat(), source_url=SOURCE_PAGE,
                      endpoint=ENDPOINT, mapping_sha256=mapping_sha, return_method=RETURN_METHOD,
                      currency='INR', series=series, failures=failures)
        # Validate availability and arithmetic before replacing the canonical snapshot.
        from data.processors.india_equity_matrix import build
        build(result, cutoff)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--output', type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    if pd.Timestamp(args.as_of).date() > datetime.now(timezone.utc).date():
        raise ValueError('Cannot request future official history')
    snapshot = IndiaTRIFetcher().fetch(args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix('.pending.json')
    temp.write_text(json.dumps(snapshot, separators=(',', ':'), allow_nan=False) + '\n')
    temp.replace(args.output)
    print('Published validated official TRI snapshot: ' + str(args.output))


if __name__ == '__main__':
    main()
