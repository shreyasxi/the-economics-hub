"""Publication-aware, timestamped INR reference valuation; no date-string joins."""
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

CONVENTION = ('Weekly Wednesday 15:30 Asia/Kolkata checkpoint, next observed Indian session if closed. '
 'Domestic marks: latest completed prior-day close; foreign marks: latest completed New York 16:00 close. '
 'FX: latest H.10 fixing from a publicly released week, INR per USD. H.10 normally releases Monday '
 '16:15 New York; federal holidays shift to the next federal business day. These are revised historical '
 'asynchronous reference marks, not executable quotes or proof of historical publication latency. '
 'Fixed allocation/SIP simulations use these reference prices; settlement, fund cutoff, NAV applicability, '
 'spreads, loads, taxes and remittance costs are not modelled. Fractional ETF units are assumed; '
 'lot rounding and residual cash are not modelled. No strategy uses macro observations.')


def validated(series):
    s=series.copy().astype(float)
    if not isinstance(s.index,pd.DatetimeIndex) or s.index.tz is not None or s.index.hasnans or not s.index.equals(s.index.normalize()) or s.index.duplicated().any() or not s.index.is_monotonic_increasing or s.empty:
        raise ValueError('Ordered unique timezone-free source dates required')
    if s.isna().any() or not np.isfinite(s).all() or (s<=0).any():raise ValueError('Missing/nonpositive source prices or FX')
    return s


def h10_availability(dates):
    # The week is not publicly available before its scheduled weekly release.
    days=pd.DatetimeIndex(dates)
    mondays=days.to_period('W-FRI').end_time.normalize()+pd.Timedelta(days=3)
    business=CustomBusinessDay(calendar=USFederalHolidayCalendar())
    release=pd.DatetimeIndex([business.rollforward(d) for d in mondays])+pd.Timedelta(hours=16,minutes=15)
    return release.tz_localize('America/New_York').tz_convert('UTC')


def asof_values(series,effective,checkpoints,max_age_days):
    """Bounded known-mark lookup, with explicit fixing/effective evidence."""
    s=validated(series);effective=pd.DatetimeIndex(effective);cut=pd.DatetimeIndex(checkpoints)
    if effective.tz is None or cut.tz is None or not effective.is_monotonic_increasing:
        raise ValueError('Explicit ordered UTC availability required')
    # Several H.10 fixings share one release; choose the latest source fixing.
    idx=effective.searchsorted(cut,side='right')-1
    values=np.full(len(cut),np.nan);chosen=np.full(len(cut),np.datetime64('NaT'),dtype='datetime64[ns]')
    known=np.full(len(cut),np.datetime64('NaT'),dtype='datetime64[ns]')
    for i,j in enumerate(idx):
        if j<0:continue
        source_day=s.index[j]
        if (cut[i].tz_convert('Asia/Kolkata').tz_localize(None).normalize()-source_day).days>max_age_days:
            continue
        values[i]=s.iloc[j];chosen[i]=source_day.to_datetime64();known[i]=effective[j].tz_convert('UTC').tz_localize(None).to_datetime64()
    evidence=pd.DataFrame({'checkpoint_utc':cut,'source_date':chosen,'available_utc':pd.to_datetime(known,utc=True),'value':values})
    if (evidence.available_utc.dropna()>cut[evidence.available_utc.notna()]).any():raise ValueError('Future information join')
    return values,evidence


