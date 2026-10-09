"""Offline source contracts using actual RBI HTML excerpts and DEA PDFs.

Expected values are read independently from the official tables, not calculated
with the parsers under test. sources.json identifies each captured source.
"""
import copy
import re
import logging
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from bs4 import BeautifulSoup

from data.fetchers import rbi_external as ext
from charts.india_charts.india_external import load_forex, regular_panel, chart_vulnerability, single_quarter_bridges

FIX = Path(__file__).parent / 'fixtures' / 'rbi_external'
SOURCES = json.loads((FIX/'sources.json').read_text())
logging.getLogger('pdfminer').setLevel(logging.ERROR)


def fixture(name): return (FIX/name).read_text()
def url(name): return SOURCES[name]['source_url']
def wss(name='wss_2026-10-02.html'): return ext.parse_wss(fixture(name),url(name))
def reer(name='reer_2026-09-25.html'): return ext.parse_reer(fixture(name),url(name))
def bop(prid):
    name=f'bop_{prid}.html';return ext.parse_bop(fixture(name),url(name))
def debt(prid=63700):
    name=f'debt_{prid}.html';return ext.parse_debt(fixture(name),url(name))


class WssTests(unittest.TestCase):
    def test_total_units_and_observation_not_publication_date(self):
        row=wss()[0]
        self.assertEqual(row['date'],'2026-09-25')
        self.assertEqual(row['release_date'],'2026-10-02')
        self.assertEqual(row['total_reserves_usd_mn'],747557)
        self.assertEqual(row['unit'],'US$ million')
        self.assertEqual(row['source'],'RBI WSS')

    def test_seven_independent_historical_spot_checks(self):
        expected={'2026-08-14':('2026-08-07',707002), '2026-08-21':('2026-08-14',716907),
                  '2026-08-28':('2026-08-21',729328), '2026-09-04':('2026-08-28',740803),
                  '2026-09-11':('2026-09-04',785706), '2026-09-18':('2026-09-11',780782),
                  '2026-09-25':('2026-09-18',765901)}
        for published,(observed,value) in expected.items():
            row=wss('wss_'+published+'.html')[0]
            self.assertEqual((row['date'],row['total_reserves_usd_mn']),(observed,value))

    def test_wrong_units_and_malformed_sources_rejected(self):
        for html in [fixture('wss_2026-10-02.html').replace('US$ Mn.','US$ billion'),
                     fixture('wss_2026-10-02.html').replace('747557','NaN'),'<html>Access denied</html>',
                     fixture('wss_2026-10-02.html').replace('Foreign Exchange Reserves','Bank Assets')]:
            with self.assertRaises(ext.ExternalDataError): ext.parse_wss(html,url('wss_2026-10-02.html'))

    def test_components_must_reconcile(self):
        with self.assertRaises(ext.ExternalDataError):
            ext.parse_wss(fixture('wss_2026-10-02.html').replace('615411','600000'),url('wss_2026-10-02.html'))

    def test_duplicate_total_row_and_date_rejected(self):
        soup=BeautifulSoup(fixture('wss_2026-10-02.html'),'html.parser')
        row=next(tr for tr in soup.select('tr') if '1 Total Reserves' in tr.get_text())
        row.insert_after(copy.copy(row))
        with self.assertRaises(ext.ExternalDataError):ext.parse_wss(str(soup),url('wss_2026-10-02.html'))
        with self.assertRaises(ext.ExternalDataError):ext.merge_rows([],wss()*2,'wss')

    def test_overlap_rounding_and_definition_mismatch(self):
        new=[];old=[]
        legacy=[707001.7,716906.6,729328.3,740803.5,785706.2,780781.8,765900.7]
        for p,v in zip(sorted(FIX.glob('wss_*.html'))[:-1],legacy):
            row=wss(p.name)[0];new.append(row);old.append(dict(row,total_reserves_usd_mn=v,source='legacy'))
        self.assertEqual(len(ext.compare_legacy(old,new)),7)
        old[0]['total_reserves_usd_mn']+=5
        with self.assertRaises(ext.ExternalDataError):ext.compare_legacy(old,new)
        with self.assertRaises(ext.ExternalDataError):ext.compare_legacy(new[:4],new)

    def test_revision_replaces_date_without_duplicate_and_stale_release_ignored(self):
        original=wss()[0];revised=dict(original,total_reserves_usd_mn=747560,release_date='2026-10-09')
        merged=ext.merge_rows([original],[revised],'wss')
        self.assertEqual(len(merged),1);self.assertEqual(merged[0]['total_reserves_usd_mn'],747560)
        self.assertEqual(ext.merge_rows(merged,[original],'wss'),merged)

    def test_latest_discovery_is_dynamic(self):
        urls=ext.discover_wss_releases('<html>RBI Weekly Statistical Supplement published release calendar <a href="BS_viewWssExtract.aspx?SelectedDate=10/02/2026">2</a></html>',8)
        self.assertEqual(len(urls),8);self.assertIn('10/02/2026',urls[-1]);self.assertIn('08/14/2026',urls[0])
        newer=ext.discover_wss_releases('<html>RBI Weekly Statistical Supplement published release calendar <a href="BS_viewWssExtract.aspx?SelectedDate=10/09/2026">9</a></html>',1)
        self.assertIn('10/09/2026',newer[0])
        with self.assertRaises(ext.ExternalDataError):ext.discover_wss_releases('<html>RBI calendar empty; no data release present</html>')

    def test_storage_conversion_and_missing_week_change(self):
        rows=wss('wss_2026-09-18.html')+wss()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'wss.csv';ext.atomic_write(p,rows,ext.WSS_COLUMNS,'wss')
            frame=load_forex(path=p)
            self.assertEqual(frame['forex_reserves_usd_bn'].iloc[-1],747.557)
            self.assertTrue(frame['forex_reserves_wow_chg'].isna().all())


