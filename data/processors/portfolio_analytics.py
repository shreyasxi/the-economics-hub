"""Pure, independently testable historical portfolio calculations. No I/O or UI."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from config.portfolio_settings import (INITIAL_WEALTH, MIN_ANNUAL_OBSERVATIONS,
                                     REBALANCING, RISK_WINDOW, TRADING_DAYS)


def validate_weights(weights):
    if not weights:
        raise ValueError("Select at least one asset.")
    values = np.asarray(list(weights.values()), dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise ValueError("Weights must be finite and between 0% and 100%.")
    if not np.isclose(values.sum(), 1, atol=1e-8, rtol=0):
        raise ValueError("Weights must total 100%; current total is {:.2f}%.".format(values.sum()*100))


def validate_prices(prices):
    if prices.empty or len(prices) < 2 or prices.columns.duplicated().any():
        raise ValueError("At least two observations and unique asset columns are required.")
    if not isinstance(prices.index, pd.DatetimeIndex) or prices.index.hasnans:
        raise ValueError("Prices require valid dated observations.")
    if prices.index.tz is not None or not prices.index.equals(prices.index.normalize()):
        raise ValueError("Prices require timezone-free trading dates.")
    if prices.index.duplicated().any() or not prices.index.is_monotonic_increasing:
        raise ValueError("Trading dates must be chronological and unique.")
    observed = prices.to_numpy(dtype=float)
    if np.isinf(observed).any() or (observed[~np.isnan(observed)] <= 0).any():
        raise ValueError("Observed prices must be positive and finite.")


def aligned_prices(prices, tickers, start=None, end=None):
    """Intersect coverage endpoints; reject omissions within common coverage.

    Whole-market holidays have no rows. Individual source omissions cause an
    explicit failure, never a filled price or an artificial multi-day daily return.
    """
    validate_prices(prices)
    tickers = list(dict.fromkeys(tickers))
    missing = set(tickers) - set(prices.columns)
    if missing:
        raise ValueError("Missing histories: " + ", ".join(sorted(missing)))
    selected = prices[tickers].loc[start:end]
    bounds = [(selected[t].first_valid_index(), selected[t].last_valid_index()) for t in tickers]
    if any(a is None or b is None for a, b in bounds):
        raise ValueError("No valid history in the requested period.")
    selected = selected.loc[max(a for a, _ in bounds):min(b for _, b in bounds)]
    if len(selected) < 2:
        raise ValueError("No common history with at least two trading closes.")
    if selected.isna().any().any():
        counts = selected.isna().sum()
        raise ValueError("Missing observations inside common coverage: " + ", ".join(
            "{} ({})".format(t, n) for t, n in counts.items() if n))
    max_gap = prices.attrs.get('max_gap_days', 7)
    if max_gap not in (7, 14):
        raise ValueError('Unsupported evaluation calendar gap limit')
    if selected.index.to_series().diff().dt.days.max() > max_gap:
        raise ValueError("Material gap in the common calendar (more than {} calendar days).".format(max_gap))
    return selected


@dataclass
class Simulation:
    wealth: pd.Series
    returns: pd.Series
    weights: pd.DataFrame
    holdings: pd.DataFrame
    trades: pd.DataFrame


def rebalance_positions(positions, target, cost_bps):
    """Shared exact self-financing rebalance, also used by cash-flow simulations."""
    positions=np.asarray(positions,dtype=float);target=np.asarray(target,dtype=float)
    if positions.shape!=target.shape or not np.isfinite(positions).all() or (positions<0).any():
        raise ValueError('Invalid holdings for rebalance')
    validate_weights(dict(enumerate(target)))
    if not np.isfinite(cost_bps) or not 0<=cost_bps<=100:raise ValueError('Invalid rebalance cost')
    total=positions.sum();fee=cost_bps/10000;low,high=0.,total*2*fee
    for _ in range(60):
        cost=(low+high)/2;required=fee*np.abs(target*(total-cost)-positions).sum()
        if cost<required:low=cost
        else:high=cost
    cost=(low+high)/2 if fee else 0.
    traded=np.abs(target*(total-cost)-positions).sum()
    return target*(total-cost),float(cost),float(traded)


def simulate(prices, weights, rebalancing="Buy and hold", cost_bps=0, initial=INITIAL_WEALTH):
    validate_weights(weights)
    if rebalancing not in REBALANCING:
        raise ValueError("Unknown rebalancing convention.")
    if not np.isfinite(initial) or initial <= 0 or not np.isfinite(cost_bps) or not 0 <= cost_bps <= 100:
        raise ValueError("Initial wealth must be positive; cost must be 0–100 bps.")
    prices = aligned_prices(prices, list(weights))
    target = np.asarray(list(weights.values()), dtype=float)
    returns = prices.pct_change(fill_method=None).iloc[1:].to_numpy()
    positions = initial * target
    history = [positions.copy()]
    trade_log = []
    frequency = REBALANCING[rebalancing]
    periods = prices.index.to_period(frequency) if frequency else None
    for i, daily in enumerate(returns, 1):
        positions = positions * (1 + daily)
        if frequency and i < len(prices)-1 and periods[i] != periods[i+1]:
            total = positions.sum()
            # Exact self-financing cost: C = fee * sum(abs(w*(V-C)-holdings)).
            # Turnover is BOTH buys and sells divided by pre-trade wealth.
            positions, cost, traded = rebalance_positions(positions, target, cost_bps)
            if traded > total * 1e-12:
                trade_log.append((prices.index[i], traded, traded/total, cost))
        history.append(positions.copy())
    holdings = pd.DataFrame(history, index=prices.index, columns=list(weights))
    wealth = holdings.sum(axis=1).rename("wealth")
    trades = pd.DataFrame(trade_log, columns=["date", "traded_notional", "turnover", "cost"])
    return Simulation(wealth, wealth.pct_change(fill_method=None).iloc[1:],
                      holdings.div(wealth, axis=0), holdings, trades)


def drawdown(wealth):
    return wealth / wealth.cummax() - 1


def metrics(result, periods_per_year=TRADING_DAYS, currency_symbol='$'):
    wealth, daily = result.wealth, result.returns
    days = (wealth.index[-1]-wealth.index[0]).days
    minimum = MIN_ANNUAL_OBSERVATIONS if periods_per_year == TRADING_DAYS else max(26, periods_per_year//2)
    annual_ok = len(daily) >= minimum and days >= 182
    # Zero minimum acceptable return; downside RMS includes every observation,
    # with non-negative returns contributing zero, not dropped from the sample.
    downside = np.sqrt(np.square(np.minimum(daily, 0)).mean())
    sortino = daily.mean()*np.sqrt(periods_per_year)/downside if annual_ok and downside > 1e-14 else np.nan
    return {
        "Cumulative return": wealth.iloc[-1]/wealth.iloc[0]-1,
        "CAGR": (wealth.iloc[-1]/wealth.iloc[0])**(365.25/days)-1 if annual_ok else np.nan,
        "Annualised volatility": daily.std(ddof=1)*np.sqrt(periods_per_year) if annual_ok else np.nan,
        "Maximum drawdown": drawdown(wealth).min(),
        "Sortino ratio (0% target)": sortino,
        "Final wealth ("+currency_symbol+")": wealth.iloc[-1],
        "Negative "+('daily' if periods_per_year==TRADING_DAYS else 'weekly')+" observations": (daily < 0).mean(),
    }


def compare(prices, a, b, benchmark="SPY", start=None, end=None,
            rebalancing="Buy and hold", cost_bps=0, initial=INITIAL_WEALTH):
    validate_weights(a)
    validate_weights(b)
    common = aligned_prices(prices, list(a)+list(b)+[benchmark], start, end)
    results = {"Portfolio A": simulate(common, a, rebalancing, cost_bps, initial),
               "Portfolio B": simulate(common, b, rebalancing, cost_bps, initial),
               "Benchmark": simulate(common, {benchmark: 1.0}, initial=initial)}
    return common, results


def risk_contributions(prices, weights, window=RISK_WINDOW, periods_per_year=TRADING_DAYS):
    validate_weights(weights)
    if window < 2:
        raise ValueError("Covariance window must contain at least two returns.")
    prices = aligned_prices(prices, list(weights))
    returns = prices.pct_change(fill_method=None).iloc[1:].tail(window)
    if len(returns) < max(20, 5*len(weights)):
        raise ValueError("Risk estimation requires at least max(20, five times the number of holdings) common return observations.")
    covariance = returns.cov() * periods_per_year
    w = np.array(list(weights.values()))
    marginal = covariance.to_numpy() @ w
    variance = float(w @ marginal)
    contributions = w*marginal/variance if variance > 1e-14 else np.full(len(w), np.nan)
    if variance > 1e-14 and not np.isclose(contributions.sum(), 1, atol=1e-9):
        raise ValueError("Risk contributions do not reconcile.")
    table = pd.DataFrame({"Allocation": w, "Risk contribution": contributions}, index=list(weights))
    return {"table": table, "variance": variance, "covariance": covariance,
            "correlation": returns.corr(), "observations": len(returns),
            "start": returns.index[0], "end": returns.index[-1],
            "requested_window": window, "complete_window": len(returns)==window,
            "capital_concentration": float(w@w),
            "condition": float(np.linalg.cond(covariance.to_numpy())),
            "diagnostic": "Unstable/singular covariance; duplicated exposures or too little independent variation" if np.linalg.cond(covariance.to_numpy())>1e8 else "Empirical covariance; no regularisation"}
