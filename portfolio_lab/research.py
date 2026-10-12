"""Research views consume the same simulations and immutable prepared inputs."""
import numpy as np
import pandas as pd
import streamlit as st
from portfolio_lab.layout import centered_chart, centered_dataframe, centered_note
from portfolio_lab.labels import short_asset_label, asset_frame, asset_chart_frame
from config.portfolio_settings import ASSETS
from data.fetchers import portfolio_macro
from data.processors.portfolio_analytics import simulate, metrics, risk_contributions
from data.processors.portfolio_attribution import attribute
from data.processors.portfolio_regimes import classify, conditional, DISCLOSURE, RULES
from data.processors.portfolio_stress import diversification_windows
from portfolio_lab.charts import contribution_bars, allocation_risk, correlations, research_lines, regime_distribution, regime_strip, stress_risk_change, paths, heading_html, legend_html

@st.cache_data(show_spinner=False,max_entries=3)
def _macro(bundle):
    return portfolio_macro.load(bundle)


def macro_data():
    try:
        data, manifest=_macro(str(portfolio_macro.current()))
        st.caption('FRED prepared '+manifest['retrieved_utc'][:10]+' · Latest revised observations, not release vintages.')
        for sid, meta in manifest['series'].items():
            age=(pd.Timestamp.now().normalize()-pd.Timestamp(meta['latest'])).days
            if age>meta['max_age_days']:
                st.warning('{} history is stale: latest {}.'.format(sid,meta['latest']))
        return data, manifest
    except (OSError,ValueError,KeyError) as exc:
        st.info('Macro research unavailable: '+str(exc)+'. Prepare offline with python -m data.fetchers.portfolio_macro.')
        return None,None


def attribution_view(common, results, rebalance, cost):
    st.markdown(heading_html('Return Contribution by Holding','Holdings sorted by contribution magnitude · gains right, detractors left'),unsafe_allow_html=True)
    classes={t:m['asset_class'] for t,m in ASSETS.items()}
    analyses={n:attribute(common,r,classes) for n,r in results.items()}
    parts=pd.DataFrame({n:a['contributions'] for n,a in analyses.items()}).fillna(0)
    centered_chart(contribution_bars(asset_chart_frame(parts.drop(columns="Benchmark",errors="ignore"))))
    st.caption('Exact accounting: sum of daily dollar P&L / initial $10,000. The bars include compounding through actual entering holdings; trading costs are separate. These are percentage-point contributions, not standalone asset returns.')
    with st.expander('Attribution reconciliation · exact percentage points'):
        st.dataframe(asset_frame((parts*100).round(3)),use_container_width=True)
    for n,a in analyses.items():
        st.caption('{}: contributions sum to {:.2%}; net cumulative return {:.2%}; costs ${:,.2f}; summed two-way turnover {:.2%}.'.format(n,a['contributions'].sum(),a['cumulative_return'],a['cost'],a['turnover']))
    if 'Portfolio B' in analyses:
        st.markdown('**A minus B: {:.2f} percentage points**'.format(100*(analyses['Portfolio A']['cumulative_return']-analyses['Portfolio B']['cumulative_return'])))
    st.caption('Portfolio minus benchmark: '+ ' · '.join('{} {:+.2f} pp'.format(n,100*(a['cumulative_return']-analyses['Benchmark']['cumulative_return'])) for n,a in analyses.items() if n!='Benchmark'))
    with st.expander('Asset classes, asset returns, drift and trading detail'):
        st.dataframe(pd.DataFrame({n:a['classes']*100 for n,a in analyses.items()}).fillna(0).round(2),use_container_width=True)
        for n,r in results.items():
            a=analyses[n]; st.markdown('**'+n+'**')
            st.dataframe(asset_frame(pd.DataFrame({'Standalone asset return (%)':a['asset_returns']*100,'Start weight (%)':r.weights.iloc[0]*100,'Final weight (%)':r.weights.iloc[-1]*100,'Weight drift (pp)':a['drift']*100}).round(2)),use_container_width=True)
            st.dataframe(r.trades,use_container_width=True)
    if rebalance!='Buy and hold':
        st.markdown('#### Rebalanced versus buy-and-hold counterfactual')
        rows=[]
        for n,r in results.items():
            if n=='Benchmark':continue
            bh=simulate(common,r.weights.iloc[0].to_dict())
            rows.append({'Portfolio':n,'Rebalanced net return (%)':100*metrics(r)['Cumulative return'],'Buy-and-hold return (%)':100*metrics(bh)['Cumulative return'],'Difference (pp)':100*(metrics(r)['Cumulative return']-metrics(bh)['Cumulative return'])})
        st.dataframe(pd.DataFrame(rows),use_container_width=True)
        st.caption('Same initial holdings and market path; chosen costs only on rebalancing. A transparent counterfactual, not formal attribution of every allocation decision.')


