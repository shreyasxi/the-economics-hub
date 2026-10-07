"""Focused checks against local RBI source and rejected non-comparable inputs."""
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch

import openpyxl
from data import rbi_surveys as survey
from charts import india_inflation_surveys as chart
from config.insights import get_insight


FIXTURE = Path(__file__).resolve().parent / 'fixtures/rbi_surveys/inflation.xlsx'

class CategoryTests(unittest.TestCase):
    def test_exact_latest_estimates_and_order(self):
        report = survey.read_categories(FIXTURE)
        self.assertEqual((report["survey_date"], report["round"]), ("2026-05-01", "83B"))
        expected = [("Services", 71.062552243527, 81.2663153856217, 42),
                    ("Housing", 78.3101068076663, 87.0035305287401, 35),
                    ("Household durables", 68.1991104310611, 74.9524794898119, 28),
                    ("Non-food", 81.0899864738161, 82.7229802251291, 21),
                    ("Food", 85.4364346742313, 85.9222930468186, 14)]
        for record, (category, a, b, row) in zip(report["categories"], expected):
            self.assertEqual(record["category"], category)
            self.assertEqual((record["three_month"], record["one_year"]), (a, b))
            self.assertTrue(record["three_month_cell"].endswith(f"!EI{row}"))
            self.assertAlmostEqual(record["change_pp"], b-a)

    def test_missing_bad_measure_se_and_mismatched_latest_rejected(self):
        path = FIXTURE
        for sheet, cell, value in [("T1A Product-wise 3M", "EI42", None),
                                   ("T1A Product-wise 3M", "B42", "Price increase more than current rate"),
                                   ("T1A Product-wise 3M", "EI6", "SE"),
                                   ("T1B Product-wise 1Y", "EI5", datetime(2026, 7, 1)),
                                   ("T1B Product-wise 1Y", "EI4", "84"),
                                   ("T1B Product-wise 1Y", "EI42", 120)]:
            with self.subTest(sheet=sheet, cell=cell, value=value):
                workbook = openpyxl.load_workbook(path, data_only=True)
                workbook[sheet][cell] = value
                with patch.object(survey.openpyxl, "load_workbook", return_value=workbook):
                    with self.assertRaises(ValueError):
                        survey.read_categories(path)

    def test_chart_single_axis_horizons_labels_and_order(self):
        report = survey.read_categories(FIXTURE)
        with patch.object(chart.EconStyle, "save_chart") as save:
            chart.render_categories(report, Path("unused.png"))
        fig = save.call_args.args[0]
        from matplotlib import pyplot as plt
        self.addCleanup(plt.close, fig)
        self.assertEqual(len(fig.axes), 1)
        ax = fig.axes[0]
        self.assertEqual(len(ax.lines), 5)
        self.assertEqual(len(ax.collections), 10)
        self.assertEqual([t.get_text() for t in ax.get_yticklabels()],
                         [r["category"].replace("Household durables", "Household\ndurables")
                          for r in report["categories"]])
        self.assertIn("What Households Think Will Get More Expensive", [t.get_text() for t in fig.texts])
        self.assertIn(chart.SUBTITLE, [t.get_text() for t in fig.texts])
        self.assertEqual(len([t for t in ax.texts if t.get_text().endswith("%")]), 10)
        self.assertFalse(fig.legends[0].get_frame_on())
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        labels = [t for t in ax.texts if t.get_text().endswith('%')]
        boxes = [t.get_window_extent(renderer) for t in labels]
        self.assertFalse(any(a.overlaps(b) for i, a in enumerate(boxes) for b in boxes[i+1:]))
        self.assertEqual(tuple(fig.get_size_inches()), (9.2, 4.8))
        self.assertEqual(fig.texts[0].get_position(), (.075, .948))
        self.assertEqual(fig.texts[1].get_position(), (.075, .893))

    def test_insights_four_sections(self):
        text = get_insight(chart.NAMES[1]+".png")
        self.assertEqual([line.split(":**")[0][2:] for line in text.splitlines() if line.startswith("**")],
                         ["How to read this chart", "Practical Takeaway", "Frequency", "Source"])
        self.assertIn(survey.INFLATION_SOURCE, text)
        self.assertIn("Bi-monthly", text)


if __name__ == "__main__":
    unittest.main()
