"""Publication chart of the Chicago Fed's two published monthly activity series."""
import numpy as np
import pandas as pd

from charts.style import EconStyle


def prepare(monthly, ma3, start='2022-01'):
    """Align calendar months without recomputing MA3, filling gaps or rebasing."""
    def canonical(series):
        values = series.astype(float).copy()
        values.index = pd.DatetimeIndex(values.index).to_period('M')
        if values.index.duplicated().any():
            raise ValueError('CFNAI: duplicate monthly observation')
        if not np.isfinite(values.dropna()).all():
            raise ValueError('CFNAI: non-finite observation')
        return values.sort_index()

    frame = pd.concat({'monthly': canonical(monthly), 'ma3': canonical(ma3)}, axis=1)
    if frame.monthly.dropna().empty or frame.ma3.dropna().empty:
        raise ValueError('CFNAI: both published series are required')
    calendar = pd.period_range(start=start, end=frame.index.max(), freq='M')
    frame = frame.reindex(calendar)
    if frame.ma3.notna().sum() < 6:
        raise ValueError('CFNAI: insufficient recent moving-average observations')
    frame.index = frame.index.to_timestamp()
    return frame


def draw(frame, path, smoother):
    import matplotlib.dates as mdates
    import matplotlib.patheffects as pe
    import matplotlib.ticker as mticker
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    EconStyle.apply_global_style()
    fig, ax = EconStyle.create_figure(size='wide')
    # Muted versions of EconHub's navy and burgundy bar palette.
    navy, burgundy, charcoal, muted = '#41617E', '#945868', '#25282D', '#697480'
    values = frame.monthly
    positive, negative = values >= 0, values < 0
    ax.bar(frame.index[positive], values[positive], width=23, color=navy, linewidth=0, zorder=3)
    ax.bar(frame.index[negative], values[negative], width=23, color=burgundy, linewidth=0, zorder=3)
    valid = frame.ma3.notna()
    # A missing observation breaks the curve; smoothing passes through every
    # published point and never changes the stored monthly or MA3 values.
    for _, segment in frame.ma3[valid].groupby((~valid).cumsum()[valid]):
        ax.plot(*smoother(segment.index, segment.values), color=charcoal, lw=2.4,
                solid_capstyle='round', zorder=5)
    ax.axhline(0, color='#65707B', lw=1.1, zorder=2)
    ax.axhline(-.70, color=muted, lw=.9, linestyle=(0, (4, 3)), zorder=2)
    halo = [pe.withStroke(linewidth=3, foreground='white')]
    for value, label, offset, location in [(0, 'Historical trend', 7, .012),
                                           (-.70, '−0.70 · Historical recession signal (3M average)', 10, .48)]:
        ax.annotate(label, xy=(location, value), xycoords=ax.get_yaxis_transform(),
                    xytext=(0, offset), textcoords='offset points', ha='left', va='center',
                    fontsize=8, color=muted, path_effects=halo, zorder=7)

    last_date, last_value = frame.ma3.dropna().index[-1], frame.ma3.dropna().iloc[-1]
    ax.scatter([last_date], [last_value], s=42, color=charcoal, edgecolors='white',
               linewidths=1, zorder=7)
    ax.annotate(f'{last_date:%b %Y}  {last_value:+.2f}\nCFNAI-MA3',
                xy=(last_date, last_value), xytext=(-5, 23), textcoords='offset points',
                ha='right', va='bottom', fontsize=9, weight='bold', color=charcoal,
                path_effects=halo, arrowprops=dict(arrowstyle='-', linewidth=.6,
                                                  color=muted, shrinkA=4, shrinkB=5), zorder=7)

    low = min(frame.min().min(), -.70)
    high = max(frame.max().max(), 0)
    span = high - low or 1
    ax.set_ylim(low - span * .055, high + span * .17)
    start, end = frame.index[0], frame.index[-1]
    ax.set_xlim(start - pd.Timedelta(days=20), end + pd.Timedelta(days=40))
    years = [pd.Timestamp(year, 1, 1) for year in range(start.year, end.year + 1)
             if start <= pd.Timestamp(year, 1, 1) <= end]
    ax.set_xticks(years)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'.replace('-', '−')))
    ax.set_ylabel('Index units', fontsize=EconStyle.FONT_SIZE_AXIS, color=muted, labelpad=8)
    ax.tick_params(axis='y', length=0, labelsize=EconStyle.FONT_SIZE_TICK)
    ax.tick_params(axis='x', length=4, width=.8, labelsize=EconStyle.FONT_SIZE_TICK)
    ax.grid(axis='y', color=EconStyle.GRID_COLOR, linewidth=.45)
    ax.grid(axis='x', visible=False)
    ax.set_axisbelow(True)
    for spine in ('top', 'right', 'left'):
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color(EconStyle.AXIS_COLOR)
    ax.spines['bottom'].set_linewidth(1)
    ax.legend(handles=[Patch(facecolor=navy, label='Monthly · above trend'),
                       Patch(facecolor=burgundy, label='Monthly · below trend'),
                       Line2D([], [], color=charcoal, lw=2.4, label='Three-month average')],
              loc='upper left', ncol=3, frameon=False, fontsize=8.5,
              handlelength=1.5, handletextpad=.5, columnspacing=1.5)

    # One historically meaningful turning point, with its full observed
    # magnitude retained on the same linear axis as every other observation.
    pandemic = pd.Timestamp('2020-04-01')
    if pandemic in values.index and pd.notna(values.loc[pandemic]):
        ax.annotate('2020 pandemic\nactivity shock', xy=(pandemic, values.loc[pandemic]),
                    xytext=(pd.Timestamp('2021-07-01'), low + span * .23),
                    fontsize=8.5, color=muted, ha='left', va='center',
                    arrowprops=dict(arrowstyle='-', linewidth=.6, color=muted,
                                    shrinkA=4, shrinkB=5), zorder=7)
    EconStyle.set_title(ax, 'U.S. Economic Activity | Above or Below Trend?',
                       'Positive = above-trend activity · Negative = below-trend activity')
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[.02, .04, .98, .96])
    EconStyle.add_source(fig, 'Federal Reserve Bank of Chicago, via FRED',
                         f'Latest observation: {frame.dropna(how="all").index[-1]:%b %Y}')
    EconStyle.save_chart(fig, path)
