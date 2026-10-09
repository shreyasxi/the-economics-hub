"""Observed mixed-return arithmetic, source policy, schema and presentation."""
from __future__ import annotations
import ast
import json
import re
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from config.market_matrix import (ASSETS, GROUPS, HORIZONS, ADJUSTED_TOTAL_RETURN,
                                  OFFICIAL_TOTAL_RETURN, DIRECT_PRICE_RETURN)
from data.processors.market_matrix import calculate, build, validate_spec

ROOT = Path(__file__).resolve().parents[1]
SPEC = {a['id']:a for a in ASSETS}
# An isolated official-index fixture; excluded from the Weekly universe.
SPEC['nifty50_tri'] = dict(id='nifty50_tri', label='Nifty 50 TRI', group='india', currency='INR',
         source='NSE Indices', source_url='https://www.niftyindices.com/reports/historical-data',
         instrument_or_index='NSE Nifty 50 Total Return Index', ticker_or_series='NIFTY 50 TRI',
         ticker_or_series_code='NIFTY 50 TRI', return_method=OFFICIAL_TOTAL_RETURN,
         methodology_note='Official gross dividend-reinvested total-return index, in INR; not an ETF and not currency-converted.',
         methodology_url='https://www.niftyindices.com/resources/index-concepts/total-return-index')


def history(start='2018-01-01', end='2026-10-02', method=ADJUSTED_TOTAL_RETURN, frequency='B'):
    dates = pd.date_range(start, end, freq=frequency)
    s = pd.Series(100 * np.exp(np.arange(len(dates))*.0003), index=dates)
    s.attrs['return_method'] = method
    return s


class Fetch:
    def __init__(self, failures=()):self.failures=set(failures);self.calls=[]
    def get_total_return_series(self,ticker,period):
        self.calls.append(('adjusted',ticker,period))
        if ticker in self.failures:raise ValueError('download failed')
        return history()
    def get_price_return_series(self,ticker,period):
        self.calls.append(('price',ticker,period))
        if ticker in self.failures:raise ValueError('download failed')
        return history(method=DIRECT_PRICE_RETURN, frequency='D',end='2026-10-03')
    def get_nifty50_tri(self,cutoff):
        self.calls.append(('official','NIFTY 50 TRI',str(cutoff)))
        if 'NIFTY 50 TRI' in self.failures:raise ValueError('official source unavailable')
        return history(method=OFFICIAL_TOTAL_RETURN,end='2026-10-01')


def payload(fetch=None):
    fetch=fetch or Fetch()
    return build(fetch,'2026-10-03',nse_fetcher=fetch)


def renderers():
    source=(ROOT/'app.py').read_text();tree=ast.parse(source)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_load_market_matrix','_market_matrix_html')]
    import html, math
    from datetime import date
    ns=dict(Path=Path,json=json,html=html,math=math,date=date,_fmt_day=lambda d:d.isoformat())
    exec(compile('from __future__ import annotations\n'+'\n\n'.join(ast.get_source_segment(source,n) for n in nodes),'app.py','exec'),ns)
    return ns


@pytest.mark.parametrize('key',HORIZONS)
def test_horizons(key):
    s=history().drop(pd.Timestamp('2026-09-02'))
    r=calculate(s,SPEC['spy'],'2026-10-03')
    targets={'1W':s.index[-1]-pd.Timedelta(days=7),'1M':s.index[-1]-pd.DateOffset(months=1),
             '3M':s.index[-1]-pd.DateOffset(months=3),'YTD':pd.Timestamp('2025-12-31'),
             '1Y':s.index[-1]-pd.DateOffset(years=1),'3Y':s.index[-1]-pd.DateOffset(years=3),
             '5Y':s.index[-1]-pd.DateOffset(years=5)}
    base=s.iloc[:-1] if key=='1D' else s.loc[:targets[key]]
    ratio=s.iloc[-1]/base.iloc[-1]
    expected=(ratio**(365.25/(s.index[-1]-base.index[-1]).days)-1)*100 if key in ('3Y','5Y') else (ratio-1)*100
    assert r['returns'][key]==pytest.approx(expected)
    assert r['anchor_dates'][key]==str(base.index[-1].date())


