"""Offline official IIP industry breadth and PLFS snapshot metrics.

python -m charts.india_charts.india_mospi_activity --output-dir output/india/YYYY-MM
Collectors run separately; generation does not access the network or other charts.
"""
import argparse
from datetime import datetime
import math
import os
from pathlib import Path
import re
import statistics
import tempfile

import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter, MultipleLocator
import pandas as pd

from charts.style import EconStyle
from data.fetchers.mospi_dashboard import ROOT, require, atomic_json
from data.fetchers import mospi_iip_industries as iip
from data.fetchers import mospi_plfs_monthly as plfs

HEATMAP = 'india_iip_industry_heatmap.json'
YOUTH = '15b_india_urban_youth_unemployment.png'
NOTE = 'Cell colour saturates at ±20%; numbers show actual YoY growth.'


def cell_style(value):
    if value is None:
        return '#f1f1ef', '#646464'
    neutral = (239, 240, 239)
    target = (30, 93, 143) if value > 0 else (119, 52, 70)
    saturation = min(abs(value) / 20, 1)
    color = '#' + ''.join(f'{round(a + (b-a)*saturation):02x}' for a, b in zip(neutral, target))
    return color, '#ffffff' if saturation >= .65 else '#252a2d'


def display_name(name):
    shorter = {
        'Manufacture of wood and products of wood and cork, except furniture; manufacture of articles of straw and plaiting materials': 'Wood, cork, straw and plaiting products',
        'Manufacture of basic pharmaceutical products and pharmaceutical preparations': 'Pharmaceutical products and preparations',
        'Manufacture of fabricated metal products, except machinery and equipment': 'Fabricated metals, excluding machinery',
    }
    if name in shorter:
        return shorter[name]
    name = re.sub(r'^Manufacture of ', '', name, flags=re.I)
    return name[:1].upper() + name[1:]


def industry_leaders(rows):
    """Published latest YoY and 12-month output versus the prior 12 months."""
    iip.validate(rows)
    latest_month = max(r['month'] for r in rows)
    latest = [r for r in rows if r['month'] == latest_month]
    require(all(r['yoy_growth'] is not None for r in latest), 'missing latest industry growth')
    winner = sorted(latest, key=lambda r: (-r['yoy_growth'], r['nic_code']))[0]
    label = datetime.fromisoformat(latest_month + '-01').strftime('%b %y')
    metrics = [dict(label='Top Industry · Latest', value=winner['yoy_growth'],
                    display=f"{winner['yoy_growth']:+.1f}%",
                    period=f"{display_name(winner['industry'])} · {label} YoY",
                    nic_code=winner['nic_code'])]
    periods = [str(p) for p in pd.period_range(end=latest_month, periods=24, freq='M')]
    lookup = {(r['nic_code'], r['month']): r['index'] for r in rows}
    # Do not rank a partial universe, or fill gaps in a trailing window.
    if not all(lookup.get((r['nic_code'], m)) is not None for r in latest for m in periods):
        return metrics
    trailing = []
    for row in latest:
        values = [lookup[(row['nic_code'], m)] for m in periods]
        growth = (sum(values[12:]) / sum(values[:12]) - 1) * 100
        trailing.append((growth, row))
    growth, winner = sorted(trailing, key=lambda pair: (-pair[0], pair[1]['nic_code']))[0]
    start = datetime.fromisoformat(periods[12] + '-01').strftime('%b %y')
    metrics.append(dict(label='Top Industry · TTM', value=growth,
                        display=f'{growth:+.1f}%', nic_code=winner['nic_code'],
                        period=f"{display_name(winner['industry'])} · {start}–{label}"))
    return metrics


