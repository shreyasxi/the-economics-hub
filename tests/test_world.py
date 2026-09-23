"""
World tab regression tests.

  * US CPI YoY was published as 3.71% for Aug 2026 when it was 3.35%: FRED has
    no October 2025 CPI, and counting 12 rows back crossed the gap.
  * UK CPI from FRED had stopped in March 2025 but kept appearing as current.
  * The BoJ's 18 Sep 2026 hike was missing for a week: BIS runs about a week
    behind, so rates are now also read from the banks' own announcements.

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


# ── Central banks, currency ─────────────────────────────────────────────────

def test_last_move_finds_latest_change_and_sign():
    s = pd.Series([4.0, 4.0, 3.75, 3.75, 3.75],
                  index=pd.to_datetime(["2025-12-08", "2025-12-09", "2025-12-11", "2026-01-02", "2026-09-14"]))
    assert ws.last_move(s) == {"date": "2025-12-11", "bps": -25}
    assert ws.last_move(pd.Series([2.0, 2.0], index=pd.to_datetime(["2026-01-01", "2026-01-02"]))) is None


def test_fomc_range_parses_hike_hold_and_ignores_dissent():
    hike = ("The Committee decided to raise the target range for the federal funds rate by 1/4 percentage "
            "point to 3-3/4 to 4 percent, in support of the Federal Reserve's dual mandate.")
    hold = ("The Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 "
            "percent. Voting against were A and B, who preferred to raise the target range for the federal "
            "funds rate by 1/4 percentage point at this meeting.")
    assert ws.parse_fomc_range(hike) == (3.75, 4.0)
    assert ws.parse_fomc_range(hold) == (3.5, 3.75)
    assert ws.parse_fomc_range("to lower the target range for the federal funds rate to 0 to 1/4 percent") == (0.0, 0.25)


def test_fomc_decision_fills_the_gap_before_fred_posts_it():
    """16 Sep 2026: the Fed hiked at 18:00 UTC; a run at 03:20 UTC on the 17th still read 3.50-3.75 from FRED."""
    idx = pd.to_datetime(["2026-09-15", "2026-09-16"])
    lo, hi = pd.Series([3.5, 3.5], index=idx), pd.Series([3.75, 3.75], index=idx)
    decision = {"date": "2026-09-16", "lo": 3.75, "hi": 4.0}
    lo2, hi2 = ws.apply_fomc_decision(lo, hi, decision)
    assert hi2.index[-1] == pd.Timestamp("2026-09-17") and hi2.iloc[-1] == 4.0 and lo2.iloc[-1] == 3.75
    assert ws.last_move(hi2) == {"date": "2026-09-17", "bps": 25}
    # Once FRED has posted the new range the statement adds nothing ...
    lo3, hi3 = ws.apply_fomc_decision(lo2, hi2, decision)
    assert len(hi3) == len(hi2)
    # ... and a FRED value that contradicts the statement is an error, not a silent pick.
    try:
        ws.apply_fomc_decision(lo2, hi2, {"date": "2026-09-16", "lo": 3.5, "hi": 3.75})
    except ValueError:
        pass
    else:
        raise AssertionError("conflicting FRED and FOMC ranges were accepted")


def _raises(fn, *args) -> bool:
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def test_decision_shows_before_it_takes_effect_and_is_checked_later():
    """BoJ, 18 Sep 2026: 1.00% -> 1.25% from 24 Sep; BIS then ended on 15 Sep."""
    bis = pd.Series([1.0, 1.0], index=pd.to_datetime(["2026-09-14", "2026-09-15"]))
    s = ws.apply_decision(bis, 1.25, date(2026, 9, 24), "BoJ statement")
    assert s.index[-1] == pd.Timestamp("2026-09-24") and s.iloc[-1] == 1.25
    assert ws.last_move(s) == {"date": "2026-09-24", "bps": 25}
    # BIS catching up with the same rate adds nothing; a different rate is an error.
    caught_up = pd.concat([bis, pd.Series([1.0, 1.25], index=pd.to_datetime(["2026-09-23", "2026-09-24"]))])
    assert len(ws.apply_decision(caught_up, 1.25, date(2026, 9, 24), "BoJ statement")) == len(caught_up)
    assert _raises(ws.apply_decision, caught_up, 1.5, date(2026, 9, 24), "BoJ statement")


BOJ_CHANGE = ("1 September 18, 2026 Bank of Japan Change in the Guideline for Money Market Operations 1. At the "
              "Monetary Policy Meeting held today, the Policy Board of the Bank of Japan decided, by a 7-2 majority "
              "vote, to set the following guideline for money market operations for the intermeeting period: [Note] "
              "The Bank will encourage the uncollateralized overnight call rate to remain at around 1.25 percent.1 "
              "... 1 The new guideline for money market operations will be effective from September 24, 2026.")
BOJ_HOLD = ("July 31, 2026 Bank of Japan Statement on Monetary Policy At the Monetary Policy Meeting held today, "
            "... [Note] The Bank will encourage the uncollateralized overnight call rate to remain at around 1.0 "
            "percent. [Note] Voting for the action: ... He proposed that the Bank set the guideline for money market "
            "operations as follows: the Bank would encourage the uncollateralized overnight call rate to remain at "
            "around 1.25 percent. The proposal was defeated by a majority vote.")


def test_boj_statement_reads_the_decision_not_the_dissent():
    assert ws.parse_boj_statement(BOJ_CHANGE) == {"date": date(2026, 9, 18), "rate": 1.25,
                                                  "effective": date(2026, 9, 24)}
    # A hold names no effective day, and the dissent's 1.25% is not the decision.
    assert ws.parse_boj_statement(BOJ_HOLD) == {"date": date(2026, 7, 31), "rate": 1.0,
                                                "effective": date(2026, 7, 31)}
    assert _raises(ws.parse_boj_statement, "The Bank decided to buy more bonds.")


def test_boj_decisions_page_skips_the_reference_copy():
    page = """<table><tr><th>Date</th><th>Title</th></tr>
      <tr><td>Sept. 18, 2026</td><td><a href="/en/mopo/mpmdeci/mpr_2026/mpr260918a.pdf">Amendment to "Principal
        Terms"</a></td></tr>
      <tr><td>Sept. 18, 2026</td><td><a href="/en/mopo/mpmdeci/mpr_2026/k260918b.pdf">(Reference) Change in the
        Guideline for Money Market Operations (September 2026 MPM)</a></td></tr>
      <tr><td>Sept. 18, 2026</td><td><a href="/en/mopo/mpmdeci/mpr_2026/k260918a.pdf">Change in the Guideline for
        Money Market Operations [PDF 204KB]</a></td></tr>
      <tr><td>July 31, 2026</td><td><a href="/en/mopo/mpmdeci/mpr_2026/k260731a.pdf">Statement on Monetary
        Policy [PDF 160KB]</a></td></tr></table>"""
    assert ws.parse_boj_decisions(page) == ["/en/mopo/mpmdeci/mpr_2026/k260918a.pdf",
                                            "/en/mopo/mpmdeci/mpr_2026/k260731a.pdf"]


def test_pboc_notice_both_layouts_and_days_without_a_7_day_operation():
    new = ("2026年9月23日中国人民银行以固定利率、数量招标方式开展了80亿元7天期逆回购操作，全额满足了一级交易商需求。"
           "具体情况如下： 逆回购操作情况 期限 操作利率 投标量 中标量 7天 1<span>.</span>40% 80亿元 80亿元")
    old = "开展了1820亿元逆回购操作。具体情况如下： 逆回购操作情况 期限 操作量 操作利率 7天 1820亿元 1.50%"
    fourteen_day = "开展了2780亿元逆回购操作。具体情况如下： 逆回购操作情况 期限 操作量 操作利率 14天 2780亿元 1.65%"
    none = "人民银行不开展逆回购操作。"
    assert ws.parse_pboc_omo(ws.html_text(new)) == 1.40      # figure split across spans
    assert ws.parse_pboc_omo(old) == 1.50
    assert ws.parse_pboc_omo(fourteen_day) is None
    assert ws.parse_pboc_omo(none) is None


def _pboc_site(notices: list[tuple[str, str]]):
    """A fake PBoC list page (one page, newest first) and its notices: [(date, body)]."""
    base = "/zhengcehuobisi/125207/125213/125431/125475/"
    items = "".join(
        f'<font class="newslist_style"><a href="{base}{i}/index.html" onclick="void(0)" target="_blank" '
        f'title="公开市场业务交易公告 [2026]第{100 - i}号" istitle="true">公开市场业务交易公告</a></font>'
        f'<span class="hui12">{d}</span>' for i, (d, _) in enumerate(notices))
    pages = {ws.PBOC_OMO_LIST + "index.html": items}
    pages.update({f"https://www.pbc.gov.cn{base}{i}/index.html": body for i, (_, body) in enumerate(notices)})

    class Page:
        def __init__(self, text):
            self.content = text.encode("utf-8")

    return lambda url, *a, **k: Page(pages[url])


def _omo(rate: str | None) -> str:
    return "不开展逆回购操作" if rate is None else f"期限 操作利率 投标量 中标量 7天 {rate}% 80亿元 80亿元"


def test_pboc_new_move_is_dated_by_the_first_operation_at_the_new_rate():
    ledger = pd.Series([1.5, 1.4], index=pd.to_datetime(["2024-09-29", "2025-05-08"]))
    site = _pboc_site([("2026-09-25", _omo("1.30")), ("2026-09-24", _omo(None)), ("2026-09-23", _omo("1.30")),
                       ("2026-09-22", _omo("1.40")), ("2026-09-21", _omo("1.40"))])
    original = ws._get
    ws._get = site
    try:
        latest, moves = ws.fetch_pboc_reverse_repo(ledger)
    finally:
        ws._get = original
    assert (latest["date"], latest["rate"]) == ("2026-09-25", 1.3)
    assert [(m["date"], m["rate"]) for m in moves] == [("2026-09-23", 1.3)]


def test_pboc_unchanged_rate_reads_one_notice_and_records_nothing():
    ledger = pd.Series([1.4], index=pd.to_datetime(["2025-05-08"]))
    site = _pboc_site([("2026-09-23", _omo("1.40")), ("2026-09-22", _omo("9.99"))])  # the second is never read
    original = ws._get
    ws._get = site
    try:
        latest, moves = ws.fetch_pboc_reverse_repo(ledger)
    finally:
        ws._get = original
    assert latest["rate"] == 1.4 and moves == []


def test_committed_pboc_ledger_is_valid():
    s = ws.read_pboc_ledger()
    assert s.index[0] == pd.Timestamp("2019-10-25") and s.iloc[-1] == 1.4


def test_ecb_table_reads_blank_years_footnotes_and_minus_signs():
    page = """<table><tr><th>Date (with effect from)</th><th>Deposit facility</th></tr>
      <tr><td>2026</td><td>16 Sep.</td><td>2.50</td><td>2.65</td><td>-</td><td>2.90</td></tr>
      <tr><td>2024</td><td>18 Sep. 5</td><td>3.50</td><td>3.65</td><td>-</td><td>3.90</td></tr>
      <tr><td>2014</td><td>10 Sep.</td><td>\u22120.20</td><td>0.05</td><td>-</td><td>0.30</td></tr>
      <tr><td></td><td>11 Jun.</td><td>\u22120.10</td><td>0.15</td><td>-</td><td>0.40</td></tr></table>"""
    s = ws.parse_ecb_key_rates(page)
    assert s[pd.Timestamp("2014-06-11")] == -0.10 and s[pd.Timestamp("2024-09-18")] == 3.50
    assert s.index[-1] == pd.Timestamp("2026-09-16") and s.iloc[-1] == 2.50


def test_boe_bank_rate_table():
    page = ("<table><tr><th>Date Changed</th><th>Rate</th></tr><tr><td> 18 Dec 25 </td><td>3.75</td></tr>"
            "<tr><td>07 Aug 25</td><td>4.00</td></tr></table>")
    s = ws.parse_boe_bank_rate(page)
    assert s.index[-1] == pd.Timestamp("2025-12-18") and s.iloc[-1] == 3.75 and len(s) == 2


def test_extend_series_carries_moves_not_levels():
    """BIS records the middle of the Fed's range (3.625); the page uses its top (4.00)."""
    bis = pd.Series([3.625], index=pd.to_datetime(["2026-09-15"]))
    fed_top = pd.Series([3.75, 3.75, 4.0], index=pd.to_datetime(["2026-09-14", "2026-09-15", "2026-09-17"]))
    s = ws.extend_series(bis, fed_top)
    assert s.index[-1] == pd.Timestamp("2026-09-17") and abs(s.iloc[-1] - 3.875) < 1e-9
    assert ws.extend_series(bis, None) is bis


