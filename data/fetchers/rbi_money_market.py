"""Official RBI monetary plumbing, including deterministic daily overlap refresh.

python -m data.fetchers.rbi_money_market --start 2025-10-07 --end 2026-10-07
Policy values are effective-date records from RBI resolutions, never inferred
from market rates. WSS liquidity is a different flow concept and is not merged.
The collector supports the SDF regime only (8 April 2022 onwards).
"""
from __future__ import annotations

import argparse
import bisect
import csv
import logging
import math
import os
import re
import tempfile
import time
from zoneinfo import ZoneInfo
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.rbi.org.in/Scripts/'
from data.paths import RBI_MONEY_MARKET_CSV

DEFAULT_PATH = RBI_MONEY_MARKET_CSV
SDF_START = date(2022, 4, 8)
COLUMNS = ['date', 'call_rate', 'treps_rate', 'market_repo_rate',
           'repo_rate', 'sdf_rate', 'msf_rate', 'call_volume_cr', 'treps_volume_cr',
           'market_repo_volume_cr', 'net_liquidity_injection_cr',
           'today_net_liquidity_injection_cr', 'source_unit', 'release_date',
           'source_url', 'policy_source_url', 'fetched_at']
log = logging.getLogger(__name__)


class RbiMoneyMarketError(ValueError):
    """Fail closed on unavailable, ambiguous or malformed official data."""


def official_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in {'rbi.org.in', 'www.rbi.org.in'}:
        raise RbiMoneyMarketError(f'Not an official RBI URL: {url}')
    return url


def soup_for(html):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(' ', strip=True)
    if re.search(r'captcha|verify you are human|access denied|request rejected|checking your browser', text, re.I):
        raise RbiMoneyMarketError('RBI challenge/error page; no observations accepted')
    return soup


def number(text):
    text = str(text).strip().replace('\u2212', '-').replace('\xa0', ' ')
    if text in {'', '-', '–', '—', '..'}:
        return None
    # Accept western and Indian digit grouping; reject misplaced commas.
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?', text):
        raise RbiMoneyMarketError(f'Malformed RBI number: {text!r}')
    result = float(text.replace(',', ''))
    if not math.isfinite(result):
        raise RbiMoneyMarketError('Non-finite value')
    return result


