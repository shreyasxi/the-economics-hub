"""INR research presentation. Remote downloads never occur during interaction."""
from html import escape
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from portfolio_lab.layout import centered_chart, centered_dataframe, centered_note, research_navigation
from portfolio_lab.labels import short_asset_label, asset_frame, asset_chart_frame
from config.portfolio_india_settings import TEMPLATES,EPISODES
from config.portfolio_settings import REBALANCING
from data.fetchers.portfolio_india import current,load
from data.processors.portfolio_currency import CONVENTION,decomposition,portfolio_fx_pnl
from data.processors.portfolio_analytics import compare,metrics,risk_contributions,simulate
from data.processors.portfolio_attribution import attribute
from data.processors.portfolio_sip import sip
from data.processors.portfolio_stress import diversification_windows,hypothetical_shock
from data.processors.portfolio_india_regimes import observations
from portfolio_lab.charts import (heading_html,legend_html,paths,format_inr,contribution_bars,allocation_risk,
    correlations,regime_distribution,regime_strip,stress_risk_change,research_lines,_style,PALETTE)




@st.cache_data(show_spinner=False,max_entries=2)
def prepared(path):return load(path)


def _apply(prefix,weights):
    st.session_state[prefix+'_model']=dict(weights);st.session_state[prefix+'_assets']=list(weights)
    for key,w in weights.items():st.session_state[prefix+'_'+key]=float(w*100)


def _template(prefix):_apply(prefix,TEMPLATES[st.session_state[prefix+'_template']])


def _normalise(prefix):
    assets=st.session_state[prefix+'_assets'];total=sum(st.session_state[prefix+'_'+k] for k in assets)
    if total>0:
        for key in assets:st.session_state[prefix+'_'+key]*=100/total


def builder(prefix,title,metadata):
    default='India with gold' if prefix=='in_b' else 'Indian fund allocation'
    if prefix+'_assets' not in st.session_state:_apply(prefix,st.session_state.get(prefix+'_model',TEMPLATES[default]))
    if prefix+'_template' not in st.session_state:st.session_state[prefix+'_template']=default
    templates={k:v for k,v in TEMPLATES.items() if set(v).issubset(metadata)}
    st.markdown('#### '+title)
    st.selectbox('Portfolio type',list(templates),key=prefix+'_template',on_change=_template,args=(prefix,))
    st.button('Normalize weights',key=prefix+'_normalise',on_click=_normalise,args=(prefix,),use_container_width=True)
    selected=st.multiselect('Holdings',list(metadata),key=prefix+'_assets',format_func=lambda k:metadata[k]['name']+' ('+k.replace('.NS','')+')')
    columns=st.columns(2);weights={}
    for i,key in enumerate(selected):
        widget=prefix+'_'+key
        if widget not in st.session_state:st.session_state[widget]=0.
        weights[key]=columns[i%2].number_input(short_asset_label(key)+' weight (%)',min_value=0.,max_value=100.,key=widget,step=1.)/100
    st.caption('Total allocation: {:.2f}%'.format(sum(weights.values())*100))
    st.session_state[prefix+'_model']=dict(weights)
    return weights


def heading(title,subtitle):st.markdown(heading_html(title,subtitle),unsafe_allow_html=True)
def plot(chart):
    centered_chart(chart)


def holdings_key(frame):
    return frame.rename(index=lambda k:str(k).removesuffix('.NS'),columns=lambda k:str(k).removesuffix('.NS'))


def correlation_chart(matrix):
    centered_chart(correlations(holdings_key(matrix)),width=720,stretch=False)
    centered_note('Holdings: '+' · '.join(short_asset_label(k) for k in matrix.columns))


def display_table(display):
    headers=''.join('<th>'+escape(n)+'</th>' for n in display.columns)
    body=''.join('<tr><th>'+escape('Sortino ratio' if row=='Sortino ratio (0% target)' else row)+'</th>'+''.join('<td>'+escape(str(display.loc[row,n]))+'</td>' for n in display.columns)+'</tr>' for row in display.index)
    st.markdown('<table class="pl-summary"><thead><tr><th>Metric</th>'+headers+'</tr></thead><tbody>'+body+'</tbody></table>',unsafe_allow_html=True)


