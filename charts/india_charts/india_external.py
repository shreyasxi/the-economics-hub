"""Research charts from validated official RBI / DEA external-sector datasets."""
from pathlib import Path

import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from charts.style import EconStyle
from data.fetchers.rbi_external import (
    WSS_PATH, REER_PATH, VULNERABILITY_PATH, read_rows,
)


def load_forex(n_weeks=78, path=WSS_PATH):
    rows = read_rows(path, 'wss')
    if not rows: return None
    df = pd.DataFrame(rows)
    df['week_ending'] = pd.to_datetime(df['date'])
    df['forex_reserves_usd_bn'] = pd.to_numeric(df['total_reserves_usd_mn']) / 1000
    consecutive = df['week_ending'].diff().dt.days.eq(7)
    df['forex_reserves_wow_chg'] = df['forex_reserves_usd_bn'].diff().where(consecutive)
    df = df.tail(n_weeks).reset_index(drop=True)
    df.attrs['source'] = 'RBI WSS; earlier RBI DBIE history' if (df['source'] != 'RBI WSS').any() else 'RBI WSS'
    df.attrs['latest_observation'] = df['week_ending'].iloc[-1].strftime('%d %b %Y')
    return df


def regular_panel(rows, value_fields, frequency):
    """Insert NaN at absent periods so plotted lines never bridge missing data."""
    frame = pd.DataFrame(rows).set_index(pd.to_datetime([r['date'] for r in rows]))
    for field in value_fields:
        frame[field] = pd.to_numeric(frame[field], errors='coerce')
    periods = pd.date_range(frame.index.min(), frame.index.max(), freq=frequency)
    return frame.reindex(periods)


def decorate(ax):
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', alpha=.16)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.margins(x=.09)


def label_latest(ax, values, suffix='', provisional=False, color='#0369A1'):
    latest = values.dropna()
    if latest.empty: return
    x, y = latest.index[-1], latest.iloc[-1]
    ax.scatter([x], [y], color=color, s=20, zorder=5)
    ax.annotate(f'{y:.1f}{suffix}' + (' P' if provisional else ''), (x, y),
                xytext=(6, 5), textcoords='offset points', color=color,
                fontsize=EconStyle.FONT_SIZE_AXIS, weight='bold')


def single_quarter_bridges(ax, values, color):
    """Connect only isolated missing quarters, using observed endpoints only.

    The solid series and its NaNs remain intact. Never bridge a longer gap,
    an endpoint gap, or nonconsecutive quarterly dates.
    """
    periods = values.index.to_period('Q')
    for i in range(1, len(values) - 1):
        if (pd.isna(values.iloc[i]) and pd.notna(values.iloc[i-1])
                and pd.notna(values.iloc[i+1])
                and periods[i].ordinal - periods[i-1].ordinal == 1
                and periods[i+1].ordinal - periods[i].ordinal == 1):
            ax.plot(values.index[[i-1, i+1]], values.iloc[[i-1, i+1]],
                    color=color, linewidth=.9, linestyle=(0, (3, 3)),
                    alpha=.55, zorder=2)


def chart_reer(output_dir, path=REER_PATH):
    rows = read_rows(path, 'reer')
    if not rows: return None
    frame = regular_panel(rows, ['reer'], 'MS')
    # Display up to ten years of RBI's consistent back-series.
    frame = frame.loc[frame.index >= frame.index.max() - pd.DateOffset(years=10)]
    fig, ax = EconStyle.create_figure(size='standard')
    ax.plot(frame.index, frame['reer'], color='#0369A1', linewidth=2)
    ax.axhline(100, color=EconStyle.TEXT_MUTED, linewidth=.9, linestyle='--')
    ax.text(.01, .04, '100 = index base; not an estimate of fair value', transform=ax.transAxes,
            fontsize=EconStyle.FONT_SIZE_SOURCE, color=EconStyle.TEXT_MUTED)
    label_latest(ax, frame['reer'], provisional=rows[-1]['provisional'] == 'true')
    ax.set_ylabel('Index · 2015–16 = 100')
    decorate(ax)
    EconStyle.set_title(ax, 'India’s Real Effective Exchange Rate', 'RBI 40-currency trade-weighted REER · CPI based')
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[.02,.09,.98,.98])
    latest = pd.Timestamp(rows[-1]['date']).strftime('%b %Y')
    EconStyle.add_source(fig, 'RBI Bulletin Table 37 / Handbook', f'{latest} · P = provisional')
    dest = Path(output_dir) / '30_india_reer.png'
    EconStyle.save_chart(fig, dest)
    return dest


