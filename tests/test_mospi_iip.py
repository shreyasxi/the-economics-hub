"""Focused current-base IIP production contracts and emergency fallback tests."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from data.fetchers import mospi_iip as iip
from data import india_db_manager as dbm
from data import india_manual_entry as manual

PAYLOAD = json.loads((Path(__file__).parent/'fixtures/iip/official_2022_23_history.json').read_text())


class Response:
    def __init__(self,payload):self.content=json.dumps(payload).encode()
    def json(self):return json.loads(self.content)
    def raise_for_status(self):pass


class IipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'india.db'
        with patch.object(dbm,'DB_PATH',self.db):dbm.init_db()

    def fetch(self,payload=None,dry_run=False):
        with patch('requests.Session.get',return_value=Response(payload or PAYLOAD)):
            return iip.fetch(dry_run=dry_run,db=self.db)

    def test_full_backfill_uses_published_growth_and_preserves_unrelated_fields(self):
        with patch.object(dbm,'DB_PATH',self.db):
            dbm.upsert_monthly('2022-01',dict(india_iip_yoy=2,india_mfg_pmi=50,source_flags=json.dumps({'pmi':'manual','india_iip_yoy':'legacy'})))
            dbm.upsert_monthly('2026-08',dict(india_iip_yoy=4,india_cpi_yoy=4.82,source_flags=json.dumps({'india_cpi_yoy':'manual:cpi','india_iip_yoy':'legacy'})))
        result=self.fetch();records=iip.load(self.db)
        self.assertEqual(len(records),41)
        self.assertEqual(records[0]['month'],'2023-04')
        self.assertEqual(records[-1]['month'],'2026-08')
        self.assertEqual(records[-1]['growth_rate'],8)
        self.assertEqual(records[-1]['index_level'],123.3)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT india_iip_yoy,india_mfg_pmi FROM india_monthly WHERE month='2022-01'").fetchone(),(None,50))
            self.assertEqual(conn.execute("SELECT india_iip_yoy,india_cpi_yoy FROM india_monthly WHERE month='2026-08'").fetchone(),(8,4.82))
            self.assertEqual(conn.execute('SELECT month,growth_rate FROM india_iip_legacy_archive ORDER BY month').fetchall(),[('2022-01',2),('2026-08',4)])
            flags=json.loads(conn.execute("SELECT source_flags FROM india_monthly WHERE month='2026-08'").fetchone()[0])
            self.assertEqual(flags['india_cpi_yoy'],'manual:cpi')
            self.assertIn('base=2022-23',flags['india_iip_yoy'])

    def test_invalid_base_concept_month_schema_and_bounds_rejected_atomically(self):
        self.fetch();before=self.db.read_bytes()
        for field,value in [('base_year','2011-12'),('type','Sectoral'),('category','Manufacturing'),
                            ('sub_category','Total'),('month','Aug'),('year',True),('year',2027),
                            ('growth_rate','123.3'),('growth_rate','NaN'),('index','0'),('index',123.3),('new_field',1)]:
            bad=copy.deepcopy(PAYLOAD);bad['data'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises((ValueError,TypeError)):
                self.fetch(bad)
            self.assertEqual(self.db.read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'not accepted'):iip.load(self.db)
        self.fetch();self.assertEqual(len(iip.load(self.db)),41)

    def test_missing_duplicate_and_truncated_pagination_rejected(self):
        for transform in ('missing','duplicate','count','page'):
            bad=copy.deepcopy(PAYLOAD)
            if transform=='missing':del bad['data'][10];bad['meta_data']['totalRecords']-=1
            elif transform=='duplicate':bad['data'][-1]=bad['data'][0]
            elif transform=='count':bad['meta_data']['totalRecords']+=1
            else:bad['meta_data']['page']=2
            with self.subTest(transform=transform),self.assertRaises(ValueError):self.fetch(bad)

    def test_official_revision_accepted_logged_and_previous_source_preserved(self):
        self.fetch();first=json.loads((self.root/'IIP/current.json').read_text())
        bad=copy.deepcopy(PAYLOAD);bad['data'][1]['growth_rate']='7.3';self.fetch(bad)
        current=json.loads((self.root/'IIP/current.json').read_text())
        self.assertEqual(current['revisions'],[dict(month='2026-07',before=7.4,after=7.3)])
        run=json.loads((self.root/'IIP/runs'/(current['run_id']+'.json')).read_text())
        self.assertEqual(run['previous']['run_id'],first['run_id'])
        self.assertTrue((self.root/'IIP'/first['sources'][0]['raw']).exists())

    def test_update_cannot_drop_previously_stored_official_months(self):
        self.fetch();before=self.db.read_bytes()
        reduced=copy.deepcopy(PAYLOAD);reduced['data']=reduced['data'][:-1]
        reduced['meta_data']['totalRecords']-=1
        with self.assertRaisesRegex(ValueError,'drops stored official months'):self.fetch(reduced)
        self.assertEqual(before,self.db.read_bytes())

    def test_generic_source_flags_cannot_replace_official_iip_provenance(self):
        self.fetch()
        with patch.object(dbm,'DB_PATH',self.db):
            dbm.upsert_monthly('2026-08',dict(source_flags=json.dumps({'india_iip_yoy':'manual:unverified','pmi':'manual'})))
        with sqlite3.connect(self.db) as conn:
            flags=json.loads(conn.execute("SELECT source_flags FROM india_monthly WHERE month='2026-08'").fetchone()[0])
        self.assertTrue(flags['india_iip_yoy'].startswith('mospi:General:base=2022-23'))
        self.assertEqual(flags['pmi'],'manual')

    def test_pagination_backfills_every_month(self):
        first=copy.deepcopy(PAYLOAD);first['data']=PAYLOAD['data'][:20];first['meta_data']['totalPages']=2
        second=copy.deepcopy(PAYLOAD);second['data']=PAYLOAD['data'][20:];second['meta_data'].update(page=2,totalPages=2)
        with patch('requests.Session.get',side_effect=[Response(first),Response(second)]) as get:
            rates=iip.fetch(db=self.db)
        self.assertEqual(len(rates),41)
        self.assertEqual(get.call_args_list[1].kwargs['params']['page'],2)
        self.assertEqual(len(json.loads((self.root/'IIP/current.json').read_text())['sources']),2)

    def test_manual_conflict_is_separate_and_requires_explicit_chart_opt_in(self):
        self.fetch()
        with patch.object(manual,'DB_PATH',self.db),self.assertLogs('data.fetchers.mospi_iip',level='WARNING') as log:
            manual.main(['set','2026-08','--iip','5'])
        self.assertIn('CONFLICT',log.output[0])
        self.assertEqual(iip.load(self.db)[-1]['growth_rate'],8)
        self.assertEqual(iip.load(self.db,manual_fallback=True)[-1]['growth_rate'],5)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT india_iip_yoy FROM india_monthly WHERE month='2026-08'").fetchone()[0],8)
        with patch.object(dbm,'DB_PATH',self.db),self.assertRaisesRegex(ValueError,'Conflicting IIP'):
            dbm.upsert_monthly('2026-08',dict(india_iip_yoy=5))

    def test_corruption_rejected_and_failed_chart_removed(self):
        self.fetch()
        with sqlite3.connect(self.db) as conn:conn.execute("UPDATE india_iip_monthly SET growth_rate=5 WHERE month='2026-08'")
        with self.assertRaisesRegex(ValueError,'published growth'):iip.load(self.db)
        import generate_india as charts
        fp=self.root/'15_india_iip.png';fp.write_bytes(b'old')
        with patch.object(charts,'DEFAULT_DB',self.db),patch.dict('os.environ',{'IIP_MANUAL_FALLBACK':'false'}):
            self.assertIsNone(charts.chart_iip(None,self.root))
        self.assertFalse(fp.exists())

    def test_database_initialization_closes_writer_before_dry_run(self):
        # Retain the connection so garbage-collection timing cannot hide a leak.
        connections = []
        connect = sqlite3.connect
        def retain(*args, **kwargs):
            conn = connect(*args, **kwargs)
            connections.append(conn)
            return conn
        with patch.object(dbm, 'DB_PATH', self.db), patch.object(dbm.sqlite3, 'connect', side_effect=retain):
            dbm.init_db()
        self.assertEqual(len(connections), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute('SELECT 1')
        before = self.db.read_bytes()
        self.fetch(dry_run=True)
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse((self.root / 'IIP').exists())

    def test_dry_run_leaves_database_and_archive_untouched(self):
        before=self.db.read_bytes();self.fetch(dry_run=True)
        self.assertEqual(before,self.db.read_bytes());self.assertFalse((self.root/'IIP').exists())

    def test_workflow_integration_and_optional_artifact_cleanup(self):
        workflow=Path('.github/workflows/india.yml').read_text()
        self.assertLess(workflow.index('run: python -m data.fetchers.mospi_iip'),workflow.index('run: python generate_india.py'))
        self.assertIn('IIP_UPDATE_FAILED',workflow);self.assertIn('manual_iip_fallback',workflow)
        self.assertIn('06_india_inflation_bar 15_india_iip;',workflow)
        self.assertIn('data/gva data/IIP;',workflow)


if __name__=='__main__':unittest.main()
