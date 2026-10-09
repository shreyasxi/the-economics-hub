"""Shared official-source transport and atomic storage for India activity data."""
import calendar
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin, urlsplit

from data.fetchers.mospi_http import get

from data.paths import PROJECT_ROOT as REPO_ROOT

ROOT = REPO_ROOT
SITE = 'https://www.mospi.gov.in/'
PRODUCT_URL = SITE + 'api/product/get-product-data'
RELEASES_URL = SITE + 'api/latest-release/get-web-latest-release-list'
BULLETINS_URL = SITE + 'api/publications-reports/get-web-publications-report-list'


def require(condition, message):
    if not condition:
        raise ValueError('MoSPI dashboard: ' + message)


def official_url(url):
    p = urlsplit(url)
    require(p.scheme == 'https' and p.hostname in
            ('mospi.gov.in', 'www.mospi.gov.in', 'api.mospi.gov.in', 'esankhyiki.mospi.gov.in')
            and p.port in (None, 443), 'non-official source URL')
    return url


def month(year, name):
    require(str(year).isdigit() and name in calendar.month_name[1:], 'invalid monthly date')
    value = f'{int(year):04d}-{list(calendar.month_name).index(name):02d}'
    require(value < datetime.now(timezone.utc).strftime('%Y-%m'), 'future reference month')
    return value


def number(value, nullable=False):
    if nullable and value in (None, '', '-', 'NA'):
        return None
    require(not isinstance(value, bool), 'boolean numeric value')
    value = float(value)
    require(math.isfinite(value), 'non-finite numeric value')
    return value


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, data):
    atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def read_csv(path):
    path = Path(path)
    return list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []


def write_csv(path, rows, fields):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    atomic_bytes(path, output.getvalue().encode())


def retain(directory, content):
    checksum = hashlib.sha256(content).hexdigest()
    path = Path(directory) / (checksum + '.raw')
    if not path.exists():
        atomic_bytes(path, content)
    return checksum


def verify_retained(directory, rows):
    """A checksum is useful only when the original official payload is retained."""
    for checksum in {r['raw_sha256'] for r in rows}:
        path = Path(directory) / (checksum + '.raw')
        require(path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum,
                'retained official source missing or checksum changed')


def download(session, url):
    response = get(session, official_url(url), timeout=(15, 90))
    response.raise_for_status()
    official_url(response.url)
    require(bool(response.content), 'empty download')
    return response.content


def listing(session, endpoint, search):
    rows, page, total = [], 1, None
    while True:
        response = session.post(official_url(endpoint), json=dict(
            page_no=page, page_size=100, search_term=search, sort_field='published_year',
            sort_order='DESC', lang='en', data_source='web'), timeout=(15, 90))
        response.raise_for_status()
        official_url(response.url)
        payload = response.json()
        require(payload.get('status') == 'success' and isinstance(payload.get('data'), list)
                and payload['data'], 'malformed/empty publication listing')
        meta = payload.get('pagination', {})
        require(meta.get('currentPage') == page and type(meta.get('totalPages')) is int
                and 1 <= meta['totalPages'] <= 100 and type(meta.get('totalItems')) is int,
                'publication pagination changed')
        observed = (meta['totalPages'], meta['totalItems'])
        require(total is None or total == observed, 'publication listing changed during fetch')
        total = observed
        rows.extend(payload['data'])
        if page == total[0]:
            require(len(rows) == total[1], 'incomplete publication listing')
            require(len({r['id'] for r in rows}) == len(rows), 'duplicate publication ID')
            return rows
        page += 1


def publication_month(title):
    title = re.sub('<[^>]*>', '', title)
    match = re.search(r'\b(' + '|'.join(calendar.month_name[1:]) + r')\s*,?\s*(20\d{2})\b', title, re.I)
    require(match is not None, 'missing publication reference month')
    return month(match[2], match[1].capitalize())


def select_latest(rows, predicate):
    selected = [r for r in rows if predicate(r)]
    require(selected, 'required official publication missing')
    for r in selected:
        date.fromisoformat(r['published_year'])
    result = max(selected, key=lambda r: (r['published_year'], int(r['id'])))
    require(result['published_year'] <= date.today().isoformat(), 'future publication')
    require(result['published_year'][:7] > publication_month(result['title']),
            'release date does not follow reference month')
    return result


def attachment(record, suffix):
    matches = [record[k] for k in ('file_one', 'file_two', 'file_three')
               if record.get(k) and record[k]['path'].lower().endswith(suffix)]
    require(len(matches) == 1, 'ambiguous/missing official ' + suffix + ' attachment')
    return official_url(urljoin(SITE, matches[0]['path']))


def api_rows(session, url, params):
    rows, sources, page, total = [], [], 1, None
    while True:
        response = get(session, official_url(url), params=dict(params, page=page), timeout=(15, 90))
        response.raise_for_status()
        official_url(response.url)
        payload = response.json()
        require(payload.get('statusCode') is True and isinstance(payload.get('data'), list)
                and payload['data'], 'malformed/empty API response')
        meta = payload.get('meta_data', {})
        require(meta.get('page') == page and type(meta.get('totalPages')) is int
                and 1 <= meta['totalPages'] <= 100 and type(meta.get('totalRecords')) is int,
                'API pagination changed')
        observed = (meta['totalPages'], meta['totalRecords'])
        require(total is None or total == observed, 'API changed during pagination')
        total = observed
        rows.extend(payload['data'])
        sources.append(response.content)
        if page == total[0]:
            require(len(rows) == total[1], 'incomplete API response')
            return rows, sources
        page += 1


def reconcile(old, incoming, keys, validate):
    """Only a newer official publication can replace an existing observation.

    Conflicting data attributed to the same publication fail the whole refresh.
    Old rows absent from a truncated source also fail; no silent history loss.
    """
    validate(incoming)
    if old:
        validate(old)
    key = lambda r: tuple(r[k] for k in keys)
    prior = {key(r): r for r in old}
    new = {key(r): r for r in incoming}
    require(set(prior) <= set(new), 'source drops validated history')
    combined = dict(prior)
    for k, r in new.items():
        if k in prior:
            before = prior[k]
            if r['release_date'] < before['release_date']:
                continue
            if r['release_date'] == before['release_date']:
                ignored = {'fetched_at', 'raw_sha256'}
                require(all(str(before[f]) == str(r[f]) for f in r if f not in ignored),
                        'conflicting observation within same official vintage')
                continue
        combined[k] = r
    result = [combined[k] for k in sorted(combined)]
    validate(result)
    return result
