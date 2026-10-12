"""Synthetic observations are confined to tests; expectations use independent arithmetic."""
import unittest
import numpy as np
import pandas as pd
from data.processors.portfolio_analytics import (aligned_prices, compare, drawdown, metrics,
                                               risk_contributions, simulate, validate_weights)
from data.processors.portfolio_stress import historical_replay, hypothetical_shock


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.prices = pd.DataFrame({"SPY": [100., 110., 121., 108.9], "AGG": [100., 100., 100., 100.]},
                                   index=pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-04"]))

    def test_sortino_zero_target_and_undefined_cases(self):
        from types import SimpleNamespace
        dates=pd.bdate_range('2020-01-01', periods=201)
        returns=pd.Series([.02,-.01,0,.01]*50, index=dates[1:])
        wealth=pd.Series(10000*np.r_[1,(1+returns).cumprod()], index=dates)
        result=SimpleNamespace(wealth=wealth, returns=returns)
        expected=.005*np.sqrt(252)/.005
        self.assertAlmostEqual(metrics(result)['Sortino ratio (0% target)'], expected)
        result.returns=pd.Series(.01,index=dates[1:])
        self.assertTrue(np.isnan(metrics(result)['Sortino ratio (0% target)']))
        result.returns=returns.iloc[:20];result.wealth=wealth.iloc[:21]
        self.assertTrue(np.isnan(metrics(result)['Sortino ratio (0% target)']))

    def test_single_asset(self):
        r = simulate(self.prices, {"SPY": 1}, "Monthly", 20)
        np.testing.assert_allclose(r.wealth, [10000, 11000, 12100, 10890])
        np.testing.assert_allclose(r.returns, [.1, .1, -.1])
        self.assertTrue(r.trades.empty)

    def test_buy_hold_drift(self):
        r = simulate(self.prices, {"SPY": .6, "AGG": .4})
        np.testing.assert_allclose(r.wealth, [10000, 10600, 11260, 10534])
        self.assertAlmostEqual(r.weights.iloc[1]["SPY"], 6600/10600)
        np.testing.assert_allclose(r.holdings.iloc[-1], [6534, 4000])
        self.assertTrue((r.wealth > 0).all())

    def test_rebalance_timing_no_lookahead(self):
        r = simulate(self.prices, {"SPY": .6, "AGG": .4}, "Monthly")
        np.testing.assert_allclose(r.wealth, [10000, 10600, 11236, 10536.4])
        np.testing.assert_allclose(r.weights.iloc[1], [.6, .4])
        self.assertAlmostEqual(r.weights.iloc[2]["SPY"], 6996/11236)
        changed = self.prices.copy()
        changed.iloc[2:, 0] *= 2
        np.testing.assert_allclose(simulate(changed, {"SPY": .6, "AGG": .4}, "Monthly").holdings.iloc[:2], r.holdings.iloc[:2])

    def test_exact_cost_on_traded_notional(self):
        r = simulate(self.prices, {"SPY": .6, "AGG": .4}, "Monthly", 10)
        # Buy and sell both count: 480 + .2*C; C=.001*(480+.2*C).
        cost = .48/.9998
        self.assertAlmostEqual(r.trades.iloc[0]["cost"], cost)
        self.assertAlmostEqual(r.trades.iloc[0]["traded_notional"], cost/.001)
        self.assertAlmostEqual(r.wealth.iloc[1], 10600-cost)
        self.assertAlmostEqual(r.wealth.iloc[2], (10600-cost)*1.06)
        self.assertEqual(len(r.trades), 1)
        self.assertTrue(simulate(self.prices, {"SPY": .6, "AGG": .4}, cost_bps=100).trades.empty)

    def test_distinct_schedules(self):
        dates = pd.bdate_range("2019-12-20", "2021-02-04")
        p = pd.DataFrame({"SPY": 100*1.001**np.arange(len(dates)), "AGG": 100.}, index=dates)
        counts = [len(simulate(p, {"SPY": .6, "AGG": .4}, s).trades) for s in ["Monthly", "Quarterly", "Annual"]]
        self.assertEqual(counts, [14, 5, 2])
        for s in ["Monthly", "Quarterly", "Annual"]:
            r = simulate(p, {"SPY": .6, "AGG": .4}, s)
            for d in r.trades.date:
                np.testing.assert_allclose(r.weights.loc[d], [.6, .4])

    def test_invalid_weights_and_parameters(self):
        for w in [{}, {"SPY": .7}, {"SPY": 1.1, "AGG": -.1}, {"SPY": np.nan}, {"SPY": np.inf}]:
            with self.assertRaises(ValueError):
                validate_weights(w)
        for kwargs in [{"rebalancing": "Weekly"}, {"cost_bps": -1}, {"cost_bps": np.nan}, {"initial": 0}]:
            with self.assertRaises(ValueError):
                simulate(self.prices, {"SPY": 1}, **kwargs)

    def test_same_inputs_same_results_and_same_dates(self):
        p, r = compare(self.prices, {"SPY": .6, "AGG": .4}, {"SPY": .6, "AGG": .4})
        pd.testing.assert_series_equal(r["Portfolio A"].wealth, r["Portfolio B"].wealth)
        self.assertTrue(all(x.wealth.index.equals(p.index) for x in r.values()))
        np.testing.assert_allclose(simulate(self.prices, {"SPY": 1}, initial=100).returns,
                                   simulate(self.prices, {"SPY": 1}).returns)

    def test_missing_and_bad_dates_fail(self):
        for kind in ["missing", "duplicate", "unsorted", "zero", "inf", "gap"]:
            p = self.prices.copy()
            if kind == "missing": p.iloc[1, 1] = np.nan
            if kind == "duplicate": p.index = pd.to_datetime(["2020-01-30", "2020-01-30", "2020-02-03", "2020-02-04"])
            if kind == "unsorted": p = p.iloc[::-1]
            if kind == "zero": p.iloc[1, 0] = 0
            if kind == "inf": p.iloc[1, 0] = np.inf
            if kind == "gap": p.index = pd.to_datetime(["2020-01-01", "2020-01-31", "2020-02-03", "2020-02-04"])
            with self.assertRaises(ValueError, msg=kind):
                aligned_prices(p, ["SPY", "AGG"])

    def test_common_coverage_is_explicit(self):
        p = self.prices.copy()
        p.iloc[0, 1] = np.nan
        common, r = compare(p, {"SPY": 1}, {"AGG": 1})
        self.assertEqual(common.index[0], p.index[1])
        self.assertTrue(all(x.wealth.index.equals(common.index) for x in r.values()))

    def test_drawdown_short_sample(self):
        series = pd.Series([100, 120, 90, 108, 121])
        np.testing.assert_allclose(drawdown(series), [0, 0, -.25, -.1, 0])
        m = metrics(simulate(self.prices, {"SPY": 1}))
        self.assertTrue(np.isnan(m["CAGR"]))
        self.assertTrue(np.isnan(m["Annualised volatility"]))

    def test_annualisation_actual_horizon(self):
        dates = pd.bdate_range("2020-01-02", "2021-01-04")
        p = pd.DataFrame({"SPY": np.exp(np.arange(len(dates))*.001)}, index=dates)
        r = simulate(p, {"SPY": 1})
        m = metrics(r)
        self.assertAlmostEqual(m["CAGR"], np.exp((len(dates)-1)*.001*365.25/368)-1)
        self.assertAlmostEqual(m["Annualised volatility"], np.std(r.returns, ddof=1)*np.sqrt(252))

    def test_risk_reconciles_negative_hedge_and_window(self):
        dates = pd.bdate_range("2020-01-01", periods=400)
        x = np.tile([.01, -.01], 199)
        x = np.r_[.08, x]
        p = pd.DataFrame({"SPY": np.r_[100, 100*np.cumprod(1+x)],
                          "AGG": np.r_[100, 100*np.cumprod(1-x*.5)]}, index=dates)
        r = risk_contributions(p, {"SPY": .8, "AGG": .2})
        cov = np.cov(np.column_stack([x[-252:], -.5*x[-252:]]), rowvar=False)*252
        w = np.array([.8, .2])
        self.assertAlmostEqual(r["variance"], w@cov@w)
        np.testing.assert_allclose(r["table"]["Risk contribution"], [8/7, -1/7])
        self.assertAlmostEqual(r["table"]["Risk contribution"].sum(), 1)
        self.assertEqual(r["observations"], 252)
        self.assertEqual(r["start"], dates[-252])

    def test_near_zero_variance_and_minimum(self):
        p = pd.DataFrame({"SPY": 100.}, index=pd.bdate_range("2020-01-01", periods=30))
        r = risk_contributions(p, {"SPY": 1})
        self.assertTrue(r["table"]["Risk contribution"].isna().all())
        with self.assertRaises(ValueError): risk_contributions(p.iloc[:15], {"SPY": 1})

    def test_hypothetical_shocks(self):
        impact, parts = hypothetical_shock({"SPY": .5, "AGG": .3, "GLD": .2}, {"SPY": -.2, "AGG": -.05, "GLD": .1})
        self.assertAlmostEqual(impact, -.095)
        np.testing.assert_allclose(parts, [-.1, -.015, .02])
        with self.assertRaises(ValueError): hypothetical_shock({"SPY": 1}, {})
        with self.assertRaises(ValueError): hypothetical_shock({"SPY": 1}, {"SPY": -1.01})

    def test_historical_boundaries_and_fresh_allocation(self):
        dates = pd.bdate_range("2020-02-01", "2020-05-15")
        p = pd.DataFrame({"SPY": 100*1.01**np.arange(len(dates)), "AGG": 100.}, index=dates)
        window, result, summary, asset = historical_replay(p, {"SPY": .6, "AGG": .4}, {"SPY": 1}, "SPY", "COVID-19 Market Shock")
        self.assertEqual(window.index[0], pd.Timestamp("2020-02-19"))
        self.assertEqual(window.index[-1], pd.Timestamp("2020-04-30"))
        self.assertEqual(result["Portfolio A"].wealth.iloc[0], 10000)
        self.assertAlmostEqual(result["Portfolio A"].wealth.iloc[-1], 6000*1.01**(len(window)-1)+4000)
        self.assertAlmostEqual(summary.loc["Episode return", "Portfolio B"], asset["SPY"])
        self.assertFalse(historical_replay(p, {"SPY": .6, "AGG": .4}, {"SPY": 1}, "SPY", "COVID-19 Market Shock", "Monthly")[1]["Portfolio A"].trades.empty)
        for broken in [p.loc["2020-03-01":], p.assign(AGG=np.nan), p.drop(columns="AGG")]:
            with self.assertRaisesRegex(ValueError, "unavailable"):
                historical_replay(broken, {"AGG": 1}, {"SPY": 1}, "SPY", "COVID-19 Market Shock")


if __name__ == "__main__": unittest.main()
