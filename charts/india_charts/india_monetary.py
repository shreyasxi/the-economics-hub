"""India monetary conditions in the existing EconStyle; stored official inputs only."""
from __future__ import annotations

import logging
import json
import sqlite3
import argparse
import os
import re
import tempfile
from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from charts.style import EconStyle
from data.fetchers.rbi_money_market import DEFAULT_PATH, RbiMoneyMarketError, read_rows

from data.paths import PROJECT_ROOT as REPO_ROOT, RBI_SENTINEL_DB, CPI_MAIN_STATUS

ROOT = REPO_ROOT
log = logging.getLogger(__name__)
# Stable artifact key keeps dashboard ordering and prevents stale duplicates.
WACR_SPREAD = '19_india_money_market_corridor.png'
LIQUIDITY = '20_india_system_liquidity.png'
REAL = '21_india_real_policy_rate.png'


def crore_to_lakh_crore(value):
    return value / 100_000


def liquidity_average(frame):
    """20 weekday observations; a missing weekday invalidates that window.

    RBI also publishes weekend operations: those stay in the raw bars. RBI does
    not provide a business-day calendar in MMO, so the average explicitly uses
    Mon–Fri, including holidays with published operations, without gap filling.
    """
    daily = frame.set_index('date')['net_liquidity_injection_cr'].sort_index()
    weekdays = daily.reindex(pd.bdate_range(daily.index.min(), daily.index.max()))
    return weekdays.rolling(20, min_periods=20).mean() / 100_000


def banking_system_liquidity(frame):
    """Display RBI's original net injection (+) / absorption (−) convention.

    RBI net injection (+) meets a banking-system deficit; absorption (−)
    indicates surplus. Never mutate the canonical net_liquidity_injection_cr.
    """
    return frame.net_liquidity_injection_cr.copy()


def _finish(fig, ax, output, filename, title, subtitle, source, asof, unit):
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    ax.set_ylabel(unit)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.grid(axis='x', visible=False)
    ax.tick_params(labelsize=EconStyle.FONT_SIZE_TICK)
    ax.legend(loc='upper left', ncol=3, fontsize=EconStyle.FONT_SIZE_ANNOTATION, frameon=False)
    asof_text = asof if isinstance(asof, str) else f'As of {asof:%d %b %Y}'
    EconStyle.add_source(fig, source, asof_text)
    fig.tight_layout(rect=[.02, .07, .98, .97])
    return EconStyle.save_chart(fig, Path(output) / filename)


def wacr_spread_data(frame):
    """Only actual positive-volume WACR dates; connect without calendar filling."""
    if frame.empty or frame.date.isna().any():
        raise RbiMoneyMarketError('WACR observation dates unavailable')
    if frame.date.duplicated().any():
        raise RbiMoneyMarketError('Duplicate WACR observation dates')
    if (~np.isfinite(frame.call_volume_cr) | (frame.call_volume_cr < 0)).any():
        raise RbiMoneyMarketError('Invalid call-market volume')
    missing = frame.call_rate.isna()
    bad = missing & (frame.call_volume_cr > 0)
    if bad.any():
        dates = frame.loc[bad, 'date'].dt.strftime('%Y-%m-%d').tolist()
        raise RbiMoneyMarketError(f'Positive call volume but missing WACR: {dates}')
    if ((~missing) & ((frame.call_volume_cr == 0) | ~np.isfinite(frame.call_rate)
                     | (frame.call_rate <= 0) | (frame.call_rate >= 30))).any():
        raise RbiMoneyMarketError('WACR must be finite with positive call-market volume')
    valid = frame.loc[~missing].sort_values('date').copy()
    if valid.empty or (~np.isfinite(valid.repo_rate) | (valid.repo_rate <= 0)).any():
        raise RbiMoneyMarketError('Comparable WACR / repo observations unavailable')
    valid['spread_bps'] = (valid.call_rate - valid.repo_rate) * 100
    if (~np.isfinite(valid.spread_bps)).any():
        raise RbiMoneyMarketError('Non-finite WACR spread calculation')
    cutoff = frame.date.max() - pd.DateOffset(months=12)
    valid = valid.loc[valid.date >= cutoff]
    if valid.empty:
        raise RbiMoneyMarketError('No recent valid WACR observations')
    return valid.set_index('date')


def spread_display_limits(values):
    """Full observed range with 8% padding on each side (at least 10 bps)."""
    low, high = float(values.min()), float(values.max())
    padding = max(10., .08 * (high - low))
    return low - padding, high + padding


