"""Six-category decomposition rendered only from validated local CPI snapshots."""
import calendar
import json
import logging
import os
from pathlib import Path

import numpy as np
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator

from charts.style import EconStyle
from data.processors import cpi_contributions as cpi

NAME = '24_india_cpi_contributions'
COLORS = EconStyle.CATEGORICAL_COLORS[:6]


def figure(derived, variant='line'):
    if variant not in ('line', 'markers'):
        raise ValueError('Unknown CPI chart variant')
    cpi.require(derived and all(r['month'] >= '2026-01' for r in derived), 'invalid chart history')
    fig, ax = EconStyle.create_figure('wide')
    fig.subplots_adjust(left=.08, right=.96, bottom=.145, top=.685)
    fig.text(.055, .890, 'What’s Driving Indian Inflation?', fontsize=EconStyle.FONT_SIZE_TITLE,
             fontproperties=EconStyle._get_font('bold'))
    fig.text(.055, .843, 'Contribution to headline CPI inflation by major consumption category · percentage points', fontsize=9,
             fontproperties=EconStyle._get_font('regular'))
    handles = [Patch(facecolor=color, edgecolor=EconStyle.BAR_EDGE_COLOR,
                     linewidth=EconStyle.BAR_EDGE_WIDTH, label=name)
               for color, name in zip(COLORS, cpi.BUCKETS)]
    x = np.arange(len(derived))
    positive, negative = np.zeros(len(x)), np.zeros(len(x))
    for color, name in zip(COLORS, cpi.BUCKETS):
        values = np.array([float(r['buckets'][name]) for r in derived])
        bottom = np.where(values >= 0, positive, negative)
        ax.bar(x, values, bottom=bottom, width=.64, color=color,
               edgecolor=EconStyle.BAR_EDGE_COLOR, linewidth=EconStyle.BAR_EDGE_WIDTH,
               label=name, zorder=3)
        positive += np.maximum(values, 0)
        negative += np.minimum(values, 0)
    headline = np.array([float(r['published_headline']) for r in derived])
    headline_line, = ax.plot(x, headline, color='#171717', linewidth=.9 if variant=='line' else 0,
            marker='o', markersize=3.2, zorder=5, label='Published headline CPI')
    # Four entries above three entries; preserve category reading order.
    handles.append(headline_line)
    for row, entries in enumerate((handles[:4], handles[4:])):
        fig.legend(handles=entries, loc='upper left',
                   bbox_to_anchor=(.05, .810-row*.052), ncol=len(entries), frameon=False,
                   fontsize=8.7, handlelength=1.2, handleheight=.8, columnspacing=1.65)
    if variant == 'markers':
        for xi, value in zip(x[:-1], headline[:-1]):
            ax.annotate(f'{value:.2f}', (xi, value), xytext=(0, 6), textcoords='offset points',
                        ha='center', fontsize=8, color='#333333')
    latest = derived[-1]
    ax.annotate(f'{headline[-1]:.2f}%',
                (x[-1], headline[-1]), xytext=(5, 6), textcoords='offset points',
                fontsize=9, color='#171717', ha='left', va='bottom')
    ax.axhline(0, color='#202020', linewidth=.8, zorder=4)
    ax.set_ylim(min(-.16, float(negative.min())-.12), max(positive.max(), headline.max())+.85)
    ax.set_xlim(-.65, len(x)+.65)
    stride = max(1, (len(x)+17)//18)
    ticks = list(range(0, len(x), stride))
    if len(x)-1 not in ticks:
        ticks.append(len(x)-1)
    ax.set_xticks(ticks)
    ax.set_xticklabels([calendar.month_abbr[int(derived[i]['month'][5:])]+ '\n'+derived[i]['month'][:4] for i in ticks], fontsize=8.5)
    ax.set_ylabel('Contribution to headline CPI inflation (pp)', fontsize=9, labelpad=7)
    ax.yaxis.set_major_locator(MultipleLocator(1))
    ax.grid(axis='y', color='#D6D6D6', linewidth=.5, zorder=0)
    ax.grid(axis='x', visible=False)
    for side in ('right', 'top', 'left'):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis='both', length=0)
    ax.spines['bottom'].set_visible(False)
    EconStyle.add_top_rule(ax)
    # Keep the house separator directly under the subtitle, above the keys.
    rule = ax.lines[-1]
    rule.set_transform(fig.transFigure)
    rule.set_data([.08, .96], [.823, .823])
    month_label = calendar.month_abbr[int(latest['month'][5:])]+' '+latest['month'][:4]
    EconStyle.add_source(fig, 'MoSPI / eSankhyiki · Author’s calculations', date_text=month_label)
    return fig


def generate(output_dir, root=cpi.ROOT):
    output_dir = Path(output_dir)
    png, metadata = output_dir/(NAME+'.png'), output_dir/(NAME+'.json')
    # Remove artifacts before validation so every failure path omits this edition.
    png.unlink(missing_ok=True)
    metadata.unlink(missing_ok=True)
    try:
        cpi.require(os.environ.get('CPI_UPDATE_FAILED', '').lower() != 'true', 'workflow CPI update failed')
        _, derived, manifest = cpi.load_current(root)
        EconStyle.save_chart(figure(derived), png)
        metadata.write_bytes(cpi.encoded(dict(source_month=manifest['latest_month'],
            run_id=manifest['run_id'], source_retrieval=manifest['source_retrieval'],
            latest=derived[-1], design='line', source=cpi.API_URL)))
        print(f'   CPI contributions: {manifest["latest_month"]} → {png.name}')
        return png
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as exc:
        png.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        logging.warning('CPI CONTRIBUTION CHART OMITTED: %s', exc)
        return None
