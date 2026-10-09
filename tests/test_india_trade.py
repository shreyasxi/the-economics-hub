import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from data.fetchers.india_fetcher import fetch_trade_releases
from generate_india import chart_trade_balance


class TradeTests(unittest.TestCase):
    def test_august_supplement_and_provenance(self):
        row = fetch_trade_releases({})["2026-08"]
        self.assertEqual(row["india_exports_usd_bn"], 43.81)
        self.assertEqual(row["india_imports_usd_bn"], 70.67)
        self.assertEqual(row["india_trade_deficit_usd_bn"], 26.86)
        self.assertIn("2310636", row["_sources"]["india_exports_usd_bn"])

    def test_dbie_revision_takes_precedence(self):
        rows = {"2026-08": {"india_exports_usd_bn": 44,
                              "india_imports_usd_bn": 71}}
        self.assertEqual(fetch_trade_releases(rows), {})

    def test_footer_uses_latest_complete_trade_month(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-01", "2026-08-01", "2026-09-01"]),
            "india_exports_usd_bn": [44.2434, 43.81, None],
            "india_imports_usd_bn": [76.2232, 70.67, None],
        })
        with tempfile.TemporaryDirectory() as directory:
            with patch("generate_india.EconStyle.add_source") as footer:
                path = chart_trade_balance(df, Path(directory))
            self.assertTrue(path.exists())
            self.assertEqual(footer.call_args.kwargs["date_text"],
                             "Data through Aug 2026")


if __name__ == "__main__":
    unittest.main()