@pytest.mark.parametrize('asset,method',[('spy',ADJUSTED_TOTAL_RETURN),('nifty50_tri',OFFICIAL_TOTAL_RETURN),('bitcoin',DIRECT_PRICE_RETURN)])
def test_mixed_inputs(asset,method):
    s=history(method=method)
    row=calculate(s,SPEC[asset],'2026-10-03')
    assert row['return_method']==method and row['source']==SPEC[asset]['source']
    s.attrs['return_method']='price return'
    with pytest.raises(ValueError,match='matching'):calculate(s,SPEC[asset],'2026-10-03')


def test_routing_and_exact_universe():
    f=Fetch();p=payload(f)
    assert len(ASSETS)==28 and p['summary']['valid_markets']==28
    assert [g['label'] for g in p['groups']]==['US Equities','US Sectors','Developed Markets','Emerging Markets','Fixed Income','Commodities','Crypto']
    assert [len(g['rows']) for g in p['groups']]==[3,3,3,6,6,6,1]
    assert ('price','BTC-USD','max') in f.calls
    assert not any(c[1] in ('^NSEI','NIFTY 50 TRI') for c in f.calls)
    assert ('adjusted','INDA','max') in f.calls
    assert p['groups'][3]['rows'][1]['label']=='India (MSCI proxy)'
    assert all(r['currency']=='USD' for g in p['groups'] for r in g['rows'])
    assert p['groups'][-1]['rows'][0]['latest_date']=='2026-10-03'
    assert p['groups'][0]['rows'][0]['latest_date']=='2026-10-02'


@pytest.mark.parametrize('field',['source','source_url','instrument_or_index','ticker_or_series','return_method'])
def test_missing_metadata_rejected(field):
    spec=dict(SPEC['spy']);spec.pop(field)
    with pytest.raises(ValueError):validate_spec(spec)


def test_nifty_and_commodity_methodology_gates():
    for changes in ({'ticker_or_series':'^NSEI'},{'source':'Yahoo Finance'},{'return_method':ADJUSTED_TOTAL_RETURN}):
        with pytest.raises(ValueError,match='official NSE'):validate_spec(dict(SPEC['nifty50_tri'],**changes))
    for asset in ('dbc','uso','cper','dba'):
        assert SPEC[asset]['futures_roll_accounted']
        with pytest.raises(ValueError,match='rolling-futures'):validate_spec(dict(SPEC[asset],futures_roll_accounted=False))
    with pytest.raises(ValueError,match='non-income'):validate_spec(dict(SPEC['spy'],return_method=DIRECT_PRICE_RETURN))
    p=build(Fetch(),'2026-10-03',assets=[dict(a,futures_roll_accounted=False) if a['id']=='uso' else a for a in ASSETS],nse_fetcher=Fetch())
    assert p['left_out'][0]['id']=='uso' and not any(r['id']=='uso' for g in p['groups'] for r in g['rows'])


def test_observation_quality():
    s=history();assert calculate(s,SPEC['spy'],'2026-10-03')['latest_date']=='2026-10-02'
    with pytest.raises(ValueError,match='stale'):calculate(history(end='2026-09-20'),SPEC['spy'],'2026-10-03')
    with pytest.raises(ValueError,match='stale'):calculate(history(end='2026-10-02',method=DIRECT_PRICE_RETURN),SPEC['bitcoin'],'2026-10-05')
    with pytest.raises(ValueError,match='5 years'):calculate(history(start='2024-01-01'),SPEC['spy'],'2026-10-03')
    with pytest.raises(ValueError,match='monotonic'):calculate(s.iloc[::-1],SPEC['spy'],'2026-10-03')
    doubled=pd.concat([s.iloc[:1],s]);doubled.attrs=s.attrs
    with pytest.raises(ValueError,match='duplicate'):calculate(doubled,SPEC['spy'],'2026-10-03')
    for bad in (float('inf'),-1,0):
        invalid=s.copy();invalid.iloc[-1]=bad
        with pytest.raises(ValueError,match='non-finite or non-positive'):calculate(invalid,SPEC['spy'],'2026-10-03')
    s.loc['2026-10-01']=np.nan;s.loc['2026-10-05']=999
    r=calculate(s,SPEC['spy'],'2026-10-03')
    assert r['anchor_dates']['1D']=='2026-09-30' and r['latest_date']=='2026-10-02'
    assert r['validation']['missing_observations_dropped']==1


