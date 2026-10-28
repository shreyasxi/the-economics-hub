"""Streamlit interaction tests with prepared data (no downloads during reruns)."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class PortfolioUITests(unittest.TestCase):
    def app(self):
        app = AppTest.from_string("from portfolio_lab.page import render\nrender()", default_timeout=30).run()
        return app.button(key="pl_enter_global").click().run()

    def test_entry_chooser_defers_data_and_enters_india(self):
        with patch("portfolio_lab.page.snapshot_path", side_effect=AssertionError("Landing loaded data")), patch("portfolio_lab.india.current", side_effect=ValueError("No INR snapshot")):
            app=AppTest.from_string("from portfolio_lab.page import render\nrender()",default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.button),2)
            self.assertFalse(app.radio)
            self.assertFalse(app.number_input)
            app.button(key="pl_enter_india").click().run()
            self.assertEqual(app.radio(key="pl_mode").value,"Indian Investor — INR")
            self.assertFalse(app.exception)
            self.assertTrue(app.warning)

    def test_compare_duplicate_normalize_and_invalid(self):
        from data.fetchers.portfolio_prices import snapshot_path
        from data.fetchers.portfolio_prices import snapshot_path
        try: snapshot_path()
        except ValueError: self.skipTest("Real local snapshot not prepared")
        # This interaction test checks stress-period coverage warnings, not
        # whether the versioned snapshot happens to be recent on the test date.
        with patch("data.fetchers.yfinance_fetcher.YFinanceFetcher._download", side_effect=AssertionError("UI fetched data")), \
                patch("portfolio_lab.page.freshness", return_value="Historical end-of-day observations"):
            app = self.app()
            self.assertFalse(app.exception)
            app.checkbox(key="pl_compare").check().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.number_input(key="pl_b_SPY").value, 50)
            self.assertEqual(app.multiselect(key="pl_b_assets").value, ["SPY", "AGG", "GLD"])
            app.number_input(key="pl_a_SPY").set_value(20).run()
            self.assertTrue(any("100%" in e.value for e in app.error))
            app.button(key="pl_a_normalize").click().run()
            self.assertFalse(app.error)
            self.assertAlmostEqual(app.number_input(key="pl_a_SPY").value, 100/3)
            app.checkbox(key="pl_compare").uncheck().run()
            app.checkbox(key="pl_compare").check().run()
            self.assertEqual(app.number_input(key="pl_b_SPY").value, 50)
            app.radio(key="pl_view").set_value("Risk").run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Risk contributions sum to 100.00%" in c.value for c in app.caption))
            app.radio(key="pl_view").set_value("Stress Testing").run()
            for episode in ["Global Financial Crisis", "COVID-19 Market Shock", "2022 Equity and Bond Sell-Off"]:
                app.selectbox(key="pl_episode").set_value(episode).run()
                self.assertFalse(app.exception)
                self.assertFalse(app.warning, [w.value for w in app.warning])
            other = self.app()
            self.assertEqual(other.number_input(key="pl_a_SPY").value, 60)
            self.assertFalse(other.checkbox(key="pl_compare").value)

    def test_research_views_and_recent_history(self):
        from data.fetchers.portfolio_prices import snapshot_path
        try: snapshot_path()
        except ValueError: self.skipTest("Real snapshot unavailable")
        from data.fetchers.portfolio_macro import current
        try: current()
        except OSError: self.skipTest("Real macro snapshot unavailable")
        with patch("data.fetchers.fred_fetcher.FredFetcher.fetch_series", side_effect=AssertionError("UI fetched macro")):
            app=self.app()
            app.checkbox(key="pl_compare").check().run()
            for view in ["Performance Attribution","Risk","Macro Regimes","Stress Testing"]:
                app.radio(key="pl_view").set_value(view).run()
                self.assertFalse(app.exception, [e.message for e in app.exception])
            app.radio(key="pl_view").set_value("Macro Regimes").run()
            app.selectbox(key="pl_regime").set_value("Growth").run()
            self.assertFalse(app.exception)
            app.radio(key="pl_view").set_value("Risk").run()
            self.assertFalse(app.exception)
            self.assertFalse(any(c.key == "pl_credit" for c in app.checkbox))
            app.selectbox(key="pl_cov_window").set_value(756).run()
            self.assertFalse(app.exception)
            app.radio(key="pl_view").set_value("Stress Testing").run()
            self.assertNotIn("Factor shocks", app.selectbox(key="pl_stress_mode").options)
            app.selectbox(key="pl_stress_mode").set_value("Direct asset shocks").run()
            self.assertTrue(app.number_input(key="pl_shock_SPY"))
            self.assertFalse(app.exception)

    def test_short_lookback_research_is_unavailable_without_exceptions(self):
        from datetime import date
        app=self.app()
        if app.warning: self.skipTest("Prepared data unavailable")
        app.date_input[0].set_value((date(2026,10,5),date(2026,10,9))).run()
        for view in ["Risk","Macro Regimes"]:
            app.radio(key="pl_view").set_value(view).run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertTrue(app.info)

    def test_no_snapshot_explains_preparation(self):
        with patch("portfolio_lab.page.snapshot_path", side_effect=ValueError("No prepared data")):
            app = self.app()
            self.assertFalse(app.exception)
            self.assertTrue(app.warning)
            self.assertFalse(app.number_input)

    def test_bitcoin_oil_persist_and_unavailable_crisis(self):
        from data.fetchers.portfolio_prices import snapshot_path, load_bundle
        try:
            _, manifest = load_bundle(snapshot_path())
        except (ValueError, OSError):
            self.skipTest('Expanded local snapshot unavailable')
        if 'BTC' not in manifest['assets']:
            self.skipTest('Expanded local snapshot unavailable')
        app = self.app()
        app.checkbox(key='pl_compare').check().run()
        app.selectbox(key='pl_b_template').set_value('Bitcoin & oil research').run()
        self.assertFalse(any(button.label == 'Apply template' for button in app.button))
        expected = ['SPY', 'AGG', 'GLD', 'BTC', 'USO']
        for view in ['Performance Attribution', 'Risk', 'Macro Regimes', 'Stress Testing', 'Overview']:
            app.radio(key='pl_view').set_value(view).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertEqual(app.multiselect(key='pl_b_assets').value, expected)
            self.assertEqual(app.number_input(key='pl_b_BTC').value, 5)
        app.radio(key='pl_view').set_value('Stress Testing').run()
        app.selectbox(key='pl_episode').set_value('Global Financial Crisis').run()
        self.assertTrue(any('BTC lacks complete coverage' in w.value for w in app.warning))
        app.selectbox(key='pl_episode').set_value('COVID-19 Market Shock').run()
        self.assertFalse(app.exception)
        app.selectbox(key='pl_stress_mode').set_value('Direct asset shocks').run()
        app.number_input(key='pl_shock_BTC').set_value(-50).run()
        app.number_input(key='pl_shock_USO').set_value(-30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Portfolio B impact: -14.50%' in m.value for m in app.markdown))
