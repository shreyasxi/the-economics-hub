"""Companion ECB charts: daily historical stress and monthly official drivers."""
import pandas as pd

from charts.style import EconStyle
from data.fetchers.ciss import COMPONENTS


def draw(report, path):
    import matplotlib.dates as mdates
    import matplotlib.patheffects as pe
    import matplotlib.ticker as mticker

    frame = pd.DataFrame(report['rows']).set_index('date')
    dates = pd.to_datetime(frame.index)
    latest_date = pd.Timestamp(report['latest_observation'])
    latest = report['latest']
    fig, top = EconStyle.create_figure('wide')
    fig.subplots_adjust(left=.08, right=.96, top=.78, bottom=.15)
    EconStyle.set_title(top, 'Euro Area | Systemic Financial Stress',
                        f"ECB New CISS · Latest: {latest['SS_CIN']:.4f} · {latest_date:%d %b %Y}")
    EconStyle.add_top_rule(top)
    ink, muted, color = EconStyle.INK, EconStyle.INK_MUTED, EconStyle.LINE_MAROON
    halo = [pe.withStroke(linewidth=3, foreground='white')]
    top.plot(dates, frame.CISS, color=color, lw=2.2, zorder=3)
    top.fill_between(dates, 0, frame.CISS, color=color, alpha=.065, lw=0)
    top.set_xlim(pd.Timestamp(report['window_start']), latest_date + pd.Timedelta(days=100))
    peak = frame.CISS.max()
    top.set_ylim(0, peak * 1.28)
    top.set_ylabel('CISS index units', color=muted, labelpad=9)
    top.xaxis.set_major_locator(mdates.YearLocator(2))
    top.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    top.yaxis.set_major_locator(mticker.MaxNLocator(5))
    top.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))
    # Anchor each episode to its actual local maximum; omit episodes outside the window.
    episodes = [('2011-01-01', '2012-12-31', 'Sovereign debt\ncrisis', (28, 26)),
                ('2020-02-01', '2020-06-30', 'COVID-19\nfinancial shock', (-36, 28)),
                ('2022-01-01', '2022-12-31', 'Inflation &\nmonetary tightening', (24, 28))]
    for start, end, label, offset in episodes:
        window = frame.loc[start:end, 'CISS']
        if window.empty:
            continue
        d = pd.Timestamp(window.idxmax())
        top.annotate(label, xy=(d, window.max()), xytext=offset, textcoords='offset points',
                     fontsize=7.5, color=muted, ha='center', va='bottom', path_effects=halo,
                     arrowprops=dict(arrowstyle='-', lw=.55, color=muted))

    top.set_axisbelow(True)
    top.tick_params(axis='both', labelsize=8, length=0, pad=6)
    for spine in ('top', 'right', 'left'):
        top.spines[spine].set_visible(False)
    top.spines['bottom'].set_linewidth(.8)
    top.grid(visible=False)
    top.grid(axis='y', color=EconStyle.GRID_COLOR, lw=.45)
    fig.text(.04, .067, '15-year daily history · Higher CISS values indicate greater systemic financial stress.',
             fontsize=7, color=muted)
    EconStyle.add_source(fig, 'European Central Bank', 'Daily · CISS index units')
    EconStyle.save_chart(fig, path)


def draw_drivers(report, path):
    import calendar
    import numpy as np
    from matplotlib.patches import Patch
    from matplotlib.ticker import MaxNLocator, FuncFormatter

    rows = report['monthly']['rows']
    # Same proportions, header, legend, bar geometry and footer as india_cpi_contributions.
    fig, ax = EconStyle.create_figure('wide')
    fig.subplots_adjust(left=.08, right=.96, bottom=.165, top=.685)
    fig.text(.055, .890, 'What’s Driving Euro Area Financial Stress?', fontsize=EconStyle.FONT_SIZE_TITLE,
             fontproperties=EconStyle._get_font('bold'))
    fig.text(.055, .843, 'Monthly contribution to ECB systemic financial stress by market segment · index units',
             fontsize=9, fontproperties=EconStyle._get_font('regular'))
    colors = [EconStyle.CATEGORICAL_COLORS[i] for i in (0, 1, 2, 3, 5)] + [EconStyle.WATERMARK_COLOR]
    handles = [Patch(facecolor=color, edgecolor=EconStyle.BAR_EDGE_COLOR,
                     linewidth=EconStyle.BAR_EDGE_WIDTH, label=name)
               for color, name in zip(colors, COMPONENTS.values())]
    x = np.arange(len(rows))
    positive, negative = np.zeros(len(x)), np.zeros(len(x))
    for code, color in zip(COMPONENTS, colors):
        values = np.array([row[code] for row in rows])
        base = np.where(values >= 0, positive, negative)
        ax.bar(x, values, bottom=base, width=.64, color=color,
               edgecolor=EconStyle.BAR_EDGE_COLOR, linewidth=EconStyle.BAR_EDGE_WIDTH, zorder=3)
        positive += np.maximum(values, 0)
        negative += np.minimum(values, 0)
    aggregate = np.array([row['SS_CIN'] for row in rows])
    line, = ax.plot(x, aggregate, color='#171717', linewidth=2.2,
                    marker='o', markersize=3.2, zorder=5, label='Published New CISS')
    handles.append(line)
    # Four market segments above the remaining two components and aggregate.
    for row, entries in enumerate((handles[:4], handles[4:])):
        fig.legend(handles=entries, loc='upper left', bbox_to_anchor=(.05, .810-row*.052),
                   ncol=len(entries), frameon=False, fontsize=8.2,
                   handlelength=1.2, handleheight=.8, columnspacing=1.25)
    ax.annotate(f'{aggregate[-1]:.4f}', (x[-1], aggregate[-1]), xytext=(5, 6),
                textcoords='offset points', fontsize=9, color='#171717', ha='left', va='bottom',
                bbox=dict(facecolor='white', edgecolor='none', pad=.6, alpha=.9))
    ax.axhline(0, color='#202020', linewidth=.8, zorder=4)
    low, high = min(negative.min(), aggregate.min(), 0), max(positive.max(), aggregate.max(), 0)
    span = high - low or .01
    ax.set_ylim(low - span*.07, high + span*.16)
    ax.set_xlim(-.65, len(x)+.65)
    ax.set_xticks(x)
    ax.set_xticklabels([calendar.month_abbr[int(r['month'][5:])]+'\n'+r['month'][:4] for r in rows], fontsize=8.5)
    ax.set_ylabel('Contribution to CISS · index units', fontsize=9, labelpad=7)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:.2f}'.replace('-', '−')))
    ax.grid(axis='y', color=EconStyle.GRID_COLOR, linewidth=.5, zorder=0)
    ax.grid(axis='x', visible=False)
    for side in ('right', 'top', 'left', 'bottom'):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis='both', length=0)
    EconStyle.add_top_rule(ax)
    rule = ax.lines[-1]
    rule.set_transform(fig.transFigure)
    rule.set_data([.08, .96], [.823, .823])
    fig.text(.04, .073, 'Monthly means over common daily observations · Positive contributions increase stress; negative contributions offset it.',
             fontsize=6.7, color=EconStyle.INK_MUTED)
    month = pd.Period(rows[-1]['month'], freq='M').strftime('%b %Y')
    EconStyle.add_source(fig, 'European Central Bank · Monthly averages', f'Latest completed month: {month}')
    EconStyle.save_chart(fig, path)