class ReerTests(unittest.TestCase):
    def test_exact_monthly_trade_series_and_metadata(self):
        rows=reer();self.assertEqual([(r['date'],r['reer']) for r in rows],
                                   [('2025-08-01',98.75),('2026-07-01',91.78),('2026-08-01',92)])
        for r in rows:
            self.assertEqual(r['base'],'2015-16=100');self.assertEqual(r['methodology'],ext.REER_METHOD)
            self.assertEqual(r['provisional'],'true');self.assertEqual(r['unit'],'index')

    def test_five_history_months_and_latest(self):
        name='reer_handbook_2026.html';rows=ext.parse_reer_history(fixture(name),url(name))
        got={r['date']:r['reer'] for r in rows}
        for d,v in [('2021-01-01',102.98),('2022-02-01',104.10),('2023-03-01',100.11),
                    ('2024-06-01',106.30),('2025-12-01',95.11),('2026-05-01',89.21)]:self.assertEqual(got[d],v)
        self.assertEqual(len(rows),65)
        self.assertEqual(reer()[-1]['reer'],92)

    def test_bulletin_history_overlap_and_missing_june_is_official(self):
        name='reer_handbook_2026.html';history=ext.parse_reer_history(fixture(name),url(name))
        prior=reer('reer_2026-08-25.html')
        overlap=[r for r in prior if r['date']=='2025-07-01'][0]
        self.assertEqual(next(r['reer'] for r in history if r['date']==overlap['date']),overlap['reer'])
        merged=ext.merge_rows(history,prior,'reer');merged=ext.merge_rows(merged,reer(),'reer')
        self.assertEqual(next(r['reer'] for r in merged if r['date']=='2026-06-01'),91.26)
        self.assertEqual(len(merged),68)

    def test_wrong_table_basket_base_or_cpi_is_rejected(self):
        raw=fixture('reer_2026-09-25.html')
        for changed in [raw.replace('37. Indices','36. Indices'),raw.replace('40-Currency Basket','36-Currency Basket'),
                        raw.replace('40-Currency Basket (Base: 2015-16=100)','40-Currency Basket (Base: 2022-23=100)'),
                        raw.replace('Consumer Price Index (combined)','Wholesale Price Index')]:
            with self.assertRaises(ext.ExternalDataError):ext.parse_reer(changed,url('reer_2026-09-25.html'))

    def test_duplicate_month_and_bad_value_rejected(self):
        raw=fixture('reer_2026-09-25.html')
        with self.assertRaises(ext.ExternalDataError):ext.parse_reer(raw.replace('>Jul<','>Aug<'),url('reer_2026-09-25.html'))
        with self.assertRaises(ext.ExternalDataError):ext.parse_reer(raw.replace('92.00','NaN'),url('reer_2026-09-25.html'))
        with self.assertRaises(ext.ExternalDataError):ext.validate_rows(reer()*2,'reer')

    def test_history_mixed_base_discontinuity_rejected(self):
        name='reer_handbook_2026.html'
        raw=fixture(name).replace('2015-16=100','2022-23=100',1)
        with self.assertRaises(ext.ExternalDataError):ext.parse_reer_history(raw,url(name))

    def test_methodology_break_in_storage_rejected(self):
        row=reer()[-1]
        for field,value in [('base','2004-05=100'),('methodology','36 currencies'),('date','2026-08-31')]:
            with self.assertRaises(ext.ExternalDataError):ext.merge_rows([], [dict(row,**{field:value})],'reer')


