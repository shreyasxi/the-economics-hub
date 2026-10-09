"""Official source identity, observed-date arithmetic, rolling high and edition safety."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from config.india_equity_matrix import INDICES, GROUPS, HORIZONS, SOURCE_PAGE, ENDPOINT, RETURN_METHOD, ARTIFACT, METHOD_NOTE
from data.fetchers.india_equity_tri import parse_response, series_digest, IndiaTRIFetcher
from data.processors.india_equity_matrix import build, calculate, generate, validate_payload
from charts.india_charts.india_equity_matrix import render_html

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2026-10-09'


def history(start='2021-09-25'):
    ds = pd.date_range(start,CUTOFF,freq='B')
    return pd.Series(100*np.exp(np.arange(len(ds))*.0004),index=ds)


def entry(spec, series):
    records = [[str(d.date()),float(v)] for d,v in series.items()]
    return dict(id=spec['id'],label=spec['label'],code=spec['code'],records=records,
                sha256=series_digest(records), source_checks=[dict(date=str(d.date()),level=float(series.loc[d]))
                    for d in (series.index[0],series.index[len(series)//2],series.index[-1])],
                requests=[dict(start='2026-09-01',end=CUTOFF,rows=29,status=200,endpoint=ENDPOINT,
                              parameters=dict(name=spec['code'],indexName=spec['label']))])


def snapshot():
    return dict(schema_version=1,as_of=CUTOFF,fetched_at=CUTOFF+'T18:00:00Z',source_url=SOURCE_PAGE,
                endpoint=ENDPOINT,return_method=RETURN_METHOD,currency='INR',failures=[],
                series=[entry(spec,history()*(1+i*.2)) for i,spec in enumerate(INDICES)])


class IndiaEquityMatrixTests(unittest.TestCase):
    def test_approved_universe_and_no_excluded_rows(self):
        self.assertEqual(len(INDICES),37)
        self.assertEqual([sum(s['group']==g for s in INDICES) for g,_ in GROUPS],[3,3,13,9,7,2])
        forbidden={'Nifty 100','Nifty 200','Nifty Financial Services','Nifty Private Bank','Nifty Healthcare',
                   'Nifty Oil & Gas','Nifty Media','Nifty Commodities','Nifty CPSE','Nifty India Tourism',
                   'Nifty EV & New Age Automotive'}
        self.assertFalse(forbidden & {s['label'] for s in INDICES})

    def test_only_gross_levels_and_exact_identity(self):
        spec=INDICES[0]
        record={'Index Name':spec['label'],'Date':'09 Oct 2026','TotalReturnsIndex':'34219.70','NTR_Value':'1'}
        for payload in ([record],{'d':json.dumps([record])}):
            self.assertEqual(parse_response(payload,spec,CUTOFF,CUTOFF).iloc[0],34219.7)
        for bad in ({'Index Name':'Nifty 500'}, {'TotalReturnsIndex':'0'}, {'TotalReturnsIndex':'NaN'}, {'Date':'12 Oct 2026'}):
            with self.assertRaises(ValueError):parse_response([dict(record,**bad)],spec,CUTOFF,CUTOFF)
        del record['TotalReturnsIndex'];record['Close']='34219.70'
        with self.assertRaisesRegex(ValueError,'Gross'):parse_response([record],spec,CUTOFF,CUTOFF)

    def test_duplicate_source_and_window_limit(self):
        r={'Index Name':INDICES[0]['label'],'Date':'09 Oct 2026','TotalReturnsIndex':'1'}
        with self.assertRaisesRegex(ValueError,'Duplicate'):parse_response([r,r],INDICES[0],CUTOFF,CUTOFF)
        with self.assertRaisesRegex(ValueError,'365'):IndiaTRIFetcher(client=object(),pause=0).window(INDICES[0],'2024-01-01','2026-01-01')

    def test_common_dates_cagr_and_percentage_point_excess(self):
        snap=snapshot(); peer=history()**1.4
        snap['series'][1]=entry(INDICES[1],peer.drop(pd.Timestamp('2025-10-09')))
        p=build(snap,CUTOFF);rows=[r for g in p['groups'] for r in g['rows']]
        self.assertEqual(p['relative_anchor'],'2025-10-08')
        self.assertTrue(all(r['anchor_dates']['1Y']['date']=='2025-10-08' for r in rows))
        ratio=peer.loc[CUTOFF]/peer.loc['2025-10-08']
        self.assertAlmostEqual(rows[1]['returns']['1Y'],(ratio-1)*100)
        self.assertAlmostEqual(rows[1]['vs_nifty50_1y'],rows[1]['returns']['1Y']-rows[0]['returns']['1Y'])
        self.assertEqual(rows[0]['vs_nifty50_1y'],0)
        for horizon,years in [('3Y',3),('5Y',5)]:
            a=rows[1]['anchor_dates'][horizon];elapsed=(pd.Timestamp(CUTOFF)-pd.Timestamp(a['date'])).days
            self.assertAlmostEqual(rows[1]['returns'][horizon],((peer.loc[CUTOFF]/a['level'])**(365.25/elapsed)-1)*100)
        self.assertIsNone(rows[1]['off_5y_high'])  # the missing day may have held the peak

    def test_common_latest_and_no_lookahead(self):
        snap=snapshot();snap['series'][1]=entry(INDICES[1],history().iloc[:-1])
        p=build(snap,CUTOFF)
        self.assertEqual(p['as_of'],'2026-10-08')
        self.assertTrue(all(r['latest_date']==p['as_of'] for g in p['groups'] for r in g['rows']))
        bad=snapshot();bad['series'][0]['records'].append(['2026-10-12',999]);bad['series'][0]['sha256']=series_digest(bad['series'][0]['records'])
        with self.assertRaisesRegex(ValueError,'future'):build(bad,CUTOFF)

    def test_rolling_peak_excludes_older_all_time_high(self):
        s=history('2020-01-01');s.loc['2020-10-01']=10000;s.loc['2022-03-15']=500
        r=calculate(s,INDICES[0],pd.Timestamp(CUTOFF),s.index,pd.Timestamp('2025-10-09'))
        self.assertEqual(r['high_5y_date'],'2022-03-15')
        self.assertAlmostEqual(r['off_5y_high'],(s.loc[CUTOFF]/500-1)*100)
        self.assertNotAlmostEqual(r['off_5y_high'],(s.loc[CUTOFF]/10000-1)*100)
        self.assertEqual(r['high_5y_start'],'2021-10-09')

    def test_missing_horizons_and_distant_anchors_are_dashes(self):
        s=history('2024-01-01')
        r=calculate(s,INDICES[0],pd.Timestamp(CUTOFF),s.index,pd.Timestamp('2025-10-09'))
        self.assertIsNone(r['returns']['3Y']);self.assertIsNone(r['returns']['5Y']);self.assertIsNone(r['off_5y_high'])
        s=s.drop(s.loc['2026-08-25':'2026-09-09'].index)
        r=calculate(s,INDICES[0],pd.Timestamp(CUTOFF),s.index,pd.Timestamp('2025-10-09'))
        self.assertIsNone(r['returns']['1M'])
        self.assertTrue(all('2026-08-25' > x['date'] or x['date'] > '2026-09-09' for x in r['sparkline']))

    def test_source_corruption_and_method_mismatch_rejected(self):
        for mutate in (lambda s:s.update(currency='USD'),lambda s:s.update(return_method='price return'),
                       lambda s:s['series'][0]['records'][-1].__setitem__(1,1)):
            s=snapshot();mutate(s)
            with self.assertRaises(ValueError):build(s,CUTOFF)

    def test_failures_preserve_rows_but_never_metrics(self):
        snap=snapshot();gone=snap['series'].pop(4);snap['failures']=[dict(id=gone['id'],reason='source unavailable')]
        p=build(snap,CUTOFF);rows=[r for g in p['groups'] for r in g['rows']]
        self.assertEqual(len(rows),37);self.assertEqual(rows[4]['status'],'unavailable')
        self.assertTrue(all(x is None for x in rows[4]['returns'].values()))
        snap=snapshot();gone=snap['series'].pop(0);snap['failures']=[dict(id=gone['id'],reason='missing')]
        with self.assertRaisesRegex(ValueError,'Nifty 50'):build(snap,CUTOFF)
        snap=snapshot();gone=snap['series'][0:8];snap['series']=snap['series'][8:];snap['series'].insert(0,gone[0])
        snap['failures']=[dict(id=e['id'],reason='missing') for e in gone[1:]]
        # Seven unavailable is permitted, eight is not.
        build(snap,CUTOFF)
        lost=snap['series'].pop();snap['failures'].append(dict(id=lost['id'],reason='missing'))
        with self.assertRaisesRegex(ValueError,'20%'):build(snap,CUTOFF)

    def test_stale_and_failed_refresh_cannot_leave_an_old_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'2026-10';out.mkdir();source=root/'source.json';source.write_text(json.dumps(snapshot()))
            self.assertTrue(generate(out,source,CUTOFF))
            with patch.dict('os.environ',{'NSE_EQUITY_UPDATE_FAILED':'true'}):
                self.assertIsNone(generate(out,source,CUTOFF))
            self.assertFalse((out/ARTIFACT).exists())
            self.assertIsNone(generate(out,source,'2026-10-20'))
            self.assertIsNone(generate(root/'2026-11',source,CUTOFF))

    def test_render_approved_columns_scroll_and_methodology(self):
        p=build(snapshot(),CUTOFF);content=render_html(p)
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(content,'html.parser')
        self.assertEqual([th.get_text() for th in soup.select('thead th')],
                         ['Index','52 weeks','1W','1M','YTD','1Y','vs Nifty 50','3Y','5Y','Off 5Y high'])
        self.assertEqual(len(soup.select('tr.iem-row')),37)
        self.assertEqual(len(soup.select('svg')),37)
        self.assertEqual(soup.select_one('.iem-method').get_text(),METHOD_NOTE)
        self.assertIn('overflow-x:auto',content);self.assertIn('position:sticky',content)
        self.assertIn(' pp',content);self.assertIn('52 weeks of gross TRI',content)
        p['groups'][0]['rows'][1]['vs_nifty50_1y']=123
        with self.assertRaisesRegex(ValueError,'Relative-return'):render_html(p)

    def test_equity_page_placement_with_and_without_valuations(self):
        source=(ROOT/'app.py').read_text();tree=ast.parse(source)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='page_india')
        # Exercise the actual equity section, independent of Streamlit and unrelated charts.
        equity_if=next(n for n in ast.walk(node) if isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='equity')
        fragment=ast.Module(body=equity_if.body,type_ignores=[]);ast.fix_missing_locations(fragment)
        for include_valuations in (True,False):
            names=['23_india_sector_rotation_12m_benchmark.png','21_india_risk_appetite.png','03_india_fpi_monthly.png']
            if include_valuations:names.append('22_india_sector_valuations.png')
            calls=[]
            class St:
                def markdown(self,*a,**k):pass
            ns=dict(st=St(),equity=[Path('/tmp/2026-10')/n for n in names],answers={5:''},
                    _eh_question_header=lambda *a:'',_render_grid=lambda cs:calls.extend(p.name for p in cs),
                    _render_india_equity_matrix=lambda p:calls.append('MATRIX'))
            exec(compile(fragment,'app.py','exec'),ns)
            self.assertEqual(calls[:3],['03_india_fpi_monthly.png','21_india_risk_appetite.png','MATRIX'])
            self.assertEqual(calls[-1],'23_india_sector_rotation_12m_benchmark.png')
            if include_valuations:self.assertEqual(calls[3],'22_india_sector_valuations.png')


if __name__ == '__main__':unittest.main()