def summary(results):
    frame=pd.DataFrame({n:metrics(r,52,'₹') for n,r in results.items()})
    rows=['Cumulative return','CAGR','Annualised volatility','Maximum drawdown','Sortino ratio (0% target)','Final wealth (₹)']
    display=frame.loc[rows].astype(object)
    for row in rows:
        for name in frame:
            v=frame.loc[row,name];display.loc[row,name]='—' if pd.isna(v) else format_inr(v) if 'wealth' in row else '{:.2f}'.format(v) if 'ratio' in row.lower() else '{:.2%}'.format(v)
    display_table(display)


def currency_chart(parts):
    rows=asset_frame(parts).rename_axis('Instrument').reset_index().melt('Instrument',var_name='Component',value_name='Return');rows['Return']*=100
    rows['Row']=rows.Instrument+'\n'+rows.Component
    base=alt.Chart(alt.Data(values=rows.to_dict('records'))).encode(y=alt.Y('Row:N',title=None,sort=None,scale=alt.Scale(paddingInner=.55,paddingOuter=.25),axis=alt.Axis(labelLimit=230)),
        x=alt.X('Return:Q',title='Cumulative return / component (pp)',scale=alt.Scale(zero=True,padding=25)),
        color=alt.Color('Component:N',scale=alt.Scale(domain=['Foreign asset','Currency','Interaction','Total INR'],range=['#245A94','#0B8F82','#9B1C31','#1A1A1A']),legend=None),
        tooltip=['Instrument:N','Component:N',alt.Tooltip('Return:Q',format='+.2f')])
    zero=alt.Chart(alt.Data(values=[{'Zero':0}])).mark_rule(color='#87919C').encode(x='Zero:Q')
    positive=base.transform_filter('datum.Return>=0').mark_text(align='left',dx=7,font='Inter',fontSize=13,fontWeight=600).encode(text=alt.Text('Return:Q',format='+.2f'),color=alt.value('#1A1A1A'))
    negative=base.transform_filter('datum.Return<0').mark_text(align='right',dx=-7,font='Inter',fontSize=13,fontWeight=600).encode(text=alt.Text('Return:Q',format='+.2f'),color=alt.value('#1A1A1A'))
    return _style((zero+base.mark_bar(size=18)+positive+negative).properties(height=max(240,len(rows)*64)),inline=True)


def sip_chart(analyses):
    rows=[]
    for name,result in analyses.items():
        for date,v in result['wealth'].items():rows.append(dict(Date=date.isoformat(),Value=float(v),Series=name))
    first=next(iter(analyses.values()))
    for date,v in first['invested'].items():rows.append(dict(Date=date.isoformat(),Value=float(v),Series='Invested capital'))
    names=list(analyses)+['Invested capital']
    chart=alt.Chart(alt.Data(values=rows)).mark_line(strokeWidth=2.7).encode(x=alt.X('Date:T',title=None,axis=alt.Axis(format='%Y',grid=False,tickCount=5)),
        y=alt.Y('Value:Q',title='INR · capital and market value',scale=alt.Scale(zero=True),axis=alt.Axis(tickCount=5,labelExpr="'₹'+format(datum.value/100000,'.1f')+' lakh'",gridColor='#AAB2BC',gridOpacity=1)),
        color=alt.Color('Series:N',scale=alt.Scale(domain=names,range=[PALETTE[n] for n in analyses]+['#1A1A1A']),legend=alt.Legend(columns=1,direction='vertical'),title=None),
        strokeDash=alt.StrokeDash('Series:N',scale=alt.Scale(domain=names,range=[[1,0] for n in analyses]+[[5,3]]),legend=None),
        tooltip=[alt.Tooltip('Date:T',format='%d %b %Y'),'Series:N',alt.Tooltip('Value:Q',format=',.2f',title='INR')])
    values=chart.transform_filter('datum.Series != "Invested capital"').mark_line(strokeWidth=2.7)
    capital=chart.transform_filter('datum.Series == "Invested capital"').mark_line(strokeWidth=2,interpolate='step-after')
    return _style((values+capital).properties(height=430))


