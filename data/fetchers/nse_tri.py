"""Official NSE Nifty 50 gross total-return history; never use price/NTR data.

NSE's historical-data page (IISLComponet.js, TotalReturnindexHistoricalData)
POSTs cinfo to /BackPage/getTotalReturnIndexString. Each window is at most
365 elapsed days. We query from the earliest date in NSE's historical FAQ,
keep exact dates, and independently re-request five historical observations.
Every run fetches fresh source data; there is no stale-cache fallback.
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from config.market_matrix import OFFICIAL_TOTAL_RETURN

SOURCE_PAGE = 'https://www.niftyindices.com/reports/historical-data'
ENDPOINT = 'https://www.niftyindices.com/BackPage/getTotalReturnIndexString'
SOURCE_SCRIPT = 'https://liveindexsa.niftyindices.com/assets/js/IISLComponet.js'
HISTORY_START = '1990-07-03'


def parse_response(payload, start, end):
    """Decode the official TRI schema; never accept Close or NTR_Value alone."""
    if isinstance(payload, dict) and 'd' in payload:
        payload = payload['d']
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, list):
        raise ValueError('NSE TRI response is not a record array')
    dates, values = [], []
    for record in payload:
        if str(record.get('Index Name', '')).upper().replace(' ', '') != 'NIFTY50':
            raise ValueError('NSE TRI response contains a different index')
        if 'TotalReturnsIndex' not in record:
            raise ValueError('NSE response missing gross TotalReturnsIndex; price/NTR fallback forbidden')
        day = pd.Timestamp(datetime.strptime(record['Date'], '%d %b %Y'))
        value = float(record['TotalReturnsIndex'])
        if not np.isfinite(value) or value <= 0:
            raise ValueError('NSE TRI level must be positive and finite')
        if day < pd.Timestamp(start) or day > pd.Timestamp(end):
            raise ValueError('NSE TRI observation outside requested dates')
        dates.append(day); values.append(value)
    result = pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float)
    if result.index.has_duplicates:
        raise ValueError('duplicate NSE TRI dates')
    if not (result.index.is_monotonic_increasing or result.index.is_monotonic_decreasing):
        raise ValueError('NSE TRI dates not monotonic')
    result = result.sort_index()
    result.attrs['return_method'] = OFFICIAL_TOTAL_RETURN
    return result


class NiftyTRIFetcher:
    def __init__(self, client=None, audit_dir=None):
        if client is None:
            from curl_cffi import requests
            client = requests.Session(impersonate='chrome')
            client.headers.update({'Referer': SOURCE_PAGE, 'Accept': 'application/json, text/javascript, */*; q=0.01',
                                   'X-Requested-With': 'XMLHttpRequest'})
        self.client = client
        self.audit_dir = audit_dir
        self.requests = []

    def _window(self, start, end, role='history'):
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        if not 0 <= (end-start).days <= 365:
            raise ValueError('NSE TRI window must have 0–365 elapsed days')
        info = dict(name='NIFTY 50', startDate=start.strftime('%d-%b-%Y'),
                    endDate=end.strftime('%d-%b-%Y'), indexName='NIFTY 50')
        for attempt in range(2):
            try:
                response = self.client.post(ENDPOINT, json={'cinfo': json.dumps(info)}, timeout=25)
                response.raise_for_status()
                raw = response.json()
                break
            except Exception as exc:
                if attempt:
                    raise ValueError(f'Official NSE TRI retrieval failed for {start.date()}–{end.date()}: {type(exc).__name__}') from exc
                time.sleep(0.5)
        result = parse_response(raw, start, end)
        record = dict(role=role, start=str(start.date()), end=str(end.date()),
                      rows=len(result), source_url=ENDPOINT, parameters=info)
        self.requests.append(record)
        if self.audit_dir is not None:
            from pathlib import Path
            directory = Path(self.audit_dir)
            directory.mkdir(parents=True, exist_ok=True)
            (directory/f'{role}_{start.date()}_{end.date()}.json').write_text(json.dumps(raw, indent=2)+'\n')
        return result

    def get_nifty50_tri(self, cutoff):
        end = pd.Timestamp(cutoff).normalize()
        start = pd.Timestamp(HISTORY_START)
        pieces = []
        while start <= end:
            window_end = min(start + pd.Timedelta(days=365), end)
            piece = self._window(start, window_end)
            if piece.empty and pieces and (window_end-start).days > 7:
                raise ValueError('Official NSE TRI has an empty historical window after history began')
            if not piece.empty:
                pieces.append(piece)
            start = window_end + pd.Timedelta(days=1)
        if not pieces:
            raise ValueError('Official NSE Nifty 50 TRI history unavailable')
        result = pd.concat(pieces)
        if result.index.has_duplicates or not result.index.is_monotonic_increasing:
            raise ValueError('NSE TRI history overlaps or is not monotonic')
        if len(result) < 5:
            raise ValueError('NSE TRI has too few values for five-date validation')
        checks = []
        for index in np.linspace(0, len(result)-1, 5, dtype=int):
            day = result.index[index]
            check = self._window(day, day, role='validation')
            if len(check) != 1 or float(check.iloc[0]) != float(result.iloc[index]):
                raise ValueError(f'NSE TRI separate historical-date check failed for {day.date()}')
            checks.append(dict(date=str(day.date()), value=float(result.iloc[index]),
                               verified_value=float(check.iloc[0]), source_url=ENDPOINT,
                               check='Separate official single-date request matched the full-history request'))
        result.attrs['return_method'] = OFFICIAL_TOTAL_RETURN
        result.attrs['source_checks'] = checks
        if self.audit_dir is not None:
            from pathlib import Path
            (Path(self.audit_dir)/'manifest.json').write_text(json.dumps(dict(
                source=SOURCE_PAGE, endpoint=ENDPOINT, source_script=SOURCE_SCRIPT,
                generated_at=datetime.now(timezone.utc).isoformat(), requested_start=HISTORY_START,
                cutoff=str(end.date()), history_start=str(result.index[0].date()),
                history_end=str(result.index[-1].date()), observations=len(result),
                requests=self.requests, source_checks=checks), indent=2)+'\n')
        return result
