"""Native, responsive research views using EconHub's existing ink/accent palette."""
from __future__ import annotations

import html
import json
import pandas as pd
import altair as alt
import streamlit as st

from data.processors.emerging_opportunity import flow_metrics, company_panel
from data.processors.emerging_publication import read_manifest, load_sector
from config.emerging_opportunity import SECTORS, EQUITY_SECTORS, AI_PAGE

INK, BLUE, ORANGE, RED = '#0A1F3D', '#1F5596', '#C8620A', '#9B1C31'


def finish(chart):
    return (chart.configure(background='#FFFFFF').configure_view(stroke=None)
            .configure_axis(labelFont='Inter', titleFont='Inter', labelColor=INK, titleColor=INK,
                            gridColor='#E5E0D7', domain=False, labelFontSize=11, titleFontSize=12)
            .configure_legend(labelFont='Inter', titleFont='Inter', labelColor=INK)
            .configure_title(font='Inter', color=INK, fontSize=16, anchor='start'))


def show(chart):
    st.altair_chart(finish(chart), use_container_width=True, theme=None)


def quarter_label(value):
    return pd.Timestamp(value).strftime('%b %Y')


def _key(data, name):
    # Keep each sector's filters, search and company selection independent.
    return name if data['sector'] == 'Consumer Services' else name + '-' + SECTORS[data['sector']]


def render():
    st.markdown('Identify sectors attracting foreign money, then rank their stocks by quarterly changes in DII, FPI, mutual fund and insurer ownership. '
                'Covers 22 equity sectors and AI Catalysts, with stock coverage drawn from verified index constituents.')
    try:
        folder, publication = read_manifest()
        rows = publication['ranking']
    except (OSError, ValueError, KeyError, TypeError):
        st.warning('Institutional research is unavailable: the published snapshot could not be verified.')
        return
    order = st.radio('Rank sectors by', ['Six-month net buying', 'Latest fortnight', 'Buying relative to holdings'],
                     horizontal=True, key='eo-sector-ranking')
    column = {'Six-month net buying': 'Six-month net (₹ cr)', 'Latest fortnight': 'Latest fortnight (₹ cr)',
              'Buying relative to holdings': 'Net / opening FPI holdings (%)'}[order]
    ranked = sorted(rows, key=lambda r: (r[column] is not None, r[column] or 0), reverse=True)
    options = [r['Sector'] for r in ranked] + [s for s in EQUITY_SECTORS if s not in {r['Sector'] for r in ranked}] + ['AI Catalysts']
    labels = {}
    for i, row in enumerate(ranked, 1):
        value = row[column]
        amount = ('Unavailable' if value is None else f"{value:+.2f}%" if order == 'Buying relative to holdings' else f"₹{value:,.0f} cr")
        labels[row['Sector']] = f"{i}. {row['Sector']} · {amount}"
    st.session_state.setdefault('eo-active-sector', options[0])
    sector = st.selectbox('Sector or theme', options, format_func=lambda name: labels.get(name, name + ' · theme' if name == 'AI Catalysts' else name),
                          key='eo-active-sector')
    try:
        data = load_sector(sector, folder, publication)
    except (OSError, ValueError, KeyError, TypeError):
        st.warning(f'{sector} research is unavailable: the source archive or snapshot failed validation.')
        return
    theme = sector == 'AI Catalysts'
    metrics = flow_metrics(data)
    st.markdown('<h3 style="font-family:Newsreader,Georgia,serif;font-size:28px;color:#28251f;margin:12px 0">'
                f'{html.escape(sector)}</h3>', unsafe_allow_html=True)
    window_start = pd.Timestamp(data['window_start']) + pd.Timedelta(days=1)
    if theme:
        signal = f"The official Nifty basket tracks {len(data['companies'])} AI-enabling stocks across industries and has no separate NSDL flow series."
    else:
        period = f"{window_start.strftime('%b %Y')}–{pd.Timestamp(data.get('flows_as_of') or data['as_of']).strftime('%d %b %Y')}"
        streak = (f"buying continued for {metrics['current_streak']} consecutive fortnights" if metrics['current_streak'] else 'the latest fortnight recorded no net buying')
        signal = (f"FPI net equity investment was ₹{metrics['net_cr']:,.0f} crore in {period}; {streak}." if metrics['complete'] else
                  f"{metrics['count']} of {metrics['expected']} fortnights are available for {period}; missing periods are excluded rather than treated as zero.")
    st.markdown(f"**{'Theme' if theme else 'Flow signal'}:** {signal}")
    if not theme:
        st.caption(f"FPI flows through {pd.Timestamp(data.get('flows_as_of') or data['as_of']).strftime('%d %b %Y')} · Ownership through {quarter_label(data.get('ownership_as_of') or data['as_of'])}")
    if theme:
        tabs = st.tabs(['Company explorer', 'Sources & method'])
        with tabs[0]:
            _companies(data)
        with tabs[1]:
            _sources(data)
    else:
        tabs = st.tabs(['Sector flows', 'Company explorer', 'Sources & method'])
        with tabs[0]:
            _flows(data, metrics)
        with tabs[1]:
            _companies(data)
        with tabs[2]:
            _sources(data)