class VulnerabilityTests(unittest.TestCase):
    def test_quarterly_ratio_sign_latest_and_exclude_annual(self):
        rows=bop(63493)
        self.assertEqual([(r['date'],r['current_account_gdp_pct']) for r in rows],[('2025-06-30',-.4),('2026-06-30',-.5)])
        rows=bop(62890);self.assertEqual(next(r['current_account_gdp_pct'] for r in rows if r['date']=='2026-03-31'),.7)
        self.assertEqual(len(rows),3)

    def test_current_account_arithmetic_and_unit_validation(self):
        raw=fixture('bop_63493.html')
        for changed in [raw.replace('-4.2','-7.2'),raw.replace('(US$ billion)','(US$ million)'),raw.replace('A. Current Account','Goods Account')]:
            with self.assertRaises(ext.ExternalDataError):ext.parse_bop(changed,url('bop_63493.html'))

    def test_explicit_revisions_and_latest_release_wins(self):
        rows=ext.merge_rows(bop(61714),bop(62317),'cab');rows=ext.merge_rows(rows,bop(62890),'cab')
        values={r['date']:r for r in rows}
        self.assertEqual(values['2025-09-30']['current_account_gdp_pct'],-1.5)
        self.assertEqual(values['2025-12-31']['current_account_gdp_pct'],-1.5)
        self.assertEqual(values['2025-12-31']['cab_status'],'explicit revision')
        strip=lambda observations:[{k:v for k,v in r.items() if k != 'fetched_at'} for r in observations]
        self.assertEqual(strip(ext.merge_rows(rows,bop(61714),'cab')),strip(rows))

    def test_at_least_five_quarterly_cab_spot_checks(self):
        rows=[]
        for prid in [61129,61714,62317,62890,63493]:rows=ext.merge_rows(rows,bop(prid),'cab')
        values={r['date']:r['current_account_gdp_pct'] for r in rows}
        for d,v in [('2025-03-31',1.4),('2025-06-30',-.4),('2025-09-30',-1.5),('2025-12-31',-1.5),('2026-03-31',.7),('2026-06-30',-.5)]:self.assertEqual(values[d],v)

    def test_debt_exact_convention_five_spot_checks_latest(self):
        rows=debt();values={r['date']:r for r in rows}
        for d,v in [('2022-03-31',20),('2023-03-31',22.2),('2024-03-31',19.7),('2025-03-31',20.1),('2026-03-31',21.6),('2026-06-30',23)]:
            self.assertEqual(values[d]['short_term_debt_reserves_pct'],v)
        self.assertEqual(values['2026-06-30']['external_debt_gdp_pct'],20.8)
        self.assertEqual(values['2026-06-30']['debt_maturity'],'original maturity <=1 year')

    def test_debt_denominator_identity_rejects_wrong_ratio(self):
        raw=fixture('debt_63700.html')
        # Table 5 final row: 23.0%, not the separate 50.5% residual ratio.
        with self.assertRaises(ext.ExternalDataError):ext.parse_debt(raw.replace('23.0','50.5'),url('debt_63700.html'))
        with self.assertRaises(ext.ExternalDataError):ext.parse_debt(raw.replace('Per cent','US$ billion'),url('debt_63700.html'))

    def test_dea_pdf_convention_and_revised_previous_quarter(self):
        name='dea_dec2025.pdf';rows=ext.parse_dea_pdf((FIX/name).read_bytes(),url(name),'2026-03-30')
        values={r['date']:r for r in rows}
        for d,v in [('2021-03-31',17.5),('2022-03-31',20),('2023-03-31',22.2),('2024-03-31',19.7),('2025-03-31',20.1)]:
            self.assertEqual(values[d]['short_term_debt_reserves_pct'],v)
        self.assertEqual(values['2025-06-30']['short_term_debt_reserves_pct'],19.3)
        self.assertEqual(values['2025-09-30']['short_term_debt_reserves_pct'],19.7)
        self.assertEqual(values['2025-12-31']['short_term_debt_reserves_pct'],21.9)
        with self.assertRaises(ext.ExternalDataError):ext.parse_dea_pdf(b'<html>no PDF</html>',url(name),'2026-03-30')

    def test_quarter_alignment_and_missing_observations_stay_missing(self):
        cab=bop(63493);merged=ext.merge_rows(cab,debt(),'debt')
        recent=[r for r in merged if r['date']>='2025-06-30']
        # Annual end-March debt records must not be relabelled as quarterly flows.
        self.assertEqual(recent[0]['date'],'2025-06-30')
        blank=[dict.fromkeys(ext.EXT_COLUMNS,'') | r for r in recent]
        frame=regular_panel(blank,['current_account_gdp_pct','short_term_debt_reserves_pct'],pd.offsets.QuarterEnd(startingMonth=12))
        self.assertTrue(pd.isna(frame.loc['2025-09-30','current_account_gdp_pct']))
        self.assertTrue(pd.isna(frame.loc['2025-09-30','short_term_debt_reserves_pct']))
        self.assertEqual(frame.loc['2026-06-30','short_term_debt_reserves_pct'],23)

    def test_duplicate_quarter_and_non_quarter_rejection(self):
        with self.assertRaises(ext.ExternalDataError):ext.merge_rows([],bop(63493)*2,'cab')
        with self.assertRaises(ext.ExternalDataError):ext.validate_rows([dict(bop(63493)[0],date='2025-05-31')],'cab')
        raw=fixture('bop_63493.html').replace('April-June 2026 P','April-June 2025 PR')
        with self.assertRaises(ext.ExternalDataError):ext.parse_bop(raw,url('bop_63493.html'))

    def test_no_composite_and_empty_quarter_rejected(self):
        self.assertFalse(any('score' in field for field in ext.EXT_COLUMNS))
        with self.assertRaises(ext.ExternalDataError):ext.validate_rows([dict.fromkeys(ext.EXT_COLUMNS,'') | {'date':'2026-06-30'}],'external')


