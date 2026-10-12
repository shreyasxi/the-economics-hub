"""Matched weekly and trailing-12-month FX performance bars."""
from datetime import date
from pathlib import Path

import pandas as pd

from charts.style import EconStyle
from charts.templates.change_bars import render_change_bars
from config.weekly_settings import WEEKLY_FX


def fx_returns(histories, as_of):
    """Use the last completed Friday and observed closes on/before each anchor.

    Holiday gaps of up to seven days are allowed. A missing annual baseline
    never becomes a shorter-period return or a filled observation.
    """
    cutoff = pd.Timestamp(as_of).normalize()
    # Friday itself is still in progress; use the prior completed week.
    end = cutoff - pd.Timedelta(days=(cutoff.weekday() - 4) % 7 or 7)
    anchors = (end, end - pd.Timedelta(days=7), end - pd.DateOffset(years=1))
    rows = []
    for name in WEEKLY_FX:
        series = histories[name].dropna().copy()
        series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
        series = series.sort_index()
        prices = []
        for anchor in anchors:
            observations = series.loc[series.index <= anchor]
            if observations.empty or (anchor - observations.index[-1]).days > 7:
                raise ValueError(f"{name}: no close near {anchor:%Y-%m-%d}")
            price = float(observations.iloc[-1])
            if not 0 < price < float("inf"):
                raise ValueError(f"{name}: invalid close at {anchor:%Y-%m-%d}")
            prices.append(price)
        rows.append((name, (prices[0] / prices[1] - 1) * 100,
                     (prices[0] / prices[2] - 1) * 100))
    return end.date(), rows


def generate_fx_charts(output_dir, fetcher=None, as_of=None):
    """Fetch once per pair; validate all ten before replacing either chart."""
    if fetcher is None:
        from data.fetchers.yfinance_fetcher import YFinanceFetcher
        fetcher = YFinanceFetcher()
    as_of = as_of or date.today()
    histories = {}
    for name, ticker in WEEKLY_FX.items():
        histories[name] = fetcher.get_close_series(ticker, period="2y")
        print(f"   FX: {name} ({len(histories[name])} closes)")
    end, rows = fx_returns(histories, as_of)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, title, period, filename in (
        (1, "Foreign Exchange — Weekly Performance", "Weekly", "03_fx_weekly.png"),
        (2, "Key FX Rates — Trailing 12 Months", "Trailing 12-month", "04_fx_trend.png"),
    ):
        fig = render_change_bars([r[0] for r in rows], [r[index] for r in rows], title,
                                 f"{period} percentage change · quoted rates · week ending {end:%d %b %Y}",
                                 "Yahoo Finance", source_date=f"{end:%d %b %Y}")
        EconStyle.save_chart(fig, output_dir / filename)
    return end, rows