def stress(prices,a,b,benchmark,rebalance,cost,enabled,local,fx,metadata):
    episode=st.selectbox('Historical episode',list(EPISODES),key='in_episode')
    start,end=EPISODES[episode];st.caption(start+' – '+end+' · specified episode window; not optimised peaks/troughs. Weekly reference sampling may miss daily extremes.')
    with st.expander('Instrument availability for this episode'):
        eligible=prices.loc[start:end]
        st.dataframe(pd.DataFrame([{'Instrument':short_asset_label(k),'First source observation':metadata[k]['first'],
            'First reference valuation':str(prices[k].first_valid_index().date()),
            'Complete episode':bool(len(eligible)>1 and eligible[k].notna().all())} for k in dict.fromkeys(list(a)+list(b)+[benchmark])]),hide_index=True,use_container_width=True)
    try:
        study=diversification_windows(prices,a,b,benchmark,episode,rebalance,cost,surrounding=52,episode_windows=EPISODES,initial=100000,periods_per_year=52,currency_symbol='₹')
    except ValueError as exc:st.warning(str(exc));return
    results={n:r for n,r in study['results'].items() if enabled or n!='Portfolio B'}
    heading('Diversification Under Stress',episode+' · losses and the changing sources of risk')
    with st.container(horizontal=True,horizontal_alignment='center'):
        with st.container(width=900):
            chosen=st.selectbox('Portfolio for risk comparison',[n for n in results if n!='Benchmark'],key='in_stress_risk') if enabled else 'Portfolio A'
            st.markdown(legend_html(results,is_drawdown=True,currency='INR'),unsafe_allow_html=True)
            before=study['estimates'].get('Pre-stress',{}).get(chosen)
            during=study['estimates'].get('During stress (ex-post)',{}).get(chosen)
            left,right=st.columns(2,gap='large')
            with left:
                st.markdown('**Losses through the episode**')
                plot(paths(results,is_drawdown=True,height=320,currency='INR'))
                st.caption('Drawdown from the running wealth peak, measured at weekly reference valuations.')
            with right:
                st.markdown('**'+chosen+' · risk before and during**')
                if before and during:
                    plot(stress_risk_change({'table':asset_chart_frame(before['table'])},{'table':asset_chart_frame(during['table'])},chosen,height=320))
                    st.caption('Diamonds: before · circles and values: during (% of variance). Target allocations are held constant.')
                else:
                    st.info('Covariance comparison unavailable: '+str(study['unavailable']))
            with st.expander('Stress comparison · sample dates and interpretation'):
                st.caption('Target weights fixed for covariance snapshots; actual replay holdings drift. 52 surrounding weekly returns required; small crisis samples are noisy. Ex-post association, not causation.')
                if before and during:
                    st.caption('Before {}–{} · {} returns. During {}–{} · {} returns.'.format(before['start'].date(),before['end'].date(),before['observations'],during['start'].date(),during['end'].date(),during['observations']))
    heading('Stress-Period Return Contributions','Reconciled INR P&L / initial ₹1,00,000 · costs separate')
    parts=pd.DataFrame({n:v['contributions'] for n,v in study['attribution'].items() if n in results and n!='Benchmark'}).fillna(0)
    plot(contribution_bars(asset_chart_frame(parts)));summary(results)
    if any(metadata[k]['currency']=='USD' for k in set(a)|set(b)):
        currency_parts=pd.DataFrame({n:portfolio_fx_pnl(prices,local,fx,r,metadata) for n,r in results.items() if n!='Benchmark'})
        with st.expander('How much of the episode return came from FX?'):
            st.dataframe(asset_frame(currency_parts*100));st.caption('Exact entering INR holdings × foreign return / FX return / interaction, accumulated as P&L divided by starting wealth. These components reconcile to the net episode return.')
    with st.expander('Exact episode attribution and covariance evidence'):
        st.dataframe(asset_frame(parts*100),use_container_width=True);st.json(study['unavailable'])