def _flows(data, metrics):
    if not data['flows']:
        st.warning('No validated sector-flow observations are available for this window.')
        return
    cols = st.columns(4)
    for col, label, value in zip(cols,
                                ['Six-month net buying' if metrics['complete'] else 'Available-period net buying',
                                 'Positive fortnights', 'Current buying streak', 'Latest fortnight'],
                                [f"₹{metrics['net_cr']:,.0f} cr", f"{metrics['positive']} / {metrics['expected']}",
                                 str(metrics['current_streak']), f"₹{data['flows'][-1]['equity_flow_cr']:,.0f} cr"]):
        col.metric(label, value)
    frequency_col, currency_col = st.columns(2)
    with frequency_col:
        aggregation = st.radio('Flow frequency', ['Fortnightly', 'Monthly'], horizontal=True, key=_key(data, 'eo-flow-frequency'))
    with currency_col:
        unit = st.radio('Currency', ['₹ crore', 'US$ million'], horizontal=True, key=_key(data, 'eo-flow-unit'))
    frame = pd.DataFrame(metrics['rows'])
    frame['period'] = pd.to_datetime(frame['date']).dt.strftime('%d %b')
    if aggregation == 'Monthly':
        frame['month'] = pd.to_datetime(frame.date).dt.strftime('%Y-%m')
        frame = frame.groupby('month', sort=True).agg(equity_flow_cr=('equity_flow_cr', 'sum'),
                                                    equity_flow_usd_m=('equity_flow_usd_m', 'sum'),
                                                    observations=('date', 'count')).reset_index()
        # A monthly bar requires both fortnights. Do not sum a partial month as a full month.
        frame.loc[frame.observations != 2, ['equity_flow_cr', 'equity_flow_usd_m']] = float('nan')
        frame['period'] = pd.to_datetime(frame.month).dt.strftime('%b')
    column = 'equity_flow_cr' if unit == '₹ crore' else 'equity_flow_usd_m'
    title = 'Equity flows · ₹ crore' if unit == '₹ crore' else 'Equity flows · US$ million'
    frame['direction'] = frame[column].apply(lambda value: 'Unavailable' if pd.isna(value) else
                                             'Net buying' if value > 0 else 'Net selling' if value < 0 else 'No net flow')
    palette = alt.Scale(domain=['Net buying', 'Net selling', 'No net flow', 'Unavailable'],
                        range=['#287D73', '#C49343', '#9C9689', '#DDD8CD'])
    bars = alt.Chart(frame).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3,
                                    size=20 if aggregation == 'Fortnightly' else 36).encode(
        x=alt.X('period:O', sort=frame.period.tolist(), title=None,
                axis=alt.Axis(labelAngle=-45, labelPadding=8, ticks=False)),
        y=alt.Y(column + ':Q', title=title, axis=alt.Axis(tickCount=5, titlePadding=12)),
        color=alt.Color('direction:N', title=None, scale=palette,
                        legend=alt.Legend(orient='bottom', direction='horizontal', symbolType='square',
                                          labelFontSize=11, offset=16)),
        tooltip=[alt.Tooltip('period:O', title='Period end'), alt.Tooltip('direction:N', title='Flow'),
                 alt.Tooltip('equity_flow_cr:Q', title='Net equity buying · ₹ cr', format=',.0f'),
                 alt.Tooltip('equity_flow_usd_m:Q', title='Net equity buying · US$ mn', format=',.1f')])
    baseline = alt.Chart(pd.DataFrame({'zero': [0]})).mark_rule(color='#8F897D', strokeWidth=1).encode(y='zero:Q')
    st.markdown('<style>.st-key-eo-persistence-chart{max-width:480px!important;width:100%!important;'
                'margin-left:auto!important;margin-right:auto!important;border:1.5px solid #333638;'
                'padding:12px;box-sizing:border-box;}</style>', unsafe_allow_html=True)
    with st.container(key='eo-persistence-chart'):
        chart = (bars + baseline).properties(height=440, title='Has buying persisted?')
        st.altair_chart(finish(chart).configure(background='#FAF8F2')
                       .configure_axis(labelColor='#57534A', titleColor='#57534A', gridColor='#E8E3D8')
                       .configure_title(color='#373D37', fontSize=16), use_container_width=True, theme=None)
    with st.expander('Underlying fortnightly observations'):
        st.dataframe(pd.DataFrame(data['flows']), hide_index=True, use_container_width=True)
    st.download_button('Download sector flows · CSV', pd.DataFrame(data['flows']).to_csv(index=False),
                       file_name=SECTORS[data['sector']] + '_fortnightly.csv', mime='text/csv', key=_key(data, 'eo-flows-download'))


