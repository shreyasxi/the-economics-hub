"""
World tab regression tests.

  * US CPI YoY was published as 3.71% for Aug 2026 when it was 3.35%: FRED has
    no October 2025 CPI, and counting 12 rows back crossed the gap.
  * UK CPI from FRED had stopped in March 2025 but kept appearing as current.

No network: fetchers are exercised with canned responses.

Run:  python tests/test_world.py      (or: python -m pytest tests/test_world.py -q)
"""
from __future__ import annotations

import csv
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data.world_snapshot as ws
from config.world_settings import CENTRAL_BANKS, MANUAL_FIELDS
from data.world_manual_entry import HEADER, ManualDataError, load_rows, validate_row
from generate_macro import _spread_labels_centred, complete_month_average, monotone_curve, weekly_average


def _monthly(values: dict) -> pd.Series:
    return pd.Series({pd.Timestamp(k + "-01"): v for k, v in values.items()})


# ── YoY across a missing month ──────────────────────────────────────────────

def test_yoy_matches_calendar_month_across_a_gap():
    """With October missing, August's YoY must still compare with last August."""
    months = pd.date_range("2025-06-01", "2026-08-01", freq="MS")
    level = pd.Series(range(100, 100 + len(months)), index=months, dtype=float)
    level = level.drop(pd.Timestamp("2025-10-01"))
    yoy = ws.yoy_by_date(level)
    expected = (level[pd.Timestamp("2026-08-01")] / level[pd.Timestamp("2025-08-01")] - 1) * 100
    assert abs(yoy[pd.Timestamp("2026-08-01")] - expected) < 1e-9
    # Positional counting would have used July 2025 instead:
    positional = level.pct_change(12).iloc[-1] * 100
    assert abs(positional - expected) > 0.1


def test_yoy_leaves_month_without_prior_year_blank():
    months = pd.date_range("2025-01-01", "2026-12-01", freq="MS")
    level = pd.Series(100.0, index=months).drop(pd.Timestamp("2025-10-01"))
    assert pd.Timestamp("2026-10-01") not in ws.yoy_by_date(level).index


def test_value_months_ago_needs_the_exact_month():
    s = _monthly({"2026-05": 1.0, "2026-07": 2.0})
    assert ws.value_months_ago(s, 1) is None
    assert ws.value_months_ago(s, 2) == 1.0


# ── Central banks, regime, currency ─────────────────────────────────────────

def test_last_move_finds_latest_change_and_sign():
    s = pd.Series([4.0, 4.0, 3.75, 3.75, 3.75],
                  index=pd.to_datetime(["2025-12-08", "2025-12-09", "2025-12-11", "2026-01-02", "2026-09-14"]))
    assert ws.last_move(s) == {"date": "2025-12-11", "bps": -25}
    assert ws.last_move(pd.Series([2.0, 2.0], index=pd.to_datetime(["2026-01-01", "2026-01-02"]))) is None


def test_regime_quadrants():
    assert ws.regime_label(0.3, -0.2) == "Goldilocks"
    assert ws.regime_label(0.3, 0.2) == "Overheating"
    assert ws.regime_label(-0.3, 0.2) == "Stagflation"
    assert ws.regime_label(-0.3, -0.2) == "Slowdown"


def test_fx_ytd_sign_is_local_currency_strength():
    idx = pd.to_datetime(["2025-12-31", "2026-09-15"])
    inr = pd.Series([90.0, 99.0], index=idx)          # USD/INR up = rupee weaker
    eur = pd.Series([1.10, 1.21], index=idx)          # EUR/USD up = euro stronger
    pct, _ = ws.fx_ytd_pct(inr, usd_per_local=False, today=date(2026, 9, 15))
    assert pct < 0 and abs(pct - (90 / 99 - 1) * 100) < 1e-9
    pct, _ = ws.fx_ytd_pct(eur, usd_per_local=True, today=date(2026, 9, 15))
    assert abs(pct - 10.0) < 1e-9


# ── Staleness rules ─────────────────────────────────────────────────────────

def test_stale_automatic_source_is_a_problem():
    problems = []
    old = _monthly({"2025-02": 3.0, "2025-03": 3.1})     # the dead FRED UK CPI series
    cell = ws._cell("UK", "cpi_yoy", old, date(2026, 9, 15), kind="month", compare="month", problems=problems)
    assert cell["status"] == "stale" and len(problems) == 1


def test_missing_manual_cell_awaits_entry_without_failing():
    problems = []
    cell = ws._cell("US", "mfg_pmi", None, date(2026, 9, 15), kind="month", problems=problems)
    assert cell["status"] == "awaiting" and problems == []


def test_old_hand_refreshed_cell_is_flagged_not_failed():
    problems = []
    old = _monthly({"2026-04": 5.0, "2026-05": 5.1})
    cell = ws._cell("IN", "unemployment", old, date(2026, 11, 1), kind="month", compare="month", problems=problems)
    assert cell["status"] == "stale" and problems == []


def test_missing_automatic_cell_is_a_problem():
    problems = []
    ws._cell("EA", "cpi_yoy", None, date(2026, 9, 15), kind="month", problems=problems)
    assert len(problems) == 1


# ── Eurostat JSON-stat parsing ──────────────────────────────────────────────

