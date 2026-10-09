"""Offline official fixtures: monthly source contracts, revisions and UI routing."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

import openpyxl

from charts.india_charts.india_mospi_activity import heatmap_data, validate_heatmap, cell_style, render_youth, EconStyle, youth_snapshot_row, industry_leaders
from charts.loader import get_charts, chart_key
from data.fetchers import mospi_iip_industries as iip, mospi_plfs_monthly as plfs
from data.fetchers import mospi_dashboard as shared

FIXTURE = Path(__file__).parent / 'fixtures/mospi_activity'
STAMP = '2026-10-09T12:00:00+00:00'


def workbook_bytes(mutate):
    book = openpyxl.load_workbook(FIXTURE/'iip_august_2026.xlsx')
    mutate(book)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def iip_rows(content=None):
    release = json.loads((FIXTURE/'releases.json').read_text())['data'][0]
    return iip.parse_annexure(content or (FIXTURE/'iip_august_2026.xlsx').read_bytes(),
        shared.attachment(release, '.xlsx'), release['published_year'],
        iip.release_statuses((FIXTURE/'iip_release_status.txt').read_text(), '2026-08'),
        shared.attachment(release, '.pdf'), STAMP)


def plfs_rows(raw=None):
    release = json.loads((FIXTURE/'bulletins.json').read_text())['data'][0]
    content = (FIXTURE/'plfs_monthly_urban_persons.json').read_bytes()
    return plfs.parse_api(raw or json.loads(content)['data'], release['published_year'],
        shared.attachment(release, '.pdf'), STAMP, hashlib.sha256(content).hexdigest())


class IIPIndustriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = iip_rows()

    def test_official_monthly_table_and_universe(self):
        self.assertEqual(len(self.rows), 41*23)
        self.assertEqual({r['nic_code'] for r in self.rows}, {str(n) for n in range(10, 33)})
        self.assertEqual(self.rows[0]['month'], '2023-04')
        self.assertEqual(self.rows[-1]['month'], '2026-08')
        self.assertEqual({r['base_year'] for r in self.rows}, {'2022-23'})
        self.assertEqual(self.rows[0]['industry'], 'Manufacture of food products')

    def test_five_historical_observations_and_latest_are_published_values(self):
        lookup = {(r['month'], r['nic_code']): r for r in self.rows}
        for m, c, level, growth in [('2026-03','10',103.5,1.3),
                                    ('2026-04','10',100.5,5.5),
                                    ('2026-05','10',103.3,5.2),
                                    ('2026-06','10',103.6,10.3),
                                    ('2026-07','10',105.5,2.1),
                                    ('2026-08','27',170.2,30.9)]:
            # Actual annexure values, not a YoY calculation from rounded indices.
            self.assertEqual(lookup[(m,c)]['index'], level)
            self.assertAlmostEqual(lookup[(m,c)]['yoy_growth'], growth)

    def test_source_detection_rejects_html_and_missing_table(self):
        with self.assertRaises(ValueError):
            iip_rows(b'<html>server error</html>')
        with self.assertRaises(ValueError):
            iip_rows(workbook_bytes(lambda w: setattr(w[iip.SHEET], 'title', 'Old table')))

    def test_source_rejects_wrong_base_and_wrong_growth_heading(self):
        for cell, value in [('A2','(Base 2011-12)'), ('A45','Month-on-month growth')]:
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                iip_rows(workbook_bytes(lambda w: w[iip.SHEET].__setitem__(cell, value)))

    def test_incomplete_manufacturing_block_and_missing_month_column(self):
        with self.assertRaises(ValueError):
            iip_rows(workbook_bytes(lambda w: w[iip.SHEET].delete_rows(11)))
        with self.assertRaises(ValueError):
            iip_rows(workbook_bytes(lambda w: w[iip.SHEET].__setitem__('AR6', None)))

    def test_duplicate_industry_month_rejection(self):
        with self.assertRaises(ValueError):
            iip.validate(deepcopy(self.rows) + [deepcopy(self.rows[0])])

    def test_incomplete_month_rejection(self):
        with self.assertRaises(ValueError):
            iip.validate(deepcopy(self.rows[1:]))

    def test_nullable_published_cells_are_missing_not_filled(self):
        rows = deepcopy(self.rows)
        rows[0]['index'] = None
        rows[0]['yoy_growth'] = None
        self.assertIsNone(iip.validate(rows)[0]['yoy_growth'])

    def test_official_statuses_not_old_revision_timetable(self):
        statuses = iip.release_statuses((FIXTURE/'iip_release_status.txt').read_text(), '2026-08')
        self.assertEqual(statuses, {'2026-08':'Quick estimate', '2026-07':'Final estimate'})
        text = (FIXTURE/'iip_release_status.txt').read_text().replace('final revision', 'first revision')
        self.assertEqual(iip.release_statuses(text,'2026-08')['2026-07'], 'First revision')
        self.assertEqual(self.rows[0]['status'], 'Not specified')

    def test_newer_release_replaces_vintage_and_older_cannot(self):
        old = deepcopy(self.rows)
        earlier = next(r for r in old if (r['month'],r['nic_code']) == ('2026-07','32'))
        original = earlier['index']
        earlier['status'] = 'Quick estimate'
        earlier['release_date'] = '2026-08-28'
        earlier['index'] = 118.4
        merged = shared.reconcile(old, deepcopy(self.rows), ('month','nic_code'), iip.validate)
        current = next(r for r in merged if (r['month'],r['nic_code']) == ('2026-07','32'))
        self.assertEqual(current['index'], original)
        self.assertEqual(current['status'], 'Final estimate')
        again = shared.reconcile(merged, old, ('month','nic_code'), iip.validate)
        self.assertEqual(next(r for r in again if (r['month'],r['nic_code']) == ('2026-07','32'))['index'], original)

    def test_conflicting_same_vintage_and_history_loss_fail(self):
        rows = deepcopy(self.rows)
        rows[-1]['yoy_growth'] = 99
        with self.assertRaises(ValueError):
            shared.reconcile(deepcopy(self.rows), rows, ('month','nic_code'), iip.validate)
        with self.assertRaises(ValueError):
            shared.reconcile(deepcopy(self.rows), deepcopy(self.rows[23:]), ('month','nic_code'), iip.validate)

    def test_no_superseded_wpi_or_legacy_base_splice(self):
        for field, value in [('deflator_regime','WPI'), ('release_date','2026-06-01'), ('base_year','2011-12')]:
            rows = deepcopy(self.rows)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                iip.validate(rows)

    def test_breadth_sorting_and_top_bottom(self):
        data = heatmap_data(deepcopy(self.rows))
        self.assertEqual(len(data['months']),12)
        self.assertEqual(data['months'][0]['month'],'2025-09')
        self.assertEqual(data['breadth']['expanding'],18)
        self.assertEqual(data['breadth']['contracting'],5)
        self.assertEqual(data['rows'][0]['nic_code'],'27')
        self.assertEqual(data['breadth']['bottom_three'][0]['nic_code'],'12')
        self.assertEqual(data['rows'][0]['cells'][-1]['label'],'+30.9')

    def test_color_saturation_never_clips_numbers(self):
        self.assertEqual(cell_style(20),cell_style(400))
        self.assertEqual(cell_style(-20),cell_style(-400))

    def test_ttm_leader_uses_output_totals_not_average_monthly_growth(self):
        rows = deepcopy(self.rows)
        for row in rows:
            row['index'] = 150 if row['nic_code'] == '30' and row['month'] >= '2025-09' else 100
        leaders = industry_leaders(rows)
        self.assertEqual(leaders[0]['nic_code'], '27')
        self.assertEqual(leaders[1]['nic_code'], '30')
        self.assertAlmostEqual(leaders[1]['value'], 50)
        self.assertIn('Sep 25–Aug 26', leaders[1]['period'])

    def test_ttm_leader_requires_all_industries_and_complete_windows(self):
        rows = deepcopy(self.rows)
        next(r for r in rows if r['month'] == '2024-09')['index'] = None
        self.assertEqual(len(industry_leaders(rows)), 1)
        rows = [r for r in self.rows if r['month'] != '2024-09']
        self.assertEqual(len(industry_leaders(deepcopy(rows))), 1)
        rows=deepcopy(self.rows)
        rows[-1]['yoy_growth']=400
        data=heatmap_data(rows)
        self.assertEqual(data['rows'][0]['cells'][-1]['value'],400)
        self.assertEqual(data['rows'][0]['cells'][-1]['label'],'+400.0')
        rows[-1]['yoy_growth']=0
        data=heatmap_data(rows)
        row=next(r for r in data['rows'] if r['nic_code']=='32')
        self.assertEqual(row['cells'][-1]['label'],'+0.0')

    def test_json_schema_round_trip_and_tamper_rejection(self):
        data=heatmap_data(deepcopy(self.rows))
        validate_heatmap(json.loads(json.dumps(data,allow_nan=False)))
        data['rows'][0]['cells'][-1]['label']='+20.0'
        with self.assertRaises(ValueError):validate_heatmap(data)

    def test_failed_fetch_preserves_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'iip.csv'
            shared.write_csv(target,self.rows,iip.FIELDS)
            before=target.read_bytes()
            with patch.object(iip,'listing',side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):iip.fetch(target,session=Mock())
            self.assertEqual(before,target.read_bytes())
            self.assertEqual(len(list(Path(folder).iterdir())),1)

    def test_malformed_download_after_discovery_preserves_history(self):
        release=json.loads((FIXTURE/'releases.json').read_text())['data']
        document=MagicMock();document.__enter__.return_value=[Mock(get_text=Mock(
            return_value=(FIXTURE/'iip_release_status.txt').read_text()))]
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'iip.csv';shared.write_csv(target,self.rows,iip.FIELDS)
            before=target.read_bytes()
            with patch.object(iip,'listing',return_value=release),\
                 patch.object(iip,'download',side_effect=[b'PDF',b'<html>empty</html>']),\
                 patch('fitz.open',return_value=document):
                with self.assertRaises(ValueError):iip.fetch(target,session=Mock())
            self.assertEqual(before,target.read_bytes())


class PLFSMonthlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=plfs_rows()
        cls.raw=json.loads((FIXTURE/'plfs_monthly_urban_persons.json').read_text())['data']

    def test_monthly_cws_exact_table_and_start(self):
        self.assertEqual(len(self.rows),34)
        self.assertEqual(self.rows[0]['month'],'2025-04')
        self.assertEqual(self.rows[-1]['month'],'2026-08')
        self.assertEqual({r['table_id'] for r in self.rows},{plfs.TABLE})
        self.assertEqual({r['activity_status'] for r in self.rows},{'CWS'})

    def test_five_month_bulletin_spot_checks_both_age_groups(self):
        checked=plfs.verify_bulletin((FIXTURE/'plfs_statement3.txt').read_text(),self.rows,'2026-08')
        self.assertEqual(len(checked),10)
        self.assertEqual([checked[(m,'15–29')] for m in ['2026-04','2026-05','2026-06','2026-07','2026-08']],
                         [18.0,17.5,18.2,18.6,18.7])
        self.assertEqual(checked[('2026-08','15+')],6.8)

    def test_filter_urban_age_persons_geography(self):
        for field,value in [('sector','rural'),('gender','female'),('state','Maharashtra'),('AgeGroup','0-14 years')]:
            extra=deepcopy(self.raw[0]);extra[field]=value
            self.assertEqual(len(plfs_rows(deepcopy(self.raw)+[extra])),34)
        self.assertEqual({r['age_group'] for r in self.rows},{'15–29','15+'})

    def test_reject_usual_status_quarterly_wrong_indicator_and_units(self):
        for field,value in [('frequency','Quarterly'),('indicator','WPR'),('unit','index'),
                            ('weekly_status','Usual Status'),('activity_status','US')]:
            raw=deepcopy(self.raw);raw[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):plfs_rows(raw)

    def test_month_date_parser_and_prepublication_guard(self):
        self.assertEqual(shared.month('2026','August'),'2026-08')
        for field,value in [('month','Aug'),('month','April-June'),('year','2025-26')]:
            raw=deepcopy(self.raw);raw[0][field]=value
            with self.assertRaises(ValueError):plfs_rows(raw)
        raw=deepcopy(self.raw);raw[0].update(year='2025',month='January')
        with self.assertRaises(ValueError):plfs_rows(raw)

    def test_duplicate_month_rejection(self):
        with self.assertRaises(ValueError):plfs_rows(self.raw+[deepcopy(self.raw[0])])
        with self.assertRaises(ValueError):plfs.validate(deepcopy(self.rows)+[deepcopy(self.rows[0])])

    def test_wrong_table_and_stale_api_rejected(self):
        text=(FIXTURE/'plfs_statement3.txt').read_text()
        with self.assertRaises(ValueError):plfs.parse_statement(text.replace('Statement 3:','Table 4:'))
        with self.assertRaises(ValueError):plfs.verify_bulletin(text,self.rows[:-2],'2026-08')
        rows=deepcopy(self.rows);rows[-1]['value_pct']=99
        with self.assertRaises(ValueError):plfs.verify_bulletin(text,rows,'2026-08')

    def test_no_annual_old_methodology_splice_or_missing_start(self):
        for field,value in [('methodology','Old PLFS'),('frequency','Annual'),('month','2024-12')]:
            rows=deepcopy(self.rows);rows[0][field]=value
            with self.assertRaises(ValueError):plfs.validate(rows)
        with self.assertRaises(ValueError):plfs.validate(deepcopy(self.rows[2:]))

    def test_failed_fetch_preserves_good_history(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'plfs.csv';shared.write_csv(target,self.rows,plfs.FIELDS)
            before=target.read_bytes()
            with patch.object(plfs,'listing',side_effect=ValueError('empty response')):
                with self.assertRaises(ValueError):plfs.fetch(target,session=Mock())
            self.assertEqual(before,target.read_bytes())

    def test_malformed_api_after_bulletin_download_preserves_history(self):
        release=json.loads((FIXTURE/'bulletins.json').read_text())['data']
        document=MagicMock();document.__enter__.return_value=[Mock(get_text=Mock(
            return_value=(FIXTURE/'plfs_statement3.txt').read_text()))]
        raw=deepcopy(self.raw);raw[0]['unit']='index'
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'plfs.csv';shared.write_csv(target,self.rows,plfs.FIELDS)
            before=target.read_bytes()
            with patch.object(plfs,'listing',return_value=release),\
                 patch.object(plfs,'download',return_value=b'PDF'),\
                 patch.object(plfs,'api_rows',return_value=(raw,[b'bad unit'])),\
                 patch('fitz.open',return_value=document):
                with self.assertRaises(ValueError):plfs.fetch(target,session=Mock())
            self.assertEqual(before,target.read_bytes())

    def test_missing_month_breaks_line_instead_of_interpolation(self):
        rows=[r for r in deepcopy(self.rows) if r['month']!='2025-07']
        captured=[]
        with tempfile.TemporaryDirectory() as folder:
            def capture(fig,path):
                import numpy as np
                lines=fig.axes[0].lines[:2]
                captured.extend([np.asarray(line.get_ydata()) for line in lines])
                import matplotlib.pyplot as plt
                plt.close(fig)
            with patch.object(EconStyle,'save_chart',side_effect=capture):
                render_youth(rows,Path(folder)/'youth.png')
        import math
        self.assertEqual(len(rows),32)
        self.assertTrue(all(math.isnan(values[3]) for values in captured))

    def test_png_save_failure_preserves_existing_chart(self):
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'youth.png';destination.write_bytes(b'previous chart')
            with patch.object(EconStyle,'save_chart',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):render_youth(deepcopy(self.rows),destination)
            self.assertEqual(destination.read_bytes(),b'previous chart')
            self.assertEqual(list(Path(folder).iterdir()),[destination])
        import matplotlib.pyplot as plt
        plt.close('all')


class SharedAndUITests(unittest.TestCase):
    def test_api_empty_malformed_and_pagination_inconsistency(self):
        for payload in [{}, {'statusCode':True,'data':[]},
                        {'statusCode':True,'data':[{}],'meta_data':{'page':1,'totalPages':0}}]:
            response=Mock(url=plfs.URL);response.json.return_value=payload
            with patch.object(shared,'get',return_value=response),self.assertRaises(ValueError):
                shared.api_rows(Mock(),plfs.URL,plfs.PARAMS)
        response=Mock(url=plfs.URL);response.json.side_effect=[
            dict(statusCode=True,data=[{}],meta_data=dict(page=1,totalPages=2,totalRecords=2)),
            dict(statusCode=True,data=[{}],meta_data=dict(page=2,totalPages=2,totalRecords=3))]
        with patch.object(shared,'get',return_value=response),self.assertRaises(ValueError):
            shared.api_rows(Mock(),plfs.URL,plfs.PARAMS)

    def test_listing_source_detection_and_duplicates(self):
        payload=json.loads((FIXTURE/'releases.json').read_text())
        client=Mock();client.post.return_value.url=shared.RELEASES_URL
        client.post.return_value.json.return_value=payload
        rows=shared.listing(client,shared.RELEASES_URL,'Industrial Production')
        r=shared.select_latest(rows,lambda x:'2022-23' in x['title'])
        self.assertEqual(shared.publication_month(r['title']),'2026-08')
        self.assertTrue(shared.attachment(r,'.xlsx').endswith('.xlsx'))
        payload['data'].append(payload['data'][0]);payload['pagination']['totalItems']=2
        with self.assertRaises(ValueError):shared.listing(client,shared.RELEASES_URL,'IIP')

    def test_atomic_failure_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'data.csv';target.write_bytes(b'known good')
            with patch.object(shared.os,'replace',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):shared.atomic_bytes(target,b'new')
            self.assertEqual(target.read_bytes(),b'known good')
            self.assertEqual(list(Path(folder).iterdir()),[target])

    def test_retained_source_checksum_rejects_missing_or_tampered_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            content=(FIXTURE/'iip_august_2026.xlsx').read_bytes()
            checksum=shared.retain(folder,content)
            shared.verify_retained(folder,[dict(raw_sha256=checksum)])
            (Path(folder)/(checksum+'.raw')).write_bytes(b'tampered')
            with self.assertRaises(ValueError):shared.verify_retained(folder,[dict(raw_sha256=checksum)])

    def test_csv_idempotent_vintage_reconcile(self):
        for rows,fields,validator,keys in [(iip_rows(),iip.FIELDS,iip.validate,('month','nic_code')),
                                         (plfs_rows(),plfs.FIELDS,plfs.validate,('month','age_group'))]:
            with tempfile.TemporaryDirectory() as folder:
                target=Path(folder)/'data.csv';shared.write_csv(target,rows,fields)
                out=shared.reconcile(shared.read_csv(target),deepcopy(rows),keys,validator)
                self.assertEqual(out,rows)

    def test_heatmap_html_has_exact_cells_sticky_scroll_and_escaped_labels(self):
        # Extract the pure renderer without importing the Streamlit application.
        tree=ast.parse((shared.ROOT/'app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_iip_heatmap_html')
        namespace={'re':__import__('re')}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'app.py','exec'),namespace)
        data=heatmap_data(iip_rows());data['rows'][0]['display_name']='<script>x</script>'
        html=namespace['_iip_heatmap_html'](data)
        self.assertEqual(html.count('<td '),23*12)
        self.assertIn('+30.9',html)
        self.assertIn('overflow-x:auto',html)
        self.assertIn('position:sticky',html)
        self.assertIn('max-width:100%',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)
        self.assertNotIn('border:1px solid rgba',html)
        self.assertIn('border:1.5px solid #28251f',html)
        self.assertIn('thead tr>th:first-child{background:#28251f;color:#ffffff;font-weight:700',html)
        self.assertIn('border-spacing:2px',html)
        self.assertIn('text-align:center',html)
        for row in data['rows']:
            for cell in row['cells']:
                self.assertIn(f'background:{cell["background"]};color:{cell["foreground"]}',html)
        for footer in (data['methodology_note'], data['missing_note'], 'Base 2022–23 = 100'):
            self.assertNotIn(footer,html)
        for selector in __import__('re').findall(r'([^{}]+)\{',html.split('<style>')[1].split('</style>')[0]):
            if selector.strip().startswith('@media'): continue
            self.assertTrue(all(part.strip().startswith('.iip-') for part in selector.split(',')))

    def test_youth_snapshot_uses_latest_rate_without_mom(self):
        row = youth_snapshot_row(list(reversed(plfs_rows())))
        self.assertEqual(row['value_str'], '18.7%')
        self.assertEqual(row['section'], 'UNEMPLOYMENT')
        self.assertEqual(row['name'], 'Urban Youth (15–29)')
        self.assertEqual(row['unit'], '% · Aug 26')
        self.assertIsNone(row['change'])

    def test_heatmap_not_a_generic_png_and_labour_chart_retired(self):
        with tempfile.TemporaryDirectory() as folder:
            edition=Path(folder)/'india/2026-10';edition.mkdir(parents=True)
            (edition/'india_iip_industry_heatmap.json').write_text('{}')
            chart=edition/'15b_india_urban_youth_unemployment.png';chart.write_bytes(b'chart')
            with patch('charts.loader._get_base_dirs',return_value=[Path(folder)]):
                charts,label=get_charts('india')
            self.assertEqual(charts,[])
            self.assertEqual(chart_key(chart.name),'india_urban_youth_unemployment')
        tree=ast.parse((shared.ROOT/'app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='page_india')
        source=ast.get_source_segment((shared.ROOT/'app.py').read_text(),fn)
        self.assertNotIn('urban_youth_unemployment',source)
        self.assertLess(source.index('_render_grid(activity)'),source.index('_render_iip_industry_heatmap'))


if __name__ == '__main__':
    unittest.main()
