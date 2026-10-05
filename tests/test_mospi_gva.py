"""Official workbook fixtures and failure-path tests for quarterly GVA."""
import copy
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

import openpyxl
from data.fetchers import mospi_gva as gva

FIXTURES = Path(__file__).parent / 'fixtures' / 'mospi_gva'


class GvaTests(unittest.TestCase):
    def setUp(self):
        self.history_blob = (FIXTURES / 'nas_2026_8.18.1.xlsx').read_bytes()
        self.latest_blob = (FIXTURES / 'quarterly_constant_2026-08-31.xlsx').read_bytes()
        self.entry = json.loads((FIXTURES / 'catalogue_entry.json').read_text())
        self.url = gva.DOWNLOAD_ROOT + quote(self.entry['file_path'].lstrip('/') + self.entry['file_name'], safe='/')
        self.history = gva.parse_history(self.history_blob, "https://www.mospi.gov.in/history.xlsx", "2026-08-31")
        self.latest = gva.parse_latest(self.latest_blob, self.entry, self.url)
        self.rows = gva.combine(self.history, self.latest)

    def test_official_levels_and_calendar_comparisons(self):
        self.assertEqual(len(self.rows), 17)
        self.assertEqual(self.rows[0]['quarter'], '2022-06-30')
        self.assertEqual(self.rows[3]['quarter'], '2023-03-31')
        self.assertEqual(self.rows[7]['comparison_quarter'], '2023-03-31')
        self.assertTrue(all(r['headline_yoy'] is None for r in self.rows[:4]))
        for r in self.rows[4:]:
            self.assertLess(abs(sum(r[k+'_pp'] for k in gva.LEVEL_KEYS[:3])-r['headline_yoy']), 1e-8)
            self.assertEqual(r['base_year'], '2022-23')
        self.assertAlmostEqual(self.rows[-1]['headline_yoy'], 8.229320112314227)
        self.assertAlmostEqual(self.rows[-1]['tertiary_pp'], 5.447414095084943)
        self.assertEqual(self.rows[-1]['release_date'], '2026-08-31')

    def test_missing_quarter_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing quarter'):
            gva.calculate(self.rows[:6] + self.rows[7:])

    def test_mixed_base_and_nonreconciling_levels_rejected(self):
        for field, value, error in [('base_year', '2011-12', 'mixed base'),
                                    ('gva', 1, 'reconciliation')]:
            bad = copy.deepcopy(self.rows)
            bad[5][field] = value
            with self.assertRaisesRegex(ValueError, error):
                gva.calculate(bad)

    def test_changed_schema_and_missing_values_rejected(self):
        for cell, value in [('A11', '2. New Sector'), ('B8', None),
                            ('A2', 'Constant Prices, 2011-12 Series')]:
            book = openpyxl.load_workbook(BytesIO(self.history_blob))
            book.active[cell] = value
            out = BytesIO()
            book.save(out)
            with self.assertRaises(ValueError):
                gva.parse_history(out.getvalue(), "https://www.mospi.gov.in/history.xlsx", "2026-08-31")

    def test_inconsistent_revision_rejected(self):
        latest = copy.deepcopy(self.latest)
        latest[0]['gva'] += 50
        with self.assertRaisesRegex(ValueError, 'same-vintage'):
            gva.combine(self.history, latest)

    def test_idempotent_storage_and_corruption_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'india.db'
            gva.store(self.rows, db)
            first = gva.load(db)
            gva.store(self.rows, db)
            second = gva.load(db)
            self.assertEqual([{k:v for k,v in r.items() if k!='fetched_at'} for r in first],
                             [{k:v for k,v in r.items() if k!='fetched_at'} for r in second])
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE india_gva_quarterly SET tertiary_pp=0 WHERE quarter='2026-06-30'")
            with self.assertRaisesRegex(ValueError, 'stored tertiary_pp'):
                gva.load(db)

    def methods_pdf(self, version='v1', metadata=None):
        import fitz
        with fitz.open() as book:
            page=book.new_page()
            page.insert_text((40,40), 'National Accounts Statistics methodology, constant prices, base year 2022-23.')
            page.insert_text((40,70), 'Detailed official Sources and Methods used to compile the broad sector GVA. ' + version)
            if metadata:
                book.set_metadata(metadata)
            return book.tobytes()

    def test_pdf_metadata_changes_do_not_block_normal_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'india.db';self.mocked_fetch(db)
            self.mocked_fetch(db,methodology=self.methods_pdf(metadata={'title':'Cosmetic metadata change'}))
            self.assertEqual(len(gva.load(db)),17)

    def responses(self, history_blob=None, methodology=None, release='2026-08-31'):
        if methodology is None:
            methodology = self.methods_pdf()
        class Response:
            def __init__(self, content=b'', payload=None):
                self.content = json.dumps(payload).encode() if payload is not None else content
            def raise_for_status(self):
                pass
            def json(self):
                return json.loads(self.content)
        pub = {'id':'new', 'title':'National Accounts Statistics 2027', 'is_active':True,
               'published_year':release}
        method = dict(id='method',title='Sources and Methods for Compilation of National Accounts Statistics',
                      is_active=True,published_year='2026-09-21',file_one={'path':'uploads/methods.pdf'})
        statement = dict(sub_chapter_title='Statement 8.18.1: Quarterly Estimates of GDP (At Constant Prices)',
                         file_one={'path':'uploads/new-history.xlsx'},file_two=None,file_three=None)
        chapter = dict(sub_chapters=[statement])
        pagination = dict(currentPage=1,totalPages=1,totalItems=2)
        return ([Response(payload=dict(status='success',data=[pub,method],pagination=pagination)),
                 Response(payload=dict(status='success',data=[chapter],pagination=dict(pagination,totalItems=1)))],
                [Response(methodology),Response(payload=dict(statusCode=True,data=[self.entry],
                 meta_data=dict(page=1,totalPages=1,totalRecords=1))),
                 Response(history_blob or self.history_blob),Response(self.latest_blob)])

    def mocked_fetch(self, db, **kwargs):
        post_responses,get_responses = self.responses(**kwargs)
        with patch('requests.Session.post',side_effect=post_responses), patch('requests.Session.get',side_effect=get_responses):
            return gva.fetch(db=db)

    def revised_history(self):
        book = openpyxl.load_workbook(BytesIO(self.history_blob))
        sheet = book.active
        # Revise a primary child and both parent totals consistently in FY2023-24 Q2.
        for row in (8,9,19):
            sheet.cell(row,7).value += 50
        values = list(sheet.values)
        for col in range(1,13):
            for level_row,growth_row in zip((8,11,15,19),(39,42,46,50)):
                sheet.cell(growth_row,col+1).value = 100*(sheet.cell(level_row,col+5).value/sheet.cell(level_row,col+1).value-1)
        out = BytesIO();book.save(out);book.close()
        return out.getvalue()

    def test_dynamic_discovery_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'absent.db'
            posts,gets=self.responses()
            with patch('requests.Session.post',side_effect=posts),patch('requests.Session.get',side_effect=gets) as get:
                rows=gva.fetch(dry_run=True,db=db)
                self.assertEqual(len(rows),17)
                self.assertEqual(get.call_args_list[-2].args[0],'https://www.mospi.gov.in/uploads/new-history.xlsx')
                self.assertEqual(get.call_args_list[-1].args[0],self.url)
                self.assertFalse(db.exists())
                self.assertFalse((db.parent/'gva').exists())

    def test_new_history_revision_accepted_archived_and_exactly_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'india.db'
            first=self.mocked_fetch(db)
            original=json.loads((db.parent/'gva/current.json').read_text())
            second=self.mocked_fetch(db,history_blob=self.revised_history(),release='2026-10-01')
            current=json.loads((db.parent/'gva/current.json').read_text())
            run=json.loads((db.parent/'gva/runs'/ (current['run_id']+'.json')).read_text())
            self.assertEqual([r['quarter'] for r in current['revisions']],['2023-09-30'])
            self.assertEqual(set(current['revisions'][0]['changes']),{'primary','gva'})
            self.assertEqual([r['quarter'] for r in current['derived_revisions']],['2023-09-30','2024-09-30'])
            self.assertEqual(run['previous']['run_id'],original['run_id'])
            self.assertEqual([r['gva'] for r in run['previous_records']], [r['gva'] for r in first])
            for source in original['sources']:
                self.assertTrue((db.parent/'gva'/source['raw']).exists())
            self.assertNotEqual(first[5]['headline_yoy'],second[5]['headline_yoy'])
            self.assertNotEqual(first[9]['headline_yoy'],second[9]['headline_yoy'])
            self.assertEqual(gva.load(db)[5]['gva'],second[5]['gva'])

    def test_methodology_change_rejected_database_preserved_and_chart_gated(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'india.db';self.mocked_fetch(db)
            before=db.read_bytes()
            with self.assertRaisesRegex(ValueError,'methodology changed'):
                self.mocked_fetch(db,methodology=self.methods_pdf('v2'))
            self.assertEqual(before,db.read_bytes())
            self.assertEqual(json.loads((db.parent/'gva/status.json').read_text())['status'],'rejected')
            with self.assertRaisesRegex(ValueError,'rejected'):
                gva.load(db)

    def test_committed_wal_database_reads_without_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'india.db';gva.store(self.rows,db)
            with sqlite3.connect(db) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            snapshot=Path(directory)/'committed.db';snapshot.write_bytes(db.read_bytes())
            self.assertEqual(len(gva.load(snapshot)),17)
            self.assertFalse(Path(str(snapshot)+'-wal').exists())

    def test_annual_history_can_add_a_complete_fiscal_year(self):
        book=openpyxl.load_workbook(BytesIO(self.history_blob));sheet=book.active
        sheet.cell(5,18).value='2026-27'
        sheet.cell(36,14).value='2026-27'
        for q in range(4):
            col=18+q;sheet.cell(7,col).value=f'Q{q+1}'
            sheet.cell(38,col-4).value=f'Q{q+1}'
            for row in range(8,20):
                sheet.cell(row,col).value=sheet.cell(row,col-4).value*1.1
                sheet.cell(row+31,col-4).value=10.0
        out=BytesIO();book.save(out);book.close()
        rows=gva.parse_history(out.getvalue(),'https://www.mospi.gov.in/new.xlsx','2027-05-31')
        self.assertEqual(len(rows),20)
        self.assertEqual(rows[-1]['quarter'],'2027-03-31')
        self.assertAlmostEqual(rows[-1]['headline_yoy'],10)

    def test_rejected_history_schema_preserves_database(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'india.db';self.mocked_fetch(db);before=db.read_bytes()
            book=openpyxl.load_workbook(BytesIO(self.history_blob));book.active['A2']='New methodology / 2011-12'
            out=BytesIO();book.save(out);book.close()
            with self.assertRaisesRegex(ValueError,'base/methodology changed'):
                self.mocked_fetch(db,history_blob=out.getvalue(),release='2026-10-01')
            self.assertEqual(before,db.read_bytes())

    def test_newer_quarterly_revisions_accepted_after_validation(self):
        latest=copy.deepcopy(self.latest)
        latest[0]['primary']+=50;latest[0]['gva']+=50
        for row in latest:row['release_date']='2026-10-01'
        result=gva.combine(self.history,latest)
        self.assertEqual([r['quarter'] for r in gva.revisions(self.rows,result)],['2024-06-30'])
        latest[0]['gva']+=50
        with self.assertRaisesRegex(ValueError,'reconciliation'):
            gva.combine(self.history,latest)

    def test_quarterly_rollforward_retains_intervening_stored_quarters(self):
        import copy
        latest=copy.deepcopy(self.latest)
        for row in latest:
            row['fiscal_quarter']=2
            row['quarter']=gva.fiscal_period(row['fiscal_year'],2)
            row['release_date']='2026-11-30'
        result=gva.combine(self.history,latest,self.rows)
        self.assertEqual(len(result),18)
        self.assertEqual(result[-2]['quarter'],'2026-06-30')
        self.assertEqual(result[-1]['quarter'],'2026-09-30')

    def test_catalogue_pagination_discovers_latest_on_later_page(self):
        class Response:
            def __init__(self,p):self.p=p
            def json(self):return self.p
        old=dict(self.entry,release_date='30 May 2026')
        payloads=[dict(statusCode=True,data=[old],meta_data=dict(page=1,totalPages=2,totalRecords=2)),
                  dict(statusCode=True,data=[self.entry],meta_data=dict(page=2,totalPages=2,totalRecords=2))]
        with patch('builtins.print'):
            responses=iter(payloads)
            found,url=gva.discover_latest(lambda *a,**k:Response(next(responses)))
        self.assertEqual(found['release_date'],'31 Aug 2026')
        self.assertEqual(url,self.url)

    def test_newest_publication_missing_statement_never_falls_back(self):
        posts,gets=self.responses()
        posts[-1].content=json.dumps(dict(status='success',data=[dict(sub_chapters=[])],
                                      pagination=dict(currentPage=1,totalPages=1,totalItems=1))).encode()
        with patch('requests.Session.post',side_effect=posts),patch('requests.Session.get',side_effect=gets),             tempfile.TemporaryDirectory() as directory,self.assertRaisesRegex(ValueError,'statement changed/missing'):
            gva.fetch(db=Path(directory)/'india.db')


if __name__ == '__main__':
    unittest.main()