def test_unavailable_horizons_off_high_and_spark():
    s=history(start='2024-01-01').drop(pd.Timestamp('2026-09-30'))
    s.iloc[-1]=s.max()*.8
    r=calculate(s,dict(SPEC['spy'],min_history_years=1),'2026-10-03')
    assert r['returns']['3Y'] is None and r['returns']['5Y'] is None
    assert r['off_high']==pytest.approx((s.iloc[-1]/s.max()-1)*100) and r['off_high']<=0
    assert r['high_date']==str(s.idxmax().date())
    recent=s.loc[s.index>=s.index[-1]-pd.Timedelta(weeks=52)]
    expected=recent.groupby(recent.index.to_period('W-FRI')).tail(1)
    assert [p['date'] for p in r['sparkline']]==[str(d.date()) for d in expected.index]
    assert [p['value'] for p in r['sparkline']]==pytest.approx(list(expected/expected.iloc[0]*100))
    assert r['sparkline'][0]['value']==100
    assert r['latest_month_end']=='2026-09-29'
    gap=history().loc[lambda x:~((x.index>='2026-08-20')&(x.index<='2026-09-02'))]
    assert calculate(gap,SPEC['spy'],'2026-10-03')['returns']['1M'] is None


def test_trend_states_and_completed_month():
    s=history();r=calculate(s,SPEC['spy'],'2026-10-03')
    monthly=s.loc[:'2026-09-30'];monthly=monthly.groupby(monthly.index.to_period('M')).tail(1).iloc[-10:]
    assert r['sma_10m']==pytest.approx(monthly.mean()) and r['trend_state']=='uptrend'
    assert r['distance_from_sma_pct']==pytest.approx((monthly.iloc[-1]/monthly.mean()-1)*100)
    down=100000/s;down.attrs=s.attrs
    assert calculate(down,SPEC['spy'],'2026-10-03')['trend_state']=='downtrend'
    s[:]=100
    assert calculate(s,SPEC['spy'],'2026-10-03')['trend_state']=='at trend'
    assert calculate(s,SPEC['spy'],'2026-10-03')['off_high']==0
    gap=s.loc[s.index.to_period('M')!=pd.Period('2026-06')]
    r=calculate(gap,SPEC['spy'],'2026-10-03')
    assert r['trend_state']=='insufficient data' and r['sma_10m'] is None
    r=calculate(history(end='2026-05-29'),SPEC['spy'],'2026-05-31')
    assert r['latest_month_end']=='2026-05-29'


def test_failure_policy_summary_and_schema():
    p=payload(Fetch(['SPY','QQQ','IWM','VGK']))
    assert p['schema_version']==2 and len(p['left_out'])==4 and p['summary']['valid_markets']==24
    assert p['groups'][0]['rows']==[]
    # Six of 28 exceeds 20%; no stale-value substitution.
    with pytest.raises(ValueError,match='20%'):payload(Fetch(['SPY','QQQ','IWM','VGK','EWJ','VEA']))
    p=payload();json.dumps(p,allow_nan=False)
    assert p['summary']['best_1y']['id']=='bitcoin'
    assert p['summary']['worst_1y']['id']=='agg'
    assert [(b['label'],b['valid_markets']) for b in p['summary']['breadth']]==[('Equity',15),('Fixed-income',6)]
    required={'id','label','group','source','source_url','instrument_or_index','ticker_or_series','return_method','latest_date','latest_level','returns','off_high','high_date','trend_state','latest_month_end','sma_10m','distance_from_sma_pct','sparkline'}
    assert all(required<=r.keys() for g in p['groups'] for r in g['rows'])