def _select_quarter(data, key):
    quarters = data['quarters'][1:]
    # Prefer the most recent quarter with the greatest filed coverage. One
    # persistently absent security must not push a whole sector to a sparse quarter.
    default = max(range(len(quarters)), key=lambda i: (company_panel(data, quarters[i])['filed'], i))
    return st.selectbox('Ownership quarter', quarters, index=default,
                        format_func=lambda q: f"{quarter_label(q)} · {company_panel(data, q)['filed']}/{len(data['companies'])} filings",
                        key=key)


def _investor(data, key):
    label = st.radio('Ownership group', ['DII', 'FPI', 'Mutual funds', 'Insurers'],
                     horizontal=True, key=_key(data, key))
    return {'DII':'dii', 'FPI':'fpi', 'Mutual funds':'mf', 'Insurers':'insurance'}[label], label


def _companies(data):
    if not data['companies']:
        st.info('No verified company constituents are available in the source universe for this sector.')
        return
    investor, label = _investor(data, 'eo-company-investor')
    quarter = _select_quarter(data, _key(data, 'eo-company-quarter'))
    panel = company_panel(data, quarter, investor)
    left, right = st.columns(2)
    with left:
        bucket = st.selectbox('Business bucket', ['All'] + sorted(set(r['bucket'] for r in panel['rows'])), key=_key(data, 'eo-bucket'))
    with right:
        search = st.text_input('Find a company or symbol', key=_key(data, 'eo-search'))
    sort = st.radio('Sort companies', ['Largest increases', 'Largest decreases', 'Highest ownership', 'A–Z'],
                    horizontal=True, key=_key(data, 'eo-company-sort'))
    frame = pd.DataFrame(panel['rows'])
    if bucket != 'All':
        frame = frame[frame.bucket == bucket]
    if search:
        frame = frame[frame.company.str.contains(search, case=False, regex=False) | frame.symbol.str.contains(search, case=False, regex=False)]
    column, ascending = {'Largest increases': ('change_pp', False), 'Largest decreases': ('change_pp', True),
                         'Highest ownership': ('ownership_pct', False), 'A–Z': ('company', True)}[sort]
    frame = frame.sort_values(column, ascending=ascending, na_position='last')
    display = frame[['symbol', 'company', 'bucket', 'ownership_pct', 'prior_ownership_pct', 'change_pp', 'status', 'source_url']].rename(columns={
        'symbol':'Symbol', 'company':'Company', 'bucket':'Business bucket', 'ownership_pct':f'{label} ownership (%)',
        'prior_ownership_pct':f'Prior {label} (%)', 'change_pp':'Change (pp)',
        'status':'Comparison status', 'source_url':'Filing'})
    st.caption(f"Showing {len(display)} of {panel['universe']} tracked companies. Click a column heading to sort further. "
               'Changes are in percentage points. Capital-review rows may reflect changes in shares outstanding; '
               'verify them before interpreting ownership shifts as buying or selling.')
    st.dataframe(display, hide_index=True, use_container_width=True, height=470,
                 column_config={f'{label} ownership (%)':st.column_config.NumberColumn(format='%.2f'),
                                f'Prior {label} (%)':st.column_config.NumberColumn(format='%.2f'),
                                'Change (pp)':st.column_config.NumberColumn(format='%+.2f'),
                                'Filing':st.column_config.LinkColumn(display_text='Official filing')})
    st.download_button('Download filtered company table · CSV', display.to_csv(index=False),
                       file_name=SECTORS[data['sector']] + '_companies.csv', mime='text/csv', key=_key(data, 'eo-companies-download'))


