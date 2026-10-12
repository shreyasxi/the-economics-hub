"""Exact multi-period attribution using base-currency interval P&L / starting wealth."""
import numpy as np
import pandas as pd
from data.processors.portfolio_analytics import aligned_prices


def attribute(prices, simulation, asset_classes=None):
    prices = aligned_prices(prices, list(simulation.holdings)).loc[simulation.wealth.index]
    if not prices.index.equals(simulation.holdings.index):
        raise ValueError("Attribution requires the identical simulation calendar.")
    returns = prices.pct_change(fill_method=None).iloc[1:]
    entering = simulation.holdings.shift(1).iloc[1:]
    pnl = entering * returns
    costs = pd.Series(0., index=returns.index)
    if not simulation.trades.empty:
        costs.loc[simulation.trades.date] = simulation.trades.cost.to_numpy()
    pnl['Trading costs'] = -costs
    change = simulation.wealth.diff().iloc[1:]
    if not np.allclose(pnl.sum(axis=1), change, atol=1e-8, rtol=1e-10):
        raise ValueError('Daily attribution does not reconcile to wealth changes.')
    daily = pnl.div(simulation.wealth.shift(1).iloc[1:], axis=0)
    cumulative = pnl.sum()/simulation.wealth.iloc[0]
    total = simulation.wealth.iloc[-1]/simulation.wealth.iloc[0]-1
    if not np.isclose(cumulative.sum(), total, atol=1e-10):
        raise ValueError('Cumulative attribution does not reconcile.')
    classes = asset_classes or {}
    groups = cumulative.groupby([classes.get(t, t) for t in cumulative.index]).sum()
    return dict(contributions=cumulative, classes=groups, daily=daily, pnl=pnl,
                asset_returns=prices.iloc[-1]/prices.iloc[0]-1,
                drift=simulation.weights.iloc[-1]-simulation.weights.iloc[0],
                cumulative_return=total, cost=float(costs.sum()),
                turnover=float(simulation.trades.turnover.sum()),
                method='Base-currency interval P&L divided by initial wealth; costs separate. Not a sum of arithmetic returns.')