def parse_date(text):
    text = re.sub(r'\s+', ' ', text.strip())
    for fmt in ('%B %d, %Y', '%b %d, %Y', '%d %b %Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise RbiMoneyMarketError(f'Unrecognised RBI date: {text!r}')


def publication_date(soup):
    text = soup.get_text(' ', strip=True)
    match = re.search(r'Date\s*:\s*([A-Za-z]+ \d{1,2}, \d{4}|\d{1,2} [A-Za-z]+ \d{4})', text)
    if not match:
        raise RbiMoneyMarketError('Missing publication date')
    return parse_date(match[1])


def observation_date(html):
    soup = soup_for(html)
    matches = re.findall(r'Money Market Operations as on\s+([A-Za-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4})', soup.get_text(' ', strip=True), re.I)
    dates = {parse_date(m) for m in matches}
    if len(dates) != 1:
        raise RbiMoneyMarketError('Missing/ambiguous Money Market Operations observation date')
    return dates.pop()


def table_rows(soup):
    # Direct cells only: never mistake the page wrapper for an economic row.
    for tr in soup.find_all('tr'):
        cells = tr.find_all(['td', 'th'], recursive=False)
        if cells and not any(c.find('table') for c in cells):
            expanded = []
            for c in cells:
                expanded.append(re.sub(r'\s+', ' ', c.get_text(' ', strip=True)).strip())
                expanded.extend([''] * (int(c.get('colspan', 1)) - 1))
            yield expanded


def parse_mmo(html, source_url, fetched_at=None):
    soup = soup_for(html)
    obs = observation_date(html)
    published = publication_date(soup)
    if published < obs or (published - obs).days > 7:
        raise RbiMoneyMarketError('Implausible publication/observation date pair')
    text = soup.get_text(' ', strip=True)
    units = set(re.findall(r'Amount in\s+(?:₹|`|Rs\.?|Rupees)?\s*(crore|billion)', text, re.I))
    if len(units) != 1:
        raise RbiMoneyMarketError('Missing/ambiguous monetary unit')
    unit = units.pop().lower()
    scale = 1 if unit == 'crore' else 100  # ₹1 billion = ₹100 crore
    if not re.search(r'Weighted\s+Average\s+Rate|Wtd\.?\s*Avg\.?\s*Rate', text, re.I):
        raise RbiMoneyMarketError('Weighted-average market header absent')
    out = dict.fromkeys(COLUMNS)
    out.update(date=obs.isoformat(), release_date=published.isoformat(), source_url=official_url(source_url),
               source_unit=unit, fetched_at=fetched_at or datetime.now(timezone.utc).isoformat())
    in_overnight = False
    seen = set()
    for cells in table_rows(soup):
        label = cells[0]
        if 'Overnight Segment' in label:
            in_overnight = True
        elif 'Term Segment' in label:
            in_overnight = False
        if in_overnight:
            for name, key in [('Call Money', 'call'), ('Triparty Repo', 'treps'), ('Market Repo', 'market_repo')]:
                if re.fullmatch(r'[IVX]+\.\s*' + name, label, re.I):
                    if key in seen or len(cells) != 4:
                        raise RbiMoneyMarketError(f'Unexpected {name} row')
                    volume, rate = number(cells[1]), number(cells[2])
                    if volume is None or volume < 0 or (rate is not None and not 0 < rate < 30):
                        raise RbiMoneyMarketError(f'Invalid {name} volume/rate')
                    # A zero-volume observation has no market rate, even if supplied.
                    if volume == 0:
                        rate = None
                    out[key + '_volume_cr'] = volume * scale
                    out[key + '_rate'] = rate
                    seen.add(key)
        if "Net liquidity injected from today's operations" in label:
            key = 'today_net_liquidity_injection_cr'
        elif "Net liquidity injected (outstanding including today's operations)" in label:
            key = 'net_liquidity_injection_cr'
        else:
            continue
        if key in seen:
            raise RbiMoneyMarketError(f'Duplicate liquidity row: {key}')
        # MMO operation tables: label, auction date, tenor, maturity, amount, rate.
        if len(cells) != 6 or 'injection (+)/absorption (-)' not in label:
            raise RbiMoneyMarketError('Unexpected liquidity layout/sign label')
        value = number(cells[4])
        if value is None:
            raise RbiMoneyMarketError('Missing official net liquidity figure')
        out[key] = value * scale
        seen.add(key)
    required = {'call', 'treps', 'market_repo', 'today_net_liquidity_injection_cr', 'net_liquidity_injection_cr'}
    if not required <= seen:
        raise RbiMoneyMarketError(f'Missing expected MMO rows: {required - seen}')
    return out


def parse_policy(html, source_url):
    soup = soup_for(html)
    published = publication_date(soup)
    text = soup.get_text(' ', strip=True)
    if not re.search(r'Resolution of the Monetary Policy Committee', text, re.I):
        raise RbiMoneyMarketError('Not an RBI MPC resolution')
    # Take only the decision paragraph, before outlook/assessment sections.
    start = re.search(r'policy repo rate', text, re.I)
    if not start:
        raise RbiMoneyMarketError('Policy decision absent')
    decision = text[start.start():start.start() + 1400]
    result = {'date': published, 'source_url': official_url(source_url)}
    for key, label in [('repo_rate', r'policy repo rate'), ('sdf_rate', r'standing deposit facility\s*\(SDF\)\s*rate'),
                       ('msf_rate', r'marginal standing facility\s*\(MSF\)\s*rate')]:
        m = re.search(label + r'[^.]*?\b(?:at|to|be at)\s+(\d+(?:\.\d+)?)\s*per cent', decision, re.I)
        if not m:
            raise RbiMoneyMarketError(f'Cannot identify explicit {key} in decision')
        result[key] = float(m[1])
    if published < SDF_START or not 0 < result['sdf_rate'] <= result['repo_rate'] <= result['msf_rate'] < 30:
        raise RbiMoneyMarketError('Unsupported regime/invalid policy corridor')
    return result


def validate_row(row):
    try:
        obs = date.fromisoformat(row['date'])
        release = date.fromisoformat(row['release_date'])
        fetched = datetime.fromisoformat(row['fetched_at'])
        if fetched.tzinfo is None:
            raise ValueError('fetched_at must include timezone')
    except (TypeError, ValueError, KeyError) as exc:
        raise RbiMoneyMarketError('Malformed stored dates') from exc
    official_url(row['source_url'])
    official_url(row['policy_source_url'])
    if obs < SDF_START or release < obs or row['source_unit'] not in {'crore', 'billion'}:
        raise RbiMoneyMarketError('Invalid stored regime/date/unit')
    for key in COLUMNS[1:12]:
        value = row.get(key)
        if value is not None and not math.isfinite(float(value)):
            raise RbiMoneyMarketError(f'Invalid stored {key}')
    floor, repo, ceiling = [row.get(k) for k in ('sdf_rate', 'repo_rate', 'msf_rate')]
    if None in (floor, repo, ceiling) or not 0 < floor <= repo <= ceiling < 30:
        raise RbiMoneyMarketError('Invalid stored policy corridor')
    for key in ('call', 'treps', 'market_repo'):
        rate, volume = row.get(key + '_rate'), row.get(key + '_volume_cr')
        if volume is None or volume < 0 or (rate is not None and (volume == 0 or not 0 < rate < 30)):
            raise RbiMoneyMarketError(f'Invalid stored {key} observation')
    if row.get('call_rate') is None and row['call_volume_cr'] > 0:
        raise RbiMoneyMarketError('Positive call volume but missing WACR')
    if any(row.get(k) is None for k in ('net_liquidity_injection_cr', 'today_net_liquidity_injection_cr')):
        raise RbiMoneyMarketError('Missing stored liquidity')


def read_rows(path=DEFAULT_PATH):
    if not path.exists():
        raise RbiMoneyMarketError(f'No stored official data: {path}; run collector explicitly')
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise RbiMoneyMarketError('Unexpected canonical CSV schema')
        rows = list(reader)
    if not rows:
        raise RbiMoneyMarketError('Empty canonical dataset')
    seen = set()
    for row in rows:
        for key in COLUMNS[1:12]:
            row[key] = number(row[key])
        validate_row(row)
        if row['date'] in seen:
            raise RbiMoneyMarketError('Duplicate stored observation date')
        seen.add(row['date'])
    validate_dataset(rows)
    return rows


def validate_dataset(rows):
    """Validate the complete chronological canonical series before publication."""
    if not rows:
        raise RbiMoneyMarketError('Empty canonical dataset')
    dates = [r['date'] for r in rows]
    if dates != sorted(set(dates)):
        raise RbiMoneyMarketError('Canonical dates must be unique and chronological')
    for row in rows:
        validate_row(row)
        if row['call_rate'] is not None:
            spread = (row['call_rate'] - row['repo_rate']) * 100
            if not math.isfinite(spread):
                raise RbiMoneyMarketError('Invalid WACR spread calculation')


def persist(rows, path=DEFAULT_PATH):
    if not rows:
        raise RbiMoneyMarketError('Refusing empty update')
    existing = {r['date']: r for r in read_rows(path)} if path.exists() else {}
    # A later release wins; never allow an older publication to undo a correction.
    for row in sorted(rows, key=lambda r: (r['release_date'], r['fetched_at'])):
        validate_row(row)
        previous = existing.get(row['date'])
        unchanged = previous is not None and all(
            row[k] == previous[k] for k in COLUMNS if k != 'fetched_at')
        if not unchanged and (previous is None or (row['release_date'], row['fetched_at']) >= (previous['release_date'], previous['fetched_at'])):
            existing[row['date']] = row
    ordered = [existing[d] for d in sorted(existing)]
    validate_dataset(ordered)
    if path.exists() and ordered == read_rows(path):
        return len(ordered)  # Preserve bytes and retrieval timestamps on no-op.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.rbi_money_market-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(existing[d] for d in sorted(existing))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(existing)


def check_staleness(rows, today):
    """Warn after 3 calendar days; fail after 7, allowing normal 1–4 day lags."""
    age = (today - date.fromisoformat(rows[-1]['date'])).days
    if age < 0:
        raise RbiMoneyMarketError('Latest operations date is in the future')
    if age > 3:
        print(f'::warning::Latest RBI operations are {age} calendar days old ({rows[-1]["date"]})')
    if age > 7:
        raise RbiMoneyMarketError(f'RBI observations stale by {age} calendar days; limit is 7')


def refresh_recent(path=DEFAULT_PATH, overlap=10, today=None, client=None):
    """Refetch the last N stored operations dates through today, including revisions.

    Stage the complete merge, validate and check staleness before atomic replace.
    An empty/bad fetch or invalid merge leaves the prior canonical CSV intact.
    Retrieval timestamps alone never cause a change. Returns a changed boolean.
    """
    if not 7 <= overlap <= 10:
        raise RbiMoneyMarketError('Recent overlap must be 7–10 operations dates')
    today = today or datetime.now(ZoneInfo('Asia/Kolkata')).date()
    before = read_rows(path)
    start = date.fromisoformat(before[max(0, len(before)-overlap)]['date'])
    rows = collect(start, today, client=client)
    with tempfile.TemporaryDirectory(dir=path.parent, prefix='.rbi-refresh-') as folder:
        staged = Path(folder)/path.name
        staged.write_bytes(path.read_bytes())
        persist(rows, staged)
        candidate = read_rows(staged)
        if candidate[-1]['date'] < before[-1]['date']:
            raise RbiMoneyMarketError('Latest operations date moved backwards')
        check_staleness(candidate, today)
        if staged.read_bytes() == path.read_bytes():
            return False
        os.replace(staged, path)
    return True


class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36'

    def get(self, url, **kwargs):
        official_url(url)
        time.sleep(0.25)
        try:
            r = self.session.get(url, timeout=(10, 40), **kwargs)
            r.raise_for_status()
            official_url(r.url)
            soup_for(r.text)
            return r.text
        except requests.RequestException as exc:
            raise RbiMoneyMarketError(f'RBI request failed: {url}: {exc}') from exc

    def archive(self, year, month):
        url = BASE + 'BS_PressReleaseDisplay.aspx'
        soup = soup_for(self.get(url))
        fields = {i['name']: i.get('value', '') for i in soup.select('input[type=hidden][name]')}
        if not {'__VIEWSTATE', '__EVENTVALIDATION', 'hdnYear', 'hdnMonth'} <= fields.keys():
            raise RbiMoneyMarketError('RBI archive form changed')
        fields.update(hdnYear=str(year), hdnMonth=str(month))
        fields['Struct$btn'] = ''  # RBI archive tree's GetYearMonth submit button
        try:
            r = self.session.post(url, data=fields, timeout=(10, 40))
            r.raise_for_status()
            official_url(r.url)
        except requests.RequestException as exc:
            raise RbiMoneyMarketError(f'RBI archive failed: {year}-{month:02}: {exc}') from exc
        soup = soup_for(r.text)
        if not soup.find('input', attrs={'name': 'hdnYear', 'value': str(year)}) or not soup.find('input', attrs={'name': 'hdnMonth', 'value': str(month)}):
            raise RbiMoneyMarketError('RBI archive did not honour requested month')
        links = {}
        for a in soup.find_all('a', href=True):
            title = a.get_text(' ', strip=True)
            if 'Money Market Operations as on' in title or ('Resolution of the Monetary Policy Committee' in title):
                href = official_url(urljoin(BASE, a['href']))
                if 'prid=' not in href:
                    raise RbiMoneyMarketError('Unexpected release link')
                links[href] = title
        current_month = datetime.now(ZoneInfo('Asia/Kolkata')).date().replace(day=1)
        # At a month boundary RBI may not yet have published that month's first
        # release. A validated empty current-month archive is legitimate; the
        # overlap still retrieves previous-month releases. Empty history fails.
        if not any('Money Market Operations as on' in t for t in links.values()) and date(year, month, 1) != current_month:
            raise RbiMoneyMarketError(f'No MMO releases in {year}-{month:02}; no silent empty success')
        return links


def months_between(start, end):
    month = start.replace(day=1)
    while month <= end:
        yield month.year, month.month
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)


