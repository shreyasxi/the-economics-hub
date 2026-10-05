"""Official NSE valuation audit and production refresh regression tests."""
import csv
from datetime import date
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from data.fetchers.nse_valuations.collector import SCHEMA, parse, collect_month, longest, audit
import copy
import json
import requests
from data.fetchers.nse_valuations import collector as c
from data.fetchers.nse_valuations import production as p


def fixture(name='Nifty 50', observed='30-10-2016', pe='', pb='1.23'):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(SCHEMA)
    writer.writerow([name, observed]+['1']*8+[pe,pb,'0'])
    return out.getvalue().encode()


class AuditTests(unittest.TestCase):
    def test_blank_remains_missing(self):
        row = parse(fixture(), date(2016,10,30))['Nifty 50']
        self.assertEqual(row['P/E'],'')
        self.assertEqual(row['P/B'],'1.23')

    def test_reject_html_schema_dates_numbers_duplicates_and_aliases(self):
        payload = fixture()
        for bad in [b'<html>Error</html>', payload.replace(b'P/E',b'PE'), fixture(observed='29-10-2016'), fixture(pe='NaN'), fixture(name='NIFTY 50'), payload+payload.split(b'\r\n')[1]+b'\r\n']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse(bad,date(2016,10,30))

    def test_backwards_includes_weekends_without_calendar_assumption(self):
        calls = []
        def fake(day, root):
            calls.append(day)
            if day.day == 30:
                return {'Nifty 50':{}}, {'observation_date':str(day)}, []
            return None,None,[{'outcome':'archive_not_found'}]
        with patch('data.fetchers.nse_valuations.collector.fetch',side_effect=fake):
            result = collect_month('2016-10',date(2016,10,31),Path('.'))
        self.assertEqual(calls,[date(2016,10,31),date(2016,10,30)])
        self.assertEqual(result['status'],'validated')

    def test_error_does_not_silently_pick_earlier_date(self):
        with patch('data.fetchers.nse_valuations.collector.fetch',return_value=(None,None,[{'outcome':'unresolved_error'}])) as mock:
            result = collect_month('2016-10',date(2016,10,31),Path('.'))
        self.assertEqual(result['status'],'unresolved')
        self.assertEqual(mock.call_count,1)

    def test_duplicate_month_index_rejected(self):
        entry = dict(month='2016-10',status='no_archive_found',rows={})
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError,'Duplicate month/index'):
            audit([entry,entry],Path(folder),date(2016,10,31))

    def test_official_dash_preserved_in_extraction(self):
        row = parse(fixture(pe='-'),date(2016,10,30))['Nifty 50']
        self.assertEqual(row['P/E'],'-')

    def test_gap_run(self):
        self.assertEqual(longest([True,True,False,True,True,True,False]),3)


def payload(day, pe='10', pb='2'):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(c.SCHEMA)
    for name in c.NAMES:
        writer.writerow([name,day.strftime('%d-%m-%Y')]+['1']*8+[pe,pb,'1'])
    return out.getvalue().encode()


def history():
    return [dict(month=month, **{'Index Name':name,'P/E':'10','P/B':'2'},
                 observation_date=month+'-01',partial_month=False)
            for month in c.months_to(date(2026,10,4)) for name in p.APPROVED_METRICS]


def current(pe='10',pb='2'):
    return {name:{'P/E':pe,'P/B':pb} for name in p.APPROVED_METRICS}


def seed(root):
    entries = []
    for day in [date(2026,8,31),date(2026,9,1)]:
        blob = payload(day)
        folder = root/'sources'/str(day)
        folder.mkdir(parents=True)
        meta = dict(source_url=c.URL.format(date=day.strftime('%d%m%Y')),
                    observation_date=str(day),retrieved_at=c.stamp(),sha256=c.sha(blob))
        (folder/'raw.csv').write_bytes(blob)
        (folder/'manifest.json').write_text(json.dumps(meta))
        entries.append(dict(month=day.strftime('%Y-%m'),status='validated',source=meta,
                            rows=c.parse(blob,day),attempts=[],partial_month=day.month==9))
    c.audit(entries,root,date(2026,9,1))
    meta = json.loads((root/'manifest.json').read_text())
    meta['start_month']='2026-08'
    (root/'manifest.json').write_text(json.dumps(meta))


def replies(found):
    def get(url, **kwargs):
        response = requests.Response()
        response.url = url
        response.status_code = 200 if url[-12:-4] in found else 404
        response._content = found.get(url[-12:-4],b'<html>404</html>')
        response.headers['Content-Type']='text/csv' if response.status_code==200 else 'text/html'
        return response
    return get


