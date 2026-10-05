"""Audited official observations; synthetic responses only test failure mechanics."""
import ast
import calendar
import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data import cpi_contributions as cpi
from data.fetchers import mospi_cpi as collector
from charts import india_cpi_contributions as chart
import matplotlib.pyplot as plt

FIXTURE = Path(__file__).parent/'fixtures'/'cpi'/'official_2025_2026.json'
ROWS = json.loads(FIXTURE.read_text())
EXPECTED = [
    [.7808,.2554,.0078,.2567,.2450,1.1971,2.74],
    [1.2224,.2650,-.0043,.2436,.2283,1.2572,3.21],
    [1.3485,.3432,0,.2414,.2188,1.2439,3.40],
    [1.4545,.3008,-.0009,.2561,.2075,1.2611,3.48],
    [1.6483,.3034,.1528,.2799,.1927,1.3505,3.93],
    [1.8464,.3481,.3741,.3079,.2004,1.2993,4.38],
    [1.9346,.3743,.3830,.3255,.2050,1.2275,4.45],
    [2.0938,.4512,.3951,.3490,.2071,1.3218,4.82]]


def metadata():
    return [dict(state=[dict(state_code=1,state_name='All India')],
        sector=[dict(sector_code=3,sector_name='Combined')],
        division=[dict(division_code=0,division_name=cpi.GENERAL)]+
            [dict(division_code=i,division_name=n) for i,(_,n,_) in enumerate(cpi.DIVISIONS,1)],
        month=[dict(month_code=i,month_name=calendar.month_name[i]) for i in range(1,13)],
        year=[dict(year='2026',series='Current')])]


class Response:
    status_code = 200
    def __init__(self, value):
        self.content = cpi.encoded(value)
    def json(self):
        return json.loads(self.content)
    def raise_for_status(self):
        pass


class Session:
    def __init__(self, revised=False):
        self.calls, self.revised = [], revised
    def get(self,url,params,timeout):
        self.calls.append((url,params))
        if url == collector.FILTER_URL:
            return Response(metadata())
        if params['division_code']=='0':
            raw = [r for r in ROWS if r['division']==cpi.GENERAL and r['year']=='2026']
        else:
            raw = copy.deepcopy([r for r in ROWS if r['year']==params['year'] and
                list(calendar.month_name).index(r['month'])==params['month_code']])
            if self.revised and params['month_code']==7:
                next(r for r in raw if r['code']=='04')['index']='105.01'
            # Exercise seven full API pages without fabricating production data.
            lower = dict(raw[1],group='test lower-level group')
            raw += [dict(lower) for _ in range(655)]
        page, limit = params['page'], params['limit']
        return Response(dict(statusCode=True,data=raw[(page-1)*limit:page*limit],
            meta_data=dict(totalRecords=len(raw),totalPages=(len(raw)+99)//100,
                           page=page,recordPerPage=100)))