class VulnerabilityBackfillTests(unittest.TestCase):
    def test_complete_common_quarterly_coverage(self):
        rows=ext.read_rows(ext.VULNERABILITY_PATH,'external')
        self.assertEqual((len(rows),rows[0]['date'],rows[-1]['date']),
                         (57,'2012-06-30','2026-06-30'))
        frame=regular_panel(rows,['current_account_gdp_pct','short_term_debt_reserves_pct'],
                            pd.offsets.QuarterEnd(startingMonth=12))
        self.assertEqual(frame['current_account_gdp_pct'].count(),57)
        self.assertEqual(frame['short_term_debt_reserves_pct'].count(),57)
        self.assertFalse(frame['short_term_debt_reserves_pct'].isna().any())
        self.assertTrue(all(r['debt_maturity']=='original maturity <=1 year' for r in rows if r['debt_source_url']))

    def test_recovered_quarters_are_published_ratios_with_status_and_provenance(self):
        stored={r['date']:r for r in ext.read_rows(ext.VULNERABILITY_PATH,'external')}
        for name,date,ratio,status,release in [
            ('dea_dec2016.pdf','2016-12-31',23.4,'QE','2017-03-31'),
            ('dea_dec2023.pdf','2023-12-31',20.3,'P','2024-03-28')]:
            observations=ext.parse_dea_pdf((FIX/name).read_bytes(),url(name),release)
            row=next(r for r in observations if r['date']==date)
            self.assertEqual(row['short_term_debt_reserves_pct'],ratio)
            self.assertEqual(row['debt_status'],status)
            self.assertEqual(row['debt_release_date'],release)
            self.assertEqual(float(stored[date]['short_term_debt_reserves_pct']),ratio)
            self.assertEqual(stored[date]['debt_status'],status)
            self.assertEqual(stored[date]['debt_source_url'],url(name))
        # DEA explicitly does not calculate GDP ratios for this broken year.
        self.assertEqual(stored['2016-12-31']['external_debt_gdp_pct'],'')

    def test_recovered_report_preserves_published_revisions_and_rejects_stale_vintage(self):
        name='dea_dec2023.pdf'
        new=ext.parse_dea_pdf((FIX/name).read_bytes(),url(name),'2024-03-28')
        old_name=next(n for n,m in SOURCES.items() if m['source_url'].endswith('September_2023_0.pdf'))
        old=ext.parse_dea_pdf((FIX/old_name).read_bytes(),url(old_name),'2023-12-29')
        merged=ext.merge_rows(old,new,'debt')
        september=next(r for r in merged if r['date']=='2023-09-30')
        self.assertEqual(september['short_term_debt_reserves_pct'],22.0)
        self.assertEqual(september['debt_status'],'PR')
        self.assertEqual(september['external_debt_gdp_pct'],18.8)
        self.assertEqual(ext.merge_rows(merged,old,'debt'),merged)

    def test_every_stored_ratio_and_vintage_reproduces_from_official_fixture(self):
        rows=ext.read_rows(ext.VULNERABILITY_PATH,'external')
        names={meta['source_url']:name for name,meta in SOURCES.items()}
        parsed={}
        for row in rows:
            for kind,field,prefix in [('cab','current_account_gdp_pct','cab'),('debt','short_term_debt_reserves_pct','debt')]:
                if not row[field]: continue
                source=row[prefix+'_source_url'];name=names[source]
                if (source,kind) not in parsed:
                    if name.endswith('.pdf'):
                        release=SOURCES[name]['release_date']
                        observations=ext.parse_dea_pdf((FIX/name).read_bytes(),source,release)
                    else:
                        observations=(ext.parse_bop if kind=='cab' else ext.parse_debt)(fixture(name),source)
                    parsed[source,kind]={r['date']:r for r in observations}
                observed=parsed[source,kind][row['date']]
                self.assertEqual(float(row[field]),observed[field],(row['date'],source))
                for suffix in ['release_date','status','unit']:
                    self.assertEqual(row[prefix+'_'+suffix],observed[prefix+'_'+suffix])

    def test_historical_stress_periods_and_published_revision(self):
        rows={r['date']:r for r in ext.read_rows(ext.VULNERABILITY_PATH,'external')}
        for date,cab,debt_ratio in [('2012-12-31',-6.5,31.1),('2013-06-30',-4.8,34.3),
                                    ('2013-09-30',-1.2,34.2),('2020-06-30',3.7,20.8),
                                    ('2022-09-30',-4.4,23.8)]:
            self.assertEqual(float(rows[date]['current_account_gdp_pct']),cab)
            self.assertEqual(float(rows[date]['short_term_debt_reserves_pct']),debt_ratio)
        original={r['date']:r for r in bop(28401)}
        revised={r['date']:r for r in bop(30738)}
        self.assertEqual(original['2012-12-31']['current_account_gdp_pct'],-6.7)
        self.assertEqual(revised['2012-12-31']['current_account_gdp_pct'],-6.5)
        self.assertEqual(revised['2012-12-31']['cab_status'],'partially revised')
        # Annual and half-year figures in the same release are excluded.
        self.assertEqual(set(revised),{'2012-12-31','2013-09-30','2013-12-31'})

    def test_archived_pdf_columns_quick_estimates_and_unruled_table(self):
        for ending,value in [('External_Debt_QDEC2012.pdf',31.1),('ExternalDebt_Dec15_E.pdf',23.3),
                             ('ExternalDebt_English_sep_12_0.pdf',28.7)]:
            name=next(n for n,m in SOURCES.items() if m['source_url'].endswith('/'+ending))
            rows=ext.parse_dea_pdf((FIX/name).read_bytes(),url(name),SOURCES[name]['release_date'])
            latest=rows[-1]
            self.assertEqual(latest['short_term_debt_reserves_pct'],value)
            self.assertEqual(latest['debt_status'],'QE')

    def test_historical_maturity_and_arithmetic_changes_fail_closed(self):
        raw=fixture('debt_29664.html')
        with self.assertRaises(ext.ExternalDataError):
            ext.parse_debt(re.sub(r'original\s+maturity','residual maturity',raw,flags=re.I),url('debt_29664.html'))
        with self.assertRaises(ext.ExternalDataError):
            ext.parse_bop(fixture('bop_30738.html').replace('31.9','35.9'),url('bop_30738.html'))

    def test_side_by_side_shared_history_independent_scales_and_one_masthead(self):
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgba
        from charts.style import EconStyle
        canonical_before=ext.VULNERABILITY_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as folder, patch('charts.india_charts.india_external.EconStyle.save_chart') as save:
            chart_vulnerability(folder)
            fig=save.call_args[0][0];left,right=fig.axes
            self.assertEqual(left.get_subplotspec().get_gridspec().get_geometry(),(1,2))
            self.assertTrue(left.get_shared_x_axes().joined(left,right))
            self.assertFalse(left.get_shared_y_axes().joined(left,right))
            self.assertNotEqual(left.get_ylim(),right.get_ylim())
            self.assertEqual(left.get_xlim(),right.get_xlim())
            self.assertEqual(len(left.lines[0].get_xdata()),57)
            self.assertEqual(pd.isna(right.lines[0].get_ydata()).sum(),0)
            self.assertEqual(right.lines[0].get_linestyle(),'-')
            bridges=right.lines[1:]
            self.assertEqual(len(bridges),0)
            for ax in [left,right]:
                self.assertEqual(ax.lines[0].get_color(),EconStyle.LINE_MAROON)
                self.assertEqual(tuple(ax.collections[-1].get_facecolor()[0]),to_rgba(EconStyle.LINE_MAROON))
                self.assertEqual(ax.texts[-1].get_color(),EconStyle.LINE_MAROON)
            self.assertEqual(left.lines[1].get_color(),EconStyle.TEXT_TITLE)
            self.assertAlmostEqual(left.get_position().y1,.75)
            self.assertAlmostEqual(left.get_position().y0,.18)
            self.assertEqual(left.get_position().y1,right.get_position().y1)
            self.assertTrue(any(list(line.get_ydata())==[0,0] for line in left.lines[1:]))
            self.assertEqual(sum(t.get_text()=='India’s External Vulnerability' for t in fig.texts),1)
            self.assertEqual(left.get_title(),'');self.assertEqual(right.get_title(),'')
            self.assertTrue(any(t.get_text()=='-0.5% P' for t in left.texts))
            self.assertTrue(any(t.get_text()=='23.0% P' for t in right.texts))
            fig.canvas.draw()
            renderer=fig.canvas.get_renderer()
            for ax in [left,right]:
                heading_box=ax.texts[0].get_window_extent(renderer)
                self.assertLess(heading_box.y1,.85*fig.bbox.height)
                for text in ax.texts:
                    box=text.get_window_extent(renderer)
                    self.assertGreaterEqual(box.x0,0)
                    self.assertLessEqual(box.x1,fig.bbox.width)
            plt.close(fig)
        self.assertEqual(ext.VULNERABILITY_PATH.read_bytes(),canonical_before)

    def test_visual_bridges_never_fill_values_or_bridge_longer_or_edge_gaps(self):
        import matplotlib.pyplot as plt
        from charts.style import EconStyle
        dates=pd.date_range('2020-03-31',periods=9,freq=pd.offsets.QuarterEnd())
        # Edge gaps, a single missing quarter, and two consecutive missing quarters.
        values=pd.Series([float('nan'),1,float('nan'),3,4,float('nan'),float('nan'),7,float('nan')],index=dates)
        before=values.copy(deep=True)
        fig,ax=plt.subplots()
        single_quarter_bridges(ax,values,EconStyle.LINE_MAROON)
        self.assertEqual(len(ax.lines),1)
        self.assertEqual(list(ax.lines[0].get_ydata()),[1,3])
        self.assertEqual(list(pd.DatetimeIndex(ax.lines[0].get_xdata())),list(dates[[1,3]]))
        pd.testing.assert_series_equal(values,before)
        # Sparse input cannot masquerade as a single missing quarter.
        irregular=pd.Series([1,float('nan'),4],index=dates[[0,1,3]])
        single_quarter_bridges(ax,irregular,EconStyle.LINE_MAROON)
        self.assertEqual(len(ax.lines),1)
        plt.close(fig)


