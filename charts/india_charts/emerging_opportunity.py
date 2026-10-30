"""Sector-only foreign investment view, served from checksum-verified publications."""
import pandas as pd
import altair as alt
import streamlit as st

from config.emerging_opportunity import EQUITY_SECTORS, SECTORS
from data.processors.emerging_publication import read_manifest, load_sector
from data.processors.sector_flows import PERIODS, rank_sectors

INK = '#0A1F3D'


def finish(chart):
    return (chart.configure(background='transparent').configure_view(stroke=None)
            .configure_axis(labelFont='Inter', titleFont='Inter', labelColor=INK, titleColor=INK,
                            gridColor='#DDD8CD', gridOpacity=.55, domain=False, tickSize=0,
                            labelPadding=7, titlePadding=12, labelFontSize=11, titleFontSize=11)
            .configure_title(font='Inter', color=INK, fontSize=16, anchor='start'))


def _day(value):
    return pd.Timestamp(value).strftime('%d %b %Y')


def _direction(value):
    return 'Net investment' if value > 0 else 'Net withdrawal' if value < 0 else 'No net investment'


def _color():
    return alt.Color('direction:N', title=None, legend=None,
                     scale=alt.Scale(domain=['Net investment', 'Net withdrawal', 'No net investment'],
                                     range=['#287D73', '#C49343', '#9C9689']))


@st.cache_data(show_spinner=False, max_entries=2)
def _published_flows(folder, manifest):
    # Publication directories are immutable and content-addressed. A new CURRENT
    # pointer selects a different folder/cache key; audit every sector on first use.
    result = {}
    for sector in EQUITY_SECTORS:
        data = load_sector(sector, folder, manifest)
        result[sector] = {key: data[key] for key in ('as_of', 'flows_as_of', 'flows')}
    return result


def render():
    st.markdown('Where are foreign portfolio investors adding or withdrawing equity investment? '
                'Compare 22 NSDL sectors, then follow a sector’s fortnightly history.')
    try:
        folder, manifest = read_manifest()
        datasets = _published_flows(folder, manifest)
        rows, _, _, _ = rank_sectors(datasets, PERIODS[3])
    except (OSError, ValueError, KeyError, TypeError):
        st.warning('Foreign investment by sector is unavailable: the published flow snapshot could not be verified.')
        return
    _render_comparison(datasets)
    # Keep the initial six-month ordering. Comparison controls rerun only their
    # fragment, leaving the history selection, chart and scroll position intact.
    options = pd.DataFrame(rows).sort_values('net_cr', ascending=False, na_position='last').sector.tolist()
    if st.session_state.get('eo-active-sector') not in options:
        st.session_state['eo-active-sector'] = options[0]
    st.markdown('<style>'
                '.st-key-eo-history{max-width:680px;width:100%;margin:1.5rem auto 1rem;}'
                '.st-key-eo-history [data-testid="stMarkdownContainer"] h4{text-align:center;}'
                '.st-key-eo-history [data-testid="stCaptionContainer"]{text-align:center;}'
                '</style>', unsafe_allow_html=True)
    _render_history(datasets, options)
    _render_definitions()


def _comparison_chart(available, column, unit):
    # Reserve the same label gutter for every ranking. Vega's inferred axis
    # bounds can otherwise change during responsive updates and clip labels.
    # Stable, explicit data names avoid Streamlit's content-hash dataset names:
    # those change on each period switch and can leave Vega updating a stale view.
    data = alt.InlineData(name='sector_comparison', values=available.to_dict(orient='records'))
    gutter = alt.ExprRef(expr='containerSize()[0] < 600 ? 130 : 240')
    label_limit = alt.ExprRef(expr='containerSize()[0] < 600 ? 120 : 230')
    bars = alt.Chart(data).mark_bar().encode(
        y=alt.Y('sector:N', sort=available.sector.tolist(), title=None,
                axis=alt.Axis(labelLimit=label_limit, labelPadding=8, minExtent=gutter, maxExtent=gutter)),
        x=alt.X(column + ':Q', title=unit), color=_color(),
        tooltip=[alt.Tooltip('sector:N', title='Sector'),
                 alt.Tooltip('net_cr:Q', title='Net equity investment · ₹ crore', format=',.0f'),
                 alt.Tooltip('relative_pct:Q', title='Net investment / opening holdings · %', format='.2f')])
    zero = alt.Chart(alt.InlineData(name='comparison_zero', values=[{}])).mark_rule(
        color='#8F897D').encode(x=alt.datum(0))
    return finish((bars + zero).properties(
        height=650, padding={'left': 4, 'right': 12, 'top': 8, 'bottom': 8},
        autosize=alt.AutoSizeParams(type='fit-x', contains='padding', resize=True)))


