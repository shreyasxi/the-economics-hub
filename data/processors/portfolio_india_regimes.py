"""Read-only official Indian macro histories; descriptive ex-post monthly labels."""
import json
import sqlite3
import pandas as pd
import numpy as np
from data.paths import RBI_SENTINEL_DB,CPI_MAIN_STATUS,RBI_MONEY_MARKET_CSV


def policy_history():
    with sqlite3.connect('file:'+str(RBI_SENTINEL_DB)+'?mode=ro',uri=True) as c:
        frame=pd.read_sql_query('SELECT policy_cycle,repo_rate_pct FROM mpc_meetings WHERE policy_cycle IS NOT NULL AND repo_rate_pct IS NOT NULL',c)
    frame['Date']=pd.to_datetime(frame.policy_cycle)
    if (frame.groupby('Date').repo_rate_pct.nunique()>1).any():raise ValueError('Conflicting RBI effective decisions')
    series=frame.drop_duplicates('Date').sort_values('Date').set_index('Date').repo_rate_pct
    if series.empty or not np.isfinite(series).all() or (series<=0).any():raise ValueError('Invalid RBI decision history')
    return series


def cpi_history():
    status=json.loads(CPI_MAIN_STATUS.read_text())
    if status['status']!='ready':raise ValueError('Canonical CPI not validated')
    rows=[{'Month':pd.Period(r['month'],freq='M'),'YoY':float(r['value']),'Base':r['base']}
          for r in status['changes'] if r['column']=='india_cpi_yoy' and r['concept'] in ('General','CPI (General)')]
    frame=pd.DataFrame(rows).sort_values('Month').set_index('Month')
    if frame.index.duplicated().any() or not np.isfinite(frame.YoY).all():raise ValueError('Invalid canonical published CPI rates')
    # Do not calculate changes across an incompatible base or missing month.
    frame['Change']=frame.YoY.diff()
    adjacent=frame.index.to_series().diff().map(lambda d:d.n if pd.notna(d) else 0).eq(1)
    frame.loc[frame.Base.ne(frame.Base.shift())|~adjacent,'Change']=np.nan
    return frame


def labels(start,end,fx):
    months=pd.period_range(start,end,freq='M');policy=policy_history()
    rates=policy.reindex(months.to_timestamp(how='end'),method='ffill')
    ages=months.to_timestamp(how='end')-pd.DatetimeIndex(policy.index.to_series().reindex(months.to_timestamp(how='end'),method='ffill'))
    rates.loc[ages.days>100]=np.nan
    rates.index=months
    change=rates.diff();out=pd.DataFrame(index=months)
    out['RBI policy']=change.map(lambda x:'Tightening' if x>0 else 'Easing' if x<0 else 'Unchanged' if pd.notna(x) else None)
    cpi=cpi_history().Change.reindex(months)
    out['Inflation']=cpi.map(lambda x:'Rising' if x>0 else 'Falling' if x<0 else 'Unchanged' if pd.notna(x) else None)
    f=fx.groupby(fx.index.to_period('M')).last().reindex(months).pct_change(fill_method=None)
    out['Currency']=f.map(lambda x:'INR depreciation' if x>0 else 'INR appreciation' if x<0 else 'Unchanged' if pd.notna(x) else None)
    return out


def observations(results,fx,dimension):
    from data.processors.portfolio_factors import endpoints
    series={}
    for name,result in results.items():
        level,_=endpoints(result.wealth,'M');series[name]=level.pct_change(fill_method=None)
    frame=pd.DataFrame(series);frame.index=frame.index.to_period('M')
    state=labels(frame.index[0],frame.index[-1],fx)[dimension]
    frame['Regime']=state;return frame.dropna()


def factor_design(wealth,equity,fx):
    frame=pd.DataFrame({'Return':wealth.pct_change(fill_method=None),'Equity':equity.reindex(wealth.index).pct_change(fill_method=None),
        'Currency':fx.reindex(wealth.index).pct_change(fill_method=None)})
    actual_dates=frame.index.copy()
    frame.index=frame.index.to_period('W-FRI').to_timestamp(how='end').normalize()
    result=frame.iloc[1:].dropna()
    mapping=pd.Series(actual_dates,index=frame.index)
    if len(result):
        result.attrs['reference_start']=mapping.loc[result.index[0]]
        result.attrs['reference_end']=mapping.loc[result.index[-1]]
    return result
