"""Sector-only foreign investment view, served from checksum-verified publications."""
import pandas as pd
import altair as alt
import streamlit as st

from config.emerging_opportunity import EQUITY_SECTORS, SECTORS
from data.processors.emerging_publication import read_manifest, load_sector
from data.processors.sector_flows import PERIODS, rank_sectors

INK = '#0A1F3D'
NIFTY_TOTAL_MARKET_PAGE = 'https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-total-market'
NSE_MARKET_LENS_SCREENER = 'https://marketlens.nseindia.in/screener'
NSE_MARKET_LENS_CREATE = 'https://marketlens.nseindia.in/create-screen'
NSE_MARKET_LENS_GUIDE = 'https://marketlens.nseindia.in/screener-guidelines'


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
        # Keep the directory lean: this view needs the verified company identity
        # and classification only, not the much larger quarterly ownership history.
        result[sector] = {
            **{key: data[key] for key in ('as_of', 'flows_as_of', 'flows')},
            'companies': [
                {'name': company['name'], 'symbol': company['symbol'],
                 'baskets': company.get('baskets', [])}
                for company in data.get('companies', [])
            ],
            'universe_scope': data.get('universe_scope', 'Verified company subset'),
            'collected_at': data.get('collected_at'),
        }
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
                '.st-key-eo-history-selector{max-width:680px;width:100%;margin:1.5rem auto 0;}'
                '.st-key-eo-history{max-width:680px;width:100%;margin:0 auto 1rem;}'
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
    with st.container(key='eo-history-selector'):
        sector = st.selectbox('Sector history', options, key='eo-active-sector')
    data = datasets[sector]
    history = pd.DataFrame(data['flows']).sort_values('date')
    history['period_label'] = pd.to_datetime(history.date).dt.strftime('%d %b')
    history['direction'] = history.equity_flow_cr.map(_direction)
    with st.container(key='eo-history'):
        st.markdown('#### ' + sector)
        st.caption('Fortnightly net equity investment · ₹ crore · '
                   + _day(history.iloc[0]['start']) + '–' + _day(history.iloc[-1]['date']))
        st.altair_chart(_history_chart(history), use_container_width=True, theme=None,
                        key='eo-sector-history-chart')
        st.caption('Teal: net investment · Ochre: net withdrawal. Full saved history; independent of the comparison period above.')
        st.download_button('Download selected sector history · CSV', history.drop(columns=['period_label', 'direction']).to_csv(index=False),
                           file_name=SECTORS[sector] + '_foreign_flows.csv', mime='text/csv')
    _render_directory(data, sector)


def _render_directory(data, sector):
    """Show a dated, auditable directory without implying complete market coverage."""
    companies = pd.DataFrame(data['companies'])
    if companies.empty:
        return

    with st.expander('Company directory and industry map', expanded=False):
        collected = _day(data['collected_at'][:10]) if data.get('collected_at') else 'date unavailable'
        st.markdown('#### Companies in ' + sector)
        st.caption(f"{len(companies):,} verified NSE index members · constituent snapshot collected {collected}.")
        st.caption('Coverage basis: ' + data['universe_scope'])

        st.markdown('**Sub-industry map**')
        st.caption('NSE Indices provides an official drilldown from sector to industry, basic industry and '
                   'constituent stocks. Its classification is separate from the NSDL flow sectors.')
        st.link_button('Open official NSE Indices industry map', NIFTY_TOTAL_MARKET_PAGE,
                       width='stretch')
        st.caption('On the NIFTY Total Market page, open “Sectoral Distribution” and drill into a sector.')

        st.markdown('**Continue your research in NSE Market Lens**')
        st.caption('Browse NSE stocks by Market Lens sector and sub-sector, then refine the list with financial '
                   'filters or a custom screen. Its sector labels are independent of NSDL, so choose the closest '
                   'Market Lens category for comparison.')
        browse_col, screen_col = st.columns(2)
        with browse_col:
            st.link_button('Browse NSE stocks by sector', NSE_MARKET_LENS_SCREENER,
                           width='stretch')
        with screen_col:
            st.link_button('Build a custom screen', NSE_MARKET_LENS_CREATE,
                           width='stretch')
        st.caption('Copy a starter query below into the custom-screen builder, adjust the thresholds, and review '
                   'the metric definitions before using the results.')
        query_col1, query_col2 = st.columns(2)
        with query_col1:
            st.markdown('**Quality and growth**')
            st.code('ROE > 20 AND Rev Growth > 15 AND Debt / Eq < 1', language='text')
        with query_col2:
            st.markdown('**Value and capital efficiency**')
            st.code('Market Cap > 500 AND PE Ratio < 15 AND ROCE > 22', language='text')
        st.markdown(f'[Market Lens screen-building guide]({NSE_MARKET_LENS_GUIDE}) · '
                    'Filtered results can be refined and exported as CSV.')

        st.markdown('**Search the verified directory**')
        query = st.text_input('Company name or NSE symbol', key='eo-directory-search-' + SECTORS[sector],
                              placeholder='For example, TCS or Tata Consultancy Services')
        view = companies[['name', 'symbol']].copy()
        if query.strip():
            needle = query.strip().casefold()
            mask = (view['name'].str.casefold().str.contains(needle, regex=False) |
                    view['symbol'].str.casefold().str.contains(needle, regex=False))
            view = view.loc[mask]
        view = view.rename(columns={'name': 'Company', 'symbol': 'NSE symbol'}).sort_values('Company')
        st.caption(f"Showing {len(view):,} of {len(companies):,} companies in the verified subset.")
        st.dataframe(view, hide_index=True, width='stretch',
                     height=420,
                     column_config={'Company': st.column_config.TextColumn('Company', width='large'),
                                    'NSE symbol': st.column_config.TextColumn('NSE symbol', width='small')})
        st.download_button('Download visible directory · CSV', view.to_csv(index=False),
                           file_name=SECTORS[sector] + '_company_directory.csv', mime='text/csv')