@st.fragment
def _render_comparison(datasets):
    period = st.radio('Comparison period', PERIODS, index=3, horizontal=True, key='eo-flow-period')
    relative = st.checkbox('Compare investment relative to opening foreign holdings', key='eo-flow-relative')
    rows, start, end, cutoff = rank_sectors(datasets, period)
    st.caption(f'Comparison: {_day(start)}–{_day(end)} · Latest published observation: {_day(cutoff)} · '
               'Source: NSDL fortnightly equity investment · Sector definitions follow NSDL.')
    column = 'relative_pct' if relative else 'net_cr'
    unit = '% of opening FPI equity holdings' if relative else '₹ crore'
    if relative:
        st.caption('Net equity investment over the selected period ÷ FPI equity assets under custody at the '
                   'start of that period × 100. This measures investment relative to existing foreign holdings; '
                   'it is not an investment return or a change in portfolio weight.')
    frame = pd.DataFrame(rows).sort_values(column, ascending=False, na_position='last')
    available = frame.dropna(subset=[column]).copy()
    available['direction'] = available[column].map(_direction)
    if not available.empty:
        # A normal heading cannot be clipped by the chart's canvas bounds.
        st.markdown('**Foreign equity investment by sector**')
        st.altair_chart(_comparison_chart(available, column, unit),
                        use_container_width=True, theme=None, key='eo-sector-comparison')
    missing = frame.loc[frame[column].isna(), 'sector'].tolist()
    if missing:
        st.info('Unavailable for this comparison: ' + ', '.join(missing) + '. Missing observations or opening holdings are not treated as zero.')
    st.download_button('Download sector comparison · CSV', frame.assign(period_start=start, period_end=end).to_csv(index=False),
                       file_name='foreign_sector_comparison_' + end + '.csv', mime='text/csv')


def _render_definitions():
    with st.expander('Sources and definitions'):
        st.markdown('[NSDL fortnightly sector investment reports](https://pilot.fpi.nsdl.co.in/Reports/FPI_Fortnightly_Selection.aspx)')
        st.write('Only the reported equity net-investment columns are used. Assets under custody are market values '
                 'and can change with prices as well as investment. They are not used to infer purchases or sales. '
                 'Three and six months mean six and twelve consecutive fortnights. The latest complete month '
                 'requires both halves of a calendar month. All sectors use the same comparison dates. '
                 'Sovereign and the unclassified Others residual are excluded, so these 22 sectors need not sum '
                 'to the published all-sector total. Source revisions may change past observations.')
        st.caption('These are foreign investment statistics. Domestic institutional flows and company ownership '
                   'changes are not part of this view.')


def _history_chart(history):
    # Keep the numeric-label gutter even when a sector change replaces the scale.
    # Native formatting lets Vega measure the actual comma-separated labels.
    history_axis = alt.Axis(tickCount=4, format=',.0f', minExtent=58, maxExtent=58,
                            labelLimit=58)
    data = alt.InlineData(name='sector_history', values=history.to_dict(orient='records'))
    bars = alt.Chart(data).mark_bar(size=22, cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X('period_label:O', sort=history.period_label.tolist(), title=None,
                axis=alt.Axis(labelAngle=0, labelFontSize=10, labelOverlap=True, grid=False)),
        y=alt.Y('equity_flow_cr:Q', title=None, axis=history_axis),
        color=_color(),
        tooltip=[alt.Tooltip('start:N', title='From'), alt.Tooltip('date:N', title='To'),
                 alt.Tooltip('equity_flow_cr:Q', title='Net investment · ₹ crore', format=',.0f')])
    # A constant rule shares the flow scale without introducing a second y axis.
    zero = alt.Chart(alt.InlineData(name='history_zero', values=[{}])).mark_rule(
        color='#8F897D', strokeWidth=1).encode(y=alt.datum(0))
    return finish((bars + zero).properties(
        height=230, padding={'left': 4, 'right': 12, 'top': 12, 'bottom': 8},
        autosize=alt.AutoSizeParams(type='fit-x', contains='padding', resize=True)))


@st.fragment
def _render_history(datasets, options):
    with st.container(key='eo-history'):
        sector = st.selectbox('Sector history', options, key='eo-active-sector')
        data = datasets[sector]
        history = pd.DataFrame(data['flows']).sort_values('date')
        history['period_label'] = pd.to_datetime(history.date).dt.strftime('%d %b')
        history['direction'] = history.equity_flow_cr.map(_direction)
        st.markdown('#### ' + sector)
        st.caption('Fortnightly net equity investment · ₹ crore · '
                   + _day(history.iloc[0]['start']) + '–' + _day(history.iloc[-1]['date']))
        st.altair_chart(_history_chart(history), use_container_width=True, theme=None,
                        key='eo-sector-history-chart')
        st.caption('Teal: net investment · Ochre: net withdrawal. Full saved history; independent of the comparison period above.')
        st.download_button('Download selected sector history · CSV', history.drop(columns=['period_label', 'direction']).to_csv(index=False),
                           file_name=SECTORS[sector] + '_foreign_flows.csv', mime='text/csv')
