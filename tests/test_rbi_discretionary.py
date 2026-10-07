"""Full-history balance validation, native chart semantics and dynamic Insights."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from data import rbi_surveys as rbi
from charts import india_consumer_surveys as chart
from config.insights import get_insight

class DiscretionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = Path(__file__).parent / 'fixtures/rbi_surveys/consumer'
        cls.surveys = {g: rbi.load_consumer(p) for g, p in rbi.discover_consumer(directory).items()}
        cls.report = rbi.load_discretionary_comparison(surveys=cls.surveys)

    def test_full_common_published_balances_and_provenance(self):
        report = self.report
        self.assertEqual((report['common_dates'][0], report['latest_date'], len(report['common_dates'])),
                         ('2023-09-01', '2026-07-01', 18))
        for g, expected in [('Urban', (3.3, 18.3)), ('Rural', (32.41, 42.45))]:
            self.assertEqual(report['sources'][g]['sheet'], 'T8 Non-essential spending')
            for h, value in zip(('current', 'ahead'), expected):
                self.assertAlmostEqual(report['series'][g][-1][h+'_net'], value)
                for row in report['series'][g]:
                    self.assertAlmostEqual(row[h+'_net'], row[h+'_increase']-row[h+'_decrease'], delta=.151)

    def test_missing_historical_value_round_and_wrong_balance_rejected(self):
        for mutation in ('value', 'round', 'balance'):
            surveys = copy.deepcopy(self.surveys)
            rows = surveys['Rural']['tables']['nonessential']['records']
            if mutation == 'value': rows[1]['ahead_net'] = None
            elif mutation == 'round': rows.pop(1)
            else: rows[1]['current_net'] = rows[1]['current_increase']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                rbi.load_discretionary_comparison(surveys=surveys)

    def test_shared_scale_lines_gap_and_labels(self):
        with patch.object(chart.EconStyle, 'save_chart') as save:
            chart.render_discretionary(self.report, Path('/tmp/unused.png'))
        fig = save.call_args.args[0]
        from matplotlib import pyplot as plt
        self.addCleanup(plt.close, fig)
        self.assertEqual(tuple(fig.get_size_inches()), (9.2, 4.8))
        a, b = fig.axes
        self.assertEqual(a.get_ylim(), b.get_ylim())
        self.assertEqual(a.get_xlim(), b.get_xlim())
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for ax, g in zip(fig.axes, ('Urban', 'Rural')):
            lines = [line for line in ax.lines if len(line.get_xdata()) == 18]
            self.assertEqual([line.get_linestyle() for line in lines], ['-', '--'])
            self.assertEqual({line.get_color() for line in lines}, {chart.COLORS[g]})
            self.assertEqual(ax.collections[0].get_alpha(), .07)
            labels = [t for t in ax.texts if t.get_text().startswith(('Current', '1Y Ahead'))]
            self.assertEqual(len(labels), 2)
            self.assertFalse(labels[0].get_window_extent(renderer).overlaps(labels[1].get_window_extent(renderer)))
        self.assertFalse(fig.legends)
        self.assertTrue(any('Net response = % increased − % decreased.' in t.get_text() for t in fig.texts))
        endpoints = [t.get_window_extent(renderer) for t in a.texts]
        adjacent_ticks = [t.get_window_extent(renderer) for t in b.get_yticklabels()]
        self.assertFalse(any(label.overlaps(tick) for label in endpoints for tick in adjacent_ticks))

    def test_canonical_insight_updates_from_edition_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / (chart.NAMES[3]+'.png')
            path.with_suffix('.json').write_text(json.dumps(self.report))
            insight = get_insight(path)
            self.assertIn('Rural-led', insight)
            self.assertIn('Jul 2026', insight)
            self.assertIn('3.3 pp', insight)
            for url in rbi.CONSUMER_SOURCES.values(): self.assertIn(url, insight)
            report = copy.deepcopy(self.report)
            report['latest_date'] = '2026-09-01'
            report['series']['Urban'][-1]['current_net'] = 35.0
            path.with_suffix('.json').write_text(json.dumps(report))
            updated = get_insight(path)
            self.assertIn('Sep 2026', updated)
            self.assertIn('35.0 pp', updated)
            self.assertIn('Current sentiment was Urban-led', updated)

if __name__ == '__main__': unittest.main()
