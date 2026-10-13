"""Scenarios for the editorial briefing, without running Streamlit at import."""
import ast
import html
import math
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from data.processors.macro_cards import dated_card, india_inflation, market_risk, global_inflation

ROOT = Path(__file__).resolve().parents[1]


def app_functions():
    names = {'_eh_world_answer', '_eh_front_stance', '_eh_state_card', '_eh_result',
             '_eh_number', '_eh_direction', '_eh_front_page'}
    tree = ast.parse((ROOT / 'app.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(math=math, date=date, datetime=datetime, Path=Path,
              _esc=lambda value: html.escape(str(value), quote=True),
              _stance_dir=lambda score: 'hawkish' if score > .05 else 'dovish' if score < -.05 else 'neutral')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec'), ns)
    return ns


def pmi(values, changes, status='ok', month=None):
    month = month or date.today().strftime('%Y-%m')
    return {'scoreboard': [dict(country=code, label=code, cells={'mfg_pmi':
            dict(status=status, value=value, change=change, period=month)})
            for code, value, change in zip(('US','EA','CN'), values, changes)]}


def test_rising_pmi_below_50_is_still_contraction():
    fn = app_functions()['_eh_world_answer']
    result = fn(pmi([48,49,49.5], [1,1,1]), 'mfg_pmi', 'Strengthening', 'Slowing')
    assert result['state'] == 'Strengthening'
    assert 'below 50 indicates contraction' in result['evidence']
    assert 'All are above 50' not in result['evidence']
    assert 'GDP' not in result['evidence']
    assert fn(pmi([55,54,53],[-1,1,0]), 'mfg_pmi','Strengthening','Slowing')['state']=='Mixed'
    assert fn(pmi([55,54,53],[1,None,1]), 'mfg_pmi','Strengthening','Slowing')['state']=='Awaiting data'
    assert fn(pmi([55,54,53],[1,1,1],month='2020-01'), 'mfg_pmi','Strengthening','Slowing')['state']=='Awaiting data'


def test_dated_retained_evidence_is_explicit():
    card=dict(state='Mixed', conclusion='Conflicting signals.', evidence='Dated evidence.', observation_date='2026-10-09')
    assert dated_card(card,date(2026,10,13),14)==card
    for today, failure in [(date(2026,11,1),False),(date(2026,10,13),True),(date(2026,10,1),False)]:
        result=dated_card(card,today,14,failure)
        assert result['state']=='Awaiting data' and result['evidence'].endswith('Dated evidence.')
    assert card['state']=='Mixed'
    assert dated_card(dict(state='Mixed',evidence='Undated.'),date(2026,10,13),14)['state']=='Awaiting data'


def test_rbi_hawkish_hold_and_signed_dates():
    fn=app_functions()['_eh_front_stance']
    result=fn(dict(composite_overall_score=.3, previous_score=-.2, previous_cycle='2026-08-05',
                   policy_cycle=date.today().isoformat(), repo_rate_pct=5.5, rate_action='hold',
                   facts={'stated_stance':'neutral'}))
    assert result['state']=='Hawkish'
    assert '+0.30 from -0.20' in result['evidence'] and 'repo held at 5.50%' in result['evidence']
    assert '05 Aug 2026' in result['evidence'] and 'separate from the rate decision' in result['evidence']
    assert 'hike' not in result['evidence']
    assert fn({})['state']=='Awaiting data'


def test_cpi_base_change_does_not_create_acceleration():
    derived=[dict(month='2026-09',published_headline=5,buckets={'Food':2})]
    items=[dict(month_key=month,item_code='a',yoy=value,base_year=base)
           for month,value,base in [('2026-08',2,'2012'),('2026-09',3,'2024')]]
    result=india_inflation(derived,items)
    assert result['state']=='Awaiting data' and '1/1 items' in result['evidence']
    assert 'Insufficient matched' in result['evidence']


def test_render_six_ordered_accessible_links(tmp_path):
    import json
    ns=app_functions(); rendered=[]
    cards={key:dict(state='Mixed',conclusion='Evidence differs.',evidence='Prepared observations.',
                    observation_date=date.today().isoformat())
           for key in ('risk','commodities','india_activity','india_inflation','global_inflation')}
    folder=tmp_path/'assets';folder.mkdir()
    (folder/'macro_cards.json').write_text(json.dumps(dict(schema_version=1,cards=cards)))
    ns.update(PROJECT_ROOT=tmp_path,json=json, _EH_STYLE='',
              _EH_QUESTIONS=['How is India’s economic activity trending?'],_EH_ANCHORS=['growth','prices'],
              _anchor=lambda domain,title: domain+'-'+title,
              _load_signals=lambda charts: {},get_charts=lambda domain: ([],''),
              _load_world_snapshot=lambda charts: pmi([55,54,53],[1,1,1]),_eh_brief=lambda: {},
              st=SimpleNamespace(markdown=lambda text,**kwargs: rendered.append(text)))
    ns['_eh_front_page']([])
    result=rendered[0]
    assert result.count('<article class="eh-card">')==6
    assert result.count('class="eh-state"')==6 and result.count('class="eh-arrow"')==6
    assert result.count('class="eh-conclusion"')==6 and result.count('<a ')==6
    destinations=['#weekly-Cross-Asset Signals','#weekly-Commodities','/world#global-inflation-breadth',
                  '/india?chart=india-growth-question','/india?chart=india-prices-question','/rbi-sentinel']
    offsets=[result.index('href="'+link+'"') for link in destinations]
    assert offsets==sorted(offsets)
    assert 'aria-hidden="true"' in result and 'aria-level="3"' in result


def test_layout_keeps_original_border_shadow_and_scopes_arrow():
    source=(ROOT/'app.py').read_text()
    assert 'border:2px solid #28251f;' in source and 'box-shadow:4px 4px 0 #28251f;' in source
    assert '.eh-card .eh-arrow {position:absolute;top:20px;right:20px;white-space:nowrap;' in source
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))' in source
    assert '@media(max-width:640px)' in source


