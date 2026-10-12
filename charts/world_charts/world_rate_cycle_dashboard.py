"""Native World dashboard views of central-bank breadth and weighted moves."""
from datetime import date

import altair as alt
import pandas as pd

from charts.style import EconStyle

AVERAGE_MONTHS = 6


def legend_html(weighted=False):
    """A wrapping HTML legend outside the plotting surface."""
    entries = [('Hikes', f'background:{EconStyle.LOSS};height:9px'),
               ('Cuts', f'background:{EconStyle.GAIN};height:9px'),
               ('Net · 6-month average', 'border-top:2px solid #1C2430')]
    if weighted:
        entries.append(('Equal-weight bp · 6-month average', 'border-top:2px dashed #7A8490'))
    return ('<div style="display:flex;flex-wrap:wrap;gap:8px 18px;margin:0 0 12px;'
            'font-size:12px;color:#4B5563">' + ''.join(
                '<span style="display:inline-flex;align-items:center;gap:6px">'
                f'<span aria-hidden="true" style="display:inline-block;width:17px;{style}"></span>'
                f'{label}</span>' for label, style in entries) + '</div>')


def frames(cycle, weighted=False, today=None):
    """Use the saved monthly counts or weighted bp moves without reweighting."""
    months = pd.period_range(cycle['start'], periods=len(cycle['hikes']), freq='M')
    if not len(months):
        raise ValueError('No monthly rate-cycle observations available')
    hikes, cuts = cycle['hikes'], cycle['cuts']
    if weighted:
        hikes, cuts = cycle['weighted']['hikes_bp'], cycle['weighted']['cuts_bp']
    reporting = cycle['reporting']
    if any(len(values) != len(months) for values in (hikes, cuts, reporting)):
        raise ValueError('Rate-cycle monthly arrays have different lengths')
    partial = (months[-1] >= pd.Period(today or date.today(), freq='M')
               or reporting[-1] < cycle['banks'])
    rows = []
    for i, month in enumerate(months):
        provisional = partial and i == len(months) - 1
        for label, magnitude, sign in [('Hikes', hikes[i], 1), ('Cuts', cuts[i], -1)]:
            rows.append({'date': month.to_timestamp().isoformat(), 'series': label,
                         'value': magnitude * sign, 'magnitude': magnitude,
                         'reporting': reporting[i],
                         'status': 'Partial month' if provisional else 'Reported month',
                         'opacity': .40 if provisional else 1})
    # The current/incomplete month must not enter the completed-month average.
    done = len(months) - int(partial)
    net = pd.Series([h - c for h, c in zip(hikes, cuts)], index=months)
    averages = [('Net · 6-month average', net.iloc[:done].rolling(AVERAGE_MONTHS).mean())]
    if weighted:
        equal = cycle['weighted']['equal_bp']
        if len(equal) != len(months):
            raise ValueError('Equal-weight monthly array has a different length')
        averages.append(('Equal-weight bp · 6-month average',
                         pd.Series(equal, index=months).iloc[:done].rolling(AVERAGE_MONTHS).mean()))
    lines = [{'date': month.to_timestamp().isoformat(), 'value': float(value), 'series': label}
             for label, values in averages for month, value in values.dropna().items()]
    return rows, lines, partial


