"""Official FPI source contracts, atomic adoption, rollover and presentation."""
import gzip
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from data.fetchers import nsdl_fpi as fpi
from data.processors import india_db_manager as dbm

FIXTURES = Path(__file__).parent / "fixtures" / "nsdl_fpi"
TODAY = date(2026, 10, 28)


def fixture(name):
    return gzip.decompress((FIXTURES / (name + ".html.gz")).read_bytes())


class Client:
    def year(self, year):
        return fixture("year_2026" if year == 2026 else "year_2025")

    def daily(self):
        return fixture("daily_2026_10_27")


class ParserTests(unittest.TestCase):
    def test_real_monthly_totals_allow_source_rounding(self):
        values, partial = fpi.parse_year(fixture("year_2026"), 2026, TODAY)
        self.assertEqual(values["2026-09"], Decimal("-58443"))
        self.assertEqual(values["2026-08"], Decimal("25492"))
        self.assertNotIn("2026-10", values)
        self.assertEqual(partial["asof"], "2026-10-27")

    def test_daily_routes_subtotals_and_totals_counted_once(self):
        mtd = fpi.parse_daily(fixture("daily_2026_10_27"), TODAY)
        self.assertEqual(mtd, {"month": "2026-10", "asof": "2026-10-27", "value": Decimal("-36397.78")})

    def test_stale_default_wrong_year_units_and_future_rejected(self):
        with self.assertRaises(fpi.SourceError):
            fpi.parse_year(fixture("year_2026"), 2025, TODAY)
        for html in [fixture("year_2026").replace(b"INR Crores", b"USD Million"), fixture("pilot_year")]:
            with self.assertRaises(fpi.SourceError):
                fpi.parse_year(html, 2026, TODAY)
        for html, today in [(fixture("pilot_daily"), TODAY), (fixture("daily_2026_10_27"), date(2026,10,26)),
                            (fixture("daily_2026_10_27"), date(2026,11,7))]:
            with self.assertRaises(fpi.SourceError):
                fpi.parse_daily(html, today)
        self.assertIsNone(fpi.parse_daily(fixture("daily_2026_10_27"), date(2026,11,3)))

    def test_money_missing_is_not_zero(self):
        self.assertEqual(fpi.money("(1,234.56)"), Decimal("-1234.56"))
        for value in ["", "-", "NaN", "Infinity", "1 23", "N/A"]:
            with self.assertRaises(fpi.SourceError):
                fpi.money(value)

    def test_duplicate_missing_and_changed_daily_values_rejected(self):
        raw = fixture("daily_2026_10_27")
        for mutation in [raw.replace(b"17667.90", b"17668.90", 1), raw.replace(b"17667.90", b"-", 1),
                         raw.replace(b"Primary market & others", b"Unexpected route", 1)]:
            with self.assertRaises(fpi.SourceError):
                fpi.parse_daily(mutation, TODAY)
        soup = BeautifulSoup(raw, "html.parser")
        table = fpi._table(str(soup), "Daily Trends in FPI Investments on")
        rows = table.find_all("tr")
        # Removing a total must not silently produce an incomplete MTD.
        total_row = next(r for r in rows if any(c.get_text(strip=True) == "Total" for c in r.find_all("td", recursive=False)))
        total_row.decompose()
        with self.assertRaises(fpi.SourceError):
            fpi.parse_daily(str(table), TODAY)

    def test_recent_months_and_independent_reports_reconcile(self):
        data, sources = fpi.collect(Client(), TODAY)
        self.assertEqual(set(data["completed"]), {"2026-07", "2026-08", "2026-09"})
        self.assertEqual(len(sources), 2)
        class Disagree(Client):
            def year(self, year):
                # Keep monthly reconciliation valid while changing its total.
                return super().year(year).replace(b"-46748", b"-46738").replace(b"-36398", b"-36388")
        with self.assertRaises(fpi.SourceError):
            fpi.collect(Disagree(), TODAY)

    def test_year_selection_posts_the_official_form_state(self):
        client = object.__new__(fpi.OfficialClient)
        with patch.object(client, "request", side_effect=[fixture("year_2026"), fixture("year_2025")]) as request:
            raw = client.year(2025)
        self.assertEqual(request.call_args.args[:2], ("POST", fpi.YEAR_URL))
        self.assertEqual(request.call_args.kwargs["data"]["ddl"], "2025")
        self.assertTrue(request.call_args.kwargs["data"]["__VIEWSTATE"])
        self.assertEqual(fpi.parse_year(raw, 2025, date(2026,1,7))[0]["2025-12"], Decimal("-38568"))

    def test_january_fetches_prior_year_and_no_fake_mtd(self):
        class January(Client):
            def year(self, year):
                if year == 2025:
                    return super().year(year)
                return '<table><tr><td>Monthly FPI Net Investments (Calendar Year - 2026)</td></tr><tr><td>INR Crores</td></tr></table>'
            def daily(self):
                return fixture("daily_2026_10_27").replace(b"27-Oct-2026", b"31-Dec-2025")
        data, sources = fpi.collect(January(), date(2026,1,3))
        self.assertEqual(set(data["completed"]), {"2025-10", "2025-11", "2025-12"})
        self.assertIsNone(data["mtd"])
        self.assertEqual(len(sources), 3)


