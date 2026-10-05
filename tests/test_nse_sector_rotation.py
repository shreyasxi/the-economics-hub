"""Benchmarked India rotation and unchanged weekly defaults, using official fixture."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import matplotlib.pyplot as plt
from data.fetchers import india_fetcher as f
from data.fetchers import nse_sector_rotation as r
from charts.templates.change_bars import render_change_bars, _format
from charts.loader import chart_key, group_charts
from generate_india import chart_sector_rotation_12m

FIXTURE = Path(__file__).parent/'fixtures/nse_rotation/allIndices_2026-10-01.json'


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text())

    def load(self, payload=None, include_snapshot=True):
        response = Mock()
        response.json.return_value = self.payload if payload is None else payload
        with patch('requests.Session') as session:
            session.return_value.get.return_value = response
            result = f.fetch_nifty_sector_changes(list(r.INDICES), include_snapshot=include_snapshot)
            self.assertEqual(session.return_value.get.call_args.args[0], f._NSE_ALL_INDICES_URL)
            return result

    def data(self, payload=None):
        return r.validate_snapshot(*self.load(payload))

    def test_benchmark_first_and_sectors_sorted_independently(self):
        rows, meta = self.data()
        self.assertEqual(len(rows),11)
        self.assertEqual(rows[0]['index'],'NIFTY 50')
        self.assertGreater(rows[1]['return_pct'],rows[0]['return_pct'])
        self.assertEqual([x['return_pct'] for x in rows[1:]],
                         sorted([x['return_pct'] for x in rows[1:]],reverse=True))
        self.assertEqual({x['observation_date'] for x in rows},{meta['observation_date']})
        self.assertEqual({x['year_ago_date'] for x in rows},{meta['year_ago_date']})

    def test_same_formula_as_weekly_not_reported_percentage_or_total_return(self):
        changes=self.load(include_snapshot=False)
        rows,_=self.data()
        for row in rows:
            self.assertEqual(row['return_pct'], changes[row['index']]['change_pct_1y'])
            self.assertEqual(row['return_pct'],round((row['last']/row['year_ago']-1)*100,2))
        self.assertEqual(rows[0]['return_pct'],-9.93)
        self.assertNotEqual(rows[0]['return_pct'],self.payload['data'][0]['perChange365d'])

    def test_date_mismatch_and_invalid_values_rejected(self):
        for key,value in [('previousDay','30-Sep-2026'),('date365dAgo','01-Oct-2025'),
                          ('last',float('nan')),('last',0),('oneYearAgoVal',-1)]:
            with self.subTest(key=key,value=value):
                p=copy.deepcopy(self.payload);p['data'][1][key]=value
                with self.assertRaises(ValueError): self.data(p)

    def test_intraday_snapshot_accepts_previous_trading_day_and_keeps_weekly_formula(self):
        p=copy.deepcopy(self.payload)
        p['timestamp']='05-Oct-2026 11:15'
        for row in p['data']:
            row['previousDay']='01-Oct-2026'
        changes,snapshot=self.load(p)
        rows,meta=r.validate_snapshot(changes,snapshot)
        self.assertEqual(meta['observation_date'],'2026-10-05')
        self.assertEqual(meta['previous_close_date'],'2026-10-01')
        self.assertEqual(meta['timestamp'],'05-Oct-2026 11:15')
        for row in rows:
            self.assertEqual(row['return_pct'],changes[row['index']]['change_pct_1y'])
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(r,'load_rotation_data',return_value=(rows,meta)):
                path=chart_sector_rotation_12m(Path(directory))
            self.assertTrue(path.exists())
            saved=json.loads(path.with_suffix('.json').read_text())
            self.assertEqual(saved['timestamp'],p['timestamp'])

    def test_future_previous_close_reference_is_rejected(self):
        p=copy.deepcopy(self.payload)
        for row in p['data']:
            row['previousDay']='02-Oct-2026'
        with self.assertRaisesRegex(ValueError,'Future NSE previous-close'):
            self.data(p)

    def test_missing_benchmark_or_sector_rejected(self):
        for name in ['NIFTY 50','NIFTY IT']:
            p=copy.deepcopy(self.payload);p['data']=[x for x in p['data'] if x['index']!=name]
            with self.assertRaises(ValueError): self.data(p)

    def test_failure_removes_prior_artifact_no_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);file=root/'23_india_sector_rotation_12m_benchmark.png'
            file.write_bytes(b'old');file.with_suffix('.json').write_text('{}')
            with patch.object(r,'fetch_nifty_sector_changes',side_effect=ValueError('Missing NIFTY 50')) as fetch:
                self.assertIsNone(chart_sector_rotation_12m(root))
            fetch.assert_called_once_with(list(r.INDICES),include_snapshot=True)
            self.assertFalse(file.exists());self.assertFalse(file.with_suffix('.json').exists())

    def test_renderer_pins_benchmark_and_formats_signs(self):
        fig=render_change_bars(['Low','NIFTY 50','High'],[-3,1,8], 'Title','Subtitle','NSE',benchmark='NIFTY 50')
        labels=[t.get_text() for t in fig.axes[0].texts]
        self.assertLess(labels.index('NIFTY 50'),labels.index('High'))
        self.assertLess(labels.index('High'),labels.index('Low'))
        self.assertIn('+8.0%',labels);self.assertIn('−3.0%',labels)
        self.assertEqual(_format(0),'0.0%');plt.close(fig)
        with self.assertRaises(ValueError):
            render_change_bars(['High'],[1],'T','S','NSE',benchmark='NIFTY 50')

    def test_weekly_default_still_sorts_every_row_without_benchmark_styling(self):
        fig=render_change_bars(['IT','NIFTY 50','Metal'],[-16,1,21],
                               'Weekly','Price returns','NSE')
        ax=fig.axes[0]
        names=[t for t in ax.texts if t.get_text() in ['IT','NIFTY 50','Metal']]
        self.assertEqual([t.get_text() for t in names],['Metal','NIFTY 50','IT'])
        self.assertEqual([t.get_position()[1] for t in names],[0,1,2])
        self.assertTrue(all(t.get_fontweight()=='normal' for t in names))
        plt.close(fig)

    def test_network_failure_propagates_without_other_source(self):
        with patch('requests.Session') as session:
            session.return_value.get.side_effect=ConnectionError('NSE unavailable')
            with self.assertRaises(ConnectionError): r.load_rotation_data()
            self.assertEqual(session.return_value.get.call_count,1)

    def test_india_explicit_layout_and_distinct_key(self):
        tree=ast.parse(Path('app.py').read_text())
        assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and
                        any(isinstance(t,ast.Name) and t.id=='equity_markets' for t in n.targets))
        def ordered_names(node):
            if isinstance(node,ast.Name):
                return [node.id]
            self.assertIsInstance(node,ast.BinOp)
            self.assertIsInstance(node.op,ast.Add)
            return ordered_names(node.left)+ordered_names(node.right)
        self.assertEqual(ordered_names(assignment.value),
                         ['fpi','risk_appetite','sector_valuations','sector_rotation'])
        grid=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and
                  isinstance(n.func,ast.Name) and n.func.id=='_render_grid' and
                  n.args and isinstance(n.args[0],ast.Name) and n.args[0].id=='equity_markets')
        self.assertEqual({k.arg:ast.literal_eval(k.value) for k in grid.keywords},{'cols':2})
        self.assertNotEqual(chart_key('23_india_sector_rotation_12m_benchmark.png'),
                            chart_key('10c_india_sector_rotation_12m.png'))

    def test_generator_and_workflow_integration(self):
        source=Path('generate_india.py').read_text()
        main=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='main')
        self.assertIn('chart_sector_rotation_12m(output_dir)',ast.unparse(main))
        workflow=Path('.github/workflows/india.yml').read_text()
        self.assertIn('0 8 * * 6',workflow)
        self.assertIn('23_india_sector_rotation_12m_benchmark.png',workflow)


if __name__=='__main__':
    unittest.main()