def test_html_scoping_escaping_metadata_and_values():
    p=payload();r=p['groups'][0]['rows'][0];r['label']='<script>alert("x")</script>';r['source']='<img src=x onerror=x>';r['returns']['1Y']=9999;r['returns']['1D']=-1;r['returns']['1W']=-1
    out=renderers()['_market_matrix_html'](p)
    assert '<script>' not in out and '<img src=x' not in out and '&lt;script&gt;' in out
    assert '+9999.0%' in out and '<svg' in out and 'position:sticky' in out and 'overflow-x:auto' in out
    assert 'background:#ffffff' in out and 'background:#e7eae5' in out and '#f8f0e3' not in out and 'box-shadow' not in out
    assert 'stroke-width="2.4"' in out and 'stroke="#505b64"' in out
    assert 'mmatrix-ticker' not in out and '(SPY)' in out
    assert 'font-size:13px;font-weight:500' in out
    assert 'font-size:14px' in out and 'font-weight:700' in out
    assert 'Cross-Asset Market Performance Matrix</h2>' in out
    assert 'Returns across major global asset classes and markets' not in out
    assert 'border:1.5px solid #87918f' in out
    assert 'thead .mmatrix-name{color:#ffffff;background:#3d4549' in out
    assert 'border-bottom:1px solid #edf0ee' in out
    assert 'border:1px solid rgba' not in out
    for bg in ('#3e6b86', '#8b4057'):
        assert f'background:{bg};color:#ffffff;font-weight:600' in out
    assert 'color:#30393d;font-weight:400' in out
    assert '#181d24' not in out and 'ETF total returns' not in out
    heads=re.findall(r'<th[^>]*scope="col"[^>]*>(.*?)</th>',out)
    assert heads==['Market','52 weeks','1W','1M','YTD','1Y','3Y','5Y','Off high']
    assert 'class="mmatrix-group" colspan="2"' in out
    assert 'class="mmatrix-group-rest" colspan="7"' in out
    assert '.mmatrix-group-rest{background:#e7eae5;' in out
    assert '<col span="7">' in out
    assert set(p['groups'][0]['rows'][0]['returns'])==set(HORIZONS)
    assert '3Y and 5Y are annualised' in out and '>3Y</th>' in out and '>5Y</th>' in out
    assert 'Nifty 50' not in out and 'INDA' in out and 'direct price return' in out
    assert '15 of 15 equity markets' in out and '6 of 6 fixed-income markets' in out
    css=out.split('<style>')[1].split('</style>')[0]
    for selector in re.findall(r'([^{}]+)\{',css):
        if selector.strip().startswith('@media'):continue
        assert all(part.strip().startswith('.mmatrix') for part in selector.split(','))
    p['groups'][0]['rows'][0]['returns']['5Y']=None
    assert '—' in renderers()['_market_matrix_html'](p)


def test_same_edition_loading_and_placement(tmp_path):
    p=payload();ns=renderers();edition=tmp_path/'2026-10-03';edition.mkdir()
    target=edition/'market_matrix.json';target.write_text(json.dumps(p));assert ns['_load_market_matrix'](edition)
    other=tmp_path/'2026-09-27';other.mkdir();assert ns['_load_market_matrix'](other) is None
    p['as_of']='2026-09-27';target.write_text(json.dumps(p));assert ns['_load_market_matrix'](edition) is None
    source=(ROOT/'app.py').read_text();page=source[source.index('def page_weekly()'):source.index('def page_world()')]
    assert page.index('_eh_front_page')<page.index('_render_capped(summary')<page.index('_market_matrix_html')<page.index('st.markdown(headlines')<page.index('for title, section_charts')
    assert 'SUMMARY_CHART' in page
    assert '[("Top Headlines", "nh-title")] if headlines else []' in page
    assert page.index('("Top Headlines", "nh-title")')<page.index('[(title, _anchor("weekly", title))')
    assert 'id="nh-title"' in source
    node=ast.get_source_segment(source,next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_market_matrix_html'))
    assert 'get_charts' not in node and '.png' not in node and 'st.dataframe' not in node


def test_saturday_cli_atomic_write_and_failed_rerun(tmp_path,monkeypatch):
    import generate_market_matrix as cli
    import sys
    edition=tmp_path/'2026-10-10';edition.mkdir();(edition/'chart.png').write_bytes(b'chart')
    real_timestamp=pd.Timestamp
    class SaturdayClock:
        def __new__(cls,value):return real_timestamp(value)
        @staticmethod
        def now(tz=None):return real_timestamp('2026-10-10',tz=tz)
    monkeypatch.setattr(cli.pd,'Timestamp',SaturdayClock)
    monkeypatch.setattr(cli,'YFinanceFetcher',lambda:object())
    p={'groups':[],'left_out':[],'as_of':'2026-10-10'}
    monkeypatch.setattr(cli,'build',lambda fetch,cutoff,**kwargs:p)
    monkeypatch.setattr(sys,'argv',['generate_market_matrix.py','--out',str(edition)])
    assert cli.main()==0
    target=edition/'market_matrix.json'
    assert json.loads(target.read_text())==p and not target.with_suffix('.json.tmp').exists()
    def fail(*args,**kwargs):raise ValueError('threshold exceeded')
    monkeypatch.setattr(cli,'build',fail)
    assert cli.main()==1 and not target.exists()


def test_raw_front_month_oil_cannot_pass_proxy_gate():
    with pytest.raises(ValueError,match='rolling-futures'):
        validate_spec(dict(SPEC['uso'],ticker_or_series='CL=F'))