def chart(cycle, weighted=False, today=None):
    bars, averages, partial = frames(cycle, weighted, today)
    unit = 'Basis points' if weighted else 'Central banks'
    value_format = '.1f' if weighted else '.0f'
    end = pd.Timestamp(bars[-1]['date'])
    x = alt.X('date:T', title=None, scale=alt.Scale(domain=[bars[0]['date'],
              (end + pd.DateOffset(months=3)).isoformat()]),
              axis=alt.Axis(format='%Y', tickCount=7, grid=False, labelAngle=0))
    y = alt.Y('value:Q', title=unit, stack=None,
              axis=alt.Axis(gridColor='#E4E7EB', tickCount=6), scale=alt.Scale(zero=True))
    names = ['Hikes', 'Cuts', 'Net · 6-month average']
    colors = [EconStyle.LOSS, EconStyle.GAIN, '#1C2430']
    if weighted:
        names.append('Equal-weight bp · 6-month average')
        colors.append('#7A8490')
    palette = alt.Scale(domain=names, range=colors)
    legend = None  # The dashboard places a wrapping legend below its description.
    columns = alt.Chart(alt.Data(values=bars)).mark_bar().encode(
        x=x, y=y,
        color=alt.Color('series:N', scale=palette, legend=legend),
        opacity=alt.Opacity('opacity:Q', scale=None, legend=None),
        tooltip=[alt.Tooltip('date:T', title='Month', format='%b %Y'),
                 alt.Tooltip('series:N', title='Direction'),
                 alt.Tooltip('magnitude:Q', title=unit, format=value_format),
                 alt.Tooltip('reporting:Q', title='Banks reporting', format='.0f'),
                 alt.Tooltip('status:N', title='Coverage')])
    zero = alt.Chart(alt.Data(values=[{'value': 0}])).mark_rule(
        color='#7A8490', strokeWidth=1).encode(y='value:Q')
    layers = [zero, columns]
    if averages:
        line = alt.Chart(alt.Data(values=averages)).mark_line(strokeWidth=2).encode(
            x=x, y=y, color=alt.Color('series:N', scale=palette, legend=legend),
            strokeDash=alt.StrokeDash('series:N', legend=None, scale=alt.Scale(
                domain=['Net · 6-month average', 'Equal-weight bp · 6-month average'],
                range=[[1, 0], [5, 3]])),
            tooltip=[alt.Tooltip('date:T', title='Month', format='%b %Y'),
                     alt.Tooltip('series:N', title='Measure'),
                     alt.Tooltip('value:Q', title=unit, format='.1f')])
        layers.append(line)
    if partial:
        # One monthly bar is tiny across 26 years. Locate it explicitly while
        # retaining its true height and faded fill (a zero move gets no point).
        guide = alt.Chart(alt.Data(values=[{'date': end.isoformat(),
                                           'label': f'{end:%b %Y} · partial'}]))
        layers.append(guide.mark_rule(color='#9CA3AF', strokeDash=[3, 3], strokeWidth=1)
                      .encode(x=x))
        layers.append(guide.mark_text(align='right', dx=-7, color='#56616D', fontSize=11)
                      .encode(x=x, y=alt.value(12), text='label:N'))
        latest = [row for row in bars[-2:] if row['magnitude'] > 0]
        if latest:
            layers.append(alt.Chart(alt.Data(values=latest)).mark_point(
                filled=True, fillOpacity=.4, size=55, strokeWidth=1.3).encode(
                    x=x, y=y, color=alt.Color('series:N', scale=palette, legend=None),
                    stroke=alt.Stroke('series:N', scale=palette, legend=None),
                    tooltip=columns.encoding.tooltip))
    return alt.layer(*layers).properties(height=340, background='#FFFFFF').configure_view(stroke=None).configure_axis(
        domain=False, ticks=False, labelFont='Inter', titleFont='Inter',
        labelFontSize=11, titleFontSize=11, titleFontWeight='normal',
        labelColor='#4B5563', titleColor='#4B5563', labelPadding=7).configure_legend(
        labelFont='Inter', labelFontSize=11, labelColor='#4B5563')


def latest_summary(cycle, weighted=False, today=None):
    _, _, partial = frames(cycle, weighted, today)
    month = pd.Period(cycle['start'], freq='M') + len(cycle['hikes']) - 1
    label = month.strftime('%B %Y') + (' so far' if partial else '')
    counts = f"{cycle['hikes'][-1]} hiking · {cycle['cuts'][-1]} cutting"
    if weighted:
        w = cycle['weighted']
        counts = f"Net {w['hikes_bp'][-1] - w['cuts_bp'][-1]:+.1f} bp · " + counts
    return f"{label}: {counts} · {cycle['reporting'][-1]}/{cycle['banks']} banks reporting"