def test_eurostat_parser_picks_geo_with_latest_data(monkeypatch=None):
    payload = {
        "id": ["freq", "geo", "time"], "size": [1, 2, 3],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}}},
            "geo": {"category": {"index": {"EA20": 0, "EA21": 1}}},
            "time": {"category": {"index": {"2026-05": 0, "2026-06": 1, "2026-07": 2}}},
        },
        # EA20 stops in May; EA21 has June and July.
        "value": {"0": 6.2, "4": 6.3, "5": 6.4},
    }

    class Fake:
        def json(self):
            return payload

    original = ws._get
    ws._get = lambda *a, **k: Fake()
    try:
        s = ws.fetch_eurostat("une_rt_m", {})
    finally:
        ws._get = original
    assert list(s.index.strftime("%Y-%m")) == ["2026-06", "2026-07"]
    assert list(s.values) == [6.3, 6.4]


# ── Chart lines: smoothing and averaging never invent data ─────────────────

def test_monotone_curve_passes_through_data_and_never_overshoots():
    """The smooth line may round corners but must not add a peak, trough or level the data lacks."""
    months = pd.date_range("2025-01-01", "2026-08-01", freq="MS").drop(pd.Timestamp("2025-10-01"))  # a gap too
    values = [2.4, 2.9, 3.3, 3.3, 3.3, 4.2, 2.5, 2.6, 3.0, 2.7, 2.7, 2.4, 3.3, 3.8, 4.2, 3.5, 3.3, 3.35, 3.1]
    s = pd.Series(values, index=months)
    x, y = monotone_curve(s.index, s.values, per_segment=16)
    curve = pd.Series(y, index=x)
    for t, v in s.items():                                   # every observation is on the curve
        assert abs(curve[curve.index.get_indexer([t], method="nearest")[0]] - v) < 1e-9
    for (t0, v0), (t1, v1) in zip(s.items(), list(s.items())[1:]):
        seg = curve[(curve.index >= t0) & (curve.index <= t1)]
        assert seg.min() >= min(v0, v1) - 1e-9 and seg.max() <= max(v0, v1) + 1e-9, f"overshoot between {t0:%b %Y} and {t1:%b %Y}"
    flat = curve[(curve.index >= pd.Timestamp("2025-03-01")) & (curve.index <= pd.Timestamp("2025-05-01"))]
    assert (abs(flat - 3.3) < 1e-9).all()                    # a flat stretch stays flat


def test_weekly_average_keeps_only_complete_weeks():
    days = pd.bdate_range("2026-08-05", "2026-09-16")        # starts on a Wednesday, ends mid-week
    s = pd.Series(range(len(days)), index=days, dtype=float)
    w = weekly_average(s, today=date(2026, 9, 16))
    assert w.index[0] == pd.Timestamp("2026-08-14")         # the week cut by the start is dropped
    assert w.index[-1] == pd.Timestamp("2026-09-11")        # the week still in progress is dropped
    assert w[pd.Timestamp("2026-08-14")] == s["2026-08-10":"2026-08-14"].mean()


def test_end_labels_never_overlap_and_stay_centred():
    ys = _spread_labels_centred([3.35, 3.34, 2.31, 2.0], 0.16)
    ordered = sorted(ys)
    assert all(b - a >= 0.16 - 1e-9 for a, b in zip(ordered, ordered[1:]))
    assert abs((ys[0] + ys[1]) / 2 - 3.345) < 1e-9          # the colliding pair straddles its own average
    assert ys[2] == 2.31 and ys[3] == 2.0                    # labels with room stay beside their lines


def test_complete_month_average_drops_part_months():
    days = pd.bdate_range("2026-06-15", "2026-09-15")
    s = pd.Series(1.0, index=days)
    m = complete_month_average(s, today=date(2026, 9, 15))
    assert list(m.index.strftime("%Y-%m")) == ["2026-07", "2026-08"]


# ── Manual entry ────────────────────────────────────────────────────────────

def _row(**kw):
    base = {"month": "2026-08", "country": "US", "field": "mfg_pmi", "value": "52.4", "source": "S&P Global"}
    return {**base, **kw}


def test_manual_row_accepts_valid_pmi():
    assert validate_row(_row())["value"] == 52.4


def test_manual_row_refusals():
    for bad in (_row(value="524"), _row(country="US", field="cpi_yoy"), _row(source=""),
                _row(month="2026-8"), _row(month="2999-01"), _row(value="n/a")):
        try:
            validate_row(bad)
        except ManualDataError:
            continue
        raise AssertionError(f"accepted a bad row: {bad}")


def test_manual_file_rejects_duplicates():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "world_manual.csv"
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADER)
            w.writeheader()
            w.writerow(_row())
            w.writerow(_row(value="52.9"))
        try:
            load_rows(path)
        except ManualDataError:
            return
        raise AssertionError("duplicate month/country/field accepted")


def test_committed_manual_file_is_valid():
    load_rows()


def test_india_cells_are_not_manual():
    assert not any(country == "IN" for country, _ in MANUAL_FIELDS)


# ── Meeting calendars ───────────────────────────────────────────────────────

def test_meeting_calendars_are_sorted_and_not_exhausted():
    """Fails when a bank's published dates run out: add next year's from MEETING_SOURCES."""
    soon = date.today().isoformat()
    for bank in CENTRAL_BANKS:
        dates = bank["meetings"]
        if dates is None:
            continue
        assert dates == sorted(dates), f"{bank['id']} meetings are not in order"
        for d in dates:
            date.fromisoformat(d)
        assert dates[-1] >= soon, (
            f"{bank['id']}: no future meeting date listed — add next year's calendar in config/world_settings.py"
        )


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
