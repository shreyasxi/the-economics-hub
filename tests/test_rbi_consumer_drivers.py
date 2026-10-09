import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime
from data.processors import rbi_surveys as rbi
from charts.india_charts import india_consumer_surveys as d
from config.insights import get_insight
import matplotlib.pyplot as plt

class DriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.latest,cls.previous,cls.rows,cls.sources=rbi.read_components(rbi.discover_consumer(Path(__file__).resolve().parent/'fixtures/rbi_surveys/consumer'))

    def test_latest_values_and_provenance(self):
        self.assertEqual(self.latest,'2026-07-01');self.assertEqual(len(self.rows),20)
        self.assertEqual(self.previous,'2026-05-01')
        expected={'Urban':[-23.4,-21.9,-92.7,1.9,77.3,11.1,15.1,-74.9,45.8,79.7],
                  'Rural':[-11.87,-7.97,-90.5,-8.65,77.35,15.69,22.62,-79.12,32.07,76.89]}
        for g in d.COLORS:
            actual=[next(r['plotted_value'] for r in self.rows if r['geography']==g and r['horizon']==h and r['component']==n)
                    for h in ('current','ahead') for n,_ in d.COMPONENTS]
            for a,e in zip(actual,expected[g]):self.assertAlmostEqual(a,e)
        for r in self.rows:
            self.assertEqual(r['raw_balance'],r['plotted_value'])
            self.assertEqual(r['supplied_or_calculated'],'RBI supplied')
            self.assertFalse(r['sign_reversal'])
            self.assertIn(r['raw_cell'][0],('F','J'))
            self.assertLessEqual(abs(r['rounding_residual']),.151)
            self.assertAlmostEqual(r['delta'],r['plotted_value']-r['previous_value'])
            self.assertLessEqual(abs(r['previous_rounding_residual']),.151)
            self.assertFalse(r['previous_sign_reversal'])

    def test_price_orientation_and_index_reconciliation(self):
        for r in self.rows:
            if r['component']=='Prices':
                self.assertLess(r['plotted_value'],0)
                self.assertAlmostEqual(r['raw_balance'],r['decrease_or_worsen']-r['increase_or_improve'],delta=.151)
        headline={'Urban':(88.3,115.3),'Rural':(91.672,113.63)}
        for g in d.COLORS:
            for h,index in zip(('current','ahead'),headline[g]):
                self.assertAlmostEqual(100+sum(r['plotted_value'] for r in self.rows if r['geography']==g and r['horizon']==h)/5,index,delta=.151)

    def test_component_tables_preserve_values_and_comparisons(self):
        for geography in d.COLORS:
            with self.subTest(geography=geography), patch.object(d.EconStyle, 'save_chart') as save:
                d.render_components(self.rows, datetime.fromisoformat(self.latest),
                                    datetime.fromisoformat(self.previous), geography, Path('/tmp/unused.png'))
            fig = save.call_args.args[0]
            self.addCleanup(plt.close, fig)
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            self.assertEqual(len(fig.axes), 1)
            ax = fig.axes[0]
            self.assertFalse(ax.axison)
            self.assertEqual(len(ax.collections), 0)  # No dots.
            self.assertEqual(len(ax.patches), 2)  # Only horizon background bands.
            self.assertEqual([t.get_text() for t in ax.texts if t.get_position()[0] == 0],
                             [name for name, _ in d.COMPONENTS])
            for horizon, centers in [('current', (.265, .385, .515)),
                                     ('ahead', (.645, .765, .895))]:
                for y, (name, _) in zip((.72, .58, .44, .30, .16), d.COMPONENTS):
                    row = next(r for r in self.rows if r['geography'] == geography
                               and r['horizon'] == horizon and r['component'] == name)
                    for x, key in zip(centers, ('previous_value', 'plotted_value', 'delta')):
                        label = next(t for t in ax.texts if t.get_position() == (x, y))
                        self.assertEqual(label.get_text(), d.signed(row[key]))
                        if key == 'plotted_value':
                            self.assertEqual(label.get_weight(), 'bold')
                        if key == 'delta':
                            self.assertEqual(label.get_color(), d.change_cue(row[key]))
            boxes = [t.get_window_extent(renderer) for t in ax.texts]
            self.assertFalse(any(a.overlaps(b) for i, a in enumerate(boxes) for b in boxes[i+1:]))
            self.assertFalse(fig.legends)

    def test_table_dates_follow_new_round_including_year_boundary(self):
        with patch.object(d.EconStyle, 'save_chart') as save:
            d.render_components(self.rows, datetime(2027, 1, 1), datetime(2026, 11, 1),
                                'Urban', Path('/tmp/unused.png'))
        fig = save.call_args.args[0]
        self.addCleanup(plt.close, fig)
        text = [t.get_text() for t in fig.axes[0].texts]
        self.assertEqual(text.count('Nov 2026'), 2)
        self.assertEqual(text.count('Jan 2027'), 2)
        self.assertNotIn('May 2026', text)
        self.assertNotIn('Jul 2026', text)

    def test_insights_sections(self):
        text=get_insight(d.NAMES[1]+'.png')
        self.assertEqual([t.split(':**')[0][2:] for t in text.splitlines() if t.startswith('**')],
                         ['How to read this chart','Practical Takeaway','Frequency','Source'])
        self.assertIn('neither round is sign-reversed',text)
        self.assertIn('price',text.lower())

    def test_change_cues_depend_on_delta_not_level(self):
        self.assertEqual(d.change_cue(.02),d.EconStyle.INK_MUTED)
        self.assertEqual(d.change_cue(1),d.EconStyle.LINE_TEAL)
        self.assertEqual(d.change_cue(-1),d.EconStyle.LINE_MAROON)
        urban_income=next(r for r in self.rows if r['geography']=='Urban' and r['horizon']=='current' and r['component']=='Income')
        self.assertAlmostEqual(urban_income['previous_value'],.94)
        self.assertAlmostEqual(urban_income['delta'],.96)
        price=next(r for r in self.rows if r['geography']=='Rural' and r['horizon']=='ahead' and r['component']=='Prices')
        self.assertAlmostEqual(price['previous_value'],-76.6)
        self.assertAlmostEqual(price['delta'],-2.52)

if __name__=='__main__':unittest.main()
