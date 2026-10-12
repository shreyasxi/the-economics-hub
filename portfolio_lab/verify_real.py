"""Explicit local verification; refuses synthetic fixtures and writes an audit report.

Run: .venv/bin/python -m portfolio_lab.verify_real
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from config.portfolio_settings import ASSETS, EPISODES, REBALANCING, TEMPLATES
from data.fetchers.portfolio_prices import load_bundle, snapshot_path
from data.processors.portfolio_analytics import compare, metrics, risk_contributions, simulate
from data.processors.portfolio_stress import historical_replay, hypothetical_shock


def independent_path(prices, weights, convention):
    """Share-unit reference (the engine uses asset notionals and daily returns)."""
    w = pd.Series(weights)
    p = prices[list(weights)]
    shares = 10000*w/p.iloc[0]
    values = []
    periods = p.index.to_period(REBALANCING[convention]) if REBALANCING[convention] else None
    for i, (d, row) in enumerate(p.iterrows()):
        value = float((shares*row).sum())
        values.append(value)
        if periods is not None and i > 0 and i < len(p)-1 and periods[i] != periods[i+1]:
            shares = value*w/row
    return np.asarray(values)


def main():
    bundle = snapshot_path()
    prices, manifest = load_bundle(bundle)
    a, b = TEMPLATES["Traditional 60/40"], TEMPLATES["Diversified allocation"]
    checks = []
    report = {"snapshot": bundle.name, "retrieved_utc": manifest["retrieved_utc"],
              "coverage": manifest["assets"], "episodes": {}, "checks": checks}
    for convention in REBALANCING:
        common, results = compare(prices, a, b, "SPY", "2021-01-01", rebalancing=convention)
        for n, w in [("Portfolio A", a), ("Portfolio B", b), ("Benchmark", {"SPY": 1})]:
            expected = independent_path(common, w, convention if n != "Benchmark" else "Buy and hold")
            np.testing.assert_allclose(results[n].wealth, expected, rtol=1e-11)
            daily = expected[1:]/expected[:-1]-1
            m = metrics(results[n])
            days = (common.index[-1]-common.index[0]).days
            assert np.isclose(m["CAGR"], (expected[-1]/10000)**(365.25/days)-1)
            assert np.isclose(m["Annualised volatility"], np.std(daily, ddof=1)*np.sqrt(252))
            assert np.isclose(m["Maximum drawdown"], (expected/np.maximum.accumulate(expected)-1).min())
            assert (results[n].wealth > 0).all()
        checks.append("Share-unit path and independently calculated metrics: " + convention)
    for weights in [{"SPY": 1}, {t: 1/len(ASSETS) for t in ASSETS}]:
        common, results = compare(prices, weights, weights, "SPY")
        expected = independent_path(common, weights, "Buy and hold")
        np.testing.assert_allclose(results["Portfolio A"].wealth, expected, rtol=1e-11)
        pd.testing.assert_series_equal(results["Portfolio A"].wealth, results["Portfolio B"].wealth)
    checks.append("Single SPY and all-prepared-asset portfolios; identical inputs, positive wealth, aligned benchmark")
    for episode in EPISODES:
        for convention in ["Buy and hold", "Monthly"]:
            common, results, summary, _ = historical_replay(prices, a, b, "SPY", episode, convention)
            for n, w in [("Portfolio A", a), ("Portfolio B", b), ("Benchmark", {"SPY": 1})]:
                np.testing.assert_allclose(results[n].wealth, independent_path(common, w, convention if n != "Benchmark" else "Buy and hold"), rtol=1e-11)
            report["episodes"][episode + " · " + convention] = {"start": str(common.index[0].date()),
                "end": str(common.index[-1].date()), "observations": len(common), "outcomes": summary.to_dict()}
        # Expansion includes later launches: verify every actually eligible ETF
        # and explicitly prove that unavailable instruments cannot be backfilled.
        start,end=EPISODES[episode]
        eligible=prices.loc[start:end]
        supported=[t for t in prices if eligible[t].notna().all()]
        weights={t:1/len(supported) for t in supported}
        full, replay, _, _=historical_replay(prices,weights,{"SPY":1},"SPY",episode)
        np.testing.assert_allclose(replay["Portfolio A"].wealth,independent_path(full,weights,"Buy and hold"),rtol=1e-11)
        unavailable=sorted(set(prices)-set(supported))
        for ticker in unavailable:
            try:
                historical_replay(prices,{ticker:1},{"SPY":1},"SPY",episode)
                raise AssertionError("Unavailable inception accepted: "+ticker)
            except ValueError:
                pass
        report["episodes"][episode+" · availability"]={"eligible":supported,"unavailable":unavailable}
        checks.append("Eligible-universe replay and explicit inception failures: " + episode)
    risk = risk_contributions(common, a)
    daily = common[list(a)].pct_change(fill_method=None).iloc[1:].tail(252).to_numpy()
    cov = np.cov(daily, rowvar=False)*252
    w = np.array(list(a.values()))
    assert np.isclose(risk["variance"], w@cov@w)
    assert np.isclose(risk["table"]["Risk contribution"].sum(), 1)
    impact, parts = hypothetical_shock(b, {"SPY": -.2, "AGG": -.05, "GLD": .1})
    assert np.isclose(impact, -.095)
    checks.append("Independent covariance and hypothetical shock (-9.5%) reconciliation")
    try:
        simulate(prices, {"SPY": .5})
        raise AssertionError("Invalid allocation accepted")
    except ValueError:
        checks.append("Invalid allocation blocked")
    broken = common.copy()
    broken.iloc[5, broken.columns.get_loc("SPY")] = np.nan
    try:
        compare(broken, a, b)
        raise AssertionError("Missing observations accepted")
    except ValueError:
        checks.append("Missing observation blocked")
    destination = Path("output/portfolio_lab")
    destination.mkdir(parents=True, exist_ok=True)
    (destination/"verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"checks": checks, "coverage": {t: [m["first_observation"], m["latest_observation"], m["observations"]] for t, m in manifest["assets"].items()}, "episodes": report["episodes"]}, indent=2))


if __name__ == "__main__": main()