def heatmap_data(rows):
    iip.validate(rows)
    periods = sorted({r['month'] for r in rows})[-12:]
    lookup = {(r['nic_code'], r['month']): r for r in rows}
    latest = [r for r in rows if r['month'] == periods[-1]]
    require(all(r['yoy_growth'] is not None for r in latest), 'latest IIP breadth cannot be calculated with missing growth')
    latest.sort(key=lambda r: (-r['yoy_growth'], r['nic_code']))
    output = []
    for industry in latest:
        cells = []
        for period in periods:
            r = lookup[(industry['nic_code'], period)]
            value = r['yoy_growth']
            background, foreground = cell_style(value)
            label = '—' if value is None else f'{value:+.1f}'.replace('-', '−')
            cells.append(dict(month=period, value=value, label=label, background=background,
                              foreground=foreground, index=r['index'], status=r['status'],
                              source_url=r['source_url'], release_date=r['release_date']))
        output.append(dict(nic_code=industry['nic_code'], industry=industry['industry'],
                           display_name=display_name(industry['industry']), cells=cells))
    expanded = sum(r['yoy_growth'] > 0 for r in latest)
    contracted = sum(r['yoy_growth'] < 0 for r in latest)
    label = datetime.fromisoformat(periods[-1]+'-01').strftime('%b %Y')
    summary = lambda r: dict(nic_code=r['nic_code'], industry=r['industry'], yoy_growth=r['yoy_growth'])
    result = dict(schema_version=1, title='Which Industries Are Driving Industrial Growth?',
                  description='Manufacturing output growth by industry, year on year. '
                  'Rows are sorted by the latest month; read across a row to distinguish '
                  'persistent growth from a one-month spike.',
                  base_year='2022-23', nic_version='NIC-2025', unit='% YoY',
                  deflator_regime='Output PPI', color_cap_pct=20, methodology_note=NOTE,
                  latest_month=periods[-1], latest_label=label,
                  months=[dict(month=m, label=datetime.fromisoformat(m+'-01').strftime('%b %y')) for m in periods],
                  breadth=dict(expanding=expanded, contracting=contracted,
                               unchanged=23-expanded-contracted, total=23,
                               median_growth=statistics.median(r['yoy_growth'] for r in latest),
                               top_three=[summary(r) for r in latest[:3]],
                               bottom_three=[summary(r) for r in reversed(latest[-3:])],
                               sentence=f'{expanded} of 23 manufacturing industries expanded from a year earlier in {label}.'),
                  rows=output, leaders=industry_leaders(rows),
                  ttm_method='Total index over the latest 12 months versus the preceding 12 months; all 23 industries require complete windows.',
                  source_url=latest[0]['source_url'],
                  release_date=latest[0]['release_date'], coverage_start=min(r['month'] for r in rows),
                  missing_note='A dash means MoSPI did not publish a growth value; no observations are filled.')
    validate_heatmap(result)
    return result


def validate_heatmap(data):
    require(data['schema_version'] == 1 and data['base_year'] == '2022-23'
            and data['unit'] == '% YoY' and data['color_cap_pct'] == 20, 'invalid heatmap schema')
    months = [m['month'] for m in data['months']]
    require(1 <= len(months) <= 12 and months == sorted(set(months))
            and data['latest_month'] == months[-1], 'invalid heatmap periods')
    require(len(data['rows']) == 23 and len({r['nic_code'] for r in data['rows']}) == 23,
            'invalid heatmap industry universe')
    values = []
    for row in data['rows']:
        require([c['month'] for c in row['cells']] == months, 'invalid heatmap cell coverage')
        require(row['industry'] and row['display_name'], 'missing heatmap label')
        for c in row['cells']:
            require(c['value'] is None or math.isfinite(c['value']), 'invalid heatmap growth')
            expected = '—' if c['value'] is None else f"{c['value']:+.1f}".replace('-', '−')
            require(c['label'] == expected, 'heatmap growth label altered')
            require((c['background'], c['foreground']) == cell_style(c['value']), 'invalid heatmap colours')
        values.append(row['cells'][-1]['value'])
    require(values == sorted(values, reverse=True), 'heatmap sorting mismatch')
    require(data['breadth']['expanding'] == sum(v > 0 for v in values)
            and data['breadth']['contracting'] == sum(v < 0 for v in values), 'heatmap breadth mismatch')
    return data