def collect(start, end, client=None):
    if start < SDF_START or end < start:
        raise RbiMoneyMarketError('Specify an ordered range within the SDF regime (from 2022-04-08)')
    client = client or Client()
    # Look back for a published initial regime. All resolutions in the interval
    # are then applied on their actual publication/effective date, including hikes.
    lookback = max(SDF_START, start - timedelta(days=190))
    links = {}
    for y, m in months_between(lookback, end + timedelta(days=7)):
        if date(y, m, 1) > datetime.now(ZoneInfo('Asia/Kolkata')).date():
            continue
        links.update(client.archive(y, m))
        log.info('Discovered %s-%02d', y, m)
    policies = []
    for url, title in links.items():
        if 'Resolution of the Monetary Policy Committee' in title:
            policies.append(parse_policy(client.get(url), url))
    policies.sort(key=lambda p: p['date'])
    if not policies or policies[0]['date'] > start:
        raise RbiMoneyMarketError('No authoritative initial policy corridor; cannot fill missing history')
    policy_dates = [p['date'] for p in policies]
    rows = []
    for url, title in links.items():
        if 'Money Market Operations as on' not in title:
            continue
        match = re.search(r'as on\s+([A-Za-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4})', title)
        if not match:
            raise RbiMoneyMarketError(f'Unexpected archive title: {title}')
        obs = parse_date(match[1])
        if not start <= obs <= end:
            continue
        row = parse_mmo(client.get(url), url)
        if row['date'] != obs.isoformat():
            raise RbiMoneyMarketError('Archive/page observation date disagreement')
        policy = policies[bisect.bisect_right(policy_dates, obs) - 1]
        row.update({key: policy[key] for key in ('repo_rate', 'sdf_rate', 'msf_rate')})
        row['policy_source_url'] = policy['source_url']
        rows.append(row)
        log.info('Validated %s', row['date'])
    if not rows:
        raise RbiMoneyMarketError('No observations retrieved; dataset unchanged')
    actual = {date.fromisoformat(r['date']) for r in rows}
    missing = sorted(set(start + timedelta(days=i) for i in range((end-start).days+1)) - actual)
    if missing:
        log.warning('No release retrieved for %s (left missing)', ', '.join(d.isoformat() for d in missing))
    if max(actual) < end:
        log.warning('Latest stored observation is %s; requested end was %s', max(actual), end)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--end', type=date.fromisoformat)
    parser.add_argument('--refresh-recent', action='store_true')
    parser.add_argument('--overlap', type=int, default=10)
    parser.add_argument('--output', type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if args.refresh_recent and (args.start or args.end):
        parser.error('--refresh-recent cannot be combined with --start/--end')
    if not args.refresh_recent and (args.start is None or args.end is None):
        parser.error('Specify --refresh-recent or both --start and --end')
    try:
        if args.refresh_recent:
            changed = refresh_recent(args.output, args.overlap)
            print('Canonical RBI data changed' if changed else 'No new/revised RBI observation; no changes')
            if os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                    output.write(f'changed={str(changed).lower()}\n')
            return
        rows = collect(args.start, args.end)
        total = persist(rows, args.output)
    except (RbiMoneyMarketError, OSError) as exc:
        parser.exit(1, f'RBI monetary-plumbing refresh FAILED; stored data unchanged: {exc}\n')
    print(f'{total} unique official dates persisted to {args.output}')


if __name__ == '__main__':
    main()