def wacr_spread(frame, output):
    valid = wacr_spread_data(frame)
    low, high = spread_display_limits(valid.spread_bps)
    latest = valid.iloc[-1]
    fig, ax = EconStyle.create_figure(size=(10.5, 5.4))
    ax.axhspan(-10, 10, color='#F2F3F4', zorder=0)
    # Fill to zero with house categorical colours; the observed line is unchanged.
    ax.fill_between(valid.index, valid.spread_bps, 0, where=valid.spread_bps >= 0,
                    interpolate=True, color=EconStyle.CATEGORICAL_COLORS[7],
                    alpha=.25, linewidth=0, zorder=1)
    ax.fill_between(valid.index, valid.spread_bps, 0, where=valid.spread_bps <= 0,
                    interpolate=True, color=EconStyle.CATEGORICAL_COLORS[1],
                    alpha=.25, linewidth=0, zorder=1)
    ax.axhline(0, color=EconStyle.INK, lw=1.25, zorder=2)
    # Plot every actual spread with headroom above and below the full range.
    ax.plot(valid.index, valid.spread_bps, color=EconStyle.LINE_BLUE,
            lw=2.0, zorder=3)
    ax.set_ylim(low, high)
    ax.set_xlim(valid.index.min()-pd.Timedelta(days=3),
                valid.index.max()+pd.Timedelta(days=80))
    candidates = mticker.MaxNLocator(nbins=8, steps=[1, 2, 2.5, 5, 10]).tick_values(low, high)
    # Keep ticks strictly inside the data axis, clear of the house top rule.
    ax.yaxis.set_major_locator(mticker.FixedLocator(
        candidates[(candidates > low) & (candidates < high)]))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda value, pos: f'{value:+.0f} bps'.replace('-', '−') if value else '0 bps'))
    ticks = pd.date_range(valid.index.min().to_period('M').start_time,
                          valid.index.max(), freq='2MS')
    ax.set_xticks(ticks)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.grid(axis='x', visible=False)
    ax.grid(axis='y', color=EconStyle.GRID_COLOR, lw=.8, alpha=1.)
    ax.tick_params(labelsize=EconStyle.FONT_SIZE_TICK)

    latest_y = float(latest.spread_bps)
    ax.scatter([latest.name], [latest_y], s=32, color=EconStyle.LINE_BLUE, zorder=6)
    latest_text = f'Latest: {latest.spread_bps:+.0f} bps'.replace('-', '−')
    ax.annotate(f'{latest_text}\n{latest.name:%d %b %Y}',
                xy=(latest.name,latest_y), xytext=(12,0), textcoords='offset points',
                va='center', fontsize=EconStyle.FONT_SIZE_ANNOTATION,
                color=EconStyle.LINE_BLUE)
    # Vertical sign guide just outside the axis, aligned with the right margin.
    # Each label stays in its own half, clear of the latest-reading annotation.
    for y, text in ((high*.50, 'Overnight funding\ntighter than policy'),
                    (low*.50, 'Overnight funding\neasier than policy')):
        ax.text(1.025, y, text, transform=ax.get_yaxis_transform(),
                ha='center', va='center', rotation=90, multialignment='center',
                fontsize=EconStyle.FONT_SIZE_ANNOTATION,
                color=EconStyle.TEXT_MUTED)
    EconStyle.set_title(ax, 'Overnight Funding vs. the RBI Policy Rate',
                        'Measures how closely actual overnight funding conditions are aligned with the RBI’s policy stance')
    EconStyle.add_top_rule(ax)
    EconStyle.add_source(fig, 'RBI — Money Market Operations / MPC resolutions',
                         f'As of {latest.name:%d %b %Y}')
    fig.tight_layout(rect=[.02, .07, .98, .97])
    return EconStyle.save_chart(fig, Path(output) / WACR_SPREAD)