def render_youth(rows, destination):
    plfs.validate(rows)
    grouped = {age: sorted([r for r in rows if r['age_group'] == age], key=lambda r: r['month'])
               for age in ('15–29', '15+')}
    latest = grouped['15–29'][-1]
    first = grouped['15–29'][0]
    dates = pd.date_range(first['month']+'-01', latest['month']+'-01', freq='MS')
    fig, ax = EconStyle.create_figure(size=(10, 5.4))
    ax.set_position([.075, .18, .74, .61])
    blue = '#1e5d8f'
    for age, color, width in [('15+', '#92999e', 1.3), ('15–29', blue, 2.8)]:
        values = {r['month']: r['value_pct'] for r in grouped[age]}
        # Missing months break the line. NaN is a plotting mask, never a stored
        # observation, and does not interpolate or smooth the official series.
        ax.plot(dates, [values.get(d.strftime('%Y-%m'), float('nan')) for d in dates],
                color=color, linewidth=width, marker='o' if age == '15–29' else None,
                markersize=3.5)
        end = grouped[age][-1]
        end_date = datetime.fromisoformat(end['month']+'-01')
        label = ('Youth 15–29' if age == '15–29' else 'Urban 15+')
        ax.annotate(f"{end['value_pct']:.1f}% · {end_date:%b %Y}\n{label}",
                    xy=(end_date, end['value_pct']), xytext=(12, 0), textcoords='offset points',
                    color=color, fontsize=10 if age == '15–29' else 9,
                    fontweight='bold' if age == '15–29' else 'normal', va='center')
    ax.set_ylim(0, max(r['value_pct'] for r in rows)+3)
    ax.set_xlim(dates[0]-pd.Timedelta(days=10), dates[-1]+pd.Timedelta(days=12))
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set_ylabel('% of labour force')
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.grid(axis='x', visible=False)
    EconStyle.set_title(ax, 'Urban Youth Unemployment',
        'Unemployment rate among urban Indians aged 15–29 · Current Weekly Status')
    EconStyle.add_top_rule(ax)
    fig.text(.075, .087, 'Persons · All India · Monthly observations since April 2025 · Unadjusted survey estimates',
             fontsize=8, color=EconStyle.TEXT_MUTED)
    EconStyle.add_source(fig, 'MoSPI · PLFS Monthly Bulletin, Statement 3 (CWS)',
                        f"Through {dates[-1]:%b %Y}")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+destination.stem, suffix='.png', dir=destination.parent)
    os.close(fd)
    try:
        EconStyle.save_chart(fig, temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def youth_snapshot_row(rows):
    """Latest official urban youth rate, without a snapshot MoM comparison."""
    plfs.validate(rows)
    latest = max((r for r in rows if r['age_group'] == '15–29'),
                 key=lambda r: r['month'])
    period = datetime.fromisoformat(latest['month'] + '-01').strftime('%b %y')
    return dict(section='UNEMPLOYMENT', name='Urban Youth (15–29)',
                value=latest['value_pct'],
                value_str=f"{latest['value_pct']:.1f}%",
                change=None, unit=f'% · {period}')


def load_youth_snapshot(path=plfs.CSV):
    if os.environ.get('PLFS_UPDATE_FAILED') == 'true':
        raise ValueError('official monthly PLFS refresh failed')
    return youth_snapshot_row(plfs.load(path))


def generate(output_dir, iip_csv=iip.CSV):
    """Generate the industry heatmap; PLFS now appears in the snapshot table."""
    output_dir = Path(output_dir)
    destination = output_dir / HEATMAP
    try:
        if os.environ.get('IIP_INDUSTRIES_UPDATE_FAILED') == 'true':
            raise ValueError('official IIP industry refresh failed')
        matrix = heatmap_data(iip.load(iip_csv))
        atomic_json(destination, matrix)
    except (ValueError, OSError):
        destination.unlink(missing_ok=True)
        raise
    return (destination,)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'output/india'/datetime.now().strftime('%Y-%m'))
    args = parser.parse_args()
    for path in generate(args.output_dir):
        print(path)


if __name__ == '__main__':
    main()
