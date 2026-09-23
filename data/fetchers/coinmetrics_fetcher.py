"""
Economics Hub — Coin Metrics Community API fetcher

Bitcoin's MVRV ratio, price and market value, daily since July 2010, from
Coin Metrics' free community API (no key; rate-limited to 10 requests per 6
seconds).

MVRV is market value divided by realised value. Realised value prices every
coin at the price it last moved on-chain, so it approximates what holders paid
in aggregate; MVRV is how far the market price sits above that cost.

Glassnode publishes the same metric, but its API needs a paid plan. The
community tier here carries MVRV, price, market value, hash rate, active
addresses and exchange flows; realised cap itself, NVT and supply-age metrics
are paid, so realised value is derived here as market value ÷ MVRV.

Docs: https://docs.coinmetrics.io/api/v4
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import requests

_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
_METRICS = {"CapMVRVCur": "mvrv", "PriceUSD": "price", "CapMrktCurUSD": "mcap"}


def fetch_btc_mvrv(max_age_days: int = 7) -> pd.DataFrame:
    """
    Daily Bitcoin 'mvrv', 'price' and 'mcap' (market value), with 'rcap'
    (realised value, mcap ÷ mvrv), in USD and indexed by date.

    Raises rather than return a partial or stale series: on any HTTP error,
    a missing metric, a non-positive value, or a latest reading older than
    `max_age_days`.
    """
    rows, url = [], _URL
    params = {"assets": "btc", "metrics": ",".join(_METRICS), "frequency": "1d",
              "page_size": 10000}
    while url:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        rows += body.get("data", [])
        url, params = body.get("next_page_url"), None   # the next-page URL carries its own query

    if not rows:
        raise ValueError("Coin Metrics returned no Bitcoin data")
    df = pd.DataFrame(rows)
    absent = [m for m in _METRICS if m not in df.columns]
    if absent:
        raise ValueError(f"Coin Metrics returned no {', '.join(absent)}")

    df.index = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    df = df[list(_METRICS)].apply(pd.to_numeric, errors="coerce").rename(columns=_METRICS).dropna()
    if (df <= 0).any().any():
        raise ValueError("Coin Metrics returned a non-positive MVRV, price or market value")
    if df.index[-1] < datetime.now() - timedelta(days=max_age_days):
        raise ValueError(f"Coin Metrics data is stale: latest reading {df.index[-1]:%d %b %Y}")
    df["rcap"] = df["mcap"] / df["mvrv"]
    return df.sort_index()


def mvrv_zscore(cm: pd.DataFrame) -> pd.Series:
    """
    The MVRV Z-score: market value less realised value, divided by the standard
    deviation of market value over all of bitcoin's history up to that day.

    Dividing by the spread of market value to date, rather than over the whole
    sample, keeps each reading to what was known then, and reproduces the
    published cycle highs (about 10 in 2013 and 2017, 7 in 2021); the spread of
    the whole sample, dominated by today's market value, would shrink every
    early reading towards zero. The first reading has no spread and is left
    empty.
    """
    spread = cm["mcap"].sort_index().expanding().std()
    return (cm["mcap"] - cm["rcap"]) / spread