def test_rate_moves_by_month_counts_banks_once_and_skips_unreported_months():
    days = pd.to_datetime(["2026-07-31", "2026-08-10", "2026-08-20", "2026-08-31", "2026-09-10"])
    series = {
        "A": pd.Series([1.0, 1.25, 1.5, 1.5, 1.5], index=days),    # hiked twice in August: one bank
        "B": pd.Series([2.0, 2.0, 1.75, 1.75, 1.75], index=days),  # cut in August
        "C": pd.Series([3.0, 3.0], index=days[:2]),                # data stop in August
    }
    m = ws.rate_moves_by_month(series, "2026-08")
    assert m.loc[pd.Period("2026-08", "M")].tolist() == [1, 1, 3]
    assert m.loc[pd.Period("2026-09", "M")].tolist() == [0, 0, 2]    # C has not reported September


def test_rates_fingerprint_ignores_observation_dates():
    snap = {"central_banks": [{"id": "boe", "status": "ok", "display": "3.75", "as_of": "2026-09-21",
                               "last_move": {"date": "2025-12-18", "bps": -25}}],
            "scoreboard": [{"country": "UK", "cells": {"policy_rate": {"value": 3.75, "period": "2026-09-21",
                                                                       "status": "ok"}}}],
            "rate_cycle": {"hikes": [5], "cuts": [0]}}
    later = ws.apply_rate_update(snap, {
        "central_banks": [{**snap["central_banks"][0], "as_of": "2026-09-23"}],
        "policy_cells": {"UK": {"value": 3.75, "period": "2026-09-23", "status": "ok"}},
        "rate_cycle": snap["rate_cycle"]}, "2026-09-23 21:04")
    assert ws.rates_fingerprint(later) == ws.rates_fingerprint(snap)
    moved = ws.apply_rate_update(snap, {
        "central_banks": [{**snap["central_banks"][0], "display": "3.50",
                           "last_move": {"date": "2026-11-05", "bps": -25}}],
        "policy_cells": {"UK": {"value": 3.5, "period": "2026-11-05", "status": "ok"}},
        "rate_cycle": snap["rate_cycle"]}, "2026-11-05 21:04")
    assert ws.rates_fingerprint(moved) != ws.rates_fingerprint(snap)


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
