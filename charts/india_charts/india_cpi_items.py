"""Coordinated CPI item bar panels; headings and provenance render on the page."""
import logging
from pathlib import Path
import textwrap
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, PercentFormatter
from charts.style import EconStyle
from data.processors import cpi_items as items, cpi_contributions as cpi
from data.fetchers.mospi_cpi import atomic_json

NAME = '06b_india_cpi_items'
BACKGROUND = '#FFFFF0'  # Existing Streamlit page ivory, app.py.


def panel(rows, direction):
    cpi.require(direction in ('increases','declines'), 'invalid item panel')
    fig, ax = EconStyle.create_figure(size=(7.4, 5.8))
    fig.patch.set_facecolor(BACKGROUND); ax.set_facecolor(BACKGROUND)
    fig.subplots_adjust(left=.49, right=.96, top=.90, bottom=.10)
    color = EconStyle.CATEGORICAL_COLORS[7] if direction == 'increases' else EconStyle.CATEGORICAL_COLORS[2]
    heading = 'Largest increases' if direction == 'increases' else 'Largest declines'
    fig.text((.49+.96)/2, .955, heading, ha='center', fontsize=14,
             fontproperties=EconStyle._get_font('bold'))
    ax.grid(False)
    if rows:
        values = [r['yoy'] for r in rows]
        extreme = max(abs(v) for v in values)
        bound = extreme * 1.35
        ax.barh(range(len(rows)), values, height=.60, color=color, edgecolor=EconStyle.BAR_EDGE_COLOR,
                linewidth=EconStyle.BAR_EDGE_WIDTH, zorder=3)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([textwrap.fill(r['item_name'], 30) for r in rows],
                           fontsize=11.5, fontweight='semibold', color=EconStyle.INK)
        ax.invert_yaxis()
        ax.set_ylim(7.6, -.6)  # Consistent row spacing even when fewer than eight.
        ax.set_xlim((0,bound) if direction == 'increases' else (-bound,0))
        for i, value in enumerate(values):
            ax.annotate(f'{value:+.1f}%'.replace('-', '−'), (value,i),
                        xytext=(5 if value>0 else -5,0), textcoords='offset points',
                        va='center', ha='left' if value>0 else 'right', fontsize=10,
                        fontproperties=EconStyle._get_font('bold'))
        ax.xaxis.set_major_locator(MaxNLocator(3))
        ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        ax.grid(axis='x', color=EconStyle.GRID_COLOR, linewidth=.5, alpha=.5, zorder=0)
        ax.axvline(0, color=EconStyle.RULE_LIGHT, linewidth=.8)
    else:
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(.5,.5,'No items with '+('positive' if direction=='increases' else 'negative')+' YoY readings',
                transform=ax.transAxes, ha='center', fontsize=10, wrap=True)
    ax.tick_params(axis='both', length=0)
    ax.tick_params(axis='x', labelcolor=EconStyle.INK_MUTED)
    ax.tick_params(axis='y', labelcolor=EconStyle.INK)
    for spine in ax.spines.values(): spine.set_visible(False)
    return fig


def generate(output_dir, root=items.ROOT):
    output_dir = Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    paths = [output_dir/f'{NAME}_{side}.png' for side in ('increases','declines')]
    metadata = output_dir/(NAME+'.json')
    for path in paths+[metadata]: path.unlink(missing_ok=True)
    try:
        rows, manifest = items.load_current(root)
        data = items.snapshot(rows)
        for side, path in zip(('increases','declines'), paths):
            fig = panel(data[side], side)
            # House save_chart adds a black figure border; this editorial visual has none.
            fig.savefig(path, dpi=180, facecolor=BACKGROUND, edgecolor='none', bbox_inches=None)
            plt.close(fig)
        atomic_json(metadata, dict(data,run_id=manifest['run_id'], coverage_start=manifest['coverage_start'],
                                   base_year='2024', series='Current'))
        return paths
    except (ValueError, OSError, KeyError, TypeError) as exc:
        for path in paths+[metadata]: path.unlink(missing_ok=True)
        logging.warning('CPI ITEM MOVERS OMITTED: %s', exc)
        return []
