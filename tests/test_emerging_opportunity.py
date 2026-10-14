import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from data.fetchers.emerging_opportunity import STORE, parse_nsdl, parse_shareholding
from data.processors.emerging_opportunity import load, flow_metrics, company_panel, institutional_agreement
from config.emerging_opportunity import SECTORS, EQUITY_SECTORS, sector_store

FIXTURES = Path(__file__).parent / 'fixtures/emerging_opportunity'


class OpportunityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((FIXTURES / 'snapshot.json').read_text())
        cls.domestic_data = json.loads((FIXTURES / 'domestic_snapshot.json').read_text())

    def test_sector_uses_equity_not_total_or_auc_changes(self):
        raw = gzip.decompress((FIXTURES / 'nsdl-2026-09-30.html.gz').read_bytes())
        from datetime import date
        rows = parse_nsdl(raw, date(2026, 9, 30))
        self.assertEqual([r['equity_flow_cr'] for r in rows], [422, 1911])
        self.assertEqual([r['equity_flow_usd_m'] for r in rows], [44, 199])
        self.assertEqual(rows[1]['end_equity_auc_cr'], 289584)
        with self.assertRaises(ValueError):
            parse_nsdl(raw, date(2026, 8, 31))

    def test_services_and_textiles_select_their_own_equity_rows(self):
        from datetime import date
        raw = gzip.decompress((FIXTURES / 'nsdl-2026-09-30.html.gz').read_bytes())
        self.assertEqual([r['equity_flow_cr'] for r in parse_nsdl(raw, date(2026, 9, 30), 'Services')], [905, 1397])
        self.assertEqual([r['equity_flow_cr'] for r in parse_nsdl(raw, date(2026, 9, 30), 'Textiles')], [10, 636])
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            parse_nsdl(raw, date(2026, 9, 30), 'Unknown')

    def test_sector_identity_cannot_cross_load(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            load(STORE, sector='Services')
        for sector in SECTORS:
            data = load(sector=sector)
            self.assertEqual(data['sector'], sector)
            if sector in EQUITY_SECTORS:
                self.assertTrue(flow_metrics(data)['complete'])
            else:
                self.assertEqual(data['flows'], [])
                self.assertTrue(data['universe_complete'])
            self.assertTrue(data['companies'])
            panel = company_panel(data, data['quarters'][-1])
            self.assertTrue(all(r['bucket'] != 'Unassigned' for r in panel['rows']))

    def test_all_equity_sectors_have_distinct_source_rows(self):
        from datetime import date
        raw = gzip.decompress((FIXTURES / 'nsdl-2026-09-30.html.gz').read_bytes())
        self.assertEqual(len(EQUITY_SECTORS), 22)
        for sector in EQUITY_SECTORS:
            rows = parse_nsdl(raw, date(2026, 9, 30), sector)
            self.assertEqual(len(rows), 2)
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            parse_nsdl(raw, date(2026, 9, 30), 'AI Catalysts')

    def test_ai_basket_and_searchable_selector(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('from charts.india_charts.emerging_opportunity import render\nrender()').run(timeout=60)
        self.assertEqual(len(app.selectbox(key='eo-active-sector').options), 23)
        self.assertEqual(app.selectbox(key='eo-active-sector').value, max(EQUITY_SECTORS, key=lambda s: flow_metrics(load(sector=s))['net_cr']))
        self.assertFalse(app.button)
        app.selectbox(key='eo-active-sector').set_value('AI Catalysts').run(timeout=60)
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual([t.label for t in app.tabs], ['Company explorer', 'Sources & method'])
        data = load(sector='AI Catalysts')
        import pandas as pd
        official = pd.read_csv(sector_store('AI Catalysts') / 'sources/ai_catalysts.csv')
        self.assertEqual({c['symbol'] for c in data['companies']}, set(official.Symbol))
        self.assertTrue(all(c['baskets'] == ['ai_catalysts'] for c in data['companies']))
        self.assertFalse(app.metric)
        app.selectbox(key='eo-active-sector').set_value('Information Technology').run(timeout=60)
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual([t.label for t in app.tabs], ['Sector flows', 'Company explorer', 'Sources & method'])

    def test_completed_fortnight_boundaries(self):
        from datetime import date
        from data.fetchers.emerging_opportunity import latest_completed_fortnight, fortnight_window
        for today, expected in [('2026-10-14','2026-09-30'),('2026-10-15','2026-09-30'),
                                ('2026-10-16','2026-10-15'),('2026-11-01','2026-10-31'),
                                ('2026-01-01','2025-12-31'),('2028-03-01','2028-02-29')]:
            self.assertEqual(latest_completed_fortnight(date.fromisoformat(today)).isoformat(), expected)
        self.assertEqual(fortnight_window(date(2026,10,15))[0], date(2026,4,30))

    @staticmethod
    def midmonth_report():
        cells = ['1', 'Consumer Services'] + ['1'] * 96
        for index, value in [(26,111),(38,11),(50,222),(62,22),(2,300),(74,400)]:
            cells[index] = str(value)
        headers=['','','AUC as on September 30, 2026','Net Investment September 16-30, 2026',
                 'Net Investment October 01-15, 2026','AUC as on October 15, 2026']
        return ('<table><tr>'+''.join('<td>'+c+'</td>' for c in headers)+'</tr><tr>'+
                ''.join('<td>'+c+'</td>' for c in cells)+'</tr></table>').encode()

    def test_midmonth_blocks_use_previous_month_and_current_half(self):
        from datetime import date
        rows=parse_nsdl(self.midmonth_report(),date(2026,10,15))
        self.assertEqual([r['date'] for r in rows],['2026-09-30','2026-10-15'])
        self.assertEqual([r['start'] for r in rows],['2026-09-16','2026-10-01'])
        self.assertEqual([r['equity_flow_cr'] for r in rows],[111,222])
        self.assertEqual([r['equity_flow_usd_m'] for r in rows],[11,22])
        with self.assertRaises(ValueError):
            parse_nsdl(self.midmonth_report().replace(b'AUC as on September 30',b'AUC as on September 15'),date(2026,10,15))

    def test_unreleased_report_keeps_previous_complete_window(self):
        from datetime import date
        from unittest.mock import patch
        from data.fetchers.emerging_opportunity import Collector
        previous=copy.deepcopy(self.domestic_data)
        with tempfile.TemporaryDirectory() as folder:
            collector=Collector(store=folder)
            with patch.object(collector,'get',side_effect=OSError('Not released')):
                rows,start=collector.collect_flows(date(2026,10,15),previous)
        data=dict(previous,flows=rows,flows_as_of=rows[-1]['date'],window_start=start.isoformat())
        self.assertEqual(data['flows_as_of'],'2026-09-30')
        self.assertTrue(flow_metrics(data)['complete'])

    def test_released_midmonth_advances_flows_without_advancing_ownership(self):
        from datetime import date
        from unittest.mock import patch
        from data.fetchers.emerging_opportunity import Collector
        collector=Collector(store=STORE)
        previous=copy.deepcopy(self.data)
        def get(url,name):
            if name=='nsdl-2026-10-15.html':
                collector.receipts.append(dict(url=url,file='synthetic-midmonth',sha256='test-only'))
                return self.midmonth_report()
            raw=(STORE/'sources'/name).read_bytes()
            collector.receipts.append(dict(url=url,file='sources/'+name,sha256='test-only'))
            return raw
        with patch.object(collector,'get',side_effect=get):
            rows,start=collector.collect_flows(date(2026,10,15),previous)
        data=dict(previous,flows=rows,flows_as_of=rows[-1]['date'],window_start=start.isoformat())
        self.assertEqual(data['as_of'],'2026-09-30')
        self.assertEqual(data['flows_as_of'],'2026-10-15')
        self.assertEqual(start.isoformat(),'2026-04-15')
        self.assertEqual(rows[-1]['equity_flow_cr'],222)
        self.assertTrue(flow_metrics(data)['complete'])

    def test_filings_outage_preserves_verified_ownership(self):
        from datetime import date
        from unittest.mock import patch
        from data.fetchers.emerging_opportunity import Collector
        import shutil, hashlib
        with tempfile.TemporaryDirectory() as folder:
            store=Path(folder)/'consumer_services'
            shutil.copytree(STORE,store)
            previous=load()
            company=next(c for c in previous['companies'] if c['symbol']=='TRENT')
            previous['companies']=[company]
            previous.pop('digest')
            previous['digest']=hashlib.sha256(json.dumps(previous,sort_keys=True,allow_nan=False).encode()).hexdigest()
            (store/'snapshot.json').write_text(json.dumps(previous))
            collector=Collector(store=store)
            def get(url,name):
                if name.startswith('filings-'):
                    raise OSError('Temporary filings outage')
                if name in ['niftytotalmarket.csv','niftymicrocap250.csv']:
                    raw=b'Company Name,Industry,Symbol,Series,ISIN Code\nTrent Ltd.,Consumer Services,TRENT,EQ,INE849A01020\n'
                    (store/'sources'/name).write_bytes(raw)
                else:
                    raw=(store/'sources'/name).read_bytes()
                collector.receipts.append(dict(url=url,file='sources/'+name,sha256=hashlib.sha256(raw).hexdigest()))
                return raw
            with patch.object(collector,'get',side_effect=get):
                result=collector.collect(date.fromisoformat(previous['as_of']),date.fromisoformat(previous.get('flows_as_of') or previous['as_of']))
            self.assertEqual(result['companies'][0]['holdings'],company['holdings'])
            self.assertTrue(any(f['stage']=='filings' for f in result['failures']))
            self.assertEqual(load(store)['companies'][0]['holdings'],company['holdings'])

    def test_complete_window_and_reversal(self):
        m = flow_metrics(self.data)
        self.assertTrue(m['complete'])
        self.assertEqual(m['net_cr'], 12415)
        self.assertEqual((m['positive'], m['count'], m['current_streak']), (7, 12, 7))

    def test_gap_breaks_streak_instead_of_becoming_zero(self):
        data = copy.deepcopy(self.data)
        data['flows'] = [r for r in data['flows'] if r['date'] != '2026-08-15']
        m = flow_metrics(data)
        self.assertFalse(m['complete'])
        self.assertEqual(m['current_streak'], 3)

    def test_xbrl_aggregate_excludes_named_investor_detail(self):
        raw = gzip.decompress((FIXTURES / 'TRENT-2026-09-30.xml.gz').read_bytes())
        row = parse_shareholding(raw, 'TRENT', '2026-09-30')
        self.assertEqual(row['fpi_shares'], 78572821 + 2882937)
        self.assertEqual(row['total_shares'], 197326321 + 335905980)
        self.assertEqual(row['dii_shares'], 124401025)
        self.assertEqual(row['mf_shares'], 77673328)
        self.assertEqual(row['insurance_shares'], 34502941)
        self.assertLess(row['mf_shares'] + row['insurance_shares'], row['dii_shares'])
        with self.assertRaises(ValueError):
            parse_shareholding(raw, 'DMART', '2026-09-30')
        with self.assertRaises(ValueError):
            parse_shareholding(raw, 'TRENT', '2026-06-30')

    def test_depository_receipts_do_not_inflate_ownership_denominator(self):
        raw = gzip.decompress((FIXTURES / 'LT-2026-06-30.xml.gz').read_bytes())
        row = parse_shareholding(raw, 'LT', '2026-06-30')
        self.assertEqual(row['total_shares'], 1363411493)
        self.assertEqual(row['fpi_shares'], 260441240)
        self.assertAlmostEqual(row['dii_pct'], 43.018755233567624)

    def test_absent_fpi_category_keeps_domestic_observations_available(self):
        from lxml import etree
        root = etree.fromstring(gzip.decompress((FIXTURES / 'TRENT-2026-09-30.xml.gz').read_bytes()))
        for context in root.findall('{http://www.xbrl.org/2003/instance}context'):
            if any('ForeignPortfolioInvestor' in (member.text or '') for member in context.findall('.//{http://xbrl.org/2006/xbrldi}explicitMember')):
                root.remove(context)
        row = parse_shareholding(etree.tostring(root), 'TRENT', '2026-09-30')
        self.assertIsNone(row['fpi_shares'])
        self.assertIsNone(row['fpi_pct'])
        self.assertEqual(row['dii_shares'], 124401025)

    def test_numeric_bse_identifier_still_validates_declared_symbol(self):
        raw = gzip.decompress((FIXTURES / 'ARVINDFASN-2025-09-30.xml.gz').read_bytes())
        row = parse_shareholding(raw, 'ARVINDFASN', '2025-09-30')
        self.assertGreater(row['total_shares'], row['fpi_shares'])

    def test_partial_filings_and_changed_capital_do_not_count_as_flat(self):
        p = company_panel(self.data, '2026-09-30')
        self.assertEqual(p['filed'], 11)
        self.assertEqual(p['comparable'], 6)
        self.assertEqual(p['exclusions'], 5)
        self.assertEqual(p['increases'] + p['decreases'] + p['flat'], p['comparable'])
        self.assertTrue(all(r['addition_cr'] is None for r in p['rows'] if r['capital_change']))
        self.assertTrue(all(r['change_pp'] is None for r in p['rows'] if r['fpi_pct'] is None))

    def test_concentration_is_positive_additions_not_net_flow(self):
        p = company_panel(self.data, '2026-06-30')
        total = sum(r['addition_cr'] for r in p['additions'])
        self.assertGreater(total, 0)
        self.assertAlmostEqual(p['top3_pct'], sum(r['addition_cr'] for r in p['additions'][:3]) / total * 100)
        self.assertAlmostEqual(sum(r['share_of_additions_pct'] for r in p['additions']), 100)
        self.assertTrue(all(r['addition_cr'] > 0 for r in p['additions']))

    def test_normalized_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder)
            data = copy.deepcopy(self.data)
            data['sources'] = []
            data['flows'][0]['equity_flow_cr'] = 99999
            (dest / 'snapshot.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Normalized'):
                load(dest)

    def test_all_normalized_holdings_reconcile_to_archived_filing(self):
        for sector in SECTORS:
            live = load(sector=sector)
            receipts = {s['url']: s['file'] for s in live['sources']}
            for company in live['companies']:
                for holding in company['holdings']:
                    raw = gzip.decompress((sector_store(sector) / receipts[holding['source_url']]).read_bytes())
                    actual = parse_shareholding(raw, company['symbol'], holding['quarter'])
                    for field in ['fpi_shares', 'total_shares', 'fpi_pct', 'dii_shares', 'dii_pct', 'mf_shares', 'mf_pct', 'insurance_shares', 'insurance_pct']:
                        self.assertEqual(actual[field], holding[field])

    def test_domestic_missing_category_and_capital_change_are_excluded(self):
        data = copy.deepcopy(self.domestic_data)
        company = next(c for c in data['companies'] if c['symbol'] == 'TRENT')
        latest = next(h for h in company['holdings'] if h['quarter'] == '2026-09-30')
        latest['dii_pct'] = latest['dii_shares'] = None
        p = company_panel(data, '2026-09-30', 'dii')
        row = next(r for r in p['rows'] if r['symbol'] == 'TRENT')
        self.assertEqual(row['status'], 'Missing ownership category')
        self.assertIsNone(row['addition_cr'])
        self.assertFalse(any(r['symbol'] == 'TRENT' for r in institutional_agreement(data, '2026-09-30')))

    def test_agreement_uses_the_same_comparable_companies(self):
        data = copy.deepcopy(self.domestic_data)
        rows = institutional_agreement(data, '2026-06-30')
        self.assertEqual(len(rows), 26)
        self.assertEqual({r['symbol'] for r in rows if r['agreement'] == 'Both increasing'}, {'ARVINDFASN','SAMHI','V2RETAIL'})
        p = company_panel(data, '2026-06-30', 'dii')
        self.assertEqual(p['increases'], 19)
        self.assertEqual(company_panel(data, '2026-06-30', 'mf')['increases'], 20)

    def test_sector_selector_renders_the_matching_data_and_filters(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('from charts.india_charts.emerging_opportunity import render\nrender()').run(timeout=30)
        for sector in ['Services', 'Textiles', 'Consumer Services']:
            slug = SECTORS[sector]
            app.selectbox(key='eo-active-sector').set_value(sector).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertEqual([t.label for t in app.tabs], ['Sector flows', 'Company explorer', 'Sources & method'])
            self.assertEqual(app.metric[0].value, f"₹{flow_metrics(load(sector=sector))['net_cr']:,.0f} cr")
            suffix = '' if sector == 'Consumer Services' else '-' + slug
            app.radio(key='eo-flow-frequency' + suffix).set_value('Monthly')
            app.radio(key='eo-flow-unit' + suffix).set_value('US$ million')
            app.selectbox(key='eo-company-quarter' + suffix).set_value(load(sector=sector)['quarters'][-1])
            app.run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            for group in ['FPI', 'Mutual funds', 'Insurers', 'DII']:
                app.radio(key='eo-company-investor' + suffix).set_value(group)
                app.run()
                self.assertFalse(app.exception, [e.message for e in app.exception])
                self.assertTrue(any(group + ' ownership (%)' in frame.value.columns for frame in app.dataframe))


if __name__ == '__main__':
    unittest.main()
