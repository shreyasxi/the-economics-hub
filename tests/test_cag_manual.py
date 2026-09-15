"""
Checks on the manual CAG rows (data/cag_manual_accounts.csv) that stand in for
the monthly accounts workbook while CGA does not publish it. Each test writes a
small CSV to a temporary folder; the real data files are never modified.

Run:  python tests/test_cag_manual.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate_india import CagManualError, DEFAULT_CAG, load_cag_tables

HEADER = ("fy,month,corporation_tax,income_tax,securities_transaction_tax,cgst,igst,utgst,customs,"
          "union_excise,devolution_to_states,revenue_expenditure,interest_payments,major_subsidies,"
          "capital_expenditure,fiscal_deficit,gdp,source\n")
# Test inputs only: shaped like a year-to-date row, not real figures.
ROW = "{fy},{month},900000,1050000,55000,960000,-5000,7000,262000,300000,1390000,{rev},1150000,420000,{capex},{fd},,test\n"


def _tables(body: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manual.csv"
        path.write_text(HEADER + body, encoding="utf-8")
        return load_cag_tables(DEFAULT_CAG, path)


def _fails(body: str, needle: str) -> None:
    try:
        _tables(body)
    except CagManualError as e:
        assert needle in str(e), f"expected {needle!r} in: {e}"
        return
    raise AssertionError(f"accepted a row that should fail ({needle})")


def test_empty_file_leaves_workbook_unchanged():
    actual, _, _ = _tables("")
    assert actual["Month"].iloc[-1] == "Feb-26"


def test_new_month_is_appended_in_order():
    actual, _, _ = _tables(ROW.format(fy="2025-26", month="Mar-26", rev=3400000, capex=1050000, fd=1500000))
    assert list(actual["Month"].tail(2)) == ["Feb-26", "Mar-26"]


def test_lakh_crore_typo_is_refused():
    _fails(ROW.format(fy="2025-26", month="Mar-26", rev=3400000, capex=10.5, fd=1500000), "capital_expenditure")


def test_month_outside_financial_year_is_refused():
    _fails(ROW.format(fy="2025-26", month="Mar-25", rev=3400000, capex=1050000, fd=1500000), "does not fall")


def test_falling_year_to_date_spending_is_refused():
    _fails(ROW.format(fy="2025-26", month="Mar-26", rev=3000000, capex=1050000, fd=1500000), "falls year-to-date")


def test_new_year_without_budget_estimate_is_refused():
    _fails(ROW.format(fy="2026-27", month="Apr-26", rev=300000, capex=90000, fd=150000), "no BE row")


def test_workbook_row_wins_over_manual_duplicate():
    actual, _, _ = _tables(ROW.format(fy="2025-26", month="Feb-26", rev=3115270, capex=999999, fd=1300000))
    feb = actual[(actual["FY"] == "2025-26") & (actual["Month"] == "Feb-26")]
    assert len(feb) == 1 and feb["Capital Expenditure"].iloc[0] == 929322


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
