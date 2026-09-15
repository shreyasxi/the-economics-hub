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

from generate_india import CagManualError, DEFAULT_CAG, load_cag_financing, load_cag_tables

HEADER = ("fy,month,revenue_expenditure,interest_payments,major_subsidies,"
          "capital_expenditure,fiscal_deficit,gdp,source\n")
# Test inputs only: shaped like a year-to-date row, not real figures.
ROW = "{fy},{month},{rev},1150000,420000,{capex},{fd},,test\n"

FIN_HEADER = ("fy,month,revenue_expenditure,capital_expenditure,fiscal_deficit,gdp,fin_external,fin_domestic,"
              "fin_market_borrowings,fin_small_savings_securities,fin_state_provident_funds,fin_special_deposits,"
              "fin_nssf,fin_others,fin_cash_balance,fin_surplus_cash,fin_wma,source\n")
# Test inputs only. With mb=200000 and wma=0 the domestic rows add up to the
# domestic total 300000, and external 5000 + domestic equals the deficit 305000.
FIN_ROW = "2026-27,Apr-26,400000,150000,{fd},,5000,300000,{mb},40000,1000,0,60000,50000,5000,-56000,{wma},test\n"


def _tables(body: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manual.csv"
        path.write_text(HEADER + body, encoding="utf-8")
        return load_cag_tables(DEFAULT_CAG, path)


def _financing(body: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manual.csv"
        path.write_text(FIN_HEADER + body, encoding="utf-8")
        return load_cag_financing(path)


def _fails(body: str, needle: str, load=_tables) -> None:
    try:
        load(body)
    except CagManualError as e:
        assert needle in str(e), f"expected {needle!r} in: {e}"
        return
    raise AssertionError(f"accepted a row that should fail ({needle})")


def test_workbook_alone_ends_in_february():
    actual, _, _ = _tables("")
    assert actual["Month"].iloc[-1] == "Feb-26"


def test_missing_required_figure_is_refused():
    _fails("2025-26,Mar-26,3400000,,,1050000,,,test\n", "fiscal_deficit is missing")


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


def test_financing_that_adds_up_is_accepted():
    fin = _financing(FIN_ROW.format(fd=305000, mb=200000, wma=0))
    assert len(fin) == 1 and fin["fin_market_borrowings"].iloc[0] == 200000


def test_blank_row_below_cash_balance_is_allowed():
    fin = _financing(FIN_ROW.format(fd=305000, mb=200000, wma=""))
    assert fin["fin_wma"].isna().iloc[0]


def test_financing_that_misses_the_deficit_is_refused():
    _fails(FIN_ROW.format(fd=315000, mb=200000, wma=0), "not the fiscal deficit", load=_financing)


def test_mistyped_domestic_row_is_refused():
    _fails(FIN_ROW.format(fd=305000, mb=20000, wma=0), "domestic financing rows add up", load=_financing)


def test_incomplete_financing_is_refused():
    _fails(FIN_ROW.format(fd=305000, mb="", wma=0), "financing is incomplete", load=_financing)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
