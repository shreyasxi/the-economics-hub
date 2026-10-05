"""Saturday ordering, official concepts, manual conflicts and emergency paths."""
import copy
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from data import india_db_manager as dbm
from data import india_manual_entry as manual
from data.fetchers import mospi_inflation as inflation
from data.fetchers import mospi_iip_audit as iip
from data.fetchers import nse_sector_rotation as rotation
from data.fetchers import india_fetcher as fetcher
from data.fetchers import mospi_gva as gva
from data import cpi_contributions as cpi
import generate_india as charts

FIXTURES = Path(__file__).parent/'fixtures'
CURRENT=json.loads((FIXTURES/'cpi/official_2025_2026.json').read_text())
OLD=json.loads((FIXTURES/'cpi/official_2012_history.json').read_text())['data']
IIP=json.loads((FIXTURES/'iip/official_2022_23.json').read_text())['data']
MANUAL_IIP={'2026-01':4.8,'2026-02':5.2,'2026-03':4.1,'2026-04':4.9,
            '2026-05':5.1,'2026-06':7.3,'2026-07':6.7,'2026-08':8.0}


class SaturdayTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.db=self.root/'india.db'
        with patch.object(dbm,'DB_PATH',self.db): dbm.init_db()

    def value(self,month,column):
        with sqlite3.connect(self.db) as conn:
            row=conn.execute(f'SELECT {column} FROM india_monthly WHERE month=?',(month,)).fetchone()
        return row[0] if row else None

    def test_legacy_iip_overlap_is_diagnostic_and_uses_growth(self):
        comparison=iip.compare(IIP,MANUAL_IIP,'2022-23')
        self.assertEqual(len(comparison),8)
        self.assertEqual([r['month'] for r in comparison if r['equivalent']],['2026-04','2026-08'])
        self.assertEqual(iip.validate(IIP,'2022-23')['2026-08'],8)
        old=json.loads((FIXTURES/'iip/official_2011_12.json').read_text())['data']
        self.assertEqual(max(iip.validate(old,'2011-12')),'2026-03')
        self.assertFalse(all(r['equivalent'] for r in iip.compare(old,MANUAL_IIP,'2011-12')))

    def test_iip_wrong_concept_basis_schema_and_index_as_rate_rejected(self):
        for change in ({'base_year':'2011-12'},{'category':'Mining'},
                       {'type':'Sectoral'},{'sub_category':'Manufacturing'},
                       {'growth_rate':'123.3'},{'unexpected':'x'}):
            rows=copy.deepcopy(IIP);rows[0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError): iip.validate(rows,'2022-23')

    def test_direct_published_general_and_food_mapping(self):
        rates=inflation.current_rates(CURRENT)
        self.assertEqual(len(rates),16)
        aug={r['column']:r['value'] for r in rates if r['month']=='2026-08'}
        self.assertEqual(aug,{'india_cpi_yoy':4.82,'india_food_cpi_yoy':5.66})
        self.assertNotEqual(aug['india_food_cpi_yoy'],5.95) # CFPI manual value
        bad=copy.deepcopy(CURRENT);bad[0]['sector']='Urban'
        with self.assertRaises(ValueError): inflation.current_rates(bad)

    def test_explicit_history_break_and_cfpi_excluded(self):
        rates=inflation.old_history(OLD)+inflation.current_rates(CURRENT)
        self.assertEqual({r['base'] for r in rates if r['month']<'2026-01'},{'2012'})
        self.assertEqual({r['base'] for r in rates if r['month']>='2026-01'},{'2024'})
        dec={r['column']:r['value'] for r in rates if r['month']=='2025-12'}
        self.assertEqual(dec,{'india_cpi_yoy':1.33,'india_food_cpi_yoy':-1.85})
        self.assertNotEqual(dec['india_food_cpi_yoy'],-2.71)
        bad=copy.deepcopy(OLD);bad[0]['state']='Delhi'
        with self.assertRaises(ValueError): inflation.old_history(bad)
        bad=copy.deepcopy(OLD);bad[0]['new_field']=1
        with self.assertRaises(ValueError): inflation.old_history(bad)

    def test_conflict_warns_and_no_partial_transaction(self):
        with patch.object(manual,'DB_PATH',self.db):
            manual.main(['set','2026-08','--food-cpi','5.95'])
        rates=inflation.current_rates(CURRENT)
        with self.assertLogs(inflation.LOG,level='ERROR') as logged:
            result=inflation.apply_rates(self.db,rates)
        self.assertEqual(result['status'],'conflict')
        self.assertIn('NOT overwritten',' '.join(logged.output))
        self.assertEqual(self.value('2026-08','india_food_cpi_yoy'),5.95)
        self.assertIsNone(self.value('2026-07','india_cpi_yoy'))

    def test_approved_manual_conflicts_use_official_values_and_archive_original(self):
        with patch.object(manual,'DB_PATH',self.db):
            manual.main(['set','2026-08','--food-cpi','5.95','--mfg-pmi','55.1'])
        rates=inflation.current_rates(CURRENT)
        with self.assertLogs(inflation.LOG,level='WARNING') as logged:
            result=inflation.apply_rates(self.db,rates,accept_manual_conflicts=True)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(self.value('2026-08','india_food_cpi_yoy'),5.66)
        self.assertEqual(self.value('2026-08','india_mfg_pmi'),55.1)
        self.assertIn('APPROVED MANUAL CPI RESOLUTION',' '.join(logged.output))
        with sqlite3.connect(self.db) as conn:
            flags=json.loads(conn.execute("SELECT source_flags FROM india_monthly WHERE month='2026-08'").fetchone()[0])
            old=json.loads(conn.execute("SELECT payload FROM india_cpi_observation_audit WHERE month='2026-08' AND column_name='india_food_cpi_yoy'").fetchone()[0])
        self.assertTrue(flags['india_food_cpi_yoy'].startswith('official:'))
        self.assertEqual(old['before'],5.95)
        self.assertTrue(old['previous_source'].startswith('manual:'))
        self.assertTrue(old['manual_conflict_approved'])

    def test_manual_equivalent_confirmed_and_official_revision_persisted(self):
        with patch.object(manual,'DB_PATH',self.db): manual.main(['set','2026-08','--cpi','4.82','--food-cpi','5.66'])
        rates=inflation.current_rates(CURRENT)
        first=inflation.apply_rates(self.db,rates)
        self.assertEqual(first['status'],'ready')
        revised=copy.deepcopy(rates)
        target=next(r for r in revised if r['month']=='2026-07' and r['column']=='india_cpi_yoy')
        target['value']=4.46
        with self.assertLogs(inflation.LOG,level='WARNING'): result=inflation.apply_rates(self.db,revised)
        self.assertEqual(self.value('2026-07','india_cpi_yoy'),4.46)
        change=next(r for r in result['changes'] if r['month']=='2026-07' and r['column']=='india_cpi_yoy')
        self.assertEqual(change['before'],4.45)
        with sqlite3.connect(self.db) as conn:
            flags=json.loads(conn.execute('SELECT source_flags FROM india_monthly WHERE month="2026-08"').fetchone()[0])
            journal=json.loads(conn.execute('SELECT payload FROM india_cpi_observation_audit WHERE month="2026-07" AND column_name="india_cpi_yoy" ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertEqual(journal['before'],4.45)
        self.assertEqual(journal['value'],4.46)
        self.assertTrue(flags['india_cpi_yoy'].startswith('manual:'))
        self.assertIn('india_cpi_yoy:official_confirmation',flags)

    def test_all_three_manual_cli_fallbacks_and_bounds(self):
        with patch.object(manual,'DB_PATH',self.db):
            for flag,value,column in [('--iip','8.0','india_iip_yoy'),('--cpi','4.82','india_cpi_yoy'),('--food-cpi','5.66','india_food_cpi_yoy')]:
                manual.main(['set','2026-08',flag,value])
                if flag=='--iip':
                    from data.fetchers.mospi_iip import load
                    self.assertEqual(load(self.db,manual_fallback=True)[-1]['growth_rate'],float(value))
                    self.assertIsNone(self.value('2026-08',column))
                else:
                    self.assertEqual(self.value('2026-08',column),float(value))
            for flag in ('--iip','--cpi','--food-cpi'):
                with self.assertRaises(SystemExit): manual.main(['set','2026-08',flag,'999'])
        with patch.object(charts,'DEFAULT_DB',self.db),patch.dict(os.environ,{'CPI_MANUAL_FALLBACK':'true','CPI_MAIN_UPDATE_FAILED':'true'}):
            with patch.object(dbm,'DB_PATH',self.db): df=dbm.get_monthly_series()
            self.assertTrue(charts.chart_inflation_bar(df,self.root).exists())

    def test_fred_cannot_overwrite_official_or_manual(self):
        inflation.apply_rates(self.db,inflation.current_rates(CURRENT))
        with patch.object(manual,'DB_PATH',self.db): manual.main(['set','2026-08','--food-cpi','5.66'])
        with patch.object(dbm,'DB_PATH',self.db),self.assertLogs(dbm.log,level='ERROR'):
            dbm.upsert_monthly('2026-08',{'india_cpi_yoy':9,'india_food_cpi_yoy':9,
                 'source_flags':json.dumps({'india_cpi_yoy':'fred_legacy','india_food_cpi_yoy':'fred_legacy'})})
        self.assertEqual(self.value('2026-08','india_cpi_yoy'),4.82)
        self.assertEqual(self.value('2026-08','india_food_cpi_yoy'),5.66)

    def test_main_chart_consumes_persisted_official_rates_and_marks_base_break(self):
        result=inflation.apply_rates(self.db,inflation.old_history(OLD)+inflation.current_rates(CURRENT))
        self.assertEqual(result['status'],'ready')
        (self.root/'status.json').write_text(json.dumps(result))
        with patch.object(dbm,'DB_PATH',self.db): df=dbm.get_monthly_series()
        with patch.object(inflation,'ROOT',self.root),patch.dict(os.environ,{'CPI_MAIN_UPDATE_FAILED':'false','CPI_MANUAL_FALLBACK':'false'}):
            with patch.object(charts.EconStyle,'save_chart') as save:
                charts.chart_inflation_bar(df,self.root)
        fig=save.call_args.args[0]
        self.assertAlmostEqual(fig.axes[0].containers[0][-1].get_height(),4.82)
        self.assertAlmostEqual(fig.axes[0].containers[1][-1].get_height(),5.66)
        notes=' '.join(t.get_text() for t in fig.texts)
        self.assertIn('Source: MoSPI · 2012-base through Dec 2025; 2024-base from Jan 2026 · Updated Aug 2026',notes)
        import matplotlib.pyplot as plt
        plt.close(fig)
        with patch.object(manual,'DB_PATH',self.db): manual.main(['set','2026-08','--food-cpi','5.95'])
        with patch.object(dbm,'DB_PATH',self.db): changed=dbm.get_monthly_series()
        with patch.object(inflation,'ROOT',self.root),patch.dict(os.environ,{'CPI_MAIN_UPDATE_FAILED':'false','CPI_MANUAL_FALLBACK':'false'}):
            self.assertIsNone(charts.chart_inflation_bar(changed,self.root))
            (self.root/'status.json').write_text('invalid JSON')
            self.assertIsNone(charts.chart_inflation_bar(changed,self.root))

    def test_optional_failed_sources_remove_artifacts_and_leave_independent_chart(self):
        names=['22_india_gva_contributions','21_india_risk_appetite','23_india_sector_rotation_12m_benchmark','06_india_inflation_bar']
        for name in names: (self.root/(name+'.png')).write_bytes(b'old')
        with patch.dict(os.environ,{'GVA_UPDATE_FAILED':'true','NSE_RISK_UPDATE_FAILED':'true',
                  'NSE_ROTATION_UPDATE_FAILED':'true','CPI_MAIN_UPDATE_FAILED':'true','CPI_MANUAL_FALLBACK':'false'}):
            self.assertIsNone(charts.chart_gva_contributions(self.root))
            self.assertIsNone(charts.chart_risk_appetite(self.root))
            self.assertIsNone(charts.chart_sector_rotation_12m(self.root))
            self.assertIsNone(charts.chart_inflation_bar(None,self.root))
        for name in names: self.assertFalse((self.root/(name+'.png')).exists())
        with patch.object(manual,'DB_PATH',self.db): manual.main(['set','2026-08','--iip','8'])
        with patch.object(dbm,'DB_PATH',self.db): df=dbm.get_monthly_series()
        with patch.object(charts,'DEFAULT_DB',self.db),patch.dict(os.environ,{'IIP_MANUAL_FALLBACK':'true'}):
            self.assertTrue(charts.chart_iip(df,self.root).exists())

    def test_gva_failure_still_persists_independent_monthly_source(self):
        independent={'2026-08':{'india_exports_usd_bn':35,'_sources':{'india_exports_usd_bn':'dbie_excel_monthly'}}}
        with patch.object(gva,'fetch',side_effect=ValueError('official history revision')),\
             patch.object(fetcher,'init_db'),patch.object(fetcher,'fetch_repo_rate_current'),\
             patch.object(fetcher,'fetch_dbie_all',return_value=(independent,{})),\
             patch.object(fetcher,'_existing_flags',return_value={}),\
             patch.object(fetcher,'upsert_monthly') as persist,\
             patch.object(fetcher,'get_latest_monthly_date'),patch.object(fetcher,'get_latest_weekly_date'):
            with self.assertRaisesRegex(RuntimeError,'GVA update failed'):
                fetcher.run_append(None)
            self.assertEqual(persist.call_args.args[0],'2026-08')
            self.assertEqual(persist.call_args.args[1]['india_exports_usd_bn'],35)

    def test_offline_rotation_store_and_failure_gate(self):
        clock=patch.object(rotation,'today_ist',return_value=date(2026,10,5))
        clock.start()
        self.addCleanup(clock.stop)
        payload=json.loads((FIXTURES/'nse_rotation/allIndices_2026-10-01.json').read_text())
        changes={r['index']:dict(last=float(r['last']),year_ago=float(r['oneYearAgoVal']),
              change_pct_1y=round((float(r['last'])/float(r['oneYearAgoVal'])-1)*100,2)) for r in payload['data'] if r['index'] in rotation.INDICES}
        with patch.object(rotation,'fetch_nifty_sector_changes',return_value=(changes,payload)):
            expected=rotation.update(self.root/'rotation')
        self.assertEqual(rotation.load_rotation_data(self.root/'rotation'),expected)
        with patch.object(rotation,'fetch_nifty_sector_changes',side_effect=ValueError('unavailable')):
            with self.assertRaises(ValueError): rotation.update(self.root/'rotation')
        with self.assertRaisesRegex(ValueError,'No successful'): rotation.load_rotation_data(self.root/'rotation')

    def test_rotation_rejects_stale_and_future_snapshots(self):
        payload=json.loads((FIXTURES/'nse_rotation/allIndices_2026-10-01.json').read_text())
        changes={r['index']:dict(last=float(r['last']),year_ago=float(r['oneYearAgoVal']),
              change_pct_1y=round((float(r['last'])/float(r['oneYearAgoVal'])-1)*100,2)) for r in payload['data'] if r['index'] in rotation.INDICES}
        for day,reason in [(date(2026,10,10),'stale'),(date(2026,9,30),'future')]:
            with patch.object(rotation,'today_ist',return_value=day),self.assertRaisesRegex(ValueError,reason):
                rotation.validate_snapshot(changes,payload)

    def test_workflow_order_cadence_and_all_source_gates(self):
        workflow=Path('.github/workflows/india.yml').read_text()
        generation=workflow.index('run: python generate_india.py --mode dashboard')
        for command in ['python data/fetchers/india_fetcher.py --append','python -m data.fetchers.nse_risk_appetite',
                'python -m data.fetchers.nse_sector_rotation','python -m data.fetchers.nse_valuations.collector --update',
                'python -m data.fetchers.mospi_cpi --update','python -m data.fetchers.mospi_inflation','python -m data.fetchers.mospi_iip']:
            self.assertLess(workflow.index('run: '+command),generation)
        self.assertLess(workflow.index('run: python -m data.fetchers.mospi_cpi --update'),workflow.index('run: python -m data.fetchers.mospi_inflation'))
        self.assertEqual(workflow.count('cron: "0 8 * * 6"'),1)
        self.assertNotIn('needs: fetch-data',workflow)
        self.assertIn('data/india_macro.db',workflow[workflow.index('- name: Commit and push charts'):])
        for flag in ['IIP_UPDATE_FAILED','GVA_UPDATE_FAILED','NSE_RISK_UPDATE_FAILED','NSE_ROTATION_UPDATE_FAILED','CPI_MAIN_UPDATE_FAILED','CPI_UPDATE_FAILED','NSE_VALUATIONS_UPDATE_FAILED']:
            self.assertIn(flag,workflow)


if __name__=='__main__': unittest.main()
