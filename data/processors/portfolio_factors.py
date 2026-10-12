"""Weekly raw-return OLS associations with Newey–West HAC uncertainty."""
import numpy as np
import pandas as pd

FACTOR_UNITS = {'Equity': 'pp portfolio return per 1 pp SPY return',
                'Rate': 'pp portfolio return per +100 bps Treasury yield',
                'Credit': 'pp portfolio return per +100 bps HY OAS'}


def endpoints(series, frequency='W-FRI'):
    """Actual last closes; no filling. Drop unfinished ending week/month."""
    if series.empty or not series.index.is_monotonic_increasing or series.index.duplicated().any():
        raise ValueError('Endpoints require unique chronological observations.')
    groups = series.index.to_period(frequency)
    last_dates = pd.Series(series.index, index=series.index).groupby(groups).last()
    closed = last_dates.index.end_time.normalize() <= series.index[-1]
    dates = pd.DatetimeIndex(last_dates.loc[closed].values)
    values = series.loc[dates].copy()
    values.index = last_dates.index[closed].to_timestamp(how='end').normalize()
    return values, dates


def weekly_design(wealth, spy, macro, credit=False):
    values, dates = endpoints(wealth)
    if len(values)<2:
        raise ValueError('No complete weekly intervals.')
    prices = spy.reindex(dates); prices.index = values.index
    rate = macro['DGS10'].reindex(dates); rate.index=values.index
    frame = pd.DataFrame({'Return':values.pct_change(fill_method=None),
                          'Equity':prices.pct_change(fill_method=None), 'Rate':rate.diff()/100})
    if credit:
        spread=macro['BAMLH0A0HYM2'].reindex(dates); spread.index=values.index
        frame['Credit']=spread.diff()/100
    # Differences are computed BEFORE dropping missing rows, never bridge a missing week.
    available = frame.iloc[1:].replace([np.inf,-np.inf],np.nan)
    result=available.dropna()
    result.attrs['omitted_intervals']=len(available)-len(result)
    return result


def fit(frame, min_obs=104, hac_lags=4):
    if 'Return' not in frame or len(frame.columns)<2 or frame.columns.duplicated().any():
        raise ValueError('A return and named factors are required.')
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.hasnans or (frame.index.dayofweek!=4).any() or not frame.index.equals(frame.index.normalize()):
        raise ValueError('Regression requires Friday-labelled weekly intervals.')
    if frame.index.duplicated().any() or not frame.index.is_monotonic_increasing or not np.isfinite(frame.to_numpy()).all():
        raise ValueError('Model observations must be finite, unique and ordered.')
    names=['Intercept']+[c for c in frame if c!='Return']; n=len(frame); p=len(names)
    if n<max(min_obs,20*p):
        raise ValueError('Insufficient evidence: model requires at least {} matched weekly intervals.'.format(max(min_obs,20*p)))
    factors=frame[[c for c in frame if c!='Return']].to_numpy(); scale=factors.std(axis=0,ddof=1)
    if (scale<=1e-12).any():
        raise ValueError('Unidentified constant factor.')
    z=np.column_stack([np.ones(n),(factors-factors.mean(axis=0))/scale])
    condition=float(np.linalg.cond(z))
    if condition>1000 or np.linalg.matrix_rank(z)<p:
        raise ValueError('Unstable or collinear factor design (standardised condition > 1,000).')
    x=np.column_stack([np.ones(n),factors]); y=frame.Return.to_numpy()
    beta=np.linalg.lstsq(x,y,rcond=None)[0]; residual=y-np.einsum("ij,j->i",x,beta)
    total=float(np.sum((y-y.mean())**2))
    if total<=1e-14:
        raise ValueError('Return variation is too small for a meaningful fit.')
    # HAC Bartlett kernel uses actual calendar lag, excluding omitted weeks from lag pairs.
    bread=np.linalg.inv(np.einsum("ni,nj->ij",x,x)); scores=x*residual[:,None]; meat=np.einsum("ni,nj->ij",scores,scores)
    for lag in range(1,hac_lags+1):
        past=pd.DataFrame(scores,index=frame.index).reindex(frame.index-pd.Timedelta(weeks=lag)).to_numpy()
        valid=np.isfinite(past).all(axis=1)
        cross=np.einsum("ni,nj->ij",scores[valid],past[valid]); meat+=(1-lag/(hac_lags+1))*(cross+cross.T)
    covariance=np.einsum("ij,jk,kl->il",bread,meat,bread)*n/(n-p)
    se=np.sqrt(np.maximum(np.diag(covariance),0))
    if not np.isfinite(beta).all() or not np.isfinite(covariance).all() or not np.isfinite(residual).all():
        raise ValueError('Nonfinite regression result.')
    table=pd.DataFrame({'Coefficient':beta,'HAC standard error':se,'95% lower':beta-1.96*se,'95% upper':beta+1.96*se},index=names)
    table['Units']=['decimal weekly return intercept']+[FACTOR_UNITS.get(c,'return per unit factor') for c in names[1:]]
    return dict(table=table, covariance=pd.DataFrame(covariance,index=names,columns=names),
                residual=pd.Series(residual,index=frame.index), fitted=pd.Series(np.einsum("ij,j->i",x,beta),index=frame.index),
                r_squared=1-float(np.dot(residual,residual))/total, residual_std=float(np.std(residual,ddof=p)),
                observations=n,start=frame.index[0],end=frame.index[-1],condition=condition,
                specification='Weekly raw returns; no risk-free subtraction. Intercept is not investment alpha.',hac_lags=hac_lags)


def rolling(frame, window=104, step=13):
    if window<104:
        raise ValueError('Rolling estimation requires at least 104 weekly intervals.')
    rows=[]
    # Calendar windows rather than last-N available rows across source gaps.
    for end in frame.index[::step]:
        sample=frame.loc[(frame.index>end-pd.Timedelta(weeks=window)) & (frame.index<=end)]
        if len(sample)<window:
            continue
        model=fit(sample, min_obs=window)
        rows.append(dict(Date=end, **model['table']['Coefficient'].drop('Intercept').to_dict()))
    return pd.DataFrame(rows)


def stability(frame):
    half=len(frame)//2
    if half<104:
        return None
    first, second=fit(frame.iloc[:half]),fit(frame.iloc[half:])
    return pd.DataFrame({'Earlier half':first['table'].Coefficient,'Later half':second['table'].Coefficient})


def factor_shock(model, shocks):
    names=list(model['table'].index[1:])
    if set(shocks)!=set(names):
        raise ValueError('Scenario must specify every fitted factor, and no unfitted factor.')
    x=np.asarray([shocks[n] for n in names],float)
    if not np.isfinite(x).all() or ('Equity' in names and shocks['Equity'] < -1):
        raise ValueError('Invalid factor shocks; equity return cannot be below −100%.')
    beta=model['table'].loc[names,'Coefficient'].to_numpy(); parts=pd.Series(beta*x,index=names)
    if parts.sum() < -1:
        raise ValueError('Linear model implies a loss below −100%; this extreme scenario is unsupported.')
    covariance=model['covariance'].loc[names,names].to_numpy(); se=float(np.sqrt(max(np.einsum("i,ij,j->",x,covariance,x),0)))
    return dict(impact=float(parts.sum()), contributions=parts, parameter_interval=(float(parts.sum()-1.96*se),float(parts.sum()+1.96*se)),
                residual_std=model['residual_std'], horizon='One weekly interval; beta × shock only, intercept excluded. Parameter interval excludes residual and model uncertainty.')