class AtomicRefreshTests(unittest.TestCase):
    def test_all_failed_refreshes_preserve_exact_bytes(self):
        cases=[('collect_wss',ext.refresh_wss,wss(),ext.WSS_COLUMNS,'wss'),
               ('collect_reer',ext.refresh_reer,reer(),ext.REER_COLUMNS,'reer'),
               ('collect_vulnerability',ext.refresh_vulnerability,[dict.fromkeys(ext.EXT_COLUMNS,'') | bop(63493)[0]],ext.EXT_COLUMNS,'external')]
        for collector,refresh,rows,columns,kind in cases:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'data.csv';ext.atomic_write(path,rows,columns,kind);before=path.read_bytes()
                with patch.object(ext,collector,side_effect=ext.ExternalDataError('source failed')):
                    with self.assertRaises(ext.ExternalDataError):refresh(path=path)
                self.assertEqual(path.read_bytes(),before)

    def test_malformed_and_duplicate_write_leave_file_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data.csv';ext.atomic_write(path,reer(),ext.REER_COLUMNS,'reer');before=path.read_bytes()
            for rows in [reer()*2,[dict(reer()[0],base='2004-05=100')]]:
                with self.assertRaises(ext.ExternalDataError):ext.atomic_write(path,rows,ext.REER_COLUMNS,'reer')
                self.assertEqual(path.read_bytes(),before)

    def test_replace_failure_cleans_temp_and_preserves_old(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data.csv';ext.atomic_write(path,wss(),ext.WSS_COLUMNS,'wss');before=path.read_bytes()
            with patch.object(ext.os,'replace',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):ext.atomic_write(path,wss(),ext.WSS_COLUMNS,'wss')
            self.assertEqual(path.read_bytes(),before);self.assertEqual(list(Path(folder).glob('*.tmp')),[])

    def test_indicator_refresh_does_not_erase_other_or_newer_indicator(self):
        old=dict.fromkeys(ext.EXT_COLUMNS,'') | bop(63493)[-1] | debt()[-1]
        incoming=dict(old,current_account_gdp_pct='',cab_release_date='',short_term_debt_reserves_pct=22,debt_release_date='2026-10-01')
        merged=ext.merge_rows([old],[incoming],'debt')
        self.assertEqual(merged[0]['current_account_gdp_pct'],-.5);self.assertEqual(merged[0]['short_term_debt_reserves_pct'],22)

    def test_only_official_provenance_accepted(self):
        with self.assertRaises(ext.ExternalDataError):ext.validate_rows([dict(reer()[0],source_url='https://example.com/series')],'reer')
        with self.assertRaises(ext.ExternalDataError):ext.soup_for('<html>Please enable JavaScript to view the page content. captcha</html>')


class DashboardIntegrationTests(unittest.TestCase):
    def test_real_page_orders_external_charts_once_without_catch_all_duplicate(self):
        import ast
        from datetime import datetime
        from unittest.mock import MagicMock
        from charts.loader import chart_key
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'app.py').read_text())
        page=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='page_india')
        code=compile(ast.Module(body=[page],type_ignores=[]),'app.py','exec')
        names=['17_india_trade.png','30_india_reer.png','16_india_forex_reserves.png',
               '31_india_external_vulnerability.png','01_india_pmi.png','03_india_fpi_monthly.png']
        paths=[Path(n) for n in names];rendered=[];section=[None]
        def header(index,answer): section[0]=index;return str(index)
        namespace={'st':MagicMock(),'datetime':datetime,'get_charts':lambda _: (paths,'2026-10'),
                   '_page_header_html':MagicMock(),'_anchor':lambda _,title:title,
                   'chart_key':chart_key, '_EH_ANCHORS':list(range(7)),'_EH_STYLE':'','_load_soe':lambda _:None,
                   '_soe_changes_block':lambda _: '', '_pop_summary':lambda items,_:(None,items),
                   '_eh_india_answers':lambda *_:[None]*7,'_eh_india_observations':lambda:{},
                   '_eh_brief':lambda:{},'_eh_question_header':header,
                   '_render_iip_industry_heatmap':MagicMock(), '_section':MagicMock(),
                   '_render_cpi_items':MagicMock(),'_render_india_equity_matrix':MagicMock(),
                   '_render_grid':lambda items,**kwargs:rendered.append((section[0],items))}
        exec(code,namespace);namespace['page_india']()
        external=next(items for index,items in rendered if index==3)
        self.assertEqual([chart_key(p.name) for p in external],
                         ['india_external_vulnerability','india_forex_reserves','india_reer','india_trade'])
        flat=[p.name for _,items in rendered for p in items]
        self.assertEqual(sorted(flat),sorted(names));self.assertEqual(len(flat),len(set(flat)))

    def test_new_captions_and_economically_correct_insights(self):
        from charts.loader import clean_title
        from config.insights import get_insight
        self.assertEqual(clean_title('30_india_reer.png'),'India’s Real Effective Exchange Rate')
        self.assertEqual(clean_title('31_india_external_vulnerability.png'),'India’s External Vulnerability')
        self.assertIn('not an estimate of equilibrium',get_insight('30_india_reer.png'))
        self.assertIn('original maturity',get_insight('31_india_external_vulnerability.png'))
        self.assertNotIn('Reserves above',get_insight('16_india_forex_reserves.png'))


if __name__=='__main__':unittest.main()
