"""
Signal or noise: how unusual was the week's move, series by series?

Pure functions over daily price and yield series, so the arithmetic can be
tested without a network. generate_signals.py fetches the series and writes
signals.json; the Analysis page only reads that file.

For one series and a week ending on Friday `week_end`:

    move      Friday's close against the previous Friday's: per cent for
              prices, basis points for yields and spreads
    typical   root mean square of the weekly moves over the `window_weeks`
              before this one, the size of an ordinary week, up or down
    multiple  move / typical, signed
    since     the last earlier week, in the history fetched, with a move at
              least as large in the same direction ("largest rise since ...")

Weeks are Friday-ending (W-FRI). A week with no trading at all (a market holiday
week) is left as a gap, never bridged, so no move ever spans two weeks.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd


def last_friday_before(today: date) -> date:
    """The latest Friday strictly before `today`: Saturday's run measures the week just ended."""
    return today - timedelta(days=(today.weekday() - 4) % 7 or 7)


def _daily(series: pd.Series, week_end: date) -> pd.Series:
    """The series up to and including week_end, on a tz-naive index of trade dates."""
    s = series.dropna()
    if getattr(s.index, "tz", None) is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    s = s.sort_index()
    return s[s.index < pd.Timestamp(week_end) + pd.Timedelta(days=1)]


def weekly_moves(daily: pd.Series, measure: str) -> tuple[pd.Series, pd.Series]:
    """(Friday closes, week-on-week moves). Moves are NaN wherever either week had no trading."""
    closes = daily.resample("W-FRI").last()
    if measure == "bp":
        moves = closes.diff() * 100
    else:
        moves = closes.pct_change(fill_method=None) * 100
    return closes, moves


def assess(series: pd.Series, spec: dict, week_end: date, *, window_weeks: int,
           min_weeks: int, stale_days: int) -> tuple[dict | None, str | None]:
    """
    (row, None) for a series that can be measured this week, or (None, reason)
    for one that cannot. The reason is written for a reader: it is shown under
    the board as the series' note.
    """
    daily = _daily(series, week_end)
    if daily.empty:
        return None, "no data"
    last = daily.index[-1].date()
    if (week_end - last).days > stale_days:
        return None, f"no price since {last.day} {last:%b}"

    closes, moves = weekly_moves(daily, spec["measure"])
    this_week = pd.Timestamp(week_end)
    if closes.index[-1] != this_week or math.isnan(moves.iloc[-1]):
        return None, "no price the week before"
    move = float(moves.iloc[-1])

    history = moves.iloc[:-1].dropna()
    window = history.iloc[-window_weeks:]
    if len(window) < min_weeks:
        return None, f"only {len(window)} weeks of history"
    typical = math.sqrt(float((window ** 2).mean()))
    if typical == 0:
        return None, "no movement in the past three years"

    if move > 0:
        as_large = history[history >= move]
    elif move < 0:
        as_large = history[history <= move]
    else:
        as_large = history.iloc[:0]

    return {
        "id": spec["id"],
        "name": spec["name"],
        "group": spec["group"],
        "measure": spec["measure"],
        "fmt": spec["fmt"],
        "level": round(float(closes.iloc[-1]), 6),
        "move": round(move, 4),
        "typical": round(typical, 4),
        "multiple": round(move / typical, 3),
        # The last week at least this large in the same direction, or None
        # when nothing in the history fetched comes close.
        "since": as_large.index[-1].date().isoformat() if len(as_large) else None,
        "history_from": history.index[0].date().isoformat(),
        "last_price": last.isoformat(),
    }, None


def rank(rows: list[dict]) -> list[dict]:
    """Most unusual first, whichever the direction."""
    return sorted(rows, key=lambda r: (-abs(r["multiple"]), r["name"]))