def risk_view(common, results, a, b, prices):
    selected=st.selectbox('Risk allocation',[n for n in results if n!='Benchmark'],key='pl_risk')
    weights=a if selected=='Portfolio A' else b
    window=st.selectbox('Covariance window (daily returns)',[252,756],key='pl_cov_window')
    try:
        estimate=risk_contributions(common,weights,window)
        if not estimate['complete_window']:
            st.info('Requested {} returns; only {} available. This is a shorter estimate.'.format(window,estimate['observations']))
        st.caption('Target-weight snapshot · {} returns, {} to {}. {}'.format(estimate['observations'],estimate['start'].date(),estimate['end'].date(),estimate['diagnostic']))
        if estimate['condition']>1e8:st.warning(estimate['diagnostic'])
        if estimate['variance']<=1e-14:st.info('Near-zero variance; percentage contributions undefined.')
        else:
            st.markdown(heading_html('Portfolio Risk Contributions','Bars: variance contribution · black diamonds: capital allocation'),unsafe_allow_html=True)
            centered_chart(allocation_risk(asset_chart_frame(estimate['table']),selected))
            st.caption('Risk contributions sum to {:.2f}%. Annualised historical volatility {:.2%}; capital HHI {:.3f} (effective capital holdings {:.2f}). Negative risk contributions remain visible.'.format(estimate['table']['Risk contribution'].sum()*100,np.sqrt(estimate['variance']),estimate['capital_concentration'],1/estimate['capital_concentration']))
        st.markdown(heading_html('Holding Correlations','Historical return correlations · −1: opposite · 0: unrelated · +1: together'),unsafe_allow_html=True)
        centered_chart(correlations(estimate['correlation']),width=720,stretch=False)
        centered_note('Holdings: ' + ' · '.join(short_asset_label(t) for t in estimate['correlation'].columns))
        st.markdown(heading_html('Risk Window Sensitivity','Share of portfolio variance (%) across available lookback windows'),unsafe_allow_html=True)
        tables={}
        for w in [252,756]:
            if len(common)-1>=w:tables[str(w)+' daily returns']=risk_contributions(common,weights,w)['table']['Risk contribution']*100
        centered_dataframe(asset_frame(pd.DataFrame(tables).round(2)))
        st.caption('Five observations per holding minimum; empirical covariance without regularisation. Longer windows are not necessarily better. Highly correlated holdings can still make estimates unstable.')
    except ValueError as exc:st.info(str(exc))
    st.markdown('#### Rolling equity–bond correlation')
    if {'SPY','AGG'}.issubset(prices.columns):
        returns=prices[['SPY','AGG']].loc[common.index[0]:common.index[-1]].pct_change(fill_method=None)
        corr=returns.SPY.rolling(126,min_periods=126).corr(returns.AGG)
        if corr.notna().any():
            centered_chart(research_lines(corr.rename('US Equities (SPY) / Bonds (AGG) · 126 daily returns').to_frame(),'Correlation'))
        else:st.info('Rolling correlation requires 126 common daily returns.')
    else:st.caption('Select US Equities (SPY) and Bonds (AGG) in the comparison to inspect their 126-return rolling correlation.')


def regimes_view(results):
    st.markdown('#### Portfolio returns across economic regimes')
    st.info(DISCLOSURE)
    macro,manifest=macro_data()
    if macro is None:return
    dimension=st.selectbox('Regime dimension',list(RULES),key='pl_regime')
    result=conditional(results,classify(macro),dimension)
    st.caption(result['rule'])
    if result['observations'].empty:
        st.info('No complete matched monthly intervals for this regime and lookback.')
        return
    st.caption('Non-overlapping complete monthly returns. Same observation-month classification for every portfolio. {} missing classifications omitted. Minimum 24 months and three distinct contiguous runs per state; no annualisation of pooled states. Runs are not independent experiments.'.format(result['omitted_months']))
    display=result['summary'].copy()
    for column in ['Mean monthly return','Median monthly return','Monthly volatility','Negative months','10th percentile']:
        display[column+' (%)']=display.pop(column)*100
    with st.expander('Regime statistics and evidence thresholds'):
        st.dataframe(display.round(2),hide_index=True,use_container_width=True)
    sufficient=result['summary'].loc[result['summary'].Status=='Descriptive evidence','Regime'].unique()
    observations=result['observations']
    st.markdown(heading_html('Portfolio Returns by Economic Regime','Thin interval: 10th–90th percentile · thick: 25th–75th · dot and label: median · n: observed months'),unsafe_allow_html=True)
    if len(sufficient):centered_chart(regime_distribution(observations.loc[observations.Regime.isin(sufficient)],list(results)))
    if not observations.empty:
        with st.container(key='pl-regime-timeline'):
            centered_chart(regime_strip(observations))
    st.caption('CPI change horizon is fixed at three months; growth uses the published three-month index and its established zero trend threshold. Rules are not selected using portfolio performance. Monthly standard deviations and downside frequencies are descriptive; serial dependence and revisions limit inference.')
    with st.expander('Source coverage, revisions and gaps'):
        st.json(manifest)


