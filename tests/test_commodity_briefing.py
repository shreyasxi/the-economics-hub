from datetime import date
import pandas as pd
from data.processors.market_regime import prepare_commodities, COMMODITY_BASKET
from data.processors.macro_cards import commodities, dated_card


def inputs(above=10, previous=8, quarter=10, month=3):
    return dict(as_of='2026-10-09',members=[dict(ticker=k,above_200d=i<above,previous_above_200d=i<previous)
                for i,k in enumerate(COMMODITY_BASKET)],rows={k:dict(quarter=quarter,month=month)
                for k in ('brent','copper','gold')})


def test_combines_breadth_price_direction_and_brent_pressure():
    result=commodities(inputs())
    assert result['state']=='Broad gains'
    assert '10/13' in result['evidence'] and '8/13' in result['evidence']
    assert 'Brent adds energy cost pressure' in result['conclusion']
    assert 'copper +10.0%' in result['evidence'] and 'gold +10.0%' in result['evidence']
    assert result['evidence'].startswith('10/13 futures are currently above')
    assert result['observation_date']=='2026-10-09' and 'Through' not in result['evidence']
    assert 'WTI' not in result['evidence']
    assert 'CPI pass-through' in result['evidence']


def test_oil_surge_and_gold_cannot_establish_broad_demand():
    data=inputs(above=3,previous=2)
    data['rows']['brent']['quarter']=40
    data['rows']['gold']['quarter']=20
    data['rows']['copper']['quarter']=-5
    result=commodities(data)
    assert result['state']=='Mixed' and 'concentrated' in result['conclusion']
    assert 'do not establish demand' in result['evidence']


def test_above_average_is_not_same_as_rising_recently():
    result=commodities(inputs(above=12,previous=13,quarter=-5,month=-2))
    assert result['state']=='Mixed'
    assert 'uptrends are widespread' in result['conclusion']
    assert 'Brent eases energy cost pressure' in result['conclusion']
    assert commodities(inputs(above=2,previous=4,quarter=-5,month=-2))['state']=='Broad declines'
    data=inputs();data['rows']['brent']['month']=-5
    assert 'recent direction is uneven' in commodities(data)['conclusion']


def test_partial_stale_and_deterministic_inputs():
    data=inputs();assert commodities(data)==commodities(data)
    data['members']=data['members'][:11]
    assert commodities(data)['state']=='Awaiting data'
    assert dated_card(commodities(inputs()),date(2026,11,1),14)['state']=='Awaiting data'
    data=inputs();data['rows']['brent']['quarter']=float('nan')
    assert commodities(data)['state']=='Awaiting data'


def test_preparation_uses_observed_history_and_excludes_future_prices():
    dates=pd.bdate_range('2025-08-01','2026-10-13')
    histories={k:pd.Series(range(100,100+len(dates)),index=dates,dtype=float) for k in COMMODITY_BASKET}
    for series in histories.values(): series.loc['2026-10-13']=99999
    result=prepare_commodities(histories,'2026-10-09')
    assert len(result['members'])==13 and not result['missing']
    assert all(m['above_200d'] for m in result['members'])
    assert result['rows']['brent']['observation']=='2026-10-09'
    assert result['rows']['brent']['latest']<99999
    assert commodities(result)['state']=='Broad gains'
    histories['BZ=F']=histories['BZ=F'].iloc[:100]
    assert commodities(prepare_commodities(histories,'2026-10-09'))['state']=='Awaiting data'


def test_commodity_refresh_failure_does_not_block_risk_or_disappear_on_world_refresh(monkeypatch,tmp_path):
    import json
    import generate_macro_cards as generator
    import data.processors.market_regime as regime
    folder=tmp_path/'assets/weekly/2026-10-12';folder.mkdir(parents=True)
    destination=tmp_path/'preview.json'
    old=commodities(inputs())
    destination.write_text(json.dumps(dict(schema_version=1,cards={'commodities':old},
                            editions={},market_inputs={'as_of':'2026-10-09'})))
    monkeypatch.setattr(generator,'ROOT',tmp_path)
    monkeypatch.setattr(generator,'latest',lambda domain:folder)
    monkeypatch.setattr(generator,'MARKET_INPUTS',tmp_path/'absent')
    monkeypatch.setattr(generator,'market_risk',lambda data: dict(state='Mixed',evidence='Valid risk.'))
    def failed(as_of): raise ValueError('Commodity source unavailable')
    monkeypatch.setattr(regime,'fetch_commodities',failed)
    assert generator.generate(destination,scope='markets',refresh_commodities=True)=={'commodities':'ValueError'}
    payload=json.loads(destination.read_text())
    assert payload['cards']['risk']['evidence']=='Valid risk.' and payload['cards']['commodities']==old
    (folder/'world_snapshot.json').write_text('{}')
    monkeypatch.setattr(generator,'global_inflation',lambda data: dict(state='Mixed',evidence='World evidence.'))
    assert generator.generate(destination,scope='world')=={}
    assert json.loads(destination.read_text())['refresh_errors']=={'commodities':'ValueError'}


def curve(spread=7,previous=5):
    return dict(as_of='2026-10-09',spread=spread,previous_spread=previous,
                observation='2026-10-09',comparison_date='2026-09-09',
                contracts=[dict(maturity='2026-11'),dict(maturity='2027-05')])


def test_curve_confirms_or_challenges_price_pressure():
    data=inputs();data['oil_curve']=curve()
    result=commodities(data)
    assert result['state']=='Broad gains' and 'premium has widened' in result['conclusion']
    assert 'WTI near–six-month spread +7.00 $/bbl (+5.00' in result['evidence']
    assert 'Brent moved' not in result['evidence']
    data['oil_curve']=curve(7,15)
    result=commodities(data)
    assert result['state']=='Mixed' and 'premium has narrowed' in result['conclusion']
    assert 'less prompt tightness' in result['evidence']
    data['oil_curve']=curve(-3,-2)
    result=commodities(data)
    assert result['state']=='Mixed' and 'no prompt premium' in result['evidence']
    data['oil_curve']=curve(.1,.1)
    assert 'broadly flat' in commodities(data)['evidence']
    data['oil_curve']['as_of']='2026-09-01'
    assert 'Oil curve unavailable' in commodities(data)['evidence']


def test_oil_curve_compares_same_contracts_on_common_dates():
    from data.processors.market_regime import prepare_oil_curve,oil_curve_contracts
    specs=oil_curve_contracts('2026-10-09')
    assert [s['maturity'] for s in specs]==['2026-11','2027-05']
    dates=pd.to_datetime(['2026-09-09','2026-10-08','2026-10-09','2026-10-13'])
    histories={specs[0]['ticker']:pd.Series([95,92,93,9999],index=dates),
               specs[1]['ticker']:pd.Series([80,86,87,9999],index=dates)}
    result=prepare_oil_curve(histories,'2026-10-09')
    assert result['spread']==6 and result['previous_spread']==15 and result['change']==-9
    assert result['state']=='Backwardation' and result['observation']=='2026-10-09'
    histories[specs[1]['ticker']]=histories[specs[1]['ticker']].drop(pd.Timestamp('2026-10-09'))
    result=prepare_oil_curve(histories,'2026-10-09')
    assert result['observation']=='2026-10-08' and result['spread']==6
    histories[specs[1]['ticker']]=histories[specs[1]['ticker']].drop(pd.Timestamp('2026-09-09'))
    assert prepare_oil_curve(histories,'2026-10-09')['state']=='Unavailable'