class CPITests(unittest.TestCase):
    def test_locked_weights_mapping_and_scope(self):
        cfg = cpi.configuration()
        self.assertEqual(collector.FILTERS,dict(base_year='2024',series='Current',state_code=1,sector_code=3))
        self.assertEqual(sum(Decimal(w) for _,_,w in cpi.DIVISIONS),Decimal('99.9999999999997700'))
        self.assertEqual(cfg['weights_percent']['01']['weight'],'36.7531063101009000')
        self.assertEqual(sorted(c for group in cpi.BUCKETS.values() for c in group),sorted(c for c,_,_ in cpi.DIVISIONS))
        with patch.dict(cpi.BUCKETS,{'Food':('01','02')}):
            with self.assertRaises(ValueError): cpi.configuration()

    def test_numeric_strings(self):
        self.assertEqual(cpi.numeric('108.74'),Decimal('108.74'))
        for value in (None,108.74,'',' 108.74','NaN','Infinity','abc'):
            with self.subTest(value=value), self.assertRaises(ValueError): cpi.numeric(value)

    def test_exact_hierarchy_scope_duplicates_missing_schema(self):
        self.assertEqual(len(cpi.select_aggregates(ROWS)),260)
        for field in cpi.HIERARCHY:
            lower = dict(ROWS[1],**{field:''})
            self.assertEqual(len(cpi.select_aggregates(ROWS+[lower])),260)
            with self.assertRaisesRegex(ValueError,'leakage'): cpi.validate(ROWS+[lower])
        for change in ({'state':'Delhi'},{'sector':'Urban'},{'base_year':'2012'},{'code':'12'},{'index':None}):
            rows = copy.deepcopy(ROWS); rows[1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): cpi.select_aggregates(rows)
        with self.assertRaisesRegex(ValueError,'duplicate'): cpi.validate(ROWS+[ROWS[0]])
        with self.assertRaisesRegex(ValueError,'exact 12 divisions'): cpi.validate(ROWS[1:])
        rows = copy.deepcopy(ROWS); del rows[0]['group']
        with self.assertRaisesRegex(ValueError,'schema'): cpi.select_aggregates(rows)

    def test_regression_formula_rounding_negative(self):
        derived = cpi.calculate(ROWS)
        for row,expected in zip(derived,EXPECTED):
            self.assertEqual(len(row['buckets']),6)
            for actual,wanted in zip(row['buckets'].values(),expected):
                self.assertAlmostEqual(float(actual),wanted,delta=.000051)
            self.assertEqual(float(row['published_headline']),expected[-1])
            self.assertLessEqual(abs(Decimal(row['residual_general'])),Decimal(row['allowed_general_residual']))
            self.assertLessEqual(abs(Decimal(row['residual_published'])),Decimal(row['allowed_published_residual']))
            self.assertAlmostEqual(sum(map(float,row['buckets'].values())),float(row['contribution_total']),places=12)
        aug = derived[-1]
        self.assertAlmostEqual(float(aug['contribution_total']),4.81814275034493,places=12)
        self.assertAlmostEqual(float(aug['divisions']['13']['contribution_pp']),.799320725,places=8)
        self.assertNotAlmostEqual(float(aug['divisions']['13']['contribution_pp']),float(cpi.DIVISIONS[-1][2])*15.17/100,places=3)
        self.assertLess(float(derived[1]['buckets']['Transport']),0)
        rows = copy.deepcopy(ROWS); rows[1]['index']='200.00'
        with self.assertRaisesRegex(ValueError,'RECONCILIATION FAILED'): cpi.calculate(rows)
        with self.assertRaises(ValueError): cpi.calculate([r for r in ROWS if cpi.period(r)!='2025-01'])

    def seed(self,root,official_rows=None):
        official_rows = ROWS if official_rows is None else official_rows
        retrieval = collector.Retrieval(root,None)
        retrieval.capture('fixture:official',{},cpi.encoded(official_rows),kind='manual')
        rows = [dict(r,source_retrieval=retrieval.id) for r in official_rows]
        return collector.store(root,rows,cpi.calculate(rows),retrieval.seal(True),[],'test_fixture')

    def test_new_official_month_advances_without_changing_source_values(self):
        # Start from the real archive through July; make the already-audited
        # August observations newly available. No upstream value is fabricated.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.seed(root,[r for r in ROWS if cpi.period(r)<'2026-08'])
            result=collector.update(root,session=Session())
            rows,derived,_=cpi.load_current(root)
            self.assertEqual(result['latest_month'],'2026-08')
            self.assertEqual(len(derived),8)
            self.assertEqual(derived[-1]['published_headline'],'4.82')
            self.assertEqual(sorted(cpi.encoded({k:r[k] for k in cpi.FIELDS}) for r in rows),
                             sorted(cpi.encoded(r) for r in ROWS))

    def test_incremental_pagination_revision_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first = self.seed(root)
            old_blobs = {p:p.read_bytes() for p in (root/'raw'/'blobs').glob('*')}
            session = Session()
            result = collector.update(root,session=session)
            self.assertEqual(result['api_request_count'],16)
            self.assertEqual(result['revision_count'],0)
            requested = [p for u,p in session.calls if u==cpi.API_URL and p['division_code']!='0']
            self.assertEqual({p['month_code'] for p in requested},{7,8})
            self.assertEqual({p['limit'] for p in requested},{100})
            rows,_,_ = cpi.load_current(root)
            revised = Session(True)
            # Small real-index revision stays within the legitimate rounding gate.
            july = next(r for r in ROWS if cpi.period(r)=='2026-07' and r['code']=='04')
            new_value = str(Decimal(july['index'])+Decimal('.01'))
            original_get = revised.get
            def revision_get(url,params,timeout):
                response = original_get(url,params,timeout)
                if url==cpi.API_URL and params.get('month_code')==7:
                    payload=response.json()
                    for r in payload['data']:
                        if r.get('code')=='04' and all(r[k] is None for k in cpi.HIERARCHY): r['index']=new_value
                    return Response(payload)
                return response
            revised.get=revision_get
            result = collector.update(root,session=revised)
            self.assertEqual(result['revision_count'],1)
            current,_,_=cpi.load_current(root)
            self.assertEqual(next(r for r in current if cpi.period(r)=='2026-07' and r['code']=='04')['index'],new_value)
            for path,blob in old_blobs.items(): self.assertEqual(path.read_bytes(),blob)
            self.assertTrue((root/'runs'/first['run_id']/'normalized.json').exists())
            self.assertEqual(cpi.verify_archive(root)['validated_runs'],3)
            orphan=root/'raw'/'blobs'/(cpi.sha(b'unreferenced snapshot')+'.bin')
            orphan.write_bytes(b'changed bytes')
            with self.assertRaisesRegex(ValueError,'historical raw response checksum'): cpi.verify_archive(root)
            orphan.unlink()
            blob = next((root/'raw'/'blobs').glob('*')); blob.write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError,'checksum'): cpi.load_current(root)

    def test_failure_omits_stale_chart_and_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'data'; self.seed(root)
            output = Path(directory)/'output'; output.mkdir()
            png=output/(chart.NAME+'.png'); png.write_bytes(b'stale')
            with patch.object(collector,'discover_latest',side_effect=ValueError('source unavailable')):
                with self.assertRaises(ValueError): collector.update(root,session=Session())
            self.assertIsNone(chart.generate(output,root)); self.assertFalse(png.exists())
            self.assertEqual(json.loads((root/'last_attempt.json').read_text())['status'],'failed')
            cpi.load_current(root,ready=False)  # Previous vintage remains auditable.

    def test_truncated_page_and_metadata_code_drift_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            session=Session(); original=session.get
            def truncated(url,params,timeout):
                response=original(url,params,timeout)
                if url==cpi.API_URL:
                    payload=response.json(); payload['data']=payload['data'][:-1]
                    return Response(payload)
                return response
            session.get=truncated
            retrieval=collector.Retrieval(Path(directory),session)
            with self.assertRaisesRegex(ValueError,'truncated'):
                collector.fetch_pages(retrieval,dict(year='2026',month_code=8,division_code='0,1'))
            self.assertTrue(list((Path(directory)/'raw'/'request_records').glob('*/*.json')))
            bad=metadata(); bad[0]['state'][0]['state_code']=99
            with patch.object(retrieval,'get',return_value=bad):
                with self.assertRaisesRegex(ValueError,'All India metadata'): collector.discover_latest(retrieval)

    def test_explicit_manual_import_matches_official_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            import openpyxl
            root=Path(directory)/'store'
            export=Path(directory)/'official_fixture.xlsx'
            book=openpyxl.Workbook(); book.active.title='CPI Data'
            book.active.append(cpi.FIELDS)
            for row in ROWS: book.active.append([row[k] for k in cpi.FIELDS])
            book.save(export); book.close()
            collector.update(root,file=export,session=Session())
            rows,derived,manifest=cpi.load_current(root)
            self.assertEqual(manifest['mode'],'explicit_manual_import')
            self.assertEqual(manifest['api_request_count'],0)
            self.assertEqual(sorted(cpi.encoded({k:r[k] for k in cpi.FIELDS}) for r in rows),
                             sorted(cpi.encoded(r) for r in ROWS))
            self.assertEqual(derived[-1]['published_headline'],'4.82')

    def test_chart_single_axis_six_stacks_sign_and_start(self):
        derived=cpi.calculate(ROWS)
        for variant in ('line','markers'):
            fig=chart.figure(derived,variant); ax=fig.axes[0]
            self.assertEqual(len(fig.axes),1)
            self.assertEqual(len(ax.containers),6)
            self.assertEqual(len(ax.patches),48)
            self.assertTrue(any(p.get_height()<0 and p.get_y()<=0 for p in ax.patches))
            self.assertIn('Jan\n2026',[t.get_text() for t in ax.get_xticklabels()])
            line=next(l for l in ax.lines if l.get_label()=='Published headline CPI')
            self.assertEqual(float(line.get_ydata()[-1]),4.82)
            plt.close(fig)

    def test_explicit_dashboard_order_and_loader_insight(self):
        tree=ast.parse(Path('app.py').read_text())
        candidates=[n for n in ast.walk(tree) if isinstance(n,ast.Lambda) and 'india_cpi_contributions' in ast.unparse(n)]
        self.assertEqual(len(candidates),1)
        key=eval(compile(ast.Expression(candidates[0]),'<dashboard order>','eval'))
        names=['14_india_credit_deposit.png','24_india_cpi_contributions.png','15_india_rate_transmission.png','06_india_inflation_bar.png']
        self.assertEqual([p.name for p in sorted(map(Path,names),key=key)],[names[3],names[1],names[0],names[2]])
        from config.insights import get_insight
        text=get_insight('india_cpi_contributions')
        for url in (cpi.API_URL,cpi.CATALOGUE_URL,cpi.WEIGHTS_URL,cpi.ROUNDING_URL): self.assertIn(url,text)
        from charts.loader import _TITLE_OVERRIDES
        self.assertEqual(_TITLE_OVERRIDES['india_cpi_contributions'],'What’s Driving Indian Inflation?')

if __name__=='__main__': unittest.main()