def _sources(data):
    if data['sector'] == 'AI Catalysts':
        st.markdown(f'[Official Nifty AI Catalysts definition and constituents]({AI_PAGE})')
        st.markdown('This is a current thematic basket, not an NSDL sector. Ownership history follows current constituents; '
                    'no AI-specific cash-flow series or historical index membership is inferred.')
    st.markdown('**What each dataset can establish**')
    st.markdown('Sector chart currency options use the INR crore and US dollar million equity-flow columns published by NSDL; no exchange-rate conversion is inferred.')
    st.markdown('NSDL fortnightly equity flows test foreign sector-level persistence. Quarterly NSE filings test changes in FPI, DII, mutual fund and insurer ownership. '
                'These cover different periods and universes; company estimates do not reconcile to the fortnightly flows.')
    st.markdown('**Domestic ownership definition**')
    st.markdown('DII uses the public-shareholding InstitutionsDomestic aggregate in the exchange filing. '
                'It includes mutual funds/UTI, insurers, banks, pension/provident funds, AIFs and other reported domestic institutions. '
                'Domestic aggregate and its components are never added together. Government, promoter holdings and ordinary domestic '
                'corporate/retail holdings are excluded. This is an ownership proxy, not NSE’s trading-participant DII cash-flow measure. '
                'Absent categories remain unavailable; mutual funds include active and passive funds.')
    st.markdown('**Comparison rules**')
    st.markdown('FPI Category I and II aggregates are combined; named-investor detail is not counted again. '
                'Ownership percentages use reported institutional shares and the SCRR A+B+C2 denominator, excluding custodian/DR C1 shares. '
                'An increase exceeds 0.01 percentage point; changes within ±0.01 point are Flat. '
                'Total-share changes are flagged for review of splits, bonuses, issuance, buybacks or mergers. '
                'Stock rankings show reported percentage-point ownership changes, not actual cash purchases. '
                'Missing filings and absent categories remain unavailable.')
    st.markdown('**Coverage and timing**')
    st.write(data['universe_scope'])
    st.markdown('Membership is the source list available on the collection date, not historical membership at each quarter. '
                'This can introduce survivorship and classification bias. Quarterly ownership does not prove open-market buying, '
                'reveal intra-quarter trades or distinguish active from passive investment. Business buckets for the original three sectors are editorial labels; other sectors and AI Catalysts use the constituent list’s industry classification.')
    st.caption(f"Reference prices: {data['price_date']} · FPI cutoff: {(data.get('flows_as_of') or data['as_of']) if data['sector'] in EQUITY_SECTORS else 'not applicable'} · Ownership cutoff: {data.get('ownership_as_of') or data['as_of']} · Snapshot collected: {data['collected_at']}")
    for label, url in [('NSDL sector reports', 'https://pilot.fpi.nsdl.co.in/Reports/FPI_Fortnightly_Selection.aspx'),
                       ('NSE shareholding filings', 'https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern'),
                       ('NIFTY Total Market company list', 'https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv'),
                       ('NIFTY Microcap 250 company list', 'https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv')]:
        st.markdown(f'[{label}]({url})')
    if data['failures']:
        st.dataframe(pd.DataFrame(data['failures']), hide_index=True, use_container_width=True)
    st.download_button('Download full research snapshot · JSON', json.dumps(data, indent=2),
                       file_name=SECTORS[data['sector']] + '_research.json', mime='application/json', key=_key(data, 'eo-snapshot-download'))
    st.download_button('Download all ownership observations · CSV',
                       pd.DataFrame([dict(h, company=c['name']) for c in data['companies'] for h in c['holdings']]).to_csv(index=False),
                       file_name=SECTORS[data['sector']] + '_ownership.csv', mime='text/csv', key=_key(data, 'eo-ownership-download'))
    with st.expander('Source archive and checksums'):
        st.dataframe(pd.DataFrame(data['sources']), hide_index=True, use_container_width=True)
