"""Official India external-sector collectors; no workflow or database mutation.

Run: python -m data.fetchers.rbi_external --series all
Use --history-years 3 for an initial quarterly backfill. Subsequent runs refresh
2 release-years (BoP/debt), the current Handbook + Bulletin (REER), and 8 WSS
releases. Every dataset is validated and staged completely before atomic replace.

REER contract: 40 currencies, trade weights, CPI, 2015-16=100 only. RBI's
January 2021 article supplied the revised back-series, replacing 36 currencies /
2004-05 base. Never splice that old series or the six-currency moving base.
BoP uses RBI's directly published quarterly CAB/GDP ratios, including explicit
revision footnotes. No GDP conversion, annualisation, or interpolated quarters.
Debt uses Table 5's ORIGINAL maturity <=1 year / end-quarter FX reserves ratio.
DEA supplies September/December releases absent from the RBI press archive.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import math
import os
import re
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.rbi.org.in/Scripts/'
from data.paths import DATA_DIR, RBI_WSS_CSV, RBI_REER_CSV, INDIA_EXTERNAL_CSV, INDIA_DB

DATA = DATA_DIR
WSS_PATH = RBI_WSS_CSV
REER_PATH = RBI_REER_CSV
VULNERABILITY_PATH = INDIA_EXTERNAL_CSV
REER_METHOD = '40-currency; trade-weighted; CPI combined; RBI January 2021 methodology'
METHOD_URL = BASE + 'BS_ViewBulletin.aspx?Id=20020'  # Methodology, NOT a release discovery ID.
WSS_COLUMNS = ['date', 'total_reserves_usd_mn', 'unit', 'source', 'release_date', 'source_url', 'fetched_at']
REER_COLUMNS = ['date', 'reer', 'unit', 'base', 'methodology', 'provisional', 'release_date', 'source_url', 'fetched_at']
EXT_COLUMNS = ['date', 'current_account_gdp_pct', 'current_account_usd_bn', 'cab_unit', 'cab_release_date', 'cab_source_url', 'cab_status',
               'short_term_debt_reserves_pct', 'external_debt_gdp_pct', 'debt_unit', 'debt_maturity', 'debt_release_date', 'debt_source_url', 'debt_status', 'fetched_at']


class ExternalDataError(ValueError):
    """Reject ambiguous sources without replacing stored data."""


def official_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {
        'www.rbi.org.in', 'rbi.org.in', 'bulletin.rbi.org.in', 'rbidocs.rbi.org.in',
        'wss.rbi.org.in', 'data.rbi.org.in', 'dea.gov.in', 'www.dea.gov.in',
    }:
        raise ExternalDataError(f'Unofficial URL: {url}')
    return url


def now():
    return datetime.now(timezone.utc).isoformat()


def soup_for(html):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(' ', strip=True)
    if len(text) < 50 or re.search(r'captcha|verify you are human|access denied|request rejected|error occurr?ed|enable JavaScript to view', text, re.I):
        raise ExternalDataError('Empty / challenge / error source page')
    return soup


def norm(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip().replace('–', '-').replace('‑', '-')


def number(value):
    value = norm(value).replace('−', '-')
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?', value):
        raise ExternalDataError(f'Invalid number: {value!r}')
    result = float(value.replace(',', ''))
    if not math.isfinite(result):
        raise ExternalDataError('Non-finite observation')
    return result


def parse_date(text):
    for fmt in ('%B %d, %Y', '%b %d, %Y', '%d %b %Y', '%d %B %Y', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(re.sub(r'([A-Za-z])\.', r'\1', norm(text)), fmt).date()
        except ValueError:
            pass
    raise ExternalDataError(f'Invalid date: {text}')


def publication_date(soup):
    text = soup.get_text(' ', strip=True)
    m = re.search(r'Date\s*:\s*([A-Za-z]+ \d{1,2}, \d{4}|\d{1,2} [A-Za-z]+ \d{4})', text)
    if not m:
        raise ExternalDataError('No publication date')
    return parse_date(m[1])


def quarter_end(year, month):
    if month not in (3, 6, 9, 12):
        raise ExternalDataError('Not a quarter-end month')
    return date(int(year), month, calendar.monthrange(int(year), month)[1]).isoformat()


def fiscal_quarter(q, fy):
    year = int(fy[:4]) + (1 if int(q) == 4 else 0)
    return quarter_end(year, {1: 6, 2: 9, 3: 12, 4: 3}[int(q)])


def table_grid(table):
    """Expand actual rowspan/colspan headers; ignore nested page-wrapper tables."""
    grid, spans = [], {}
    for r, tr in enumerate(table.find_all('tr')):
        cells = tr.find_all(['td', 'th'], recursive=False)
        if not cells or any(c.find('table') for c in cells):
            continue
        row, col = [], 0
        for cell in cells:
            while (r, col) in spans:
                row.append(spans[(r, col)]); col += 1
            text = norm(cell.get_text(' ', strip=True))
            width, height = int(cell.get('colspan', 1)), int(cell.get('rowspan', 1))
            for dx in range(width):
                row.append(text)
                for dy in range(1, height):
                    spans[(r + dy, col + dx)] = text
            col += width
        while (r, col) in spans:
            row.append(spans[(r, col)]); col += 1
        grid.append(row)
    return grid


def leaf_tables(soup):
    return [t for t in soup.find_all('table') if not t.find('table')]


def parse_wss(html, source_url, fetched_at=None):
    soup = soup_for(html)
    if not re.search(r'Foreign Exchange Reserves', soup.get_text(' ', strip=True), re.I):
        raise ExternalDataError('Not the WSS Foreign Exchange Reserves table')
    tables = [t for t in leaf_tables(soup) if re.search(r'\bTotal Reserves\b', t.get_text())]
    if len(tables) != 1:
        raise ExternalDataError('Missing / duplicate reserves table')
    rows = table_grid(tables[0])
    totals = [r for r in rows if re.fullmatch(r'(?:1\s+)?Total Reserves', r[0], re.I)]
    if len(totals) != 1 or len(totals[0]) != 9:
        raise ExternalDataError('Unexpected / duplicate Total Reserves row')
    headers = rows[:4]
    dates = set(re.findall(r'As on\s+([A-Za-z]+\.? \d{1,2}, \d{4})', tables[0].get_text(' ', strip=True)))
    if len(dates) != 1 or not any(len(r) == 9 and re.fullmatch(r'US\$\s*Mn\.?', r[2]) for r in headers):
        raise ExternalDataError('Missing observation date / US$ million column')
    obs, release = parse_date(dates.pop()), publication_date(soup)
    if not obs <= release <= obs + timedelta(days=14):
        raise ExternalDataError('Publication date inconsistent with observation date')
    total = number(totals[0][2])
    components = [r for r in rows if re.match(r'1\.[1-4]\s', r[0])]
    if len(components) != 4 or abs(sum(number(r[2]) for r in components) - total) > 3:
        raise ExternalDataError('Reserve components do not reconcile in US$ million')
    if not 0 < total < 10_000_000:
        raise ExternalDataError('Implausible reserve total')
    return [dict(date=obs.isoformat(), total_reserves_usd_mn=total, unit='US$ million', source='RBI WSS',
                 release_date=release.isoformat(), source_url=official_url(source_url), fetched_at=fetched_at or now())]


def validate_reer_contract(text):
    if not re.search(r'40[- ]Currency', text, re.I) or not re.search(r'2015-16\s*=\s*100', norm(text)):
        raise ExternalDataError('REER currency basket / base break')
    if not re.search(r'Consumer Price Index', text, re.I) or not re.search(r'Trade[- ]Weighted', text, re.I):
        raise ExternalDataError('REER CPI / trade-weight convention missing')


def reer_row(obs, value, release, url, provisional):
    value = number(value)
    if not 0 < value < 1000 or obs > release.replace(day=1):
        raise ExternalDataError('Invalid REER month / value')
    return dict(date=obs.isoformat(), reer=value, unit='index', base='2015-16=100', methodology=REER_METHOD,
                provisional=str(bool(provisional)).lower(), release_date=release.isoformat(),
                source_url=official_url(url), fetched_at=now())


def parse_reer(html, source_url):
    soup = soup_for(html); text = soup.get_text(' ', strip=True)
    if not re.search(r'37\.\s*Indices of Nominal Effective Exchange Rate.*Real Effective Exchange Rate', text, re.I):
        raise ExternalDataError('Not RBI Bulletin Table 37')
    validate_reer_contract(text)
    tables = [t for t in leaf_tables(soup) if '40-Currency Basket' in t.get_text()]
    if len(tables) != 1:
        raise ExternalDataError('Missing / ambiguous Table 37')
    rows = table_grid(tables[0]); release = publication_date(soup)
    basket_labels = [r[0] for r in rows if r[0].startswith('40-Currency Basket')]
    if basket_labels != ['40-Currency Basket (Base: 2015-16=100)'] or not re.search(r'Consumer Price Index\s*\(combined\)', text):
        raise ExternalDataError('Primary 40-currency base / CPI methodology changed')
    out, basket, weighting = [], None, None
    targets = []
    for r in rows:
        if '40-Currency Basket' in r[0]: basket, weighting = '40', None
        elif '6-Currency Basket' in r[0]: basket, weighting = '6', None
        elif re.fullmatch(r'1\. Trade-Weighted', r[0]): weighting = 'trade'
        elif 'Export-Weighted' in r[0]: weighting = 'export'
        elif basket == '40' and weighting == 'trade' and re.fullmatch(r'1\.2 REER', r[0]): targets.append(r)
    if len(targets) != 1 or len(targets[0]) != 6:
        raise ExternalDataError('Missing / duplicate exact 40-currency trade REER row')
    # Actual Table 37: two annual columns, then previous-year same month and
    # two current-year months. Expanded merged headers carry year over each month.
    if len(rows[0]) != 6 or len(rows[1]) != 6:
        raise ExternalDataError('Unexpected Table 37 header width')
    for col in range(3, 6):
        year, month = rows[0][col], rows[1][col]
        if not re.fullmatch(r'\d{4}', year): raise ExternalDataError('Monthly REER year absent')
        try: obs = datetime.strptime(year + ' ' + month, '%Y %b').date()
        except ValueError as exc: raise ExternalDataError('Monthly REER label absent') from exc
        # FY provisional note applies to each fiscal year explicitly named.
        fiscal = obs.year if obs.month >= 4 else obs.year - 1
        provisional = f'{fiscal}-{str(fiscal + 1)[-2:]}' in text.split('Note:')[-1]
        out.append(reer_row(obs, targets[0][col], release, source_url, provisional))
    return validate_rows(out, 'reer')


def parse_reer_history(html, source_url):
    """RBI Handbook monthly 40-currency table (number may change annually)."""
    soup = soup_for(html); text = soup.get_text(' ', strip=True)
    if not re.search(r'40-Currency Basket.*Monthly', text, re.I):
        raise ExternalDataError('Not the monthly 40-currency Handbook table')
    validate_reer_contract(text)
    tables = [t for t in leaf_tables(soup) if 'Year/Month' in t.get_text() and 'Trade-Weighted' in t.get_text()]
    if len(tables) != 1: raise ExternalDataError('Ambiguous Handbook table')
    rows = table_grid(tables[0]); release = publication_date(soup)
    bases = set(re.findall(r'Base\s*:\s*(\d{4}-\d{2})\s*=\s*100', norm(tables[0].get_text(' ', strip=True))))
    if bases != {'2015-16'}:
        raise ExternalDataError('Historical REER base discontinuity')
    if rows[0] != ['Year/Month', 'Trade-Weighted', 'Trade-Weighted', 'Export-Weighted', 'Export-Weighted'] * 2:
        raise ExternalDataError('Handbook series columns changed')
    if rows[1] != ['Year/Month', 'NEER', 'REER', 'NEER', 'REER'] * 2:
        raise ExternalDataError('Handbook REER selection ambiguous')
    years = [None, None]; out = []
    notes = text[text.find('Notes :'):]
    provisional_years = {int(y) for y in re.findall(r'\b20\d{2}\b', notes.split('provisional')[0])} if 'provisional' in notes else set()
    for row in rows[3:]:
        if len(row) != 10: continue
        for side, start in enumerate((0, 5)):
            label = row[start]
            if re.fullmatch(r'20\d{2}', label): years[side] = int(label); continue
            if label in list(calendar.month_abbr)[1:]:
                if years[side] is None: raise ExternalDataError('Month without year')
                if row[start + 2] in ('', '-', '..'): continue
                obs = datetime.strptime(f'{years[side]} {label}', '%Y %b').date()
                out.append(reer_row(obs, row[start + 2], release, source_url, years[side] in provisional_years))
    return validate_rows(out, 'reer')


def parse_bop(html, source_url):
    """Quarterly official ratios, with sign from deficit/surplus prose.

    Check every newly published quarterly amount against Credit-Debit=Net.
    Explicit revision footnotes replace the prior ratio for that quarter. Annual,
    half-year, nine-month and monthly statements are never admitted.
    """
    soup = soup_for(html); text = soup.get_text(' ', strip=True)
    if not re.search(r'Developments in India.s Balance of Payments during.*Quarter', text, re.I):
        raise ExternalDataError('Not a quarterly RBI BoP release')
    release = publication_date(soup)
    tables = [t for t in leaf_tables(soup) if re.search(r'Major Items.*Balance of Payments', norm(t.get_text(' ', strip=True)), re.I)]
    if len(tables) != 1 or not re.search(r'US\s*\$\s*billion', tables[0].get_text(), re.I):
        raise ExternalDataError('Quarterly BoP identity / US$ billion unit missing')
    rows = table_grid(tables[0]); current = [r for r in rows if re.fullmatch(r'A\.? Current Account(?: \(1\+2\+3\+4\))?', r[0], re.I)]
    if len(current) != 1: raise ExternalDataError('Ambiguous current account row')
    net_by_period, status_by_period = {}, {}
    column_headers = next((r for r in rows if 'Credit' in r and 'Net' in r), None)
    if column_headers is None: raise ExternalDataError('BoP Credit / Debit / Net headers missing')
    for row in rows:
        for col, label in enumerate(row):
            label = re.sub(r'\s*-\s*', '-', label)
            label = label.replace('(', '').replace(')', '')
            for short, full in [('Apr-Jun','April-June'), ('July-Sept','July-September'), ('Jul-Sept','July-September'), ('Jul-Sep','July-September'), ('Oct-Dec','October-December'), ('Jan-Mar','January-March')]:
                label = re.sub(r'\b' + short + r'\b', full, label)
            m = re.fullmatch(r'(April-June|July-September|October-December|January-March) (\d{4})\s*(PR|P|R|QE)?', label)
            if m and col + 2 < len(current[0]) and column_headers[col] == 'Credit':
                end = quarter_end(m[2], {'April-June':6, 'July-September':9, 'October-December':12, 'January-March':3}[m[1]])
                if end in net_by_period: raise ExternalDataError('Duplicate BoP quarter columns')
                credit, debit, net = [number(v) for v in current[0][col:col+3]]
                if abs(credit - debit - net) > .16: raise ExternalDataError('BoP Credit-Debit does not equal Net')
                net_by_period[end] = net
                status_by_period[end] = {'P':'preliminary', 'PR':'partially revised', 'R':'revised'}.get(m[3], 'published quarterly ratio')
    if not net_by_period: raise ExternalDataError('No quarterly current-account arithmetic')
    paragraphs = list(dict.fromkeys(norm(p.get_text(' ', strip=True)) for p in soup.find_all(['p', 'li']) if not p.find('li')))
    observations = {}
    # Only amount->ratio->quarter phrases with an explicit current-account context.
    pattern = re.compile(r'US\s*\$\s*([\d.]+)\s*billion\s*\(([\d.]+)\s*per cent of GDP\)\s*(?:in|during)\s*Q([1-4])(?:\s*:\s*|\s+of\s+)(\d{4}-\d{2})', re.I)
    for paragraph in paragraphs:
        if not re.search(r'current account|\bCAD\b', paragraph, re.I): continue
        for m in pattern.finditer(paragraph):
            prefix = paragraph[:m.start()]
            signs = list(re.finditer(r'\b(deficit|surplus|CAD)\b', prefix, re.I))
            if not signs: raise ExternalDataError('Current-account sign missing')
            sign = 1 if signs[-1][1].lower() == 'surplus' else -1
            period = fiscal_quarter(m[3], m[4]); amount, ratio = sign * number(m[1]), sign * number(m[2])
            if period in net_by_period and abs(net_by_period[period] - amount) > .11:
                raise ExternalDataError('Quarterly ratio amount inconsistent with Net')
            record = dict(date=period, current_account_gdp_pct=ratio, current_account_usd_bn=amount,
                          cab_unit='% of quarterly GDP', cab_release_date=release.isoformat(),
                          cab_source_url=official_url(source_url), cab_status=status_by_period.get(period, 'published quarterly ratio'), fetched_at=now())
            if period in observations and observations[period]['current_account_gdp_pct'] != ratio:
                raise ExternalDataError('Conflicting quarterly ratios')
            observations[period] = record
    # Archived releases also put the fiscal quarter before the amount, or
    # inside the GDP-ratio parentheses. Require an explicit quarter and keep
    # the same arithmetic check; never admit annual/half-year ratios.
    historical = [
        re.compile(r'Q([1-4]) of (\d{4}-\d{2}) was US\s*\$\s*([\d.]+) billion\s*\(([\d.]+) per cent of GDP\)', re.I),
        re.compile(r'US\s*\$\s*([\d.]+) billion\s*\(([\d.]+) per cent of GDP in Q([1-4]) of (\d{4}-\d{2})\)', re.I),
    ]
    for paragraph in paragraphs:
        if not re.search(r'current account|\bCAD\b', paragraph, re.I): continue
        for index, pattern_h in enumerate(historical):
            for m in pattern_h.finditer(paragraph):
                q, fy, amount, ratio = (m[1], m[2], m[3], m[4]) if index == 0 else (m[3], m[4], m[1], m[2])
                signs = list(re.finditer(r'\b(deficit|surplus|CAD)\b', paragraph[:m.start()], re.I))
                if not signs: raise ExternalDataError('Historical CAB sign missing')
                sign = 1 if signs[-1][1].lower() == 'surplus' else -1
                period = fiscal_quarter(q, fy)
                if period not in net_by_period or abs(net_by_period[period] - sign*number(amount)) > .11:
                    raise ExternalDataError('Historical CAB amount inconsistent with Net')
                observations[period] = dict(date=period, current_account_gdp_pct=sign*number(ratio),
                    current_account_usd_bn=sign*number(amount), cab_unit='% of quarterly GDP',
                    cab_release_date=release.isoformat(), cab_source_url=official_url(source_url),
                    cab_status=status_by_period[period], fetched_at=now())

    # Explicit previous-quarter comparison in a revision footnote.
    for paragraph in paragraphs:
        for m in re.finditer(r'In Q([1-4]):(\d{4}-\d{2}), the current account (deficit|surplus) stood at US\$\s*([\d.]+) billion\s*\(([\d.]+) per cent of GDP\)', paragraph, re.I):
            sign = -1 if m[3].lower() == 'deficit' else 1
            period = fiscal_quarter(m[1], m[2])
            observations[period] = dict(date=period, current_account_gdp_pct=sign*number(m[5]),
                current_account_usd_bn=sign*number(m[4]), cab_unit='% of quarterly GDP',
                cab_release_date=release.isoformat(), cab_source_url=official_url(source_url),
                cab_status='explicit revision', fetched_at=now())
    # Revision prose often places the quarter BEFORE its revised amount/ratio.
    revision = re.compile(r'current account (deficit|surplus) for Q([1-4]):(\d{4}-\d{2}).*?US\$\s*([\d.]+)\s*billion\s*\(([\d.]+)\s*per cent of GDP\).*?(?:to|from)\s*US\$\s*([\d.]+)\s*billion\s*\(([\d.]+)\s*per cent of GDP\)', re.I)
    for paragraph in paragraphs:
        for m in revision.finditer(paragraph):
            # "revised to NEW from OLD" versus "revised from OLD to NEW".
            first_new = bool(re.search(r'revised to', m[0], re.I))
            amount, ratio = (m[4], m[5]) if first_new else (m[6], m[7])
            sign = -1 if m[1].lower() == 'deficit' else 1
            period = fiscal_quarter(m[2], m[3])
            observations[period] = dict(date=period, current_account_gdp_pct=sign*number(ratio),
                current_account_usd_bn=sign*number(amount), cab_unit='% of quarterly GDP',
                cab_release_date=release.isoformat(), cab_source_url=official_url(source_url),
                cab_status='explicit revision', fetched_at=now())
    return validate_rows(list(observations.values()), 'cab')


def debt_rows(rows, release, source_url):
    header = norm(' '.join(str(v) for row in rows[:2] for v in row))
    if not all(x in header.lower() for x in ['end-march', 'external', 'gdp', 'foreign', 'reserves', 'original', 'maturity']):
        raise ExternalDataError('Debt Table 5 convention / units changed')
    if len(rows[0]) != 8 or 'GDP' not in rows[0][2] or not all(x in norm(rows[0][6]).lower() for x in ['short', 'foreign', 'reserves']):
        raise ExternalDataError('Debt ratio columns changed')
    out = []
    for row in rows[2:]:
        if len(row) != 8: continue
        label = norm(row[0])
        partial = re.fullmatch(r'(\d{4})-\d{2}\s*(PR|P|R|QE)?\s*\(end-(Dec|Sept)\.?\)', label, re.I)
        if partial:
            label = f"End-{'December' if partial[3].lower()=='dec' else 'September'} {partial[1]} {partial[2] or ''}"
        fy = re.fullmatch(r'(\d{4})-(\d{2})\s*(PR|P|R|QE)?', label)
        if fy:
            label = str(int(fy[1])+1) + ' ' + (fy[3] or '')
        # Keep QE (quick estimate) distinct from P (provisional).
        label = re.sub(r'^End Dec[’\'](\d{2})', lambda m:'End-December 20'+m[1], label)
        label = re.sub(r'(?i)End[- ](Sept\.?|Sep\.?|Dec\.?)(?=\s*\d)\s*', lambda m: 'End-' + ('September' if m[1].lower().startswith('s') else 'December') + ' ', label)
        label = re.sub(r'^Sep\. (\d{4})', r'End-September \1', label)
        m = re.fullmatch(r'(?:[Ee]nd[- ](March|June|September|December)\s+)?(\d{4})\s*(PR|P|R|QE)?', label)
        if not m: continue
        month = {'March':3, 'June':6, 'September':9, 'December':12}.get(m[1] or 'March')
        obs = quarter_end(m[2], month)
        if obs > release.isoformat(): raise ExternalDataError('Future debt quarter')
        # Debt-service ratios are unrelated to the selected indicator and may
        # have overlapping footnote glyphs in archived PDFs. Do not parse them.
        values = [number(re.sub(r'\s*[#*^a-d]+$', '', norm(v))) if i != 2 and norm(v) not in ('*', '-', '') else None for i,v in enumerate(row[1:])]
        debt, gdp, service, reserves_total, concessional, short_reserves, short_total = values
        if debt <= 0 or not all(v is None or 0 <= v <= 1000 for v in values[1:]): raise ExternalDataError('Invalid debt indicators')
        # Official rounded percentages must satisfy S/R = (S/D)/(R/D)*100.
        expected = short_total / reserves_total * 100 if reserves_total else math.inf
        tolerance = .15 + 5.1 / reserves_total if reserves_total else 0
        if abs(short_reserves - expected) > tolerance:
            raise ExternalDataError('Debt ratios fail denominator identity')
        out.append(dict(date=obs, short_term_debt_reserves_pct=short_reserves, external_debt_gdp_pct=gdp if gdp is not None else '',
                        debt_unit='%', debt_maturity='original maturity <=1 year', debt_release_date=release.isoformat(),
                        debt_source_url=official_url(source_url), debt_status=m[3] or 'published', fetched_at=now()))
    return validate_rows(out, 'debt')


def historical_debt_grid(rows, context):
    """Map archived indicator columns by their printed definitions, not position."""
    start = next((i for i,r in enumerate(rows) if norm(r[0]).lower() in ('year', 'end-march', 'end- march', 'end march')), None)
    if start is None: raise ExternalDataError('Debt header missing')
    rows = rows[start:]
    # Ignore completely empty extraction columns, never populated cells.
    keep = [i for i in range(len(rows[0])) if any(norm(r[i]) for r in rows if len(r)==len(rows[0]))]
    rows = [[r[i] for i in keep] for r in rows if len(r)==len(rows[0])]
    if len(rows)>1 and not rows[1][0] and 'GDP' in norm(' '.join(rows[1])):
        rows = [[rows[0][0]] + rows[1][1:]] + rows[2:]
    # PDF split the period label across two columns, with no second header.
    if len(rows[0])==9 and not rows[0][1]:
        if any(r[0].startswith('End-') and r[1] and not re.fullmatch(r'20\d{2}\s*(PR|P|R|QE)?',r[1]) for r in rows[2:]):
            raise ExternalDataError('Ambiguous split debt period')
        rows = [[norm(r[0]+' '+r[1])] + r[2:] for r in rows]
    headers = [re.sub(r'[-\s]+', '', norm(c).lower()).replace('external', '') for c in rows[0]]
    if len(headers) != 8: raise ExternalDataError('Historical debt column count changed')
    # Explicit original-maturity wording must qualify the indicator table or
    # its corresponding ratio prose. Residual-maturity tables are excluded.
    if not (any('short' in h and 'originalmaturity' in h for h in headers) or
            re.search(r'(?:ratio of )?short[- ]?term(?: external)? debt \(original maturity\) to foreign exchange reserves|short[- ]?term(?: external)? debt is based on original maturity', re.sub(r'-\s+', '-', norm(context)), re.I)):
        raise ExternalDataError('Historical original-maturity convention missing')
    def column(required, excluded=()):
        matches = [i for i,h in enumerate(headers) if all(w in h for w in required) and not any(w in h for w in excluded)]
        if len(matches) != 1: raise ExternalDataError('Historical debt ratio selection ambiguous')
        return matches[0]
    indices = [0, 1, column(['gdp']), column(['service']),
               column(['reserves','totaldebt'], ['short']), column(['concess']),
               column(['short','foreign','reserves']), column(['short','totaldebt'])]
    canonical = ['End-March','External Debt (US$ billion)','Ratio of External Debt to GDP',
                 'Debt Service Ratio','Ratio of Foreign Exchange Reserves to Total Debt',
                 'Ratio of Concessional Debt to Total Debt','Ratio of Short-term Debt to Foreign Exchange Reserves',
                 'Ratio of Short-term Debt (original maturity) to Total Debt']
    return [canonical, ['1','2','3','4','5','6','7','8']] + [[r[i] for i in indices] for r in rows[1:] if len(r)==8]


def parse_debt(html, source_url):
    soup = soup_for(html); text = norm(soup.get_text(' ', strip=True))
    if not re.search(r'India.s External Debt (?:as at|at|end-)', text, re.I): raise ExternalDataError('Not an RBI debt release')
    tables = [t for t in leaf_tables(soup) if re.search(r'Table [45]\s*:.*Key External Debt Indicators', norm(t.get_text(' ', strip=True)))]
    if len(tables) != 1: raise ExternalDataError('Debt indicator table missing / ambiguous')
    table = tables[0]; rows = table_grid(table)
    if not re.search(r'\(per cent(?:, unless indicated otherwise)?\)', ' '.join(c for r in rows[:4] for c in r), re.I): raise ExternalDataError('Debt ratio unit missing')
    # Newer tables carry the convention directly in the column header.
    # Earlier editions qualify it in adjacent release prose.
    return debt_rows(historical_debt_grid(rows, text), publication_date(soup), source_url)


def unruled_debt_table(page):
    """Read eight printed columns using the table's numbered column guide.

    Coordinates select published cells only; this does not calculate ratios.
    Some older DEA reports have no drawn grid, while others merge header cells.
    """
    words = page.extract_words()
    lines = {}
    for word in words:
        lines.setdefault(round(word['top']), []).append(word)
    guides = [ws for ws in lines.values() if [w['text'] for w in ws] == list('12345678')]
    if len(guides) != 1: raise ExternalDataError('Unruled debt column guide ambiguous')
    guide = guides[0]; y = guide[0]['top']
    centers = [(w['x0']+w['x1'])/2 for w in guide]
    boundaries = [(a+b)/2 for a,b in zip(centers,centers[1:])]
    title_lines = [top for top,ws in lines.items() if 'Indicators' in ' '.join(w['text'] for w in ws) and top < y]
    if not title_lines: raise ExternalDataError('Unruled debt title missing')
    title_y = max(title_lines)
    def cells(ws):
        out = ['']*8
        for word in ws:
            col = sum((word['x0']+word['x1'])/2 > b for b in boundaries)
            out[col] += ' ' + word['text']
        return [norm(c) for c in out]
    headers = cells([w for w in words if title_y+5 < w['top'] < y-2])
    rows = [headers, list('12345678')]
    cell = r'(?:[\d.,]+[#*a-d]?|\*|-)'
    data_line = re.compile(r'^(.+?)\s+' + r'\s+'.join([f'({cell})']*7) + r'$')
    for line in (page.extract_text() or '').splitlines():
        match = data_line.fullmatch(norm(line))
        if match and re.match(r'(?:End[- ]|\d{4})', match[1], re.I):
            rows.append(list(match.groups()))
        elif re.fullmatch(r'\(end-(Dec|Sept)\.?\)', norm(line), re.I) and len(rows)>2:
            rows[-1][0] += ' ' + norm(line)
    if len(rows) <= 2: raise ExternalDataError('Unruled debt observations missing')
    return rows


def parse_dea_pdf(content, source_url, release_date):
    import pdfplumber
    official_url(source_url)
    if not content.startswith(b'%PDF'): raise ExternalDataError('Not a DEA PDF')
    candidates = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = ' '.join(p.extract_text() or '' for p in pdf.pages)
        if 'external debt' not in text.lower() or not ('department of economic affairs' in norm(text).lower() or re.search(r'India.s External Debt as at', norm(text), re.I)):
            raise ExternalDataError('DEA debt identity missing')
        for page in pdf.pages:
            context = norm(page.extract_text() or '')
            if not re.search(r'Table [4-7]\s*:.*Key External Debt Indicators', context, re.I): continue
            if not re.search('per cent', context, re.I): raise ExternalDataError('DEA debt percent unit missing')
            tables = page.extract_tables()
            if not any(any(r and norm(r[0]).lower() in ('year','end-march','end- march','end march') for r in t) for t in tables):
                tables = [unruled_debt_table(page)]
            for table in tables:
                rows = [[norm(c) for c in r] for r in table]
                if any(r and norm(r[0]).lower() in ('year','end-march','end- march','end march') for r in rows):
                    candidates.append(historical_debt_grid(rows, context))
    if len(candidates) != 1: raise ExternalDataError('DEA indicator table missing / ambiguous')
    return debt_rows(candidates[0], parse_date(release_date), source_url)


def validate_rows(rows, kind):
    if not rows: raise ExternalDataError(f'Empty {kind} observations')
    seen = set()
    for row in rows:
        obs = parse_date(row['date'])
        if row['date'] in seen: raise ExternalDataError(f'Duplicate {kind} period: {obs}')
        seen.add(row['date'])
        if obs > datetime.now(timezone.utc).date(): raise ExternalDataError('Future observation')
        if kind == 'reer':
            if obs.day != 1 or row['base'] != '2015-16=100' or row['methodology'] != REER_METHOD or row['unit'] != 'index':
                raise ExternalDataError('REER frequency / methodology / base break')
            if not 0 < number(row['reer']) < 1000: raise ExternalDataError('Invalid REER value')
        elif kind in ('cab', 'debt', 'external'):
            if row['date'] != quarter_end(obs.year, obs.month): raise ExternalDataError('Not end-quarter')
            if kind == 'external' and all(row.get(f) in (None, '') for f in ('current_account_gdp_pct', 'short_term_debt_reserves_pct')):
                raise ExternalDataError('Empty quarterly observation')
            if row.get('current_account_gdp_pct') not in (None, ''):
                if row.get('cab_unit') != '% of quarterly GDP' or abs(number(row['current_account_gdp_pct'])) > 100:
                    raise ExternalDataError('Invalid CAB ratio / unit')
                official_url(row['cab_source_url'])
            if row.get('short_term_debt_reserves_pct') not in (None, ''):
                if row.get('debt_unit') != '%' or row.get('debt_maturity') != 'original maturity <=1 year' or not 0 <= number(row['short_term_debt_reserves_pct']) < 1000:
                    raise ExternalDataError('Invalid debt ratio / maturity / unit')
                official_url(row['debt_source_url'])
        elif kind == 'wss':
            if row['unit'] != 'US$ million' or not 0 < number(row['total_reserves_usd_mn']) < 10_000_000:
                raise ExternalDataError('Invalid reserves / unit')
        if row.get('source_url'): official_url(row['source_url'])
    return sorted(rows, key=lambda r:r['date'])


def read_rows(path, kind):
    path = Path(path)
    if not path.exists(): return []
    with path.open(newline='') as handle:
        return validate_rows(list(csv.DictReader(handle)), kind)


def merge_rows(old, new, kind):
    if old: validate_rows(old, kind)
    validate_rows(new, kind)
    merged = {r['date']: dict(r) for r in old}
    for row in new:
        target = merged.setdefault(row['date'], {})
        prefixes = ('cab_', 'current_account_') if kind == 'cab' else ('debt_', 'external_debt_', 'short_term_') if kind == 'debt' else None
        if prefixes:
            field = 'cab_release_date' if kind == 'cab' else 'debt_release_date'
            if target.get(field, '') > row[field]: continue
            target.update({k:v for k,v in row.items() if k.startswith(prefixes) or k in ('date','fetched_at')})
        else:
            # Release date, not retrieval time, determines economic revision order.
            if target.get('release_date', '') > row.get('release_date', ''): continue
            target.update(row)
    return sorted(merged.values(), key=lambda r:r['date'])


def atomic_write(path, rows, columns, kind):
    rows = validate_rows(rows, kind); path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns); writer.writeheader(); writer.writerows(rows)
            handle.flush(); os.fsync(handle.fileno())
        read_rows(temp, kind)  # validate serialised output before replacement
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


class OfficialClient:
    """Bounded requests; challenges never become datasets. Cache is audit evidence."""
    def __init__(self, cache_dir=None):
        self.session = requests.Session(); self.cache_dir = Path(cache_dir) if cache_dir else None
        self.session.headers['User-Agent'] = 'EconHub official statistics collector'

    def get(self, url):
        official_url(url); response = self.session.get(url, timeout=(15, 60)); response.raise_for_status(); official_url(response.url)
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha256(url.encode()).hexdigest()
            (self.cache_dir / (key + '.bin')).write_bytes(response.content)
            (self.cache_dir / (key + '.url')).write_text(url)
        return response.content

    def archive(self, url, year, month=0):
        soup = soup_for(self.get(url))
        data = {x['name']:x.get('value','') for x in soup.select('input[type=hidden][name]')}
        if not all(x in data for x in ('__VIEWSTATE', 'hdnYear', 'hdnMonth')):
            raise ExternalDataError('RBI archive form changed')
        data.update(hdnYear=str(year), hdnMonth=str(month), btn='Search')
        response = self.session.post(url, data=data, timeout=(15,60)); response.raise_for_status(); official_url(response.url)
        return response.content


def links_matching(html, pattern, base=BASE):
    soup = soup_for(html)
    return list(dict.fromkeys(official_url(urljoin(base,a['href'])) for a in soup.select('a[href]')
                             if re.search(pattern, a.get_text(' ',strip=True), re.I)))


def discover_wss_releases(html, weeks=8):
    """Use RBI's calendar routes, never one historic document ID.

    Extract calendar supplies actual published dates, including month rollover.
    Its latest published date anchors the full-document calendar's documented
    weekly query route; every candidate must resolve to a validated release.
    """
    soup = soup_for(html)
    dates = [datetime.strptime(m, '%m/%d/%Y').date() for m in re.findall(r'SelectedDate=(\d{1,2}/\d{1,2}/\d{4})', str(soup))]
    if not dates: raise ExternalDataError('No published WSS calendar dates')
    latest = max(dates)
    return [BASE + 'WSSViewDetail.aspx?TYPE=Basic&PARAM1=' + (latest - timedelta(weeks=i)).strftime('%m/%d/%Y') for i in reversed(range(weeks))]


def collect_wss(client, weeks=8):
    releases = discover_wss_releases(client.get(BASE + 'BS_viewWssExtract.aspx'), weeks)
    rows = []
    for release_url in releases:
        html = client.get(release_url)
        tables = links_matching(html, r'^Foreign Exchange Reserves$')
        if len(tables) != 1: raise ExternalDataError('WSS reserves link absent / ambiguous')
        rows.extend(parse_wss(client.get(tables[0]), tables[0]))
    return validate_rows(rows, 'wss')


def legacy_reserves(path=INDIA_DB):
    with sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro', uri=True) as conn:
        rows = conn.execute('SELECT week_ending, forex_reserves_usd_bn, fetched_at FROM india_weekly WHERE forex_reserves_usd_bn IS NOT NULL ORDER BY week_ending').fetchall()
    return [dict(date=d, total_reserves_usd_mn=v*1000, unit='US$ million', source='RBI DBIE legacy; WSS overlap checked',
                 release_date='', source_url='https://data.rbi.org.in/DBIE/', fetched_at=t or now()) for d,v,t in rows]


def compare_legacy(old, wss, minimum=5):
    by_date = {r['date']:r for r in old}; comparisons = []
    for row in wss:
        if row['date'] not in by_date: continue
        difference = number(row['total_reserves_usd_mn']) - number(by_date[row['date']]['total_reserves_usd_mn'])
        # WSS HTML is whole US$ million, DBIE stores tenths: within half a
        # million is equivalent at WSS publication precision, not a definition break.
        comparisons.append((row['date'], number(by_date[row['date']]['total_reserves_usd_mn']), number(row['total_reserves_usd_mn']), difference))
        if abs(difference) > .500001: raise ExternalDataError(f'DBIE/WSS definition/date mismatch: {comparisons[-1]}')
    if len(comparisons) < minimum: raise ExternalDataError('Need at least five DBIE/WSS overlaps before migration')
    return comparisons


def refresh_wss(client=None, path=WSS_PATH, weeks=8, dry_run=False):
    new = collect_wss(client or OfficialClient(), weeks)
    old = read_rows(path, 'wss')
    if not old:
        old = legacy_reserves(); compare_legacy(old, new)
    merged = merge_rows(old, new, 'wss')
    if not dry_run: atomic_write(path, merged, WSS_COLUMNS, 'wss')
    return merged


def collect_reer(client):
    bulletin = client.get(BASE + 'BS_ViewBulletin.aspx')
    urls = links_matching(bulletin, r'^37\. Indices of Nominal Effective Exchange Rate')
    if len(urls) != 1: raise ExternalDataError('Current Table 37 discovery failed')
    current = parse_reer(client.get(urls[0]), urls[0])
    handbook = BASE + 'AnnualPublications.aspx?head=Handbook%20of%20Statistics%20on%20Indian%20Economy'
    urls = links_matching(client.get(handbook), r'40-Currency Basket.*Monthly')
    if len(urls) != 1: raise ExternalDataError('Monthly Handbook discovery failed')
    history = parse_reer_history(client.get(urls[0]), urls[0])
    # Refresh the preceding two Bulletin editions: the Handbook may lag by
    # several months, and the current table supplies just the last two months.
    release = parse_date(current[-1]['release_date'])
    for lag in (2, 1):
        serial = release.year * 12 + release.month - 1 - lag
        year, month = divmod(serial, 12)
        archive = client.archive(BASE + 'BS_ViewBulletin.aspx', year, month + 1)
        prior_urls = links_matching(archive, r'^37\. Indices of Nominal Effective Exchange Rate')
        if len(prior_urls) != 1: raise ExternalDataError('Previous Table 37 discovery failed')
        history = merge_rows(history, parse_reer(client.get(prior_urls[0]),prior_urls[0]), 'reer')
    return merge_rows(history, current, 'reer')


def discover_dea(html):
    soup = soup_for(html); out=[]
    for a in soup.select('a[href]'):
        if '/external_debt_documents/' not in a['href'] or not a['href'].lower().endswith('.pdf'): continue
        if not re.search(r'Quarter', a['href'], re.I): continue
        parent = a.parent
        while parent and not (re.search(r'\d{2}\.\d{2}\.\d{4}', parent.get_text()) and 'Quarter' in parent.get_text()): parent = parent.parent
        if parent is None: continue
        # Smallest parent contains exactly one published date and the report title.
        dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', parent.get_text())
        if len(dates) != 1: raise ExternalDataError('DEA release date ambiguous')
        out.append((official_url(urljoin('https://dea.gov.in/',a['href'])), parse_date(dates[0])))
    if not out: raise ExternalDataError('DEA quarterly archive empty')
    return list(dict.fromkeys(out))


def collect_vulnerability(client, years=2):
    cab, debt = [], []
    current_year = datetime.now(timezone.utc).year
    press = BASE + 'BS_PressReleaseDisplay.aspx'
    for year in range(current_year-years+1, current_year+1):
        html = client.archive(press, year)
        for url in links_matching(html, r'Developments in India.s Balance of Payments during.*Quarter'):
            cab = merge_rows(cab, parse_bop(client.get(url), url), 'cab')
        for url in links_matching(html, r'India.s External Debt as at'):
            debt = merge_rows(debt, parse_debt(client.get(url), url), 'debt')
    # Supplement missing official quarters, and accept revised Table 5 observations
    # from newer DEA editions. Never replace a newer RBI release with an older PDF.
    dea = discover_dea(client.get('https://dea.gov.in/reports-external-debt'))
    for url, release in sorted(dea, key=lambda p:p[1]):
        if release.year < current_year-years+1: continue
        # Some archive entries are statements only; full Quarterly reports contain
        # Table 5. Only those full reports satisfy this collector's contract.
        if 'Statement' in url or 'Quarter' not in url: continue
        debt = merge_rows(debt, parse_dea_pdf(client.get(url),url,release.isoformat()), 'debt')
    if not cab or not debt: raise ExternalDataError('Both quarterly sources required')
    combined = merge_rows(cab, debt, 'debt')
    cutoff = quarter_end(current_year-years, 12)
    combined = [dict.fromkeys(EXT_COLUMNS, '') | r for r in combined if r['date'] > cutoff]
    return validate_rows(combined, 'external')


def refresh_reer(client=None, path=REER_PATH):
    new = collect_reer(client or OfficialClient()); old=read_rows(path,'reer')
    merged=merge_rows(old,new,'reer'); atomic_write(path,merged,REER_COLUMNS,'reer'); return merged


def refresh_vulnerability(client=None, path=VULNERABILITY_PATH, years=2):
    new = collect_vulnerability(client or OfficialClient(),years); old=read_rows(path,'external')
    # Each indicator's publication determines revisions independently; blank
    # observations never delete stored good values from the other source.
    merged=old
    for kind,field in [('cab','current_account_gdp_pct'),('debt','short_term_debt_reserves_pct')]:
        incoming=[r for r in new if r.get(field) not in ('',None)]
        merged=merge_rows(merged,incoming,kind)
    merged=[dict.fromkeys(EXT_COLUMNS,'') | r for r in merged]
    atomic_write(path,merged,EXT_COLUMNS,'external');return merged


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series',choices=['all','wss','reer','vulnerability'],default='all')
    parser.add_argument('--history-years',type=int,default=2)
    parser.add_argument('--wss-weeks',type=int,default=8)
    parser.add_argument('--cache-dir',type=Path)
    args=parser.parse_args(); client=OfficialClient(args.cache_dir)
    failures=[]
    for name,action in [('wss',lambda:refresh_wss(client,weeks=args.wss_weeks)),('reer',lambda:refresh_reer(client)),('vulnerability',lambda:refresh_vulnerability(client,years=args.history_years))]:
        if args.series not in ('all',name): continue
        try:
            rows=action();print(f'{name}: {len(rows)} observations, {rows[0]["date"]} through {rows[-1]["date"]}')
        except Exception as exc:
            failures.append(name);print(f'{name} refresh FAILED; stored data preserved: {exc}')
    if failures: raise SystemExit(1)


if __name__ == '__main__': main()