class PercentileTests(unittest.TestCase):
    def test_exact_nine_metric_mapping(self):
        self.assertEqual(p.APPROVED_METRICS, {'Nifty 50':'P/E','Nifty Auto':'P/E','Nifty FMCG':'P/E', 'Nifty IT':'P/E','Nifty Pharma':'P/E','Nifty Bank':'P/B','Nifty Metal':'P/B','Nifty Realty':'P/B','Nifty Oil & Gas':'P/B'})

    def test_pe_era_and_current_month_excluded_with_exact_le_formula(self):
        monthly = history()
        for r in monthly:
            if r['month']<'2021-04' or r['month']=='2026-10':
                r['P/E']='999'
        rows, warnings = p.calculate(monthly,current(), '2026-10-01')
        self.assertFalse(warnings)
        for row in rows:
            if row['metric']=='P/E':
                self.assertEqual(row['historical_count'],66)
                self.assertEqual(row['history_start'],'2021-04')
                self.assertEqual(row['history_end'],'2026-09')
                self.assertEqual(row['percentile'],100)
                self.assertNotIn('2026-10',row['reference_months'])

    def test_pb_ten_year_cap_and_oil_actual_history(self):
        monthly = history()
        monthly.extend(dict(month='2016-09',**{'Index Name':n,'P/B':'999','P/E':'999'}) for n in p.APPROVED_METRICS)
        for row in monthly:
            if row['Index Name']=='Nifty Oil & Gas' and row['month']<'2020-01':
                row['P/B']='999'  # Known archive start gates even spurious earlier values.
        rows, warnings = p.calculate(monthly,current(),'2026-10-01')
        self.assertFalse(warnings)
        indexed={r['index']:r for r in rows}
        for n in ['Nifty Bank','Nifty Metal','Nifty Realty']:
            self.assertEqual(indexed[n]['historical_count'],120)
            self.assertEqual(indexed[n]['history_start'],'2016-10')
        self.assertEqual(indexed['Nifty Oil & Gas']['historical_count'],81)
        self.assertEqual(indexed['Nifty Oil & Gas']['history_start'],'2020-01')

    def test_reference_end_tracks_source_month_not_calendar_cutoff(self):
        rows,_ = p.calculate(history(),current(),'2026-09-30')
        for row in rows:
            self.assertEqual(row['history_end'],'2026-08')
            self.assertNotIn('2026-09',row['reference_months'])
            self.assertNotIn('2026-10',row['reference_months'])

    def test_missing_history_never_filled_and_sixty_threshold(self):
        monthly = history()
        blanks = ['2021-04','2021-05','2021-06','2021-07','2021-08','2021-09']
        for row in monthly:
            if row['Index Name']=='Nifty Auto' and row['month'] in blanks:
                row['P/E']='-' if row['month']=='2021-04' else ''
        rows,_ = p.calculate(monthly,current(),'2026-10-01')
        auto=next(r for r in rows if r['index']=='Nifty Auto')
        self.assertEqual(auto['historical_count'],60)
        self.assertNotIn('2021-05',auto['reference_months'])
        next(r for r in monthly if r['Index Name']=='Nifty Auto' and r['month']=='2021-10')['P/E']=''
        rows,warnings=p.calculate(monthly,current(),'2026-10-01')
        self.assertNotIn('Nifty Auto',[r['index'] for r in rows])
        self.assertTrue(any('59 valid completed' in w for w in warnings))

    def test_current_missing_omitted_without_prior_value_substitution(self):
        values=current()
        values['Nifty IT']['P/E']='-'
        rows,warnings=p.calculate(history(),values,'2026-10-01')
        self.assertNotIn('Nifty IT',[r['index'] for r in rows])
        self.assertTrue(any('current P/E missing' in w for w in warnings))

    def test_bounds_and_benchmark_first_then_descending(self):
        for raw,expected in [('0',0),('10',100),('999',100)]:
            rows,_=p.calculate(history(),current(pe=raw,pb=raw),'2026-10-01')
            self.assertEqual(rows[0]['index'],'Nifty 50')
            self.assertTrue(all(0<=r['percentile']<=100 for r in rows))
            self.assertEqual(rows[0]['percentile'],expected)
            self.assertEqual([r['percentile'] for r in rows[1:]],sorted([r['percentile'] for r in rows[1:]],reverse=True))

    def test_fraction_and_ties_use_exact_less_than_or_equal(self):
        monthly=history()
        next(r for r in monthly if r['Index Name']=='Nifty IT' and r['month']=='2021-04')['P/E']='11'
        rows,_=p.calculate(monthly,current(),'2026-10-01')
        it=next(r for r in rows if r['index']=='Nifty IT')
        self.assertAlmostEqual(it['percentile'],65/66*100)

    def test_partial_old_month_not_counted_and_duplicates_rejected(self):
        monthly=history()
        next(r for r in monthly if r['Index Name']=='Nifty IT' and r['month']=='2026-09')['partial_month']=True
        rows,_=p.calculate(monthly,current(),'2026-10-01')
        self.assertEqual(next(r for r in rows if r['index']=='Nifty IT')['historical_count'],65)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            p.calculate(monthly+[monthly[0]],current(),'2026-10-01')


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        seed(self.root)

    def test_finalize_partial_month_at_final_available_archive_incrementally(self):
        found={'01102026':payload(date(2026,10,1)), '29092026':payload(date(2026,9,29))}
        with patch.object(c.requests,'get',side_effect=replies(found)) as get:
            snapshot,status=p.update(self.root,date(2026,10,4))
        self.assertEqual(status['finalized_months'],['2026-09'])
        self.assertEqual(snapshot['observation_date'],'2026-10-01')
        self.assertEqual(len(get.call_args_list),6)
        with (self.root/'monthly.csv').open() as stream:
            rows=list(csv.DictReader(stream))
        september=[r for r in rows if r['month']=='2026-09']
        self.assertTrue(all(r['observation_date']=='2026-09-29' and r['partial_month']=='False' for r in september))
        c.verify(self.root)
        with patch.object(c.requests,'get',side_effect=replies(found)) as get:
            _,status=p.update(self.root,date(2026,10,4))
        self.assertEqual(status['finalized_months'],[])
        self.assertEqual(len(get.call_args_list),4)

    def test_fresh_checkout_without_ignored_run_logs_updates_successfully(self):
        logs = self.root/'runs'
        for log in logs.iterdir():
            log.unlink()
        logs.rmdir()
        found={'01102026':payload(date(2026,10,1)), '29092026':payload(date(2026,9,29))}
        with patch.object(c.requests,'get',side_effect=replies(found)):
            _,status=p.update(self.root,date(2026,10,4))
        self.assertEqual(status['status'],'ready')
        self.assertTrue(list(logs.glob('*.json')))
        c.verify(self.root)

    def test_html_latest_is_not_csv_and_does_not_fall_back(self):
        before=(self.root/'monthly.csv').read_bytes()
        with patch.object(c.requests,'get',side_effect=replies({'04102026':b'<html>blocked</html>'})), patch.object(c.time,'sleep'):
            with self.assertRaisesRegex(ValueError,'Unresolved latest archive'):
                p.update(self.root,date(2026,10,4))
        self.assertEqual(before,(self.root/'monthly.csv').read_bytes())
        self.assertEqual(json.loads((self.root/'update_status.json').read_text())['status'],'failed_chart_must_be_omitted')
        with self.assertRaisesRegex(ValueError,'No successful'):
            p.load_chart_data(self.root,date(2026,10,4))

    def test_revised_cached_current_is_rejected_raw_remains_immutable(self):
        day=date(2026,9,1)
        path=self.root/'sources'/str(day)/'raw.csv'
        before=path.read_bytes()
        with patch.object(c.requests,'get',side_effect=replies({'01092026':payload(day,pe='99')})), patch.object(c.time,'sleep'):
            rows,_,attempts=c.fetch(day,self.root,revalidate=True)
        self.assertIsNone(rows)
        self.assertIn('Official archive changed',attempts[-1]['error'])
        self.assertEqual(before,path.read_bytes())

    def test_corruption_detected_before_any_network(self):
        path=self.root/'sources'/'2026-08-31'/'raw.csv'
        path.write_bytes(b'corrupted')
        with patch.object(c.requests,'get') as get, self.assertRaisesRegex(ValueError,'provenance mismatch'):
            p.update(self.root,date(2026,10,4))
        get.assert_not_called()

    def test_old_run_readiness_does_not_allow_stale_chart(self):
        (self.root/'update_status.json').write_text(json.dumps(dict(status='ready',requested_cutoff='2026-10-03')))
        with self.assertRaisesRegex(ValueError,'No successful'):
            p.load_chart_data(self.root,date(2026,10,4))

    def test_optional_chart_failure_removes_old_artifact(self):
        from generate_india import chart_sector_valuations
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'22_india_sector_valuations.png').write_bytes(b'old')
            (root/'22_india_sector_valuations.json').write_text('{}')
            with patch.dict('os.environ',{'NSE_VALUATIONS_UPDATE_FAILED':'true'}):
                self.assertIsNone(chart_sector_valuations(root))
            self.assertFalse((root/'22_india_sector_valuations.png').exists())

    def test_historical_audit_verification_still_passes(self):
        c.verify(c.ROOT)


if __name__ == '__main__':
    unittest.main()