def weekly_reference_panel(histories,metadata,fx):
    calendar=validated(histories.get('NIFTYBEES.NS',histories['nifty-50'])).index
    targets=pd.date_range(calendar[0],calendar[-1],freq='W-WED')
    positions=calendar.searchsorted(targets);positions=positions[positions<len(calendar)]
    sessions=calendar[positions].drop_duplicates()
    checkpoints=(sessions+pd.Timedelta(hours=15,minutes=30)).tz_localize('Asia/Kolkata').tz_convert('UTC')
    fx=validated(fx);fx_values,fx_evidence=asof_values(fx,h10_availability(fx.index),checkpoints,12)
    panel=pd.DataFrame(index=sessions);panel.attrs['max_gap_days']=14
    local=pd.DataFrame(index=sessions);evidence=[]
    for key,raw in histories.items():
        s=validated(raw);currency=metadata[key]['currency']
        if currency=='INR':
            effective=(s.index+pd.Timedelta(hours=17)).tz_localize('Asia/Kolkata').tz_convert('UTC')
            age=7
        elif currency=='USD':
            effective=(s.index+pd.Timedelta(hours=16)).tz_localize('America/New_York').tz_convert('UTC');age=7
        else:raise ValueError('Unsupported quote currency')
        values,ev=asof_values(s,effective,checkpoints,age)
        local[key]=values;panel[key]=values*fx_values if currency=='USD' else values
        ev['instrument']=key;evidence.append(ev)
    fx_evidence['instrument']='USD/INR';evidence.append(fx_evidence)
    fx_evidence['fixing_utc']=(pd.DatetimeIndex(fx_evidence.source_date)+pd.Timedelta(hours=12)).tz_localize('America/New_York').tz_convert('UTC')
    return panel,local,pd.Series(fx_values,index=sessions,name='USD/INR'),pd.concat(evidence,ignore_index=True)


def decomposition(local,fx):
    if not local.index.equals(fx.index):raise ValueError('FX and local windows must match')
    asset=local.iloc[-1]/local.iloc[0]-1;currency=fx.iloc[-1]/fx.iloc[0]-1
    parts=pd.DataFrame({'Foreign asset':asset,'Currency':currency,'Interaction':asset*currency})
    parts['Total INR']=parts.sum(axis=1)
    expected=(local.iloc[-1]*fx.iloc[-1])/(local.iloc[0]*fx.iloc[0])-1
    if not np.allclose(parts['Total INR'],expected):raise ValueError('Currency return does not reconcile')
    return parts


def portfolio_fx_pnl(prices,local,fx,simulation,metadata):
    """Three-way currency P&L at actual entering INR holdings; exact compounding."""
    dates=simulation.wealth.index;holdings=simulation.holdings.shift(1).iloc[1:]
    inr=prices.loc[dates,simulation.holdings.columns].pct_change(fill_method=None).iloc[1:]
    currency=fx.loc[dates].pct_change(fill_method=None).iloc[1:]
    totals=pd.Series(0.,index=['Domestic assets','Foreign market','Currency','Interaction','Trading costs'])
    for key in holdings:
        if metadata[key]['currency']=='INR':totals['Domestic assets']+=(holdings[key]*inr[key]).sum()
        else:
            foreign=local.loc[dates,key].pct_change(fill_method=None).iloc[1:]
            if foreign.isna().any() or currency.isna().any():raise ValueError('Missing FX attribution endpoints')
            totals['Foreign market']+=(holdings[key]*foreign).sum()
            totals['Currency']+=(holdings[key]*currency).sum()
            totals['Interaction']+=(holdings[key]*foreign*currency).sum()
    totals['Trading costs']=-simulation.trades.cost.sum()
    if not np.isclose(totals.sum(),simulation.wealth.iloc[-1]-simulation.wealth.iloc[0],atol=1e-7,rtol=1e-10):
        raise ValueError('Portfolio currency attribution does not reconcile')
    return totals/simulation.wealth.iloc[0]


def import_growth_nav(frame,identity):
    """Permission-gated AMFI/AMC import contract; no bulk automated retrieval."""
    required={'scheme_code','isin','amc','name','plan','option','inception','currency','permission','continuity_verified'}
    if not required.issubset(identity) or identity['plan']!='Direct' or identity['option']!='Growth' or identity['currency']!='INR' or not identity['permission'] or identity['continuity_verified'] is not True:
        raise ValueError('Verified Direct/Growth INR identity and source permission required')
    if set(frame.scheme_code.astype(str))!={str(identity['scheme_code'])} or set(frame['isin'])!={identity['isin']}:
        raise ValueError('Scheme/ISIN discontinuity')
    s=validated(pd.Series(frame.nav.to_numpy(),index=pd.to_datetime(frame.date)))
    if s.index[0]<pd.Timestamp(identity['inception']):raise ValueError('NAV before fund inception')
    return s
