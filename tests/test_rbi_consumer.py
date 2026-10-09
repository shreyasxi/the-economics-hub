"""Focused parser, provenance and chart-semantic tests; sources are read-only."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
import openpyxl
import matplotlib.pyplot as plt

from data.processors import rbi_surveys as c
from charts.india_charts import india_consumer_surveys as chart
from config.insights import get_insight

class ConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.surveys = {g: c.load_consumer(path) for g,path in c.discover_consumer(Path(__file__).resolve().parent/'fixtures/rbi_surveys/consumer').items()}

    def test_latest_and_common_dates(self):
        dates, series, spending, check = c.compare(self.surveys)
        self.assertEqual((dates[0], dates[-1], len(dates)), ('2023-09-01','2026-07-01',18))
        self.assertEqual([series[g][-1][k] for g in ('Urban','Rural') for k in ('csi','fei')],
                         [88.3,115.3,91.672,113.63])
        self.assertEqual([round(row[g],2) for row in spending for g in ('Urban','Rural')],
                         [86.7,81.64,3.3,32.41,85.8,81.13,18.3,42.45])
        self.assertEqual(len(check),8)
        self.assertTrue(all(abs(r['rounding_residual']) < .151 for r in check))

    def test_discover_offset_and_reordered_columns(self):
        w = openpyxl.Workbook(); s = w.active
        for cell,value in {'E9':'Survey Round','G9':'FEI*','J9':'CSI*',
                           'E10':datetime(2026,7,1),'G10':115.3,'J10':88.3}.items():
            s[cell] = value
        rows,cols = c.read_table(s,True)
        self.assertEqual(cols,{'csi':'J','fei':'G'})
        self.assertEqual(rows[0]['csi'],88.3)

    def test_duplicate_or_bad_date_rejected(self):
        for bad in [datetime(2026,7,1),'July 2026',None]:
            w=openpyxl.Workbook(); s=w.active
            s.append(['Survey Round','CSI*','FEI*'])
            s.append([datetime(2026,7,1),88.3,115.3]); s.append([bad,90,120])
            with self.assertRaises(ValueError): c.read_table(s,True)

    def test_missing_history_preserved(self):
        surveys=copy.deepcopy(self.surveys)
        surveys['Rural']['tables']['indices']['records'][1]['csi']=None
        _,series,_,_=c.compare(surveys)
        self.assertIsNone(series['Rural'][1]['csi'])

    def test_missing_latest_and_mismatched_round_rejected(self):
        surveys=copy.deepcopy(self.surveys)
        surveys['Rural']['tables']['indices']['records'][-1]['csi']=None
        with self.assertRaises(ValueError): c.compare(surveys)
        surveys=copy.deepcopy(self.surveys)
        surveys['Urban']['tables']['essential']['records'].pop()
        with self.assertRaises(ValueError): c.compare(surveys)

    def test_share_balance_confusion_rejected(self):
        surveys=copy.deepcopy(self.surveys)
        surveys['Urban']['tables']['nonessential']['records'][-1]['current_net']=32.6
        with self.assertRaises(ValueError): c.compare(surveys)

    def test_coverage_and_published_tables(self):
        self.assertEqual(c.coverage_break(self.surveys['Rural']),datetime(2024,7,1))
        self.assertIsNone(c.coverage_break(self.surveys['Urban']))
        self.assertEqual(self.surveys['Rural']['tables']['indices']['sheet'],'T9 Indices')
        self.assertTrue(any(s['sheet']=='Sheet5' and s['state']=='hidden'
                            for s in self.surveys['Rural']['inventory']))

    def test_chart_semantics(self):
        dates,series,spending,_=c.compare(self.surveys)
        captured=[]
        with patch.object(chart.EconStyle,'save_chart',side_effect=lambda fig,path: captured.append(fig)):
            chart.render_confidence(series,dates,c.coverage_break(self.surveys['Rural']),Path('/tmp/unused.png'))
        fig=captured[0]
        self.assertEqual(len(fig.axes),2)
        self.assertEqual(fig.axes[0].get_ylim(),(85,105))
        self.assertEqual(fig.axes[1].get_ylim(),(95,135))
        self.assertEqual(fig.axes[0].get_xlim(),fig.axes[1].get_xlim())
        self.assertAlmostEqual(fig.axes[0].get_position().y0,fig.axes[1].get_position().y0)
        self.assertLess(fig.axes[0].get_position().x1,fig.axes[1].get_position().x0)
        self.assertFalse(any('Common sample' in t.get_text() or 'above 100:' in t.get_text()
                             for t in fig.texts))
        for ax in fig.axes:
            self.assertTrue(any(list(line.get_ydata())==[100,100] for line in ax.lines))
            self.assertTrue(any('Urban' in t.get_text() for t in ax.texts))
            self.assertTrue(any('Rural' in t.get_text() for t in ax.texts))
            self.assertFalse(any('coverage expanded' in t.get_text() for t in ax.texts))
            self.assertFalse(any(len(line.get_xdata())==2 and
                                 list(line.get_xdata())==[datetime(2024,7,1)]*2 for line in ax.lines))
        for f in captured: plt.close(f)

    def test_insights_exact_sections(self):
        dates,series,spending,_=c.compare(self.surveys)
        text=get_insight(chart.NAMES[0]+'.png')
        self.assertEqual([line.split(':**')[0][2:] for line in text.splitlines() if line.startswith('**')],
                         ['How to read this chart','Practical Takeaway','Frequency','Source'])


if __name__=='__main__': unittest.main()
