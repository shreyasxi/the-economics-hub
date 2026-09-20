"""
Promoter holdings from NSE's shareholding filings (India tab).

The traps these guard against, all met while building the series:

  * a company that changes hands files again mid-quarter, and that interim
    filing would put two different share registers in the same quarter;
  * a revised filing arrives later for a quarter already reported, and the
    revision is the one that counts;
  * NSE's master list carries only the newest quarter, so a hole in the
    archive can be filled by a rebuild and by nothing else, and must be
    refused rather than drawn through;
  * a company enters the archive when it lists, so a median taken across
    every filer moves when the market lists companies rather than when
    promoters sell. Anything drawn across time uses a constant panel.

No network: the parsers are exercised on payloads shaped like NSE's.

Run:  python tests/test_shareholding.py   (or: python -m pytest tests/test_shareholding.py -q)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.nse_shareholding import (CONTROL, PROMOTER_CEILING, check_fresh, check_holdings, constant_panel,
                                   load_history, missing_quarters, parse_filings)


def _filing(symbol, date_text, promoter, submitted=None, public=None):
    return {"symbol": symbol, "name": f"{symbol} Limited", "date": date_text,
            "submissionDate": submitted or date_text,
            "pr_and_prgrp": promoter, "public_val": 100 - promoter if public is None else public}


# ── reading the filings ──────────────────────────────────────────────────────

def test_interim_filings_are_left_out():
    """A filing dated mid-quarter is a change of hands, not the quarter's register."""
    frame = parse_filings([_filing("ACME", "30-JUN-2026", 55.0), _filing("ACME", "08-DEC-2021", 62.0),
                           _filing("ACME", "31-DEC-2021", 61.5)], "test")
    assert sorted(frame["quarter"].dt.strftime("%b %Y")) == ["Dec 2021", "Jun 2026"]


def test_a_revised_filing_wins():
    frame = parse_filings([_filing("ACME", "30-JUN-2026", 55.0, submitted="18-JUL-2026"),
                           _filing("ACME", "30-JUN-2026", 54.2, submitted="02-AUG-2026")], "test")
    assert len(frame) == 1
    assert frame.iloc[0]["promoter"] == 54.2


def test_percentages_are_read_as_they_are_filed():
    frame = parse_filings([_filing("ACME", "30-JUN-2026", 74.99)], "test")
    assert frame.iloc[0]["promoter"] == 74.99
    assert frame.iloc[0]["symbol"] == "ACME"


def test_a_payload_without_the_holding_column_is_refused():
    broken = [{"symbol": "ACME", "date": "30-JUN-2026", "public_val": 45.0}]
    try:
        parse_filings(broken, "master list")
        assert False, "a payload with no promoter column should be refused"
    except ValueError as e:
        assert "master list" in str(e)


def test_an_empty_payload_is_refused():
    try:
        parse_filings([], "master list")
        assert False, "an empty payload should be refused"
    except ValueError as e:
        assert "no filings" in str(e)


def test_filings_with_no_quarter_end_date_are_refused():
    try:
        parse_filings([_filing("ACME", "08-DEC-2021", 55.0)], "master list")
        assert False, "a payload with no quarter-end filing should be refused"
    except ValueError as e:
        assert "quarter end" in str(e)


# ── holdings that do not add up ──────────────────────────────────────────────

def test_holdings_outside_nought_to_a_hundred_are_refused():
    frame = pd.DataFrame([{"symbol": "ACME", "quarter": pd.Timestamp("2026-06-30"), "promoter": 155.0, "public": 45.0}])
    try:
        check_holdings(frame, "master list")
        assert False, "a holding above 100% should be refused"
    except ValueError as e:
        assert "0–100%" in str(e)


def test_a_register_that_does_not_add_up_is_refused():
    """If promoter and public stopped being the whole register, every figure here changes meaning."""
    rows = [{"symbol": f"C{i}", "quarter": pd.Timestamp("2026-06-30"), "promoter": 60.0, "public": 10.0}
            for i in range(50)]
    try:
        check_holdings(pd.DataFrame(rows), "master list")
        assert False, "a register that does not add to 100% should be refused"
    except ValueError as e:
        assert "add to 100%" in str(e)


