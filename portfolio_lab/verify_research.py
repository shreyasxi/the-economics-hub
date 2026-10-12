"""Executed real-data research and independent numerical verification."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from config.portfolio_settings import ASSETS, TEMPLATES, EPISODES
from data.fetchers.portfolio_prices import load_bundle,snapshot_path
from data.fetchers.portfolio_macro import load,current
from data.processors.portfolio_analytics import compare,metrics,risk_contributions
from data.processors.portfolio_attribution import attribute
from data.processors.portfolio_factors import weekly_design,fit,stability,factor_shock
from data.processors.portfolio_regimes import classify,conditional
from data.processors.portfolio_stress import diversification_windows


def main():
    prices,manifest=load_bundle(snapshot_path()); macro,mm=load(current())
    a=TEMPLATES['Traditional 60/40']; b=TEMPLATES['Multi-asset research']
    common,results=compare(prices,a,b,rebalancing='Monthly',cost_bps=5)
    output=Path('output/portfolio_lab/v2'); output.mkdir(parents=True,exist_ok=True)
    findings={'snapshot':str(snapshot_path()),'macro_snapshot':str(current()),'allocations':{'A':a,'B':b},'dates':[str(common.index[0].date()),str(common.index[-1].date())], 'assets':manifest['assets'],'macro':mm['series'], 'metrics':{},'attribution':{},'risk':{},'factors':{},'regimes':{},'stress':{}}
    for name,r in results.items():
        findings['metrics'][name]=metrics(r)
        attributed=attribute(common,r,{t:x['asset_class'] for t,x in ASSETS.items()})
        # Independent share-unit P&L: yesterday's notional / yesterday's adjusted
        # close × price change. Different computation from production returns.
        cols=list(r.holdings); p=common[cols]
        independent=(r.holdings.iloc[:-1].to_numpy()/p.iloc[:-1].to_numpy()*np.diff(p.to_numpy(),axis=0)).sum(axis=0)/r.wealth.iloc[0]
        np.testing.assert_allclose(independent,attributed['contributions'].loc[cols],atol=1e-10)
        findings['attribution'][name]={'contributions':attributed['contributions'].to_dict(),'cost':attributed['cost'],'turnover':attributed['turnover']}
        if name=='Benchmark':continue
        weights=a if name=='Portfolio A' else b
        findings['risk'][name]={}
        for window in [252,756]:
            risk=risk_contributions(common,weights,window)
            # Independent centered matrix covariance, no pandas.cov.
            daily=common[list(weights)].pct_change(fill_method=None).iloc[1:].tail(window).to_numpy(); centered=daily-daily.mean(axis=0)
            covariance=centered.T@centered/(len(daily)-1)*252; w=np.array(list(weights.values())); variance=w@covariance@w
            np.testing.assert_allclose(risk['covariance'],covariance,atol=1e-12)
            np.testing.assert_allclose(risk['table']['Risk contribution'],w*(covariance@w)/variance,atol=1e-12)
            findings['risk'][name][str(window)]={'contributions':risk['table']['Risk contribution'].to_dict(),'volatility':float(np.sqrt(variance)),'hhi':risk['capital_concentration'],'correlation':risk['correlation'].to_dict()}
        frame=weekly_design(r.wealth,prices.SPY,macro); model=fit(frame)
        x=np.column_stack([np.ones(len(frame)),frame[['Equity','Rate']].to_numpy()]); y=frame.Return.to_numpy()
        np.testing.assert_allclose(model['table'].Coefficient,np.linalg.solve(x.T@x,x.T@y),atol=1e-9)
        halves=stability(frame)
        credit=fit(weekly_design(r.wealth,prices.SPY,macro,True))
        findings['factors'][name]={'long':model['table'].to_dict(),'r2':model['r_squared'],'n':model['observations'],'dates':[str(model['start'].date()),str(model['end'].date())], 'residual_sd':model['residual_std'],'halves':halves.to_dict() if halves is not None else None, 'recent_credit':credit['table'].to_dict(),'credit_n':credit['observations'],'credit_r2':credit['r_squared'],'credit_dates':[str(credit['start'].date()),str(credit['end'].date())], 'scenario':factor_shock(model,{'Equity':-.1,'Rate':.01})}
    for dimension in ['Inflation','Growth']:
        c=conditional(results,classify(macro),dimension)
        c['summary'].to_csv(output/(dimension.lower()+'_regimes.csv'),index=False)
        findings['regimes'][dimension]={'summary':c['summary'].to_dict(orient='records'),'omitted_months':c['omitted_months']}
    for episode in EPISODES:
        s=diversification_windows(prices,a,b,'SPY',episode,'Monthly',5)
        findings['stress'][episode]={'returns':s['summary'].to_dict(),'attribution':{n:x['contributions'].to_dict() for n,x in s['attribution'].items()},'windows':{label:{n:{'n':e['observations'],'vol':np.sqrt(e['variance']),'rc':e['table']['Risk contribution'].to_dict(),'correlations':e['correlation'].to_dict()} for n,e in values.items()} for label,values in s['estimates'].items()}}
    def serialise(value):
        if isinstance(value,pd.Series):return value.to_dict()
        if isinstance(value,(np.floating,np.integer)):return value.item()
        raise TypeError(type(value).__name__)
    (output/'research.json').write_text(json.dumps(findings,indent=2,default=serialise))
    print('Real-data accounting, covariance and regression checks passed.')
    print('Common dates: '+str(findings['dates']))
    print(pd.DataFrame(findings['metrics']).to_string())
    print('Attribution (percentage points):')
    print(pd.DataFrame({n:x['contributions'] for n,x in findings['attribution'].items()}).fillna(0).mul(100).round(3).to_string())
    print('Saved '+str(output/'research.json'))

if __name__=='__main__':main()
