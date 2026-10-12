"""Five-year diverging areas of official NFCI contributions with its published line."""
import numpy as np
import pandas as pd

from charts.style import EconStyle

COLORS = {'Risk': '#E05458', 'Credit': '#3C78E4', 'Leverage': '#90A84C'}


def draw(report, path):
    import matplotlib.dates as mdates
    import matplotlib.patheffects as pe
    import matplotlib.ticker as mticker
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    frame = pd.DataFrame(report['rows']).set_index('date')
    dates = pd.to_datetime(frame.index)
    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size='wide')
    charcoal, muted = '#25282D', '#697480'
    upper, lower = np.zeros(len(frame)), np.zeros(len(frame))
    for group, color in COLORS.items():
        values = frame[group].to_numpy()
        pos, neg = np.maximum(values, 0), np.minimum(values, 0)
        ax.fill_between(dates, upper, upper + pos, color=color, alpha=.82, linewidth=0, zorder=2)
        ax.fill_between(dates, lower, lower + neg, color=color, alpha=.82, linewidth=0, zorder=2)
        upper += pos
        lower += neg
    # Keep the weekly line unsmoothed: every plotted observation is published.
    ax.plot(dates, frame.NFCI, color=charcoal, lw=2.2, zorder=5,
            solid_capstyle='round', path_effects=[pe.withStroke(linewidth=3.4, foreground='white', alpha=.7)])
    ax.axhline(0, color='#65707B', lw=1.05, zorder=4)
    halo = [pe.withStroke(linewidth=3, foreground='white')]
    ax.annotate('Historical average', xy=(.012, 0), xycoords=ax.get_yaxis_transform(),
                xytext=(0, 7), textcoords='offset points', fontsize=8, color=muted,
                ha='left', va='bottom', path_effects=halo, zorder=6)
    last_date, last_value = dates[-1], frame.NFCI.iloc[-1]
    ax.scatter([last_date], [last_value], s=35, color=charcoal, edgecolors='white', linewidth=.9, zorder=7)
    ax.annotate(f'NFCI {last_value:+.2f}\n{last_date:%d %b %Y}', xy=(last_date, last_value),
                xytext=(-6, -28), textcoords='offset points', ha='right', va='top',
                fontsize=9, weight='bold', color=charcoal, path_effects=halo,
                arrowprops=dict(arrowstyle='-', lw=.6, color=muted, shrinkA=4, shrinkB=5), zorder=7)
    low = min(lower.min(), frame.NFCI.min())
    high = max(upper.max(), frame.NFCI.max(), 0)
    span = high - low or 1
    ax.set_ylim(low - span * .12, high + span * .20)
    ax.set_xlim(pd.Timestamp(report['window_start']), last_date + pd.Timedelta(days=28))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'.replace('-', '−')))
    ax.set_ylabel('Index units', fontsize=EconStyle.FONT_SIZE_AXIS, color=muted, labelpad=8)
    ax.tick_params(axis='y', length=0, labelsize=EconStyle.FONT_SIZE_TICK)
    ax.tick_params(axis='x', length=4, width=.8, labelsize=EconStyle.FONT_SIZE_TICK)
    ax.grid(axis='y', color=EconStyle.GRID_COLOR, lw=.45)
    ax.grid(axis='x', visible=False)
    ax.set_axisbelow(True)
    for spine in ('top', 'right', 'left'):
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color(EconStyle.AXIS_COLOR)
    ax.spines['bottom'].set_linewidth(1)
    ax.legend(handles=[*[Patch(facecolor=c, alpha=.82, label=g) for g, c in COLORS.items()],
                       Line2D([], [], color=charcoal, lw=2.2, label='NFCI')],
              loc='upper left', ncol=4, frameon=False, fontsize=8.5,
              handlelength=1.5, handletextpad=.5, columnspacing=1.5)
    latest = frame.iloc[-1]
    ax.text(.99, .98, 'Latest contributions: ' + ' · '.join(f'{g} {latest[g]:+.3f}' for g in COLORS),
            transform=ax.transAxes, ha='right', va='top', fontsize=8, color=muted)
    EconStyle.set_title(ax, 'U.S. Financial Conditions | What Is Driving the NFCI?',
                       'Positive = tighter-than-average conditions · Negative = looser-than-average conditions')
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[.02, .075, .98, .96])
    fig.text(.035, .067, f'Official indicator contributions; small source residual remains (5Y max {report["reconciliation"]["max_abs"]:.6f}).',
             ha='left', fontsize=7, color=muted)
    EconStyle.add_source(fig, 'Federal Reserve Bank of Chicago', f'Latest observation: {last_date:%d %b %Y}')
    EconStyle.save_chart(fig, path)