def diversification_view(prices,a,b,benchmark,episode,rebalance,cost,enable_b):
    study=diversification_windows(prices,a,b,benchmark,episode,rebalance,cost)
    replay={n:r for n,r in study['results'].items() if enable_b or n!='Portfolio B'}
    st.markdown(heading_html('Diversification Under Stress',episode+' · losses and the changing sources of risk'),unsafe_allow_html=True)
    with st.container(horizontal=True, horizontal_alignment="center"):
        with st.container(width=900):
            if enable_b:
                chosen=st.selectbox('Portfolio for risk comparison',['Portfolio A','Portfolio B'],key='pl_stress_risk')
            else:
                chosen='Portfolio A'
            st.markdown(legend_html(replay,is_drawdown=True),unsafe_allow_html=True)
            left,right=st.columns(2,gap="large")
            before=study['estimates'].get('Pre-stress',{}).get(chosen)
            during=study['estimates'].get('During stress (ex-post)',{}).get(chosen)
            with left:
                st.markdown('**Losses through the episode**')
                centered_chart(paths(replay,is_drawdown=True,height=320))
                st.caption('Drawdown from the episode’s running wealth peak. Each portfolio starts at its target allocation.')
            with right:
                st.markdown('**'+chosen+' · risk before and during**')
                if before is not None and during is not None:
                    centered_chart(stress_risk_change({**before, 'table': asset_chart_frame(before['table'])},{**during, 'table': asset_chart_frame(during['table'])},chosen,height=320))
                    st.caption('Diamonds: before · circles and values: during (% of variance). Target allocations are held constant for this comparison.')
                else:
                    st.info('Risk comparison unavailable: '+study['unavailable'].get('Pre-stress','Insufficient covariance evidence.'))
            with st.expander('Stress comparison · sample dates and interpretation'):
                st.write(study['caveat'])
                st.caption('Pre/post: 252 evaluation returns; during: the episode. Historical associations do not establish causation.')
                if before is not None and during is not None:
                    st.caption('Before: {}–{} · {} returns. During: {}–{} · {} returns.'.format(before['start'].date(),before['end'].date(),before['observations'],during['start'].date(),during['end'].date(),during['observations']))
                    if during['observations']<126:
                        st.caption('Short stress sample: covariance estimates can be noisy. Negative risk contributions remain visible.')
    parts=pd.DataFrame({n:x['contributions'] for n,x in study['attribution'].items() if n in replay and n!='Benchmark'}).fillna(0)
    st.markdown(heading_html('Stress-Period Return Contributions','Exact episode dollar P&L / starting wealth · costs separate'),unsafe_allow_html=True)
    centered_chart(contribution_bars(asset_chart_frame(parts)))
    with st.expander('Correlation changes, risk tables and sample dates'):
        tables={label:v[chosen]['table']['Risk contribution']*100 for label,v in study['estimates'].items()}
        centered_dataframe(asset_frame(pd.DataFrame(tables).round(2)))
        for label,reason in study['unavailable'].items():st.caption(label+' unavailable: '+reason)
        if study['estimates']:
            selected=st.selectbox('Correlation estimation period',list(study['estimates']),key='pl_stress_window')
            est=study['estimates'][selected][chosen]
            st.caption('{} returns · {} to {} · volatility {:.2%}. {}'.format(est['observations'],est['start'].date(),est['end'].date(),np.sqrt(est['variance']),est['diagnostic']))
            centered_chart(correlations(est['correlation']))
            st.caption('Holdings: ' + ' · '.join(short_asset_label(t) for t in est['correlation'].columns))