def render(on_ready=None):
    try:prices,local,fx,manifest=prepared(str(current()))
    except (ValueError,OSError,AssertionError) as exc:
        st.warning('INR data unavailable: '+str(exc));return
    if on_ready:
        on_ready(str(prices.index[-1].date()))
    if (pd.Timestamp.now(tz='Asia/Kolkata').tz_localize(None).normalize()-prices.index[-1]).days>14:
        st.warning('Prepared weekly reference data are more than two weeks old. Refresh explicitly before drawing current conclusions.')
    for key in list(st.session_state):
        if key.startswith(('in_a_','in_b_')) and not key.endswith('_normalise'):st.session_state[key]=st.session_state[key]
    st.markdown('<h3 class="pl-builder-title">Portfolio Builder</h3>',unsafe_allow_html=True)
    enabled=st.checkbox('Compare Portfolio B',key='in_compare')
    if enabled:
        left,right=st.columns(2)
        with left:a=builder('in_a','Portfolio A',manifest['assets'])
        with right:b=builder('in_b','Portfolio B',manifest['assets'])
    else:a=builder('in_a','Portfolio A',manifest['assets']);b=a.copy()
    a={k:w for k,w in a.items() if w>0};b={k:w for k,w in b.items() if w>0}
    period=st.date_input('Analysis period',value=(max(prices.index[0],pd.Timestamp('2021-10-01')).date(),prices.index[-1].date()),
        min_value=prices.index[0].date(),max_value=prices.index[-1].date(),key='in_period')
    c1,c2,c3=st.columns(3)
    rebalance=c1.selectbox('Rebalancing',list(REBALANCING),index=1,key='in_rebalance')
    benchmark=c2.selectbox('Benchmark',['nifty-50','NIFTYBEES.NS'],format_func=short_asset_label,key='in_benchmark')
    cost=c3.number_input('Trading cost (bps of buys + sells)',min_value=0.,max_value=100.,value=5.,key='in_cost')
    investment=st.radio('Investment analysis',['Lump sum','Monthly SIP'],horizontal=True,key='in_investment')
    initial_lump=st.number_input('Initial lump-sum investment (₹)',min_value=1.,value=100000.,step=10000.,key='in_lump_initial') if investment=='Lump sum' else 100000.
    if len(period)!=2 or period[0]>=period[1]:st.info('Select a valid analysis interval');return
    try:common,results=compare(prices,a,b,benchmark,str(period[0]),str(period[1]),rebalance,cost,initial=initial_lump)
    except ValueError as exc:st.error(str(exc));return
    if not enabled:results.pop('Portfolio B')
    sources=[]
    if any(manifest['assets'][k]['kind']=='Index benchmark' for k in common):sources.append('NSE Indices gross TRI')
    if any(manifest['assets'][k]['kind']!='Index benchmark' for k in common):sources.append('Yahoo adjusted ETF prices')
    if any(manifest['assets'][k]['currency']=='USD' for k in common):sources.append('Federal Reserve H.10 USD/INR')
    source_note='Sources: '+ ' · '.join(sources)+' · prepared '+manifest['retrieved_utc'][:10]
    if investment=='Monthly SIP':
        sip_period=st.date_input('SIP contribution period',value=period,min_value=period[0],max_value=period[1],key='in_sip_period')
        if len(sip_period)!=2 or sip_period[0]>sip_period[1]:st.info('Select a valid SIP contribution interval');return
        c1,c2,c3=st.columns(3)
        initial=c1.number_input('Initial SIP investment (₹)',min_value=0.,value=0.,step=1000.,key='in_sip_initial')
        amount=c2.number_input('Monthly contribution (₹)',min_value=1.,value=10000.,step=1000.,key='in_sip_amount')
        day=c3.number_input('Requested day of month',min_value=1,max_value=28,value=1,key='in_sip_day')
        analyses={}
        try:
            for name,w in [('Portfolio A',a)]+([('Portfolio B',b)] if enabled else []):
                analyses[name]=sip(common,w,sip_period[0],sip_period[1],amount,initial,day,rebalance,cost,valuation_end=period[1])
        except ValueError as exc:st.info(str(exc));return
        heading('SIP | Invested Capital and Portfolio Value','Same contribution dates and amounts · capital is not investment profit')
        plot(sip_chart(analyses))
        centered_note(source_note)
        rows=[]
        for name,s in analyses.items():
            rows.append({'Portfolio':name,'Invested':format_inr(s['invested'].iloc[-1]),'Market value':format_inr(s['wealth'].iloc[-1]),
                'Gain/loss':format_inr(s['gain'].iloc[-1]),'XIRR (money weighted)':'Unavailable' if s['xirr']['value'] is None else '{:.2%}'.format(s['xirr']['value']),
                'Flow-adjusted TWR':'{:.2%}'.format(s['twr'].iloc[-1]-1)})
            st.caption(name+': '+s['xirr']['status'])
        display_table(pd.DataFrame(rows).set_index('Portfolio').T)
        st.caption(next(iter(analyses.values()))['convention'])
        with st.expander('Cash-flow and unit ledger'):
            for name,s in analyses.items():st.markdown('**'+name+'**');st.dataframe(s['flows']);st.dataframe(s['units']);st.dataframe(s['investor_flows'])
        st.caption('The research views below use the common lump-sum portfolio to isolate allocation performance. SIP XIRR is not directly equivalent to lump-sum CAGR.')
    heading('Growth of '+format_inr(initial_lump),'')
    with st.container(horizontal=True,horizontal_alignment='center'):
        with st.container(width=900,key='in-wealth-tools'):
            subtitle,control=st.columns([2.4,1.3],gap='small',vertical_alignment='center')
            with subtitle:
                st.caption('{} – {} · same starting wealth and observation window'.format(common.index[0].date(),common.index[-1].date()))
            with control:
                scale=st.radio('Wealth scale',['Linear','Logarithmic'],horizontal=True,key='in_scale',label_visibility='collapsed')
    st.markdown(legend_html(results,currency='INR'),unsafe_allow_html=True)
    plot(paths(results,log=scale=='Logarithmic',currency='INR',wealth_baseline=True))
    centered_note(source_note)
    summary(results)
    legacy={'Attribution & currency':'Performance Attribution','Risk & factors':'Risk','Indian macro regimes':'Macro Regimes','Stress testing':'Stress Testing'}
    if st.session_state.get('in_view') in legacy:
        st.session_state['in_view']=legacy[st.session_state['in_view']]
    view=research_navigation('in_view')
    if view=='Overview':
        heading('Portfolio Drawdown','Drawdown from the running wealth peak · selected period only')
        st.markdown(legend_html(results,is_drawdown=True,currency='INR'),unsafe_allow_html=True)
        plot(paths(results,is_drawdown=True,height=300,currency='INR'))
        with st.expander('Holdings drift and rebalance trades'):
            selected=st.selectbox('Portfolio detail',list(results),key='in_details')
            st.dataframe(asset_frame((results[selected].weights*100).round(2)),use_container_width=True)
            st.dataframe(results[selected].trades,use_container_width=True)
    elif view=='Performance Attribution':
        heading('Return Contribution by Holding','Actual entering holdings × evaluated INR returns; compounding and costs reconcile')
        parts=pd.DataFrame({n:attribute(common,r)['contributions'] for n,r in results.items() if n!='Benchmark'}).fillna(0)
        plot(contribution_bars(asset_chart_frame(parts)))
        with st.expander('Exact performance reconciliation'):st.dataframe(asset_frame(parts*100))
        foreign=[k for k in common if manifest['assets'][k]['currency']=='USD']
        if foreign:
            heading('International Return and Currency Components','Standalone compounded components, not weighted portfolio contributions')
            parts=decomposition(local.loc[common.index,foreign],fx.loc[common.index]);plot(currency_chart(parts))
            st.caption('Total INR = foreign asset + currency + interaction. A rise in INR per USD means rupee depreciation. No second conversion of domestic INR prices.')
            portfolio_parts=pd.DataFrame({n:portfolio_fx_pnl(common,local,fx,r,manifest['assets']) for n,r in results.items() if n!='Benchmark'})
            with st.expander('Exact standalone and portfolio currency reconciliation'):
                st.dataframe(asset_frame(parts*100));st.dataframe(portfolio_parts*100)
                st.caption('Portfolio components use actual entering INR holdings; their P&L sums reconcile to net portfolio return, including trading costs. Standalone endpoint components above are not weighted portfolio attribution.')
    elif view=='Risk':
        chosen=st.selectbox('Risk allocation',[n for n in results if n!='Benchmark'],key='in_risk')
        weights=a if chosen=='Portfolio A' else b;window=st.selectbox('Covariance window (weekly returns)',[52,156],key='in_cov')
        try:
            risk=risk_contributions(common,weights,window,52)
            heading('Portfolio Risk Contributions','Signed variance contributions; black diamonds show capital allocation')
            plot(allocation_risk(asset_chart_frame(risk['table']),chosen));st.caption('{} weekly returns: {} – {}. Risk contributions sum to {:.2%}; annualised evaluated volatility {:.2%}.'.format(risk['observations'],risk['start'].date(),risk['end'].date(),risk['table']['Risk contribution'].sum(),np.sqrt(risk['variance'])))
            heading('Holding Correlations','Historical return correlations · −1: opposite · 0: unrelated · +1: together')
            correlation_chart(risk['correlation'])
            heading('Risk Window Sensitivity','Share of portfolio variance (%) across available lookback windows')
            sensitivity={str(n)+' weekly returns':risk_contributions(common,weights,n,52)['table']['Risk contribution']*100 for n in [52,156] if len(common)-1>=n}
            centered_dataframe(asset_frame(pd.DataFrame(sensitivity)).round(2))
        except ValueError as exc:st.info(str(exc))
        heading('Rolling Equity–Bond Correlation','26 weekly returns · Indian Equities (NIFTYBEES) and Bonds (GILT5YBEES)')
        pair=['NIFTYBEES.NS','GILT5YBEES.NS']
        if set(pair).issubset(prices.columns):
            returns=prices[pair].loc[common.index[0]:common.index[-1]].pct_change(fill_method=None)
            corr=returns[pair[0]].rolling(26,min_periods=26).corr(returns[pair[1]])
            if corr.notna().any():
                plot(research_lines(corr.rename('Equities / Bonds').to_frame(),'Correlation'))
            else:
                st.info('Rolling correlation requires 26 common weekly returns.')
        else:
            st.info('The domestic equity and bond reference histories are unavailable.')
    elif view=='Macro Regimes':
        dimension=st.selectbox('Regime dimension',['RBI policy','Inflation','Currency'],key='in_regime')
        st.info('Descriptive ex-post classifications, revised sources; not real-time signals or causal effects. RBI labels use net month-end effective repo changes; CPI uses changes in officially published YoY within each base, never cross-base index levels.')
        obs=observations(results,fx,dimension)
        if obs.empty:st.info('No comparable complete monthly intervals');return
        counts=obs.groupby('Regime').size();runs=obs.Regime.ne(obs.Regime.shift()).cumsum()
        run_counts=obs.groupby('Regime').apply(lambda g:runs.loc[g.index].nunique())
        valid=counts[(counts>=6)&(run_counts>=3)].index
        heading('Portfolio Returns by Economic Regime','Thin interval: 10th–90th percentile · thick: 25th–75th · dot and label: median · n: observed months')
        if len(valid):plot(regime_distribution(obs.loc[obs.Regime.isin(valid)],list(results)))
        with st.container(key='in-regime-timeline'):
            plot(regime_strip(obs))
        st.caption('Six observations are a low descriptive threshold; serial dependence and few policy-change months limit inference. No pooled annualisation. Omitted months remain gaps in the timeline.')
        st.caption('Observed months: {} – {}. A plotted state requires at least three distinct contiguous runs; gaps count as missing observations, not extra evidence.'.format(obs.index[0],obs.index[-1]))
        with st.expander('Sample dates and exact monthly observations'):st.dataframe(obs);st.dataframe(pd.DataFrame({'Months':counts,'Contiguous runs':run_counts}))
    else:
        mode=st.selectbox('Stress analysis',['Historical replay','Direct asset and FX shocks'],key='in_stress_mode')
        if mode=='Historical replay':stress(prices,a,b,benchmark,rebalance,cost,enabled,local,fx,manifest['assets'])
        else:
            st.caption('Simultaneous assumed local asset shocks; foreign holdings receive multiplicative FX conversion. No probabilities, dynamics or tax assumptions.')
            currency=st.number_input('USD/INR shock (%)',min_value=-100.,max_value=100.,value=10.,key='in_fx_shock')/100;shocks={}
            for key in dict.fromkeys(list(a)+list(b)):
                local_shock=st.number_input(short_asset_label(key)+' local shock (%)',min_value=-100.,max_value=1000.,value=-20.,key='in_shock_'+key)/100
                shocks[key]=(1+local_shock)*(1+currency)-1 if manifest['assets'][key]['currency']=='USD' else local_shock
            contributions={}
            for name,w in [('Portfolio A',a)]+([('Portfolio B',b)] if enabled else []):
                impact,parts=hypothetical_shock(w,shocks)
                st.markdown('**'+name+': {:.2%} · '.format(impact)+format_inr(100000*impact)+' on ₹1,00,000**')
                contributions[name]=parts
            heading('Hypothetical Shock Contributions','Immediate target-weight impact · includes FX conversion for foreign holdings')
            plot(contribution_bars(asset_chart_frame(pd.DataFrame(contributions).fillna(0))))
            with st.expander('Exact shock contributions (pp)'):
                st.dataframe(asset_frame(pd.DataFrame(contributions).fillna(0)*100).round(2),use_container_width=True)
    with st.expander('Methodology, sources and instrument identities'):
        st.write(CONVENTION)
        st.write('Lump-sum reference paths charge rebalances; initial entry and terminal liquidation excluded. SIP additionally charges subscription purchases. Fund expenses already enter observed prices. Overseas holdings are hypothetical exposures; resident eligibility, remittance and tax rules are not assumed.')
        st.write('Sortino uses a zero minimum acceptable return and 52 evaluated weekly periods per year. It requires at least 26 returns and 182 calendar days; no downside variation gives an undefined ratio.')
        st.write('Volatility uses √52 evaluated weekly intervals; weekly drawdown does not measure daily extremes. Rebalance occurs at the final evaluated mark before a new period. Domestic ETFs use adjusted market prices, not growth NAVs. Foreign ETFs and benchmark/fund mixtures are reference research portfolios, not a verified executable strategy. FX marks may be several days old after weekly release; they do not establish same-time exchange conversion or real-time tradability. Non-synchronous marks can attenuate or shift correlations, risk shares; weekly sampling does not remove that limitation. Monthly research uses complete intervals between final eligible weekly marks, not official daily month-end return indices. EFA/EEM USD fund returns already include their underlying currencies; the added currency component is only USD/INR.')
        st.dataframe(pd.DataFrame(manifest['assets']).T,use_container_width=True)
        st.caption('Data prepared UTC '+manifest['retrieved_utc']+'; private immutable histories and alignment evidence are excluded from Git. NSE/Yahoo/AMFI permissions remain a public-release gate. Corporate-debt benchmarks and Direct/Growth NAV imports require separately verified source permission and continuity.')