def test_employee_trusts_leave_the_register_just_short():
    """A fraction of a per cent sits in employee trusts, reported separately: that is not an error."""
    rows = [{"symbol": f"C{i}", "quarter": pd.Timestamp("2026-06-30"), "promoter": 60.0, "public": 39.7}
            for i in range(50)]
    check_holdings(pd.DataFrame(rows), "master list")


# ── the archive ──────────────────────────────────────────────────────────────

def test_a_hole_in_the_archive_is_spotted():
    archived = [pd.Timestamp("2025-09-30"), pd.Timestamp("2025-12-31"), pd.Timestamp("2026-06-30")]
    missing = missing_quarters(archived, pd.Timestamp("2026-06-30"))
    assert [f"{q:%b %Y}" for q in missing] == ["Mar 2026"]


def test_an_archive_one_quarter_behind_the_new_filings_is_spotted():
    archived = pd.date_range("2025-09-30", "2026-03-31", freq="QE")
    assert missing_quarters(archived, pd.Timestamp("2026-09-30")) == [pd.Timestamp("2026-06-30")]


def test_a_complete_archive_has_no_holes():
    archived = pd.date_range("2021-09-30", "2026-06-30", freq="QE")
    assert missing_quarters(archived, pd.Timestamp("2026-06-30")) == []


def test_stale_filings_are_refused():
    try:
        check_fresh(pd.Timestamp("2025-06-30"), date(2026, 9, 20))
        assert False, "filings a year old should be refused"
    except ValueError as e:
        assert "stopped updating" in str(e)


def test_filings_from_the_quarter_just_gone_are_accepted():
    check_fresh(pd.Timestamp("2026-06-30"), date(2026, 9, 20))


# ── comparing quarters like for like ─────────────────────────────────────────

def _panel_frame(n_both=700, n_new=200):
    rows = []
    for i in range(n_both):
        rows += [{"symbol": f"OLD{i}", "quarter": pd.Timestamp("2021-09-30"), "promoter": 60.0},
                 {"symbol": f"OLD{i}", "quarter": pd.Timestamp("2026-06-30"), "promoter": 57.0}]
    for i in range(n_new):                       # listed after the first quarter
        rows.append({"symbol": f"NEW{i}", "quarter": pd.Timestamp("2026-06-30"), "promoter": 72.0})
    return pd.DataFrame(rows)


def test_companies_listed_later_are_left_out_of_a_comparison():
    frame = _panel_frame()
    panel = constant_panel(frame, [pd.Timestamp("2021-09-30"), pd.Timestamp("2026-06-30")])
    assert panel.shape[1] == 700, "only the companies filing in both quarters belong in the panel"
    assert panel.loc[pd.Timestamp("2026-06-30")].median() == 57.0, (
        "the newer listings, which come with higher stakes, must not lift the median")


def test_a_panel_too_thin_to_stand_on_is_refused():
    frame = _panel_frame(n_both=20, n_new=900)
    try:
        constant_panel(frame, [pd.Timestamp("2021-09-30"), pd.Timestamp("2026-06-30")])
        assert False, "a panel of 20 companies should be refused"
    except ValueError as e:
        assert "filed in every quarter" in str(e)


# ── the rules the chart draws ────────────────────────────────────────────────

def test_the_marked_rules_are_sebi_s():
    assert CONTROL == 50.0
    assert PROMOTER_CEILING == 75.0, "a promoter may hold at most 75%: the public must hold 25%"


# ── the archive that ships with the repo ─────────────────────────────────────

def test_the_published_archive_is_whole_and_current():
    history = load_history()
    latest = history["quarter"].max()
    assert missing_quarters(history["quarter"], latest) == [], "the archived quarters must be unbroken"
    filers = history[history["quarter"] == latest]["symbol"].nunique()
    assert filers >= 1500, f"only {filers} companies in the newest archived quarter"
    assert (latest.date() - date.today()).days < 400
    check_holdings(history, "the published archive")


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
