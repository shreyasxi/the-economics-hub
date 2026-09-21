"""
Signal or noise: the arithmetic behind the Analysis page's board.

A week's move divided by the root mean square of the past three years' weekly
moves; "largest since" is the last earlier week at least as large the same way.
These build series whose answers are known by construction, offline.

Run:  python tests/test_signals.py      (or: python -m pytest tests/test_signals.py -q)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.signals_settings as cfg
from data.signals import assess, last_friday_before, rank

WEEK_END = date(2026, 9, 18)          # a Friday
PCT = {"id": "x", "name": "X", "group": "Equities", "measure": "pct", "fmt": "index"}
BP = {"id": "y", "name": "Y", "group": "Rates", "measure": "bp", "fmt": "yield"}
KW = dict(window_weeks=156, min_weeks=52, stale_days=4)


def _weekly(moves: list[float], start: float = 100.0, end: date = WEEK_END, bp: bool = False) -> pd.Series:
    """Friday closes that make exactly these week-on-week moves (per cent, or basis points)."""
    closes = [start]
    for m in moves:
        closes.append(closes[-1] + m / 100 if bp else closes[-1] * (1 + m / 100))
    index = pd.date_range(end=pd.Timestamp(end), periods=len(closes), freq="W-FRI")
    return pd.Series(closes, index=index)


def test_last_friday_before():
    assert last_friday_before(date(2026, 9, 19)) == date(2026, 9, 18)   # Saturday's run: the week just ended
    assert last_friday_before(date(2026, 9, 18)) == date(2026, 9, 11)   # a Friday: that week is not over
    assert last_friday_before(date(2026, 9, 21)) == date(2026, 9, 18)   # Monday


def test_move_typical_and_multiple():
    series = _weekly([1.0, -1.0] * 60 + [3.0])
    row, reason = assess(series, PCT, WEEK_END, **KW)
    assert reason is None
    assert abs(row["move"] - 3.0) < 1e-6
    assert abs(row["typical"] - 1.0) < 1e-6          # root mean square of +-1
    assert abs(row["multiple"] - 3.0) < 1e-3
    assert row["since"] is None                      # nothing as large before it
    assert row["last_price"] == "2026-09-18"


def test_basis_points_for_yields():
    series = _weekly([5.0, -5.0] * 60 + [-15.0], start=4.0, bp=True)
    row, _ = assess(series, BP, WEEK_END, **KW)
    assert abs(row["move"] + 15.0) < 1e-6
    assert abs(row["typical"] - 5.0) < 1e-6
    assert abs(row["multiple"] + 3.0) < 1e-3


def test_since_is_the_last_week_at_least_as_large_the_same_way():
    moves = [1.0, -1.0] * 60 + [4.0, 1.0, -5.0, 1.0, -1.0, 3.0]
    series = _weekly(moves)
    row, _ = assess(series, PCT, WEEK_END, **KW)
    four_up = series.index[-6].date()                # the week that rose 4%
    assert row["since"] == four_up.isoformat()
    falls = _weekly(moves[:-1] + [-3.0])
    row, _ = assess(falls, PCT, WEEK_END, **KW)
    assert row["since"] == falls.index[-4].date().isoformat()   # the 5% fall, not the 4% rise


def test_the_window_is_the_recent_three_years():
    # Wild weeks long ago do not set today's bar: only the last 156 count.
    series = _weekly([10.0, -10.0] * 40 + [1.0, -1.0] * 78 + [2.0])
    row, _ = assess(series, PCT, WEEK_END, **KW)
    assert abs(row["typical"] - 1.0) < 1e-6
    assert row["since"] is not None                  # but "largest since" still looks back further


def test_timezone_aware_prices_are_read_as_trade_dates():
    series = _weekly([1.0, -1.0] * 60 + [2.0])
    series.index = series.index.tz_localize("Asia/Kolkata")
    row, reason = assess(series, PCT, WEEK_END, **KW)
    assert reason is None and abs(row["multiple"] - 2.0) < 1e-3


def test_a_stale_series_is_left_out():
    series = _weekly([1.0, -1.0] * 60, end=date(2026, 9, 11))
    row, reason = assess(series, PCT, WEEK_END, **KW)
    assert row is None and reason == "no price since 11 Sep"


def test_a_week_without_trading_is_never_bridged():
    series = _weekly([1.0, -1.0] * 60 + [2.0])
    series = series.drop(pd.Timestamp("2026-09-11"))     # the previous Friday, and so the whole week
    row, reason = assess(series, PCT, WEEK_END, **KW)
    assert row is None and reason == "no price the week before"


def test_too_little_history_is_left_out():
    row, reason = assess(_weekly([1.0, -1.0] * 10), PCT, WEEK_END, **KW)
    assert row is None and reason.startswith("only ")


def test_rank_is_by_size_whatever_the_direction():
    rows = [{"name": "a", "multiple": 1.2}, {"name": "b", "multiple": -2.5}, {"name": "c", "multiple": 2.0}]
    assert [r["name"] for r in rank(rows)] == ["b", "c", "a"]


def test_the_series_list_is_well_formed():
    ids = [s["id"] for s in cfg.SERIES]
    assert len(ids) == len(set(ids)), "series ids must be unique"
    groups = {"Equities", "Rates", "Credit", "Currencies", "Commodities", "Volatility", "Crypto"}
    fmts = {"index", "usd", "fx2", "fx4", "yield", "spread", "vol", "eur"}
    for s in cfg.SERIES:
        assert s["group"] in groups, s
        assert s["source"] in ("yfinance", "fred"), s
        assert s["measure"] in ("pct", "bp"), s
        assert s["fmt"] in fmts, s
        # Basis points only make sense for FRED series quoted in per cent.
        assert s["measure"] != "bp" or s["source"] == "fred", s


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  PASS  {name}"); passed += 1
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}"); failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
