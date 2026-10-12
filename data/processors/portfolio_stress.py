"""Isolated historical replays and simultaneous user-specified shocks."""
import numpy as np
import pandas as pd
from config.portfolio_settings import EPISODES
from data.processors.portfolio_analytics import compare, metrics, validate_weights


def historical_replay(prices, a, b, benchmark, episode, rebalancing="Buy and hold", cost_bps=0,
                      episode_windows=None, initial=10000, periods_per_year=252, currency_symbol='$'):
    start, end = (episode_windows or EPISODES)[episode]
    tickers = list(dict.fromkeys(list(a)+list(b)+[benchmark]))
    # Require the entire eligible calendar, including boundary closes; never
    # shrink an episode to an asset's available sub-period.
    eligible = prices.loc[start:end]
    if len(eligible) < 2:
        raise ValueError("Episode unavailable: no eligible history.")
    for t in tickers:
        if t not in eligible or eligible[t].isna().any():
            raise ValueError("Episode unavailable: {} lacks complete coverage.".format(t))
    if ((eligible.index[0]-pd.Timestamp(start)).days > prices.attrs.get('max_gap_days',7) or
            (pd.Timestamp(end)-eligible.index[-1]).days > prices.attrs.get('max_gap_days',7)):
        raise ValueError("Episode unavailable: incomplete boundary coverage.")
    common, results = compare(eligible, a, b, benchmark, rebalancing=rebalancing, cost_bps=cost_bps,initial=initial)
    outcomes = {}
    for name, result in results.items():
        m = metrics(result,periods_per_year,currency_symbol)
        outcomes[name] = {"Episode return": m["Cumulative return"],
                          "Maximum drawdown": m["Maximum drawdown"],
                          "Worst "+('daily' if periods_per_year==252 else 'weekly')+" return": result.returns.min(),
                          "Final wealth ("+currency_symbol+")": m["Final wealth ("+currency_symbol+")"]}
    return common, results, pd.DataFrame(outcomes), common.iloc[-1]/common.iloc[0]-1


def hypothetical_shock(weights, shocks):
    validate_weights(weights)
    if not set(weights).issubset(shocks):
        raise ValueError("Enter a shock for every selected asset.")
    values = np.array([shocks[t] for t in weights], dtype=float)
    if not np.isfinite(values).all() or (values < -1).any():
        raise ValueError("Shocks must be finite and cannot be below −100%.")
    contributions = pd.Series({t: weights[t]*shocks[t] for t in weights})
    return float(contributions.sum()), contributions


def diversification_windows(prices, a, b, benchmark, episode, rebalancing='Buy and hold', cost_bps=0, surrounding=252,
                            episode_windows=None,initial=10000,periods_per_year=252,currency_symbol='$'):
    """Daily pre/episode/post covariance, same target allocations; ex-post diagnostics."""
    from data.processors.portfolio_analytics import risk_contributions
    from data.processors.portfolio_attribution import attribute
    window, results, summary, asset_returns=historical_replay(prices,a,b,benchmark,episode,rebalancing,cost_bps,episode_windows,initial,periods_per_year,currency_symbol)
    tickers=list(dict.fromkeys(list(a)+list(b)))
    # Retain a preceding baseline close for each return sample.
    before=prices[tickers].loc[:window.index[0]].iloc[:-1].tail(surrounding+1)
    after=prices[tickers].loc[window.index[-1]:].head(surrounding+1)
    estimates={}; unavailable={}
    for label, sample in [('Pre-stress',before),('During stress (ex-post)',window),('Post-stress (ex-post)',after)]:
        if label!='During stress (ex-post)' and len(sample)<surrounding+1:
            unavailable[label]='Requires {} complete surrounding {} returns.'.format(surrounding,'weekly' if periods_per_year==52 else 'daily'); continue
        if sample.isna().any().any():
            unavailable[label]='Selected assets lack full window coverage.'; continue
        try:
            estimates[label]={name:risk_contributions(sample,weights,window=len(sample)-1,periods_per_year=periods_per_year)
                              for name,weights in [('Portfolio A',a),('Portfolio B',b)]}
        except ValueError as exc:
            unavailable[label]=str(exc)
    attribution={name:attribute(window,result) for name,result in results.items()}
    return dict(window=window,results=results,summary=summary,asset_returns=asset_returns,
                estimates=estimates,unavailable=unavailable,attribution=attribution,
                caveat='During/post-stress covariances are ex-post. Target-weight snapshots isolate covariance changes; actual episode holdings drift. No forecast.')
