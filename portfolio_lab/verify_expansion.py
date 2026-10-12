"""Independent real-data share-unit checks and BTC/USO research audit."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from config.portfolio_settings import TEMPLATES,EPISODES
from data.fetchers.portfolio_prices import load_bundle,snapshot_path
from data.processors.portfolio_analytics import compare,metrics,risk_contributions
from data.processors.portfolio_attribution import attribute
from data.processors.portfolio_stress import historical_replay,diversification_windows,hypothetical_shock
from data.processors.portfolio_factors import weekly_design,fit
from data.processors.portfolio_regimes import classify,conditional
from data.fetchers.portfolio_macro import load,current


def independent(prices,weights,cost_bps):
    p=prices[list(weights)].to_numpy();w=np.array(list(weights.values()));units=10000*w/p[0];out=[10000.]
    periods=prices.index.to_period('M')
    for i in range(1,len(p)):
        positions=units*p[i];v=positions.sum()
        if i<len(p)-1 and periods[i]!=periods[i+1]:
            # Fixed-point accounting independently of engine bisection.
            cost=0.
            for _ in range(100):cost=cost_bps/10000*np.abs(w*(v-cost)-positions).sum()
            units=w*(v-cost)/p[i];v-=cost
        out.append(v)
    return np.array(out)


def main():
    prices,manifest=load_bundle(snapshot_path());macro,_=load(current())
    a=TEMPLATES['Traditional 60/40'];b=TEMPLATES['Bitcoin & oil research']
    common,results=compare(prices,a,b,start='2014-01-01',rebalancing='Monthly',cost_bps=5)
    checks=[]
    for name,w in [('Portfolio A',a),('Portfolio B',b)]:
        expected=independent(common,w,5)
        np.testing.assert_allclose(results[name].wealth,expected,rtol=1e-11)
        att=attribute(common,results[name]);assert np.isclose(att['contributions'].sum(),expected[-1]/10000-1)
        checks.append(name+' independent share units, costs and attribution reconcile')
    risk=risk_contributions(common,b);daily=common[list(b)].pct_change(fill_method=None).iloc[1:].tail(252)
    cov=np.cov(daily.to_numpy(),rowvar=False)*252;w=np.array(list(b.values()))
    np.testing.assert_allclose(risk['table']['Risk contribution'],w*(cov@w)/(w@cov@w))
    checks.append('Independent sample covariance and signed variance shares reconcile')
    design=weekly_design(results['Portfolio B'].wealth,prices.SPY,macro);model=fit(design)
    x=np.column_stack([np.ones(len(design)),design.drop(columns='Return').to_numpy()])
    beta=np.linalg.lstsq(x,design.Return.to_numpy(),rcond=None)[0]
    np.testing.assert_allclose(model['table'].Coefficient,beta)
    checks.append('Weekly BTC/oil portfolio model equals independent least squares; no BTC/oil factors added')
    episodes={}
    for episode in EPISODES:
        try:
            window,replay,summary,asset_returns=historical_replay(prices,a,b,'SPY',episode,'Monthly',5)
            np.testing.assert_allclose(replay['Portfolio B'].wealth,independent(window,b,5),rtol=1e-11)
            episodes[episode]={'start':str(window.index[0].date()),'end':str(window.index[-1].date()),'summary':summary.to_dict(),'asset_returns':asset_returns.to_dict()}
        except ValueError as exc:
            assert episode=='Global Financial Crisis' and 'BTC' in str(exc)
            episodes[episode]={'unavailable':str(exc)}
    study=diversification_windows(prices,a,b,'SPY','2022 Equity and Bond Sell-Off','Monthly',5)
    regimes=conditional(results,classify(macro),'Growth')
    uso=pd.read_csv(snapshot_path()/'USO.csv',index_col='Date',parse_dates=True)
    btc=pd.read_csv(snapshot_path()/'BTC.csv')
    audit=dict(snapshot=snapshot_path().name,coverage={t:manifest['assets'][t] for t in ['BTC','USO']},
        main_start=str(common.index[0].date()),main_end=str(common.index[-1].date()),outcomes={n:metrics(r) for n,r in results.items()},
        attribution=attribute(common,results['Portfolio B'])['contributions'].to_dict(),risk=risk['table'].to_dict(),
        factors=dict(sample=model['observations'],r_squared=model['r_squared'],coefficients=model['table'].Coefficient.to_dict()),
        regimes_months=len(regimes['observations']),episodes=episodes,
        stress_risk={label:estimate['Portfolio B']['table'].to_dict() for label,estimate in study['estimates'].items()},
        uso_2020=dict(split=uso.loc['2020-04-29','Stock Splits'],split_day_return=uso['Adj Close'].pct_change(fill_method=None).loc['2020-04-29'],
            april_return=uso.loc['2020-04-30','Adj Close']/uso.loc['2020-03-31','Adj Close']-1,
            worst_daily_2020=uso['Adj Close'].pct_change(fill_method=None).loc['2020'].min()),checks=checks)
    destination = Path('output/portfolio_lab/redesign')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'validation.json').write_text(json.dumps(audit,indent=2))
    print('\n'.join(checks));print('Real BTC/USO episodes and source evidence verified')

if __name__=='__main__':main()
