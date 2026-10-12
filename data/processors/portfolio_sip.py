"""Dated monthly cash-flow research, shared holdings/cost mathematics and XIRR."""
import numpy as np
import pandas as pd
from data.processors.portfolio_analytics import aligned_prices,validate_weights,simulate,rebalance_positions
from config.portfolio_settings import REBALANCING


def xirr(flows):
    """ACT/365; bracket/bisect in log(1+r). Conventional flows have one root."""
    f=pd.Series(flows,dtype=float).groupby(level=0).sum().sort_index()
    if not isinstance(f.index,pd.DatetimeIndex) or f.index.hasnans or not np.isfinite(f).all():raise ValueError('Invalid XIRR cash flows/dates')
    f=f[f!=0]
    if len(f)<2 or f.index[-1]<=f.index[0] or not (f<0).any() or not (f>0).any():
        return dict(value=None,status='Insufficient dated positive/negative flows')
    # Refuse non-conventional sign patterns rather than choose an arbitrary root.
    signs=np.sign(f.to_numpy());changes=np.count_nonzero(signs[1:]!=signs[:-1])
    if changes!=1 or f.iloc[0]>=0 or f.iloc[-1]<=0:
        return dict(value=None,status='Non-conventional flows: multiple/ambiguous roots not resolved')
    years=(f.index-f.index[0]).days.to_numpy()/365.
    def npv(lograte):return float(np.dot(f.to_numpy(),np.exp(np.clip(-lograte*years,-700,700))))
    lo,hi=-20.,20.
    if npv(lo)*npv(hi)>0:return dict(value=None,status='No bracketed root')
    for _ in range(160):
        mid=(lo+hi)/2
        if npv(mid)>0:lo=mid
        else:hi=mid
    value=float(np.expm1((lo+hi)/2))
    return dict(value=value,status='ACT/365; unique conventional-flow root'+(' · short horizon: annualised result may be extreme' if (f.index[-1]-f.index[0]).days<365 else ''))


def contributions(calendar,start,end,amount,initial=0.,day=1):
    if not np.isfinite([amount,initial]).all() or amount<0 or initial<0 or not 1<=day<=28 or pd.Timestamp(start)>pd.Timestamp(end):
        raise ValueError('Invalid monthly contribution schedule')
    dates=pd.DatetimeIndex(calendar);entries=[]
    if dates.hasnans or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError('Contribution calendar must be valid, unique and ordered')
    for month in pd.period_range(start,end,freq='M'):
        requested=month.start_time+pd.Timedelta(days=day-1)
        if not pd.Timestamp(start)<=requested<=pd.Timestamp(end):continue
        j=dates.searchsorted(requested)
        if j<len(dates) and dates[j]<=pd.Timestamp(end):entries.append((requested,dates[j],amount))
    if initial>0:
        j=dates.searchsorted(pd.Timestamp(start))
        if j>=len(dates) or dates[j]>pd.Timestamp(end):raise ValueError('Initial contribution has no eligible valuation')
        entries.insert(0,(pd.Timestamp(start),dates[j],initial))
    return pd.DataFrame(entries,columns=['Requested date','Investment date','Contribution'])


def sip(prices,weights,start,end,monthly,initial=0.,day=1,rebalancing='Monthly',cost_bps=0.,valuation_end=None):
    validate_weights(weights)
    if not np.isfinite(cost_bps) or not 0<=cost_bps<=100:raise ValueError('Subscription/rebalance cost must be 0–100 bps')
    if rebalancing not in REBALANCING:raise ValueError('Invalid SIP rebalance convention')
    if valuation_end is not None and pd.Timestamp(valuation_end)<pd.Timestamp(end):raise ValueError('Valuation end precedes contribution end')
    frame=aligned_prices(prices,list(weights),str(start),str(valuation_end or end));dates=frame.index
    if (dates[0]-pd.Timestamp(start)).days>14:raise ValueError('SIP unavailable before complete holding history; earlier contributions cannot be backfilled')
    ledger=contributions(dates,start,end,monthly,initial,day)
    if ledger.empty or ledger.Contribution.sum()<=0:raise ValueError('No positive contributions in eligible window')
    flows=ledger.groupby('Investment date').Contribution.sum().reindex(dates,fill_value=0.)
    positions=np.zeros(len(weights));target=np.array(list(weights.values()));history=[];twr=[1.];trade_log=[]
    freq=REBALANCING[rebalancing];periods=dates.to_period(freq) if freq else None
    for i,date in enumerate(dates):
        previous=positions.sum()
        if i and previous>0:
            # Reuse the N-asset holdings engine for each observed interval.
            part=frame.iloc[i-1:i+1]
            result=simulate(part,dict(zip(weights,positions/previous)),initial=previous)
            positions=result.holdings.iloc[-1].to_numpy()
        market_value=positions.sum();purchase_cost=flows.iloc[i]*cost_bps/10000
        positions+=target*(flows.iloc[i]-purchase_cost)
        rebalance_cost=0.
        if freq and i<len(dates)-1 and periods[i]!=periods[i+1] and positions.sum()>0:
            positions,rebalance_cost,notional=rebalance_positions(positions,target,cost_bps)
            trade_log.append((date,notional,rebalance_cost))
        if i:
            factor=(positions.sum()-(flows.iloc[i]-purchase_cost))/previous if previous>0 else 1.
            # TWR cannot use deposited capital as an investment gain.
            if factor<=0:raise ValueError('Nonpositive flow-adjusted return; unsupported cash-flow/cost combination')
            twr.append(twr[-1]*factor)
        history.append(positions.copy())
    holdings=pd.DataFrame(history,index=dates,columns=list(weights));wealth=holdings.sum(axis=1)
    cashflows=-flows[flows>0];cashflows.loc[dates[-1]]=cashflows.get(dates[-1],0)+wealth.iloc[-1]
    root=xirr(cashflows)
    return dict(wealth=wealth,invested=flows.cumsum(),gain=wealth-flows.cumsum(),holdings=holdings,
        units=holdings/frame,flows=ledger,investor_flows=cashflows,xirr=root,twr=pd.Series(twr,index=dates),
        trades=pd.DataFrame(trade_log,columns=['Date','Notional','Cost']),purchase_cost=float(flows.sum()*cost_bps/10000),
        convention='Monthly requested day rolls to next eligible weekly reference valuation within end date. Fixed allocation orders; reference-unit accounting, not executable stale-price/NAV trades. Subscription costs apply to cash invested; no terminal liquidation cost. TWR removes net subscriptions and excludes subscription fees; XIRR includes gross investor contributions and therefore those fees.')