def chart_vulnerability(output_dir, path=VULNERABILITY_PATH):
    rows = read_rows(path, 'external')
    if not rows: return None
    fields = ['current_account_gdp_pct','short_term_debt_reserves_pct']
    frame = regular_panel(rows, fields, pd.offsets.QuarterEnd(startingMonth=12))
    if any(frame[field].notna().sum() < 2 for field in fields): return None
    fig, axes = EconStyle.create_figure(size='wide', ncols=2, sharex=True, sharey=False)
    left, right = axes
    color = EconStyle.LINE_MAROON
    left.plot(frame.index, frame[fields[0]], color=color, linewidth=1.8, zorder=3)
    left.axhline(0, color=EconStyle.TEXT_TITLE, linewidth=.9)
    right.plot(frame.index, frame[fields[1]], color=color, linewidth=1.8, zorder=3)
    single_quarter_bridges(right, frame[fields[1]], color)
    headings = ['Current account balance', 'Short-term debt / FX reserves']
    notes = ['% of quarterly GDP · Surplus (+) / Deficit (−)',
             '% · Original maturity ≤1 year · Quarter-end']
    for ax,field,heading,note in zip(axes,fields,headings,notes):
        decorate(ax)
        ax.text(0, 1.09, heading, transform=ax.transAxes,
                fontsize=EconStyle.FONT_SIZE_AXIS, weight='bold', color=EconStyle.TEXT_TITLE)
        ax.text(0, 1.025, note, transform=ax.transAxes,
                fontsize=EconStyle.FONT_SIZE_SOURCE, color=EconStyle.TEXT_MUTED)
        latest = frame[field].dropna().index[-1]
        record = next(r for r in rows if pd.Timestamp(r['date']) == latest)
        preliminary = record.get('cab_status') == 'preliminary' if field == fields[0] else record.get('debt_status') in ('P','QE')
        label_latest(ax,frame[field],'%',provisional=preliminary,color=color)
        ax.margins(x=.12, y=.18)
        ax.tick_params(axis='both', labelsize=EconStyle.FONT_SIZE_AXIS)
    # Five labelled quarter-ends stay legible when the figure occupies half a
    # dashboard row. Both axes retain every observation in the common history.
    ticks = frame.index[np.linspace(0,len(frame)-1,min(5,len(frame)),dtype=int)]
    left.set_xticks(ticks)
    left.set_xticklabels([f"Q{(t.month - 1)//3 + 1}\n{t.year}" for t in ticks])
    EconStyle.add_editorial_header(fig, 'India’s External Vulnerability',
                                   'External financing needs and the reserve buffer')
    fig.subplots_adjust(left=.075,right=.965,bottom=.18,top=.75,wspace=.28)
    cab_latest=frame[fields[0]].dropna().index[-1]
    debt_latest=frame[fields[1]].dropna().index[-1]
    def quarter(t): return f'Q{(t.month-1)//3+1} {t.year}'
    dated = quarter(cab_latest) if cab_latest==debt_latest else f'CAB {quarter(cab_latest)}; debt {quarter(debt_latest)}'
    EconStyle.add_source(fig,'RBI quarterly BoP; RBI / DEA debt releases',dated + ' · P = preliminary/provisional')
    dest=Path(output_dir)/'31_india_external_vulnerability.png'
    EconStyle.save_chart(fig,dest)
    return dest


def generate(output_dir):
    Path(output_dir).mkdir(parents=True,exist_ok=True)
    out=[]
    for chart in (chart_reer,chart_vulnerability):
        result=chart(output_dir)
        if result:out.append(result)
    return out
