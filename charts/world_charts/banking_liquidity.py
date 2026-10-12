"""Monthly reserve adequacy and native-frequency IORB funding pressure."""
import numpy as np
import pandas as pd

from charts.style import EconStyle

IORB_START = pd.Timestamp('2021-07-29')
TITLE = 'U.S. Banking Liquidity | Are Reserves Becoming Scarce?'


def prepare(effr, sofr, iorb, reserves, fedwire, today=None):
    """Match actual rate dates; never fill rates or interpolate weekly reserves.

    Fetch extra history for a full 20-valid-observation warm-up before trimming
    to five calendar years. IORB's inception is the hard historical boundary.
    Each market retains its own valid dates and publication endpoint.
    """
    today = (pd.Timestamp(today) if today is not None else
             pd.Timestamp.now(tz='Asia/Kolkata').tz_localize(None)).normalize()
    start = max(IORB_START, today - pd.DateOffset(years=5))

    def clean(series, name, max_age):
        values = series.astype(float).copy()
        values.index = pd.DatetimeIndex(values.index)
        if values.index.duplicated().any():
            raise ValueError(f'{name}: duplicate observation date')
        if not np.isfinite(values.dropna()).all():
            raise ValueError(f'{name}: non-finite observation')
        values = values.sort_index().loc[IORB_START:today].dropna()
        if values.empty or (today - values.index[-1]).days > max_age:
            raise ValueError(f'{name}: missing or stale observations; no chart published')
        return values

    rates = {'EFFR': clean(effr, 'EFFR', 10), 'SOFR': clean(sofr, 'SOFR', 10)}
    administered = clean(iorb, 'IORB', 10)
    weekly = clean(reserves, 'WRESBAL', 21)
    if (weekly.index.dayofweek != 2).any() or (weekly < 0).any():
        raise ValueError('WRESBAL: expected nonnegative Wednesday week-average observations')
    spreads, averages = {}, {}
    for name, values in rates.items():
        if (values.index.dayofweek > 4).any():
            raise ValueError(f'{name}: unexpected weekend transaction observation')
        reference = administered.reindex(values.index)
        if reference.isna().any():
            raise ValueError(f'{name}: missing same-date IORB; rates are never forward-filled')
        spread = (values - reference) * 100
        spreads[name] = spread.loc[start:]
        averages[name] = spread.rolling(20, min_periods=20).mean().loc[start:]
        if spreads[name].size < 20 or averages[name].dropna().empty:
            raise ValueError(f'{name}: insufficient valid observations for 20-business-day average')
    monthly = weighted_monthly_reserves(weekly)
    if monthly.empty:
        raise ValueError('Reserve adequacy: no complete monthly reserve coverage')
    payments = fedwire.astype(float).sort_index()
    if not isinstance(payments.index, pd.PeriodIndex) or payments.index.freqstr != 'M':
        raise ValueError('Fedwire: expected monthly PeriodIndex')
    if payments.index.duplicated().any() or not np.isfinite(payments).all() or (payments <= 0).any():
        raise ValueError('Fedwire: invalid or duplicate monthly values')
    if payments.empty or payments.index[-1] >= today.to_period('M'):
        raise ValueError('Fedwire: empty or unpublished observation month')
    if (today - payments.index[-1].end_time.normalize()).days > 80:
        raise ValueError('Fedwire: stale monthly source; no chart published')
    aligned = pd.concat([monthly.rename('reserves'), payments.rename('payments')], axis=1)
    ratio = (100 * aligned.reserves / aligned.payments).sort_index()
    first = max(monthly.first_valid_index(), payments.index[0])
    required = pd.period_range(first, payments.index[-1], freq='M')
    if ratio.reindex(required).isna().any():
        raise ValueError('Reserve adequacy: incomplete reserve/Fedwire monthly coverage')
    # Published rounded anchors: differences >2 percentage points need investigation.
    for month, expected in [('2022-06', 75), ('2025-03', 71)]:
        value = ratio.get(pd.Period(month, freq='M'), np.nan)
        if pd.notna(value) and abs(value - expected) > 2:
            raise ValueError(f'Reserve adequacy: {month} {value:.2f}% fails Fed research reconciliation')
    ratio.index = ratio.index.to_timestamp(how='end').normalize()
    ratio = ratio.loc[start:today].dropna()
    if ratio.size < 2:
        raise ValueError('Reserve adequacy: insufficient complete monthly observations')
    return spreads, averages, ratio, start, today


def weighted_monthly_reserves(weekly):
    """Calendar-overlap approximation to the Fed's undocumented exact weights.

    Wednesday averages cover Thursday–Wednesday. A month is retained only if
    every calendar day has an observed weekly value. Boundary weeks are split;
    missing weeks are never filled. Units remain USD millions.
    """
    weekly = weekly.astype(float).sort_index()
    if weekly.empty or weekly.index.duplicated().any():
        raise ValueError('WRESBAL: empty or duplicate observations')
    if (weekly.index.dayofweek != 2).any() or not np.isfinite(weekly.dropna()).all() or (weekly < 0).any():
        raise ValueError('WRESBAL: expected finite nonnegative Wednesday observations')
    days = pd.concat([pd.Series(value, index=pd.date_range(date - pd.Timedelta(days=6), date))
                      for date, value in weekly.items()])
    groups = days.groupby(days.index.to_period('M'))
    count = groups.count()
    return groups.mean().where(count == count.index.days_in_month).dropna()