def liquidity(frame, output):
    """Outstanding RBI operations: injection (+) / absorption (−)."""
    display = frame.sort_values('date').copy()
    display['net_liquidity_injection_cr'] = banking_system_liquidity(display)
    trend = liquidity_average(display)
    cutoff = frame.date.max() - pd.DateOffset(months=12)
    recent = display[display.date >= cutoff]
    values = crore_to_lakh_crore(recent.net_liquidity_injection_cr)
    fig, ax = EconStyle.create_figure('wide')
    ax.bar(recent.date, values, width=.85, color=np.where(values>=0, EconStyle.LINE_MAROON, EconStyle.LINE_TEAL), alpha=.65, linewidth=0)
    shown = trend[trend.index >= cutoff]
    ax.plot(shown.index, shown, color=EconStyle.INK, lw=2, label='20-weekday average')
    ax.axhline(0, color=EconStyle.INK, lw=1.2)
    latest = float(values.iloc[-1])
    avg = trend.dropna()
    state = 'deficit' if latest > 0 else 'surplus' if latest < 0 else 'balance'
    detail = f'Latest {state}: ₹{abs(latest):.2f} lakh cr'
    if not avg.empty:
        detail += f'  |  20D: {avg.iloc[-1]:+.2f}'.replace('-', '−')
        if avg.index[-1] != recent.date.max():
            detail += f' ({avg.index[-1]:%d %b})'
    ax.text(.99, .97, detail, ha='right', va='top', transform=ax.transAxes,
            fontsize=EconStyle.FONT_SIZE_ANNOTATION)
    ax.margins(x=.015, y=.18)
    return _finish(fig, ax, output, LIQUIDITY, 'India’s Banking System Liquidity',
                   'RBI adds cash when banks face a shortage (+), absorbs excess cash (−)',
                   'RBI — Money Market Operations, total outstanding net', recent.date.max(), '₹ lakh crore')


def real_policy_data(macro, sentinel=RBI_SENTINEL_DB, cpi_status=None):
    """Repo at month end less that month's existing CPI YoY; simple ex-post rate.

    The official decision history supplies effective changes, rather than a
    monthly forward fill that might miss an intra-month policy change. Sentinel
    is opened read-only and never modified. Conflicting decisions fail closed.
    """
    with sqlite3.connect(f'file:{sentinel}?mode=ro', uri=True) as conn:
        rates = pd.read_sql_query('SELECT policy_cycle, repo_rate_pct FROM mpc_meetings WHERE policy_cycle IS NOT NULL AND repo_rate_pct IS NOT NULL', conn)
    rates['effective'] = pd.to_datetime(rates.policy_cycle, errors='raise')
    if (rates.groupby('effective').repo_rate_pct.nunique() > 1).any():
        raise RbiMoneyMarketError('Conflicting authoritative repo decisions')
    rates = rates.drop_duplicates('effective').sort_values('effective')
    if rates.empty:
        raise RbiMoneyMarketError('No authoritative repo history')
    monthly = macro[['date','india_cpi_yoy']].copy()
    monthly['date'] = pd.to_datetime(monthly.date).dt.to_period('M').dt.to_timestamp()
    if monthly.date.duplicated().any():
        raise RbiMoneyMarketError('Duplicate monthly CPI observation')
    if cpi_status is None:
        try:
            cpi_status = json.loads((CPI_MAIN_STATUS).read_text())
        except (OSError, ValueError) as exc:
            raise RbiMoneyMarketError('Existing CPI validation snapshot unavailable') from exc
    if cpi_status.get('status') != 'ready':
        raise RbiMoneyMarketError('Existing CPI validation is not ready')
    expected = {r['month']: r['value'] for r in cpi_status.get('changes', [])
                if r['column'] == 'india_cpi_yoy' and r.get('concept') in {'General', 'CPI (General)'}}
    qualified = monthly.date.dt.strftime('%Y-%m').isin(expected)
    if (~qualified & monthly.india_cpi_yoy.notna()).any():
        log.warning('Real rate excludes older/unverified CPI months; no observations changed')
    monthly = monthly[qualified].copy()
    if monthly.empty:
        raise RbiMoneyMarketError('No validated existing headline CPI history')
    for _, row in monthly.iterrows():
        target = expected[row.date.strftime('%Y-%m')]
        if pd.isna(row.india_cpi_yoy) or abs(row.india_cpi_yoy-target) > .005000001:
            raise RbiMoneyMarketError('Existing CPI observation differs from validated snapshot')
    monthly = monthly.sort_values('date')
    monthly['month_end'] = monthly.date + pd.offsets.MonthEnd(0)
    monthly = pd.merge_asof(monthly, rates[['effective','repo_rate_pct']], left_on='month_end', right_on='effective', direction='backward')
    # Do not extend the historical decision record beyond a plausible MPC cycle.
    monthly.loc[(monthly.month_end-monthly.effective).dt.days > 100, 'repo_rate_pct'] = np.nan
    monthly['real_rate'] = monthly.repo_rate_pct - monthly.india_cpi_yoy
    monthly = monthly[monthly.date >= monthly.date.max()-pd.DateOffset(years=5)]
    return monthly.set_index('date').reindex(pd.date_range(monthly.date.min(), monthly.date.max(), freq='MS')).reset_index(names='date')


