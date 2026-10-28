"""Executed INR research and independent unit/cost/currency checks."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from data.fetchers.portfolio_india import current,load
from data.processors.portfolio_analytics import compare,simulate,metrics,risk_contributions,aligned_prices
from data.processors.portfolio_attribution import attribute
from data.processors.portfolio_currency import decomposition,portfolio_fx_pnl
from data.processors.portfolio_sip import sip,xirr
from data.processors.portfolio_stress import historical_replay,diversification_windows
from data.processors.portfolio_india_regimes import observations,factor_design,policy_history
from data.processors.portfolio_factors import fit
from config.portfolio_india_settings import EPISODES

OUT=Path('output/portfolio_lab/india');OUT.mkdir(parents=True,exist_ok=True)
A={'NIFTYBEES.NS':.6,'GILT5YBEES.NS':.4}
B={'NIFTYBEES.NS':.51,'GILT5YBEES.NS':.34,'GOLDBEES.NS':.15}


def units_path(prices,w,monthly=0.,initial=100000.,schedule=None,bps=5):
    # Direct unit updates and fixed-point cost solve, independent of simulator.
    p=prices[list(w)].to_numpy();target=np.array(list(w.values()));units=initial*target/p[0] if schedule is None else np.zeros(len(w))
    history=[];months=prices.index.to_period('M')
    for i,date in enumerate(prices.index):
        positions=units*p[i]
        if schedule is not None:
            cash=schedule.get(date,0.)
            positions+=target*cash*(1-bps/10000)
        if i<len(p)-1 and months[i]!=months[i+1]:
            v=positions.sum();cost=0.
            for _ in range(100):cost=bps/10000*np.abs(target*(v-cost)-positions).sum()
            positions=target*(v-cost)
        units=positions/p[i];history.append(positions.sum())
    return np.array(history)


def main():
    prices,local,fx,manifest=load(current())
    common,results=compare(prices,A,B,'nifty-50','2021-10-01',None,'Monthly',5,100000)
    checks=[]
    for name,w in [('Portfolio A',A),('Portfolio B',B)]:
        expected=units_path(common,w)
        np.testing.assert_allclose(results[name].wealth,expected,rtol=1e-11)
        ledger=attribute(common,results[name]);assert np.isclose(ledger['contributions'].sum(),expected[-1]/100000-1)
        checks.append(name+' independent share-unit/cost/attribution reconciliation')
    risk=risk_contributions(common,B,52,52)
    w=np.array(list(B.values()));daily=common[list(B)].pct_change(fill_method=None).iloc[1:].tail(52)
    cov=np.cov(daily.to_numpy().T,ddof=1)*52
    np.testing.assert_allclose(risk['table']['Risk contribution'],w*(cov@w)/(w@cov@w),rtol=1e-10)
    international=aligned_prices(prices,['nifty-50','SPY'],'2021-10-01')
    eq={k:metrics(simulate(international,{k:1.},initial=100000),52,'₹') for k in international}
    currency=decomposition(local.loc[international.index,['SPY']],fx.loc[international.index])
    np.testing.assert_allclose(international.SPY,local.loc[international.index,'SPY']*fx.loc[international.index])
    model=fit(factor_design(results['Portfolio B'].wealth,prices['nifty-50'],fx))
    frame=factor_design(results['Portfolio B'].wealth,prices['nifty-50'],fx)
    x=np.column_stack([np.ones(len(frame)),frame[['Equity','Currency']].to_numpy()])
    np.testing.assert_allclose(np.linalg.lstsq(x,frame.Return.to_numpy(),rcond=None)[0],model['table'].Coefficient,rtol=1e-11)
    duration_prices=aligned_prices(prices,['GILT5YBEES.NS','LTGILTBEES.NS'],'2022-05-04','2023-02-15')
    duration={key:metrics(simulate(duration_prices,{key:1.},initial=100000),52,'₹') for key in duration_prices}
    decisions=policy_history().loc['2022-05-04':'2023-02-08']
    assert decisions.loc['2022-05-04']==4.4 and decisions.loc['2023-02-08']==6.5
    c={'NIFTYBEES.NS':.4,'GILT5YBEES.NS':.3,'GOLDBEES.NS':.1,'SPY':.2}
    foreign_window,foreign_replay,_,_=historical_replay(prices,c,c,'nifty-50','2022 inflation and rate shock','Monthly',5,EPISODES,100000,52,'₹')
    stress_fx=portfolio_fx_pnl(foreign_window,local,fx,foreign_replay['Portfolio A'],manifest['assets'])
    contributions=sip(common,B,common.index[0],common.index[-1],10000,0,1,'Monthly',5)
    schedule=contributions['flows'].groupby('Investment date').Contribution.sum()
    independent=units_path(common,B,initial=0,schedule=schedule)
    np.testing.assert_allclose(independent,contributions['wealth'],rtol=1e-10)
    flows=contributions['investor_flows'];rate=contributions['xirr']['value']
    npv=np.sum(flows.to_numpy()/np.power(1+rate,(flows.index-flows.index[0]).days/365.))
    assert abs(npv)<1e-6
    # Same total capital lump sum is an explicitly different timing counterfactual.
    total=contributions['invested'].iloc[-1]
    lump=simulate(common,B,'Monthly',5,total*(1-5/10000))
    lump_xirr=xirr(pd.Series([-total,lump.wealth.iloc[-1]],index=pd.DatetimeIndex([common.index[0],common.index[-1]])))
    episode={};stress={}
    for name in EPISODES:
        try:
            window,replay,summary,asset_returns=historical_replay(prices,A,B,'nifty-50',name,'Monthly',5,EPISODES,100000,52,'₹')
            episode[name]={'start':str(window.index[0].date()),'end':str(window.index[-1].date()),'summary':summary.to_dict(),'assets':asset_returns.to_dict()}
            for n,w in [('Portfolio A',A),('Portfolio B',B)]:np.testing.assert_allclose(replay[n].wealth,units_path(window,w),rtol=1e-11)
        except ValueError as exc:episode[name]={'unavailable':str(exc)}
    study=diversification_windows(prices,A,B,'nifty-50','RBI tightening 2022–23','Monthly',5,52,EPISODES,100000,52,'₹')
    for name,est in study['estimates'].items():stress[name]={'risk':est['Portfolio B']['table'].to_dict(),'observations':est['Portfolio B']['observations'],'start':str(est['Portfolio B']['start'].date()),'end':str(est['Portfolio B']['end'].date())}
    output=dict(snapshot=current().name,coverage=manifest['assets'],main_start=str(common.index[0].date()),main_end=str(common.index[-1].date()),weights={'A':A,'B':B},
        gold_comparison={n:metrics(r,52,'₹') for n,r in results.items()},attribution={n:attribute(common,r)['contributions'].to_dict() for n,r in results.items()},
        risk=risk['table'].to_dict(),international=eq,fx_decomposition=currency.to_dict(),
        duration_window=[str(duration_prices.index[0].date()),str(duration_prices.index[-1].date())],duration=duration,
        policy_decisions={str(d.date()):v for d,v in decisions.items()},
        sip=dict(invested=float(total),final=float(contributions['wealth'].iloc[-1]),gain=float(contributions['gain'].iloc[-1]),xirr=rate,
            twr=float(contributions['twr'].iloc[-1]-1),contributions=len(schedule),first=str(schedule.index[0].date()),last=str(schedule.index[-1].date()),
            same_total_lump=metrics(lump,52,'₹'),same_total_lump_xirr=lump_xirr['value'],
            same_total_lump_gain=float(lump.wealth.iloc[-1]-total),matched_subscription_cost=float(total*5/10000),xirr_npv=npv),
        factors=dict(sample=model['observations'],r_squared=model['r_squared'],coefficients=model['table'].Coefficient.to_dict()),
        regimes={dim:observations(results,fx,dim).groupby('Regime').size().to_dict() for dim in ['RBI policy','Inflation','Currency']},
        episodes=episode,stress_risk=stress,stress_fx=stress_fx.to_dict(),stress_fx_weights=c,checks=checks+['Independent covariance, exact FX conversion, independent weekly OLS, independent SIP units/costs and XIRR NPV all reconcile'])
    (OUT/'validation.json').write_text(json.dumps(output,indent=2,ensure_ascii=False))
    common.to_csv(OUT/'demo_prices.csv',index_label='Date')
    print('\n'.join(output['checks']),flush=True)
    return common,results,contributions,study


if __name__=='__main__':main()
