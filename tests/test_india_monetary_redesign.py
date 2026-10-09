"""Verify economic alignment, gap visibility, retirement and summary integration."""
from __future__ import annotations
import ast
import math
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from charts.india_charts import india_monetary as monetary
from data.fetchers.rbi_money_market import RbiMoneyMarketError

ROOT = Path(__file__).resolve().parents[1]

class RedesignTests(unittest.TestCase):
    def sample(self):
        return pd.DataFrame({'date': pd.to_datetime(['2026-08-01','2026-08-02','2026-08-03']),
            'call_rate': [3.87,np.nan,6.9], 'repo_rate': [5.25,5.25,5.5],
            'call_volume_cr': [100.,0.,200.]})

    def test_same_day_spreads_only_actual_positive_volume_dates(self):
        source = self.sample()
        before = source.copy(deep=True)
        frame = monetary.wacr_spread_data(source)
        self.assertEqual(frame.index.tolist(), [pd.Timestamp('2026-08-01'),pd.Timestamp('2026-08-03')])
        np.testing.assert_allclose(frame.spread_bps, [-138,140])
        self.assertEqual(frame.index[0].day_name(), 'Saturday')
        pd.testing.assert_frame_equal(source,before)
        with self.assertRaises(RbiMoneyMarketError):
            monetary.wacr_spread_data(pd.concat([source,source]))

    def test_positive_volume_missing_wacr_fails_loudly(self):
        frame = self.sample()
        frame.loc[1,'call_volume_cr'] = 1
        with self.assertRaisesRegex(RbiMoneyMarketError,'Positive call volume but missing WACR.*2026-08-02'):
            monetary.wacr_spread_data(frame)
        for key, value in [('call_volume_cr',np.nan),('call_volume_cr',-1),('call_rate',float('inf')),('repo_rate',np.nan)]:
            frame = self.sample(); frame.loc[0,key] = value
            with self.assertRaises(RbiMoneyMarketError):
                monetary.wacr_spread_data(frame)
        frame = self.sample(); frame.loc[0,'call_volume_cr'] = 0
        with self.assertRaises(RbiMoneyMarketError):
            monetary.wacr_spread_data(frame)

    def test_single_series_connects_valid_dates_without_synthetic_values(self):
        with patch.object(monetary.EconStyle,'save_chart',side_effect=lambda fig,path: fig):
            fig = monetary.wacr_spread(self.sample(), '/private/tmp')
        try:
            self.assertEqual(len(fig.axes), 1)
            ax = fig.axes[0]
            self.assertIsNone(ax.get_legend())
            main = ax.lines[1] # zero reference precedes the actual single series
            self.assertEqual(main.get_marker(), 'None')
            np.testing.assert_allclose(main.get_ydata(), [-138,140])
            self.assertEqual(list(main.get_xdata()), list(monetary.wacr_spread_data(self.sample()).index))
            self.assertEqual(ax.get_ylabel(), '')
            formatter = ax.yaxis.get_major_formatter()
            self.assertEqual([formatter(x) for x in (-60,-40,-20,0,20,40)],
                             ['−60 bps','−40 bps','−20 bps','0 bps','+20 bps','+40 bps'])
            self.assertTrue(all(not line.get_visible() for line in ax.get_xgridlines()))
            texts = ' '.join(t.get_text() for t in ax.texts)
            self.assertIn('Latest: +140 bps',texts)
            self.assertIn('03 Aug 2026',texts)
            for forbidden in ('SDF','MSF','TREPS','Market repo'):
                self.assertNotIn(forbidden,texts)
        finally:
            plt.close(fig)

    def test_full_range_padded_with_interior_ticks_and_no_boundary_markers(self):
        source = pd.DataFrame({'date':pd.date_range('2026-01-01',periods=100),
                               'repo_rate':5.25,'call_rate':5.15,'call_volume_cr':100.})
        source.loc[3,'call_rate'] = 3.87
        source.loc[20,'call_rate'] = 6.9
        actual = monetary.wacr_spread_data(source)
        lo, hi = monetary.spread_display_limits(actual.spread_bps)
        self.assertLess(lo,actual.spread_bps.min())
        self.assertGreater(hi,actual.spread_bps.max())
        with patch.object(monetary.EconStyle,'save_chart',side_effect=lambda fig,path:fig):
            fig = monetary.wacr_spread(source,'/private/tmp')
        try:
            ax = fig.axes[0]
            np.testing.assert_allclose(ax.lines[1].get_ydata(),actual.spread_bps)
            self.assertEqual(ax.get_ylim(),(lo,hi))
            self.assertTrue(all(lo < tick < hi for tick in ax.get_yticks()))
            self.assertGreater(hi-max(ax.get_yticks()),0)
            texts = ' '.join(t.get_text() for t in ax.texts)
            self.assertNotIn('−138 bps',texts); self.assertNotIn('+165 bps',texts)
            self.assertNotIn('Shaded band', ' '.join(t.get_text() for t in fig.texts))
            self.assertEqual(sum(t.get_text().startswith('Latest:') for t in ax.texts),1)
            from matplotlib.collections import PathCollection, PolyCollection
            self.assertEqual(sum(isinstance(c,PathCollection) for c in ax.collections),1) # latest dot only
            self.assertEqual(sum(isinstance(c,PolyCollection) for c in ax.collections),2) # signed fills
            band = ax.patches[0]
            self.assertEqual((band.get_y(),band.get_height()),(-10,20))
        finally:
            plt.close(fig)

    def test_full_range_padding_for_constant_and_new_extreme_series(self):
        for values in ([0,0],[-200,-200],[-500,900],[20,30]):
            series = pd.Series(values)
            lo,hi = monetary.spread_display_limits(series)
            self.assertGreaterEqual(series.min()-lo,10)
            self.assertGreaterEqual(hi-series.max(),10)

    def test_titles_use_unmodified_house_style(self):
        source = self.sample().assign(net_liquidity_injection_cr=-100000.)
        for chart, title in ((monetary.wacr_spread, 'Overnight Funding vs. the RBI Policy Rate'),
                             (monetary.liquidity, 'India’s Banking System Liquidity')):
            with patch.object(monetary.EconStyle, 'set_title', wraps=monetary.EconStyle.set_title) as styled, \
                 patch.object(monetary.EconStyle, 'save_chart', side_effect=lambda fig,path:fig):
                fig = chart(source, '/private/tmp')
            try:
                ax = fig.axes[0]
                styled.assert_called_once()
                self.assertEqual(styled.call_args.args[1], title)
                self.assertEqual(ax.get_title(loc='left'), title)
                self.assertEqual(ax._left_title.get_fontsize(), monetary.EconStyle.FONT_SIZE_TITLE)
                self.assertEqual(ax._left_title.get_fontweight(), 'bold')
                self.assertEqual(ax.titleOffsetTrans._t[1], 20/72)
            finally:
                plt.close(fig)

    def test_liquidity_display_sign_average_latest_and_canonical_unchanged(self):
        source = pd.DataFrame({'date':pd.date_range('2026-08-01',periods=45),
                               'net_liquidity_injection_cr':np.linspace(100000,-423480.82,45)})
        before = source.copy(deep=True)
        display = monetary.banking_system_liquidity(source)
        np.testing.assert_array_equal(display, source.net_liquidity_injection_cr)
        self.assertGreater(display.iloc[0],0) # RBI injection meets a deficit
        self.assertLess(display.iloc[-1],0) # absorption indicates surplus
        with patch.object(monetary.EconStyle,'save_chart',side_effect=lambda fig,path:fig):
            fig = monetary.liquidity(source, '/private/tmp')
        try:
            ax = fig.axes[0]
            np.testing.assert_allclose([bar.get_height() for bar in ax.patches], display/100000)
            expected = monetary.liquidity_average(source)
            np.testing.assert_allclose(ax.lines[0].get_ydata(), expected, equal_nan=True)
            texts = ' '.join(t.get_text() for t in ax.texts)
            self.assertIn('Latest surplus: ₹4.23 lakh cr',texts)
            self.assertIn(f'20D: {expected.dropna().iloc[-1]:+.2f}'.replace('-', '−'),texts)
            self.assertIn('RBI adds cash when banks face a shortage (+), absorbs excess cash (−)', texts)
            from matplotlib.colors import to_rgba
            self.assertEqual(ax.patches[0].get_facecolor(),to_rgba(monetary.EconStyle.LINE_MAROON,.65))
            self.assertEqual(ax.patches[-1].get_facecolor(),to_rgba(monetary.EconStyle.LINE_TEAL,.65))
        finally:
            plt.close(fig)
        pd.testing.assert_frame_equal(source,before)

    def test_liquidity_positive_injection_labels_system_deficit(self):
        source = pd.DataFrame({'date':pd.date_range('2026-08-01',periods=2),
                               'net_liquidity_injection_cr':[-100000.,200000.]})
        with patch.object(monetary.EconStyle,'save_chart',side_effect=lambda fig,path:fig):
            fig = monetary.liquidity(source, '/private/tmp')
        try:
            self.assertIn('Latest deficit: ₹2.00 lakh cr',
                          ' '.join(t.get_text() for t in fig.axes[0].texts))
            self.assertEqual(fig.axes[0].patches[-1].get_height(),2.)
        finally:
            plt.close(fig)

    def test_canonical_arithmetic_counts_latest_and_outliers_retained(self):
        from data.fetchers.rbi_money_market import read_rows
        path = ROOT/'data/stores/india/rbi_money_market.csv'
        before = path.read_bytes()
        source = pd.DataFrame(read_rows(path))
        source.date = pd.to_datetime(source.date)
        valid = monetary.wacr_spread_data(source)
        np.testing.assert_allclose(valid.spread_bps,(valid.call_rate-valid.repo_rate)*100,rtol=0,atol=1e-10)
        missing = source.call_rate.isna()
        self.assertEqual(int((missing & (source.call_volume_cr==0)).sum()),int(missing.sum()))
        self.assertEqual(int((missing & (source.call_volume_cr>0)).sum()),0)
        self.assertTrue((source.loc[missing,'call_volume_cr']==0).all())
        self.assertFalse(source.date.duplicated().any())
        latest_source = source.loc[~missing].iloc[-1]
        self.assertAlmostEqual(valid.iloc[-1].spread_bps,
                               (latest_source.call_rate-latest_source.repo_rate)*100)
        self.assertEqual(valid.index[-1],latest_source.date)
        lo,hi = monetary.spread_display_limits(valid.spread_bps)
        self.assertTrue(valid.spread_bps.between(lo,hi,inclusive='neither').all())
        audited = source.set_index('date').loc[pd.to_datetime(
            ['2026-02-07','2026-03-30','2026-04-18','2026-09-04','2026-09-05'])]
        np.testing.assert_allclose((audited.call_rate-audited.repo_rate)*100,[-70,165,-75,-85,-138])
        self.assertEqual(path.read_bytes(),before)

    def test_invalid_repo_before_display_window_is_rejected(self):
        source = self.sample()
        source.loc[0,'date'] = pd.Timestamp('2024-01-01')
        source.loc[0,'repo_rate'] = np.nan
        with self.assertRaises(RbiMoneyMarketError):
            monetary.wacr_spread_data(source)

    def test_dynamic_metric_same_definition_and_unavailable_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'sentinel.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE mpc_meetings(policy_cycle TEXT,repo_rate_pct REAL)')
                db.executemany('INSERT INTO mpc_meetings VALUES (?,?)', [('2026-08-05',5.25),('2026-10-07',5.5)])
            macro = pd.DataFrame({'date': pd.to_datetime(['2026-07-01','2026-08-01']), 'india_cpi_yoy':[4.5,4.82]})
            status = {'status':'ready','changes':[{'month':m,'column':'india_cpi_yoy','concept':'General','value':v}
                       for m,v in [('2026-07',4.5),('2026-08',4.82)]]}
            metric = monetary.latest_real_policy_metric(macro,sentinel=path,cpi_status=status)
            self.assertEqual(metric['display'], '+0.43 pp')
            self.assertEqual(metric['period'], '2026-08 · ex-post')
            macro.loc[1,'india_cpi_yoy'] = 4.7
            status['changes'][1]['value'] = 4.7
            self.assertEqual(monetary.latest_real_policy_metric(macro,sentinel=path,cpi_status=status)['display'], '+0.55 pp')
            for invalid in ({'status':'unavailable'}, {'status':'ready','changes':[]}):
                with self.assertRaises(RbiMoneyMarketError):
                    monetary.latest_real_policy_metric(macro,sentinel=path,cpi_status=invalid)
            macro['india_cpi_yoy'] = np.nan
            with self.assertRaises(RbiMoneyMarketError):
                monetary.latest_real_policy_metric(macro,sentinel=path,cpi_status=status)

    def test_generation_retires_old_png_without_generating_real_chart(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder)/monetary.REAL
            old.write_bytes(b'stale')
            rows = self.sample().assign(date=lambda f: f.date.dt.strftime('%Y-%m-%d')).to_dict('records')
            with patch.object(monetary,'read_rows',return_value=rows), \
                 patch.object(monetary,'wacr_spread',return_value='spread') as c, \
                 patch.object(monetary,'liquidity',return_value='liquidity') as l:
                self.assertEqual(monetary.generate(pd.DataFrame(),folder), ['spread','liquidity'])
            c.assert_called_once(); l.assert_called_once()
            self.assertFalse(old.exists())

    def test_banner_metric_order_and_missing_behavior(self):
        names = {'_eh_number','_eh_pair','_eh_metric','_eh_result','_eh_direction','_eh_india_answers'}
        tree = ast.parse((ROOT/'app.py').read_text())
        namespace = {'math': math, 'date':date}
        # Execute production helpers without launching Streamlit or importing its UI.
        module = ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)] +
                            [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'app.py','exec'),namespace)
        observations = {'monthly':[],'weekly':[],'iip':[],'transmission':[],'fiscal':[],
                        'real_policy':{'label':'Real policy rate','value':.43,'display':'+0.43 pp','period':'2026-08 · ex-post'}}
        brief = {'repo_rate_pct':5.5,'policy_cycle':'2026-10-07','rate_action':'hike'}
        result = namespace['_eh_india_answers'](observations,brief)[2]
        self.assertEqual([m['label'] for m in result['metrics']], ['Repo rate','Real policy rate'])
        self.assertEqual(result['metrics'][1]['display'], '+0.43 pp')
        for missing in (None, {'value':float('nan')}):
            observations['real_policy'] = missing
            result = namespace['_eh_india_answers'](observations,brief)[2]
            self.assertEqual([m['label'] for m in result['metrics']], ['Repo rate'])

if __name__ == '__main__':
    unittest.main()