def test_generation_is_deterministic_and_missing_market_is_safe():
    assert market_risk({'rows':{}})['state']=='Awaiting data'
    countries=[dict(code=code,series={'headline':[dict(month='2026-05',value=2),
                        dict(month='2026-08',value=value)],'core':[]})
               for code,value in zip(('USA','EA','CHN','JPN','GBR','IND'),(1,1,1,3,3,2))]
    snapshot={'inflation_breadth':{'breadth':{'month':'2026-08','comparison_month':'2026-05'},
                                 'countries':countries}}
    result=global_inflation(snapshot)
    assert result==global_inflation(snapshot) and result['state']=='Mixed'


def test_broad_core_conflict_and_major_headline_classification_change():
    countries=[dict(code=code,aggregate=code=='EA',series={measure:[dict(month='2026-05',value=2,classification='same'),
                        dict(month='2026-08',value=value,classification='same')]
                       for measure,value in [('headline',3),('core',1)]})
               for code in ('USA','EA','CHN','JPN','GBR','IND')]
    snapshot={'inflation_breadth':{'breadth':{'month':'2026-08','comparison_month':'2026-05'},
                                 'countries':countries}}
    result=global_inflation(snapshot)
    assert result['state']=='Mixed' and 'Core rose in 0/5 and eased in 5' in result['evidence']
    assert result['evidence'].index('headline inflation') < result['evidence'].index('Major-economy headline')
    assert 'Core comparisons unavailable for China' not in result['evidence']
    countries[0]['series']['headline'][1]['classification']='changed'
    result=global_inflation(snapshot)
    assert result['state']=='Awaiting data' and 'Headline comparisons unavailable for US' in result['evidence']
