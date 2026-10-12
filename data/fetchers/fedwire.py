"""Official Fedwire Funds monthly average daily transfer value, USD millions.

HTML is preferred to the dated TXT download: named columns are stable while
TXT has multi-line spatial headers, irregular whitespace and month typos.
No cached or substitute observations are used on retrieval/validation failure.
"""
import calendar
import re

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests

URL = ('https://www.frbservices.org/resources/financial-services/wires/'
       'volume-value-stats/fedwire-funds-service-monthly-statistics/')
FIELD = 'Average daily value of transfers'


def parse_monthly(html):
    soup = BeautifulSoup(html, 'html.parser')
    if 'Fedwire' not in soup.get_text() or 'Funds' not in soup.get_text():
        raise ValueError('Fedwire Funds: unexpected source document')
    candidates = []
    for table in soup.find_all('table'):
        headers = table.select('thead th')
        names = [h.get_text(' ', strip=True) for h in headers]
        matches = [i for i, name in enumerate(names)
                   if FIELD in name and re.search(r'\$\s*millions', name, re.I)]
        if len(matches) == 1 and 'Month' in names:
            candidates.append((table, names, names.index('Month'), matches[0]))
    if len(candidates) != 1:
        raise ValueError('Fedwire Funds: missing or ambiguous average daily value ($ millions) column')
    table, names, month_col, value_col = candidates[0]
    rows = []
    for row in table.select('tbody tr'):
        cells = row.find_all(['th', 'td'])
        if len(cells) != len(names):
            raise ValueError('Fedwire Funds: malformed statistics row')
        month = cells[month_col].get_text(' ', strip=True)
        match = re.fullmatch(r'(\d{4}):\s*([A-Za-z]+)', month)
        if not match:
            raise ValueError(f'Fedwire Funds: malformed month {month!r}')
        try:
            # The official HTML and TXT both spell February 2023 'Feburary'.
            year, label = match.groups()
            label = {'Feburary': 'February'}.get(label, label)
            months = {name.lower(): i for i in range(1, 13)
                      for name in (calendar.month_name[i], calendar.month_abbr[i])}
            if label.lower() not in months:
                raise ValueError('unknown month name')
            date = pd.Period(year=int(year), month=months[label.lower()], freq='M')
        except ValueError as exc:
            raise ValueError(f'Fedwire Funds: invalid month {month!r}') from exc
        raw = cells[value_col].get_text(strip=True)
        if not re.fullmatch(r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', raw):
            raise ValueError(f'Fedwire Funds: invalid average daily value {raw!r}')
        rows.append((date, float(raw.replace(',', ''))))
    series = pd.Series([v for _, v in rows], index=pd.PeriodIndex([d for d, _ in rows], freq='M'),
                       name='fedwire_daily_value_millions', dtype=float).sort_index()
    if series.empty or series.index.duplicated().any():
        raise ValueError('Fedwire Funds: empty data or duplicate months')
    if not np.isfinite(series).all() or (series <= 0).any():
        raise ValueError('Fedwire Funds: nonpositive or non-finite transfer value')
    if not series.index.equals(pd.period_range(series.index[0], series.index[-1], freq='M')):
        raise ValueError('Fedwire Funds: missing published month')
    return series


def fetch_monthly():
    try:
        response = requests.get(URL, timeout=45)
        response.raise_for_status()
        return parse_monthly(response.text)
    except (requests.RequestException, ValueError) as exc:
        raise ValueError(f'Fedwire Funds source/parsing error: {exc}; no chart published') from exc
