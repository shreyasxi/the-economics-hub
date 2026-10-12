"""Ex-post monthly descriptive regimes; no point-in-time trading signals."""
import numpy as np
import pandas as pd
from data.processors.portfolio_factors import endpoints

DISCLOSURE = 'Ex-post revised-data observation-month classification. Releases arrive later and history may change. No reconstructed vintages; not an investable signal.'
RULES = {'Inflation': 'CPIAUCSL annual inflation minus its value three months earlier: positive Rising, negative Falling, exactly zero Unchanged.',
         'Growth': 'Published CFNAIMA3 level: >=0 At/above trend, <0 Below trend. Below trend does not imply recession or falling output.'}


def classify(macro):
    cpi=macro['CPIAUCSL'].copy(); growth=macro['CFNAIMA3'].copy()
    cpi.index=cpi.index.to_period('M'); growth.index=growth.index.to_period('M')
    if cpi.index.duplicated().any() or growth.index.duplicated().any():
        raise ValueError('Duplicate macro observation months.')
    # Calendar reindex preserves omissions; pct_change never fills.
    cpi=cpi.reindex(pd.period_range(cpi.index.min(),cpi.index.max(),freq='M'))
    inflation=cpi.pct_change(12,fill_method=None)*100; change=inflation-inflation.shift(3)
    label=pd.Series(None,index=change.index,dtype=object)
    label.loc[change>0]='Rising'; label.loc[change<0]='Falling'; label.loc[change==0]='Unchanged'
    glabel=pd.Series(None,index=growth.index,dtype=object)
    glabel.loc[growth.notna() & (growth>=0)]='At/above trend'; glabel.loc[growth.notna() & (growth<0)]='Below trend'
    out=pd.DataFrame({'Inflation':label,'Growth':glabel}); out.attrs['disclosure']=DISCLOSURE
    return out


def conditional(results, labels, dimension, min_obs=24):
    if dimension not in RULES or labels.attrs.get('disclosure')!=DISCLOSURE:
        raise ValueError('Only disclosed ex-post classifications are supported.')
    returns={}
    for name, result in results.items():
        values,_=endpoints(result.wealth,'M')
        returns[name]=values.pct_change(fill_method=None).iloc[1:]
    monthly=pd.DataFrame(returns).dropna()
    monthly.index=monthly.index.to_period('M')
    matched=monthly.join(labels[dimension].rename('Regime'),how='left')
    omitted=int(matched.Regime.isna().sum()); matched=matched.dropna(subset=['Regime'])
    stats=[]
    for regime, group in matched.groupby('Regime'):
        periods=group.index.astype('int64').to_numpy()
        episodes=int(1+np.sum(np.diff(periods)!=1)) if len(periods) else 0
        sufficient=len(group)>=min_obs and episodes>=3
        for name in returns:
            vals=group[name]
            stats.append({'Regime':regime,'Portfolio':name,'Months':len(vals),'Distinct runs':episodes,
                          'Mean monthly return':vals.mean() if sufficient else np.nan,
                          'Median monthly return':vals.median() if sufficient else np.nan,
                          'Monthly volatility':vals.std(ddof=1) if sufficient else np.nan,
                          'Negative months':(vals<0).mean() if sufficient else np.nan,
                          '10th percentile':vals.quantile(.1) if sufficient else np.nan,
                          'Status':'Descriptive evidence' if sufficient else 'Insufficient evidence (<24 months or <3 runs)'})
    return dict(summary=pd.DataFrame(stats), observations=matched, omitted_months=omitted,
                disclosure=DISCLOSURE,rule=RULES[dimension],minimum=min_obs)
