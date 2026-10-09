"""IIP-style native HTML table for the prepared India equity matrix artifact."""
from __future__ import annotations
from datetime import date
from html import escape
import math
from data.processors.india_equity_matrix import validate_payload


def _performance_cell_style(value):
    """Restrained local palette on the renderer's existing column-relative scale."""
    strength = 0 if value is None else min(1, abs(value) / 20)
    # Keep ordinary cells pale; reserve the accent for the existing scale's
    # saturation point. This does not change the per-column normalisation.
    intensity = 1 if strength == 1 else .14 * strength ** 2
    ink = (62, 107, 134) if value is not None and value > 0 else (139, 64, 87)
    rgb = tuple(round(255 + (channel - 255) * intensity) for channel in ink)
    background = '#{:02x}{:02x}{:02x}'.format(*rgb)
    foreground = '#ffffff' if intensity == 1 else '#30393d'
    return background, foreground, '600' if intensity == 1 else '400'


def render_html(payload):
    validate_payload(payload)
    esc = lambda v: escape(str(v), quote=True)
    columns = ('1W','1M','YTD','1Y','vs Nifty 50','3Y','5Y','Off 5Y high')
    rows = [r for g in payload['groups'] for r in g['rows']]
    def value(row, column):
        return row['vs_nifty50_1y'] if column == 'vs Nifty 50' else row['off_5y_high'] if column == 'Off 5Y high' else row['returns'][column]
    def formatted(v, pp=False):
        if v is None:
            return '—'
        rounded = round(v, 1)
        sign = '+' if rounded > 0 else '−' if rounded < 0 else ''
        return sign + f'{abs(rounded):.1f}' + (' pp' if pp else '%')
    scales = {}
    for c in columns:
        magnitudes = sorted(abs(value(r,c)) for r in rows if value(r,c) is not None)
        scales[c] = max(.5,magnitudes[int((len(magnitudes)-1)*.8)]) if magnitudes else 1
    def spark(row):
        points = row['sparkline']
        if len(points) < 2:
            return '—'
        values = [p['value'] for p in points];low,high = min(values),max(values)
        dates = [date.fromisoformat(p['date']) for p in points];span = max(1,(dates[-1]-dates[0]).days)
        xy = [(3+(d-dates[0]).days/span*110,28-(v-low)/(high-low or 1)*23) for d,v in zip(dates,values)]
        segments,segment = [],[]
        for i,point in enumerate(xy):
            if i and (dates[i]-dates[i-1]).days > 14:
                segments.append(segment);segment=[]
            segment.append(point)
        segments.append(segment)
        paths = ''.join('<polyline points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in seg)+'" fill="none" stroke="#50595e" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round"/>' for seg in segments)
        tooltip = esc(row['label']+' · 52 weeks of gross TRI, weekly observed closes; '+points[0]['date']+' to '+points[-1]['date'])
        colour = '#3e6b86' if values[-1]>=values[0] else '#8b4057'
        return f'<svg class="iem-spark" viewBox="0 0 116 34" role="img" aria-label="{tooltip}"><title>{tooltip}</title>{paths}<circle cx="{xy[-1][0]:.2f}" cy="{xy[-1][1]:.2f}" r="2.2" fill="{colour}"/></svg>'
    css = '''<style>
.iem-block{max-width:100%;width:100%;min-width:0;margin:24px 0 32px;font-family:Inter,sans-serif;color:#28251f;box-sizing:border-box}
.iem-block h3{font-family:Newsreader,Georgia,serif;font-size:28px;line-height:1.2;font-weight:600;color:#28251f;margin:0 0 14px}
.iem-block p{font-size:12px;line-height:1.6;color:#68645d;margin:0 0 14px}
.iem-scroll{display:block;overflow-x:auto;max-width:100%;overscroll-behavior-x:contain;scrollbar-color:#aaa296 #f4f4f1}
.iem-scroll:focus-visible{outline:2px solid #1e5d8f;outline-offset:2px}
.iem-table{border:1.5px solid #87918f;border-collapse:separate;border-spacing:0;table-layout:fixed;width:100%;min-width:1080px;font-size:12px;font-variant-numeric:tabular-nums;background:#fff}
.iem-name-col{width:265px}.iem-spark-col{width:126px}.iem-relative-col{width:101px}
.iem-table th,.iem-table td{padding:9px 8px;text-align:right;border:0;line-height:1.35;white-space:nowrap}
.iem-table thead th{font-weight:600;background:#3d4549;color:#fff;white-space:nowrap;padding-top:10px;padding-bottom:10px}
.iem-table .iem-name{position:sticky;left:0;z-index:1;text-align:left;background:#fafaf8;color:#252e33;font-weight:600;white-space:normal;font-size:12px}
.iem-table thead .iem-name{background:#3d4549;color:#fff;font-weight:600;z-index:2}
.iem-row>th,.iem-row>td{border-bottom:1px solid #edf0ee}
.iem-row>td:nth-child(3),.iem-row>td:nth-child(7),.iem-row>td:nth-child(8),.iem-row>td:nth-child(10){padding-left:11px}
.iem-row>td:nth-child(7),.iem-row>td:nth-child(10){border-left:1px solid #eef0ed}
.iem-table thead th:nth-child(3),.iem-table thead th:nth-child(7),.iem-table thead th:nth-child(8),.iem-table thead th:nth-child(10){padding-left:11px}
.iem-table .iem-group{text-align:left;background:#e7eae5;color:#394247;font-weight:700;font-size:11px;letter-spacing:.065em;padding-top:11px;padding-bottom:10px;border-top:1px solid #d4dbd5;border-bottom:1px solid #dce2dc;border-left:3px solid #87948a}
.iem-group span{position:sticky;left:7px;display:block;width:max-content;max-width:250px}
.iem-spark{display:block;width:112px;height:30px;margin:0 auto}.iem-table .iem-missing{color:#747a7d}
.iem-block .iem-method{font-size:12px;margin:12px 0 0;color:#737a7e}
.iem-block details{font-size:11px;color:#68645d;line-height:1.7;margin-top:10px}.iem-block summary{cursor:pointer;color:#292d30}
.iem-block details ul{padding-left:18px}.iem-block a{color:#1e5d8f}
@media(max-width:600px){.iem-block h3{font-size:24px}.iem-name-col{width:170px}.iem-table{min-width:985px}.iem-group span{max-width:165px}.iem-table .iem-name{font-size:11px}}
</style>'''
    as_of = date.fromisoformat(payload['as_of']).strftime('%d %b %Y').lstrip('0')
    out = [css,'<section class="iem-block" id="chart-india-equity-matrix" aria-label="India equity market leadership">',
           f'<h3>{esc(payload["title"])}</h3>',
           f'<p>As of {esc(as_of)} · Returns in INR · 3Y and 5Y annualised · vs Nifty 50: 1Y excess return in percentage points.</p>',
           '<div class="iem-scroll" tabindex="0" role="region" aria-label="India equity returns; scroll horizontally for all columns">',
           '<table class="iem-table" aria-label="Official India equity total returns"><colgroup><col class="iem-name-col"><col class="iem-spark-col"><col span="4"><col class="iem-relative-col"><col span="3"></colgroup>',
           '<thead><tr><th class="iem-name" scope="col">Index</th><th scope="col">52 weeks</th>']
    for c in columns:
        tip = 'Index 1Y total return minus Nifty 50 1Y total return; percentage points' if c=='vs Nifty 50' else 'Latest TRI below its highest observed TRI in the trailing five calendar years' if c=='Off 5Y high' else c+(' annualised CAGR' if c in ('3Y','5Y') else ' total return')
        out.append(f'<th scope="col" title="{esc(tip)}">{esc(c)}</th>')
    out.append('</tr></thead><tbody>')
    for group in payload['groups']:
        out.append(f'<tr><th class="iem-group" colspan="10" scope="rowgroup"><span>{esc(group["label"].upper())}</span></th></tr>')
        for row in group['rows']:
            metadata = row['label']+' · Official NSE gross TRI · '+row['code']+' · '+('As of '+row['latest_date'] if row['status']=='available' else 'Unavailable: '+row['reason'])
            out.append(f'<tr class="iem-row"><th class="iem-name" scope="row" title="{esc(metadata)}">{esc(row["label"])}</th><td>{spark(row)}</td>')
            for c in columns:
                v = value(row,c)
                color_value = None if v is None else 0 if abs(v)<.05 else math.copysign(min(1,abs(v)/scales[c])*20,v)
                bg,fg,weight = _performance_cell_style(color_value)
                if row['status']=='unavailable':
                    tip = row['reason']
                elif c=='Off 5Y high':
                    tip = row.get('off_5y_high_reason') or f'Window {row["high_5y_start"]} to {row["latest_date"]}; peak {row["high_5y_date"]}'
                else:
                    a = row['anchor_dates'].get('1Y' if c=='vs Nifty 50' else c)
                    tip = f'Common latest {row["latest_date"]}; anchor '+(a['date'] if a else 'unavailable')
                    if c=='vs Nifty 50':tip += '; index minus Nifty 50, percentage points'
                out.append(f'<td style="background:{bg};color:{fg};font-weight:{weight}" title="{esc(tip)}">{formatted(v,c=="vs Nifty 50")}</td>')
            out.append('</tr>')
    out.append('</tbody></table></div>')
    out.append(f'<p class="iem-method">{esc(payload["methodology_note"])}</p>')
    out.append('<details><summary>Sources and calculation details</summary><p>Source: <a href="'+esc(payload['source_url'])+'" target="_blank" rel="noopener">NSE Indices historical gross TRI levels</a>. '
               'Calendar anchors use the last actual observation on or before the target, within seven days; no values are filled. '
               '1Y returns use the same actual dates as Nifty 50. 3Y/5Y use actual-day CAGR. Off 5Y high uses only the trailing five calendar years; '
               'it is unavailable when benchmark-observed sessions are missing. Colours show relative magnitude within each column.</p><ul>')
    for row in rows:
        note = f'Five-year missing observations: {len(row["missing_5y_dates"])}.' if row['status']=='available' else 'Unavailable: '+row['reason']
        out.append(f'<li><a href="{esc(row["source_url"])}" target="_blank" rel="noopener">{esc(row["label"])}</a> · {esc(row["code"])} · {esc(note)}</li>')
    out.append('</ul></details></section>')
    return ''.join(out)
