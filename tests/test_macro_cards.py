from data.processors.macro_cards import market_risk, global_inflation, india_activity, india_inflation


def test_equity_count_cannot_outvote_credit_pillar():
    equity = ('sp500','stoxx50','ftse100','nikkei','hangseng','shanghai','nifty50','korea','taiwan')
    signals = {'as_of':'2026-10-09', 'rows':
               {k:dict(quarter=10,month=2) for k in equity + ('us_ig','us_hy','em_corp')}}
    signals['rows']['vix']=dict(median_20d=16,percentile=30,month_change_pct=-10)
    result = market_risk(signals)
    assert result['state'] == 'Mixed'
    assert '9/9' in result['evidence'] and '3/3 credit spreads widened' in result['evidence']
    assert '09 Oct 2026' in result['evidence']


def test_commodity_surge_cannot_override_risk_off_and_low_vix_is_not_weekly_change():
    from data.processors.market_regime import EQUITIES,CREDIT,COMMODITIES
    rows={k:dict(quarter=-10,month=-4) for k in EQUITIES}
    rows.update({k:dict(quarter=30,month=10) for k in CREDIT})
    rows.update({k:dict(quarter=40,month=20) for k in COMMODITIES})
    rows['vix']=dict(median_20d=30,percentile=90,month_change_pct=10)
    result=market_risk(dict(as_of='2026-10-09',rows=rows))
    assert result['state']=='Risk-off'
    assert 'Copper +40.0%' in result['evidence']
    # A persistently low volatility level qualifies separately from its recent change.
    rows['vix'].update(median_20d=15,percentile=20,month_change_pct=-30)
    assert market_risk(dict(as_of='2026-10-09',rows=rows))['state']=='Mixed'


def test_market_returns_use_calendar_anchors_and_reject_missing_annual_vix_history():
    import pandas as pd
    from data.processors.market_regime import prepare
    dates=pd.to_datetime(['2026-07-09','2026-09-09','2026-10-09'])
    result=prepare({'sp500':pd.Series([100,110,120],index=dates),
                    'us_hy':pd.Series([3,3.1,3.2],index=dates),
                    'vix':pd.Series([10,12,15],index=dates)},'2026-10-09')
    assert abs(result['rows']['sp500']['quarter']-20)<1e-8
    assert abs(result['rows']['us_hy']['quarter']-20)<1e-8
    assert 'vix' in result['missing']
    assert not prepare({'sp500':pd.Series([100,120],index=dates[[1,2]])},'2026-10-09')['rows']


def test_global_breadth_excludes_aggregate_and_missing_comparisons():
    def country(aggregate=False, complete=True):
        return {'aggregate':aggregate,'series':{'headline':[
            {'month':'2026-05','value':4}, {'month':'2026-08','value':3}] if complete else
            [{'month':'2026-08','value':3}], 'core':[]}}
    snapshot={'inflation_breadth':{'breadth':{'month':'2026-08','comparison_month':'2026-05'},
                                 'countries':[country() for _ in range(4)] + [country(complete=False),country(True)]}}
    result=global_inflation(snapshot)
    assert result['state']=='Easing' and '4/4 countries' in result['evidence']
    snapshot['inflation_breadth']['countries'].append(country(complete=False))
    assert global_inflation(snapshot)['state']=='Awaiting data'


def test_expansion_and_momentum_are_distinct_and_no_gdp():
    rows=[dict(month='2026-08',india_mfg_pmi=55,india_svc_pmi=56),
          dict(month='2026-09',india_mfg_pmi=54,india_svc_pmi=55)]
    result=india_activity(rows,[],{})
    assert result['state']=='Expanding' and 'losing momentum' in result['evidence']
    assert 'GDP' not in result['evidence']
    rows[0]['month']='2026-07'
    assert 'momentum' not in india_activity(rows,[],{})['evidence']