def draw(data, path):
    import matplotlib.dates as mdates
    import matplotlib.ticker as mticker
    import matplotlib.patheffects as pe
    from matplotlib.lines import Line2D

    spreads, averages, ratio, start, today = data
    fig, (left, right) = EconStyle.create_figure(size=(EconStyle.SIZE_WIDE[0], 5.6),
                                               nrows=1, ncols=2, sharex=True)
    fig.subplots_adjust(left=.08, right=.97, bottom=.14, top=.70, wspace=.27)
    fig.text(.08, .965, TITLE, fontsize=15, weight='bold', va='top',
             fontproperties=EconStyle._get_font('bold'))
    fig.text(.08, .908, 'Bank reserves relative to payment activity, alongside the cost of overnight funding',
             fontsize=9.2, va='top')
    fig.add_artist(Line2D([.08, .97], [.865, .865], transform=fig.transFigure,
                         color=EconStyle.RULE_HEAVY, lw=1.5))
    colors = {'EFFR': '#3C78E4', 'SOFR': '#E05458'}
    teal = '#0F9389'
    halo = [pe.withStroke(linewidth=3, foreground='white')]
    for ax, title, subtitle in (
            (left, 'Reserve Adequacy', 'Reserves / average daily Fedwire payments'),
            (right, 'Overnight Funding Pressure', 'Market borrowing rates relative to IORB')):
        x = ax.get_position().x0
        fig.text(x, .815, title, fontsize=10.5, weight='bold')
        fig.text(x, .779, subtitle, fontsize=8, color=EconStyle.INK_MUTED)
    date, value = ratio.index[-1], ratio.iloc[-1]
    fig.text(left.get_position().x0, .738, f'Latest: {value:.1f}% · {date:%B %Y}',
             fontsize=8.5, weight='bold', color=teal)
    left.plot(ratio.index, ratio, color=teal, lw=2.5, zorder=4)
    left.scatter([date], [value], color=teal, s=24, edgecolors='white', zorder=5)
    left.axhline(65, color=EconStyle.INK_MUTED, lw=.8, ls=(0, (4, 4)), zorder=2)
    left.annotate('65% · Fed research estimate', xy=(.025, 65),
                  xycoords=left.get_yaxis_transform(), xytext=(0, 5),
                  textcoords='offset points', fontsize=7.5, color=EconStyle.INK_MUTED,
                  path_effects=halo, zorder=6)
    low, high = min(65, ratio.min()), max(65, ratio.max())
    span = max(20, high - low)
    left.set_ylim(max(0, low - .16 * span), high + .12 * span)
    left.set_ylabel('Reserves / Fedwire payments (%)', fontsize=9)
    left.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100, decimals=0))
    for i, (name, values) in enumerate(spreads.items()):
        right.plot(values.index, values, color=colors[name], lw=.65, alpha=.40, zorder=3)
        right.plot(averages[name].index, averages[name], color=colors[name], lw=2.2, zorder=4)
        # Compact direct labels identify each market and its genuine endpoint.
        fig.text(right.get_position().x0, .740 - i * .028,
                 f'{name}−IORB: {values.iloc[-1]:+.1f} bp · {values.index[-1]:%d %b %Y}',
                 fontsize=7.6, color=colors[name], weight='bold')
    right.axhline(0, color=EconStyle.INK_MUTED, lw=.8, zorder=2)
    right.annotate('0 bp · Equal to IORB', xy=(.025, 0), xycoords=right.get_yaxis_transform(),
                   xytext=(0, 5), textcoords='offset points', fontsize=7.5,
                   color=EconStyle.INK_MUTED, path_effects=halo, zorder=6)
    low = min(0, min(s.min() for s in spreads.values()))
    high = max(0, max(s.max() for s in spreads.values()))
    span = max(10, high - low)
    right.set_ylim(low - span * .12, high + span * .12)
    right.set_ylabel('Basis points', fontsize=9)
    for ax in (left, right):
        ax.set_xlim(start, today + pd.Timedelta(days=15))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.grid(axis='y', color=EconStyle.GRID_COLOR, lw=.45)
        ax.grid(axis='x', visible=False)
        ax.set_axisbelow(True)
        ax.tick_params(axis='y', length=0, labelsize=8)
        ax.tick_params(axis='x', labelsize=8)
        for spine in ('top', 'right', 'left'):
            ax.spines[spine].set_visible(False)
        ax.spines['bottom'].set_color(EconStyle.AXIS_COLOR)
    fig.text(.08, .063, '65% is a historical research estimate, not a fixed scarcity threshold.',
             fontsize=7.2, color=EconStyle.INK_MUTED)
    EconStyle.add_source(fig, 'FRED: WRESBAL, EFFR, SOFR, IORB; FRFS: Fedwire Funds', f'{today:%d %b %Y}')
    EconStyle.save_chart(fig, path)