def latest_real_policy_metric(macro, **kwargs):
    """Current summary metric, using the former chart's identical input rules."""
    valid = real_policy_data(macro, **kwargs).dropna(subset=['real_rate'])
    valid = valid[np.isfinite(valid.real_rate) & (valid.date <= pd.Timestamp(date.today()))]
    if valid.empty:
        raise RbiMoneyMarketError('No comparable repo/CPI observations')
    latest = valid.iloc[-1]
    return {'label': 'Real policy rate', 'value': float(latest.real_rate),
            'display': f'{latest.real_rate:+.2f} pp',
            'period': f'{latest.date:%Y-%m} · ex-post', 'previous': None}


def generate(macro, output, path=DEFAULT_PATH):
    generated = []
    try:
        frame = pd.DataFrame(read_rows(path))
        frame['date'] = pd.to_datetime(frame.date)
        age = (date.today() - frame.date.max().date()).days
        if age > 7:
            log.warning('RBI plumbing source is stale by %s days; charts retain explicit historical as-of date', age)
        generated.extend([wacr_spread(frame, output), liquidity(frame, output)])
    except (RbiMoneyMarketError, OSError) as exc:
        log.warning('RBI monetary plumbing unavailable: %s', exc)
        # An invalid dataset must not leave an old current-edition artifact.
        for name in (WACR_SPREAD, LIQUIDITY):
            (Path(output)/name).unlink(missing_ok=True)
    # Retired chart: remove an earlier local artifact, but retain calculation.
    (Path(output)/REAL).unlink(missing_ok=True)
    return generated


def active_india_edition(assets=ROOT/'assets'):
    """Newest existing YYYY-MM assets edition, as used by the deployed loader.

    Local output/ folders are intentionally excluded: they are development
    previews, not published assets. Never create a new daily/monthly edition.
    """
    base = Path(assets)/'india'
    if not base.is_dir():
        raise RbiMoneyMarketError('No existing India asset edition')
    folders = [p for p in base.iterdir()
               if p.is_dir() and re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', p.name)]
    if not folders:
        raise RbiMoneyMarketError('No existing India asset edition')
    return max(folders, key=lambda p: p.name)


def refresh_current(path=DEFAULT_PATH, assets=ROOT/'assets'):
    """Validate canonical data; render both PNGs before replacing live assets.

    Only the two monetary PNGs are published. Render failures leave both live
    PNGs intact; a replacement failure rolls back any already replaced asset.
    This entry point never reads or modifies Sentinel or the macro database.
    """
    frame = pd.DataFrame(read_rows(path))
    frame['date'] = pd.to_datetime(frame.date)
    wacr_spread_data(frame)
    edition = active_india_edition(assets)
    names = (WACR_SPREAD, LIQUIDITY)
    with tempfile.TemporaryDirectory(dir=edition, prefix='.monetary-render-') as folder:
        staging = Path(folder)
        wacr_spread(frame, staging)
        liquidity(frame, staging)
        for name in names:
            if not (staging/name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                raise RbiMoneyMarketError(f'Chart did not produce a PNG: {name}')
        replaced = []
        try:
            for name in names:
                target = edition/name
                if target.exists():
                    if target.read_bytes() == (staging/name).read_bytes():
                        continue
                    (staging/(name+'.backup')).write_bytes(target.read_bytes())
                os.replace(staging/name, target)
                replaced.append(name)
        except OSError:
            for name in reversed(replaced):
                backup = staging/(name+'.backup')
                if backup.exists():
                    os.replace(backup, edition/name)
                else:
                    (edition/name).unlink()
            raise
    return [edition/name for name in names]


def main():
    parser = argparse.ArgumentParser(description='Regenerate only current India monetary assets')
    parser.add_argument('--refresh-current', action='store_true', required=True)
    parser.add_argument('--path', type=Path, default=DEFAULT_PATH)
    parser.add_argument('--assets', type=Path, default=ROOT/'assets')
    args = parser.parse_args()
    try:
        paths = refresh_current(args.path, args.assets)
        for path in paths:
            print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write(f'edition={paths[0].parent.name}\n')
    except (RbiMoneyMarketError, OSError, ValueError) as exc:
        parser.exit(1, f'RBI monetary chart publication FAILED: {exc}\n')


if __name__ == '__main__':
    main()