class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "india.db"
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.executescript(dbm._SCHEMA)
            conn.execute("INSERT INTO india_monthly(month,india_mfg_pmi,india_fpi_net_inr_cr,source_flags) VALUES(?,?,?,?)",
                         ("2026-09", 57.7, -58000, json.dumps({"india_mfg_pmi": "manual:pmi", "india_fpi_net_inr_cr": "manual:nsdl:2026-10-03"})))

    def rows(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.row_factory = sqlite3.Row
            return {r["month"]: dict(r) for r in conn.execute("SELECT * FROM india_monthly")}

    def update(self, client=None):
        return fpi.update(db=self.db, root=self.root / "sources", today=TODAY, client=client or Client())

    def test_adoption_preserves_other_data_and_audits_manual_replacements(self):
        self.update()
        row = self.rows()["2026-09"]
        self.assertEqual(row["india_mfg_pmi"], 57.7)
        self.assertEqual(row["india_fpi_net_inr_cr"], -58443)
        self.assertEqual(json.loads(row["source_flags"])["india_mfg_pmi"], "manual:pmi")
        self.assertEqual(self.rows()["2026-10"]["india_fpi_mtd_inr_cr"], -36397.78)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            old = json.loads(conn.execute("SELECT previous_json FROM india_fpi_audit WHERE month='2026-09'").fetchone()[0])
            self.assertEqual(old["india_fpi_net_inr_cr"], -58000)
            count = conn.execute("SELECT COUNT(*) FROM india_fpi_audit").fetchone()[0]
        self.update()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM india_fpi_audit").fetchone()[0], count)
        pointer = json.loads((self.root / "sources/current.json").read_text())
        import hashlib
        for source in pointer["sources"]:
            raw = (self.root / "sources/sources" / (source["sha256"] + ".html")).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])

    def test_validation_failure_changes_neither_db_nor_success_pointer(self):
        self.update()
        before = self.rows()
        pointer = (self.root / "sources/current.json").read_bytes()
        class Broken(Client):
            def daily(self):
                return fixture("pilot_daily")
        with self.assertRaises(fpi.SourceError):
            self.update(Broken())
        self.assertEqual(self.rows(), before)
        self.assertEqual((self.root / "sources/current.json").read_bytes(), pointer)

    def test_later_row_failure_rolls_back_entire_batch(self):
        self.update()
        before = self.rows()
        data = {"completed": {"2026-09": "-58440"}, "mtd": {"month": "2026-10", "asof": "2026-10-26", "value": "1"}}
        with self.assertRaisesRegex(ValueError, "backwards"):
            dbm.apply_nsdl_fpi(data, "rejected", {"checked_on": TODAY.isoformat()}, db=self.db)
        self.assertEqual(self.rows(), before)

    def test_database_rejection_keeps_success_pointer_and_other_months(self):
        self.update()
        pointer = (self.root / "sources/current.json").read_bytes()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE india_monthly SET india_fpi_mtd_asof='2026-10-28' WHERE month='2026-10'")
        before = self.rows()
        with self.assertRaisesRegex(ValueError, "backwards"):
            self.update()
        self.assertEqual(self.rows(), before)
        self.assertEqual((self.root / "sources/current.json").read_bytes(), pointer)

    def test_invalid_existing_provenance_is_preserved_and_batch_rejected(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE india_monthly SET source_flags='unreadable' WHERE month='2026-09'")
        before = self.rows()
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual(self.rows(), before)
        self.assertFalse((self.root / "sources/current.json").exists())

    def test_rollover_adopts_final_clears_grey_and_records_revisions(self):
        self.update()
        data = {"completed": {"2026-09": "-58440", "2026-10": "-36000"}, "mtd": None}
        dbm.apply_nsdl_fpi(data, "next-month", {"checked_on": "2026-11-04"}, db=self.db)
        rows = self.rows()
        self.assertEqual(rows["2026-09"]["india_fpi_net_inr_cr"], -58440)
        self.assertEqual(rows["2026-10"]["india_fpi_net_inr_cr"], -36000)
        self.assertIsNone(rows["2026-10"]["india_fpi_mtd_asof"])
        self.assertIsNone(rows["2026-10"]["india_fpi_mtd_inr_cr"])

    def test_current_final_nonfinite_and_dry_run(self):
        for data in [{"completed": {"2026-10": "3"}, "mtd": None}, {"completed": {"2026-09": "NaN"}, "mtd": None}]:
            with self.assertRaises(ValueError):
                dbm.apply_nsdl_fpi(data, "bad", {"checked_on": TODAY.isoformat()}, db=self.db)
        before = self.rows()
        fpi.update(db=self.db, root=self.root / "dry", today=TODAY, client=Client(), dry_run=True)
        self.assertEqual(self.rows(), before)
        self.assertFalse((self.root / "dry").exists())


class PresentationTests(unittest.TestCase):
    def test_current_grey_excluded_from_cumulative_and_removed_next_month(self):
        import pandas as pd
        import matplotlib.pyplot as plt
        import generate_india as charts
        df = pd.DataFrame({"date": pd.to_datetime(["2026-09-01", "2026-10-01"]),
                           "india_fpi_nsdl_lcr": [-0.58443, float("nan")],
                           "india_fpi_mtd_lcr": [float("nan"), -0.3639778],
                           "india_fpi_mtd_asof": pd.to_datetime([None, "2026-10-27"])})
        with patch.object(charts.EconStyle, "save_chart") as save:
            charts.chart_fpi_flows(df, Path("."), today=TODAY)
            fig = save.call_args.args[0]
            self.assertEqual(len(fig.axes[0].patches), 2)
            self.assertTrue(any("1M Cumulative" in t.get_text() and "0.58" in t.get_text() for t in fig.axes[0].texts))
            self.assertTrue(any("27 Oct 2026" in t.get_text() for t in fig.texts))
            plt.close(fig)
            charts.chart_fpi_flows(df, Path("."), today=date(2026,11,4))
            fig = save.call_args.args[0]
            self.assertEqual(len(fig.axes[0].patches), 1)
            plt.close(fig)
            df.loc[1, "india_fpi_nsdl_lcr"] = -0.36
            charts.chart_fpi_flows(df, Path("."), today=date(2026,11,4))
            fig = save.call_args.args[0]
            self.assertEqual(len(fig.axes[0].patches), 2)
            self.assertTrue(any("2M Cumulative" in t.get_text() for t in fig.axes[0].texts))
            plt.close(fig)

    def test_workflow_order_optional_failure_skip_and_publication(self):
        workflow = Path(".github/workflows/india.yml").read_text()
        source = workflow.split("      - name: Refresh official NSDL monthly and MTD FPI flows", 1)[1].split("      - name:", 1)[0]
        self.assertLess(workflow.index("id: nsdl-fpi"), workflow.index("- name: Generate India charts"))
        self.assertIn("skip_fetch != 'true'", source)
        self.assertIn("continue-on-error: true", source)
        self.assertIn("run: python -m data.fetchers.nsdl_fpi", source)
        self.assertIn("IIP_DIR NSDL_FPI_DIR)", workflow)


if __name__ == "__main__":
    unittest.main()