def test_price_level_breadth_is_separate_from_inflation_acceleration():
    derived=[dict(month='2026-08',published_headline='5',buckets={'Food':'2'}),
             dict(month='2026-09',published_headline='4',buckets={'Food':'2'})]
    items=[dict(item_code=str(i),month_key=month,yoy=value)
           for i in range(3) for month,value in [('2026-08',3),('2026-09',2)]]
    result=india_inflation(derived,items)
    assert result['state']=='Cooling'
    assert '3/3 items' in result['evidence'] and 'accelerated in 0/3' in result['evidence']
    assert 'unweighted' in result['evidence'] and 'weighted contributions' in result['evidence']
    items=[r for r in items if r['month_key']=='2026-09']
    assert india_inflation(derived,items)['state']=='Awaiting data'


def test_major_economies_can_challenge_country_breadth_and_use_same_month():
    countries=[]
    for code in ('USA','EA','CHN','JPN','GBR','IND'):
        series=[{'month':'2026-05','value':2},{'month':'2026-08','value':3},
                {'month':'2026-09','value':1}]
        countries.append(dict(code=code,aggregate=code=='EA',series={'headline':series,'core':[]}))
    countries += [dict(code=str(i),aggregate=False,series={'headline':[
        {'month':'2026-05','value':3},{'month':'2026-08','value':2}], 'core':[]}) for i in range(20)]
    result=global_inflation({'inflation_breadth':{'breadth':{'month':'2026-08','comparison_month':'2026-05'},
                                               'countries':countries}})
    assert result['state']=='Mixed'
    assert 'Major-economy headline rose' in result['evidence']
    assert 'Country breadth and major economies diverge' in result['evidence']
    assert len(result['metrics'])==6
    assert all(m['period']=='2026-08' and m['change']==1 for m in result['metrics'])


def test_domain_refresh_preserves_other_cards_and_failure_keeps_dated_snapshot(monkeypatch,tmp_path):
    import json
    import generate_macro_cards as generator
    folder=tmp_path/'assets/macro/2026-10'
    folder.mkdir(parents=True)
    (folder/'world_snapshot.json').write_text('{}')
    destination=tmp_path/'assets/macro_cards.json'
    risk={'state':'Mixed','evidence':'Market snapshot through 09 Oct 2026.'}
    destination.write_text(json.dumps(dict(schema_version=1,cards={'risk':risk},editions={})))
    monkeypatch.setattr(generator,'ROOT',tmp_path)
    monkeypatch.setattr(generator,'latest',lambda domain:folder)
    expected={'state':'Easing','evidence':'Aug 2026 compared with May 2026.'}
    monkeypatch.setattr(generator,'global_inflation',lambda snapshot:expected)
    assert not generator.generate(destination,scope='world')
    payload=json.loads(destination.read_text())
    assert payload['cards']['risk']==risk
    assert payload['cards']['global_inflation']==expected
    def failed(snapshot): raise ValueError('Source unavailable')
    monkeypatch.setattr(generator,'global_inflation',failed)
    assert generator.generate(destination,scope='world')=={'world':'ValueError'}
    assert json.loads(destination.read_text())['cards']['global_inflation']==expected


def test_workflows_refresh_and_publish_only_their_card_domains():
    from pathlib import Path
    import yaml
    root=Path(__file__).resolve().parents[1]
    for name,scope in [('weekly','markets'),('macro','world'),('india','india')]:
        source=(root/'.github/workflows'/f'{name}.yml').read_text()
        workflow=yaml.safe_load(source)
        steps=next(iter(workflow['jobs'].values()))['steps']
        refresh=next(s for s in steps if 'generate_macro_cards.py' in s.get('run',''))
        assert f'--publish --only {scope}' in refresh['run']
        assert refresh['continue-on-error'] is True
        commit=next(s for s in steps if 'git add -A' in s.get('run',''))
        assert 'assets/macro_cards.json' in commit['run']
