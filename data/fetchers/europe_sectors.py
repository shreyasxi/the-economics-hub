"""STOXX Europe 600 supersector rotation using EUR dividend-adjusted ETFs."""
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.paths import DATA_CACHE, PROJECT_ROOT

# Xetra EUR listings verified against BlackRock's product list. Keep official
# supersectors separate rather than inventing a mapping into S&P's GICS sectors.
PRODUCTS = 'https://www.ishares.com/nl/particuliere-belegger/nl/producten/etf-investments'
SECTORS = {
    'EXV5.DE': 'Automobiles & Parts', 'EXV1.DE': 'Banks',
    'EXV6.DE': 'Basic Resources', 'EXV7.DE': 'Chemicals',
    'EXV8.DE': 'Construction & Materials', 'EXH2.DE': 'Financial Services',
    'EXH3.DE': 'Food & Beverage', 'EXV4.DE': 'Health Care',
    'EXH4.DE': 'Industrial Goods & Services', 'EXH5.DE': 'Insurance',
    'EXH6.DE': 'Media', 'EXH1.DE': 'Oil & Gas',
    'EXH7.DE': 'Personal & Household Goods', 'EXI5.DE': 'Real Estate',
    'EXH8.DE': 'Retail', 'EXV3.DE': 'Technology',
    'EXV2.DE': 'Telecommunications', 'EXV9.DE': 'Travel & Leisure',
    'EXH9.DE': 'Utilities',
}
STEM = '25_macro_europe_sector_rotation'
TTM_STEM = '26_macro_europe_sector_rotation_ttm'


def prepare(histories, today=None):
    today = today or date.today()
    if set(histories) != set(SECTORS):
        raise ValueError('Europe sectors: all 19 configured ETFs are required')
    series = {}
    for ticker, history in histories.items():
        if history.attrs.get('return_basis') != 'adjusted total return':
            raise ValueError(f'Europe sectors: explicit dividend-adjusted closes required for {ticker}')
        # Retain exchange-local dates, avoiding a UTC shift to the previous day.
        dates = pd.DatetimeIndex([pd.Timestamp(d).tz_localize(None).normalize() for d in history.index])
        values = pd.to_numeric(history, errors='raise').to_numpy()
        if dates.isna().any() or dates.duplicated().any():
            raise ValueError(f'Europe sectors: invalid or duplicate dates for {ticker}')
        finite = np.isfinite(values)
        if (values[finite] <= 0).any():
            raise ValueError(f'Europe sectors: non-positive adjusted close for {ticker}')
        s = pd.Series(values, index=dates).replace([np.inf, -np.inf], np.nan).dropna().sort_index()
        # Exclude today's session, which could still be trading during a refresh.
        s = s.loc[s.index < pd.Timestamp(today)]
        if s.empty or (pd.Timestamp(today) - s.index[-1]).days > 7:
            raise ValueError(f'Europe sectors: stale or empty history for {ticker}')
        series[ticker] = s
    available = pd.concat(series, axis=1).dropna(how='all').sort_index()
    common = available.dropna()
    if len(common) < 250:
        raise ValueError('Europe sectors: insufficient common history for trailing 12 months')
    end = common.index[-1]
    if (pd.Timestamp(today) - end).days > 7:
        raise ValueError('Europe sectors: no recent common observation date')
    # Missing data must not quietly lengthen the five-session horizon.
    weekly_dates = available.loc[:end].index[-6:]
    if not common.index[-6:].equals(weekly_dates):
        raise ValueError('Europe sectors: missing session in the latest five-session window')
    week_start = common.index[-6]
    anniversary = end - pd.DateOffset(years=1)
    past = common.loc[:anniversary]
    if past.empty or (anniversary - past.index[-1]).days > 7:
        raise ValueError('Europe sectors: no aligned 12-month starting observation')
    year_start = past.index[-1]
    rows = []
    for ticker, label in SECTORS.items():
        last, week, year = (float(common.at[d, ticker]) for d in (end, week_start, year_start))
        rows.append({'sector': label, 'ticker': ticker, 'weekly': (last / week - 1) * 100,
                     'ttm': (last / year - 1) * 100,
                     'adjusted_close': last, 'week_start_close': week, 'ttm_start_close': year})
    return {'as_of': today.isoformat(), 'latest_observation': end.date().isoformat(),
            'week_start': week_start.date().isoformat(), 'ttm_start': year_start.date().isoformat(),
            'coverage': 'STOXX Europe 600 supersector ETF proxies, including UK and Switzerland',
            'currency': 'EUR', 'return_basis': 'adjusted total return', 'source_products': PRODUCTS,
            'method': 'Adjusted-close ratios on common dates; TTM uses last common close on/before the calendar anniversary',
            'rows': rows}


def generate(output_dir, histories=None, today=None):
    from matplotlib.transforms import ScaledTranslation
    from charts.style import EconStyle
    from charts.templates.change_bars import render_change_bars
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if histories is None:
            from data.fetchers.yfinance_fetcher import YFinanceFetcher
            fetcher = YFinanceFetcher()
            histories = {t: fetcher.get_total_return_series(t, period='2y') for t in SECTORS}
        report = prepare(histories, today)
        cache = DATA_CACHE / 'europe_sectors'
        cache.mkdir(parents=True, exist_ok=True)
        content = pd.concat(histories, axis=1).to_csv().encode()
        digest = hashlib.sha256(content).hexdigest()
        (cache / (digest + '.csv')).write_bytes(content)
        report['retrieval'] = {'sha256': digest, 'validated_at': datetime.now(timezone.utc).isoformat(),
                               'source': 'Yahoo Finance, explicit Adj Close', 'tickers': SECTORS}
        end = pd.Timestamp(report['latest_observation']).strftime('%d %b %Y')
        for key, stem, title in (
            ('weekly', STEM, 'STOXX Europe 600 Sector Rotation | Weekly'),
            ('ttm', TTM_STEM, 'STOXX Europe 600 Sector Rotation | TTM'),
        ):
            start = pd.Timestamp(report['week_start' if key == 'weekly' else 'ttm_start']).strftime('%d %b %Y')
            horizon = '5 trading sessions' if key == 'weekly' else 'Trailing 12 months'
            subtitle = f'{horizon} · EUR ETF total returns · {start} – {end}'
            fig = render_change_bars([r['sector'] for r in report['rows']], [r[key] for r in report['rows']],
                                    title, subtitle,
                                    'Yahoo Finance · iShares ETFs, EUR', source_date=end)
            # Move only the subtitle after layout; leave the house rule in place.
            text = next(t for t in fig.axes[0].texts if t.get_text() == subtitle)
            text.set_transform(text.get_transform() + ScaledTranslation(0, -4 / 72, fig.dpi_scale_trans))
            EconStyle.save_chart(fig, output_dir / (stem + '.png'))
        (output_dir / (STEM + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        return report
    except Exception:
        for stem in (STEM, TTM_STEM):
            for ext in ('png', 'json'):
                (output_dir / (stem + '.' + ext)).unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    report = generate(PROJECT_ROOT / 'output' / 'macro' / date.today().strftime('%Y-%m'))
    print('Europe sector rotation:', report['latest_observation'], report['ttm_start'])
