"""
US equity valuation data and the OECD cycle phase (World tab).

  * Shiller's ie_data.xls: the CAPE column must not be confused with TR CAPE,
    October is written 1990.1, excess CAPE yield is a fraction, and the latest
    month is dropped while his notes say it is priced off one day's close.
  * Damodaran's ERPbymonth.xlsx stores the odd month as text ("4.06%").

No network: parsers are exercised with frames shaped like the real files.

Run:  python tests/test_valuations.py      (or: python -m pytest tests/test_valuations.py -q)
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.valuations import (_fraction, check_fresh, country_risk_links, parse_country_erps, parse_damodaran_erp,
                             parse_regional_erps, parse_shiller, parse_update_date, pick_year_ago, shiller_file_url)
from generate_macro import cli_phase


def _shiller_raw(dates, cape, tr_cape, ecy, note="Sept price is Sept 1st close"):
    width = 17
    header = [[np.nan] * width for _ in range(8)]
    for row, (c12, c14, c16) in enumerate([
        (None, None, None), ("Cyclically", "Cyclically ", None), ("Adjusted", "Adjusted", None),
        ("Price", "Total Return Price", None), ("Earnings", "Earnings", None), ("Ratio", "Ratio", "Excess"),
        ("P/E10 or", "TR P/E10 or", "CAPE"), ("CAPE", "TR CAPE", "Yield"),
    ]):
        for col, text in ((12, c12), (14, c14), (16, c16)):
            if text:
                header[row][col] = text
    header[7][0] = "Date"
    body = []
    for d, c, t, e in zip(dates, cape, tr_cape, ecy):
        row = [np.nan] * width
        row[0], row[12], row[14], row[16] = d, c, t, e
        body.append(row)
    notes = [np.nan] * width
    notes[1] = note
    return pd.DataFrame(header + body + [notes])


def test_shiller_parses_months_columns_and_units():
    raw = _shiller_raw([1990.09, 1990.1, 1990.11, 2026.07, 2026.08, 2026.09],
                       [15, 16, 17, 40, 41, 40.5], [99, 99, 99, 99, 99, 99],
                       [0.05, 0.051, 0.052, 0.012, 0.011, 0.010])
    out = parse_shiller(raw, today=date(2026, 9, 16))
    assert pd.Timestamp("1990-10-01") in out.index                  # 1990.1 is October, not January
    assert out.loc["1990-10-01", "cape"] == 16                       # CAPE, not TR CAPE
    assert abs(out.loc["1990-10-01", "excess_cape_yield"] - 5.1) < 1e-9
    assert out.index[-1] == pd.Timestamp("2026-08-01")


def test_shiller_drops_single_day_priced_month_even_after_it_ends():
    raw = _shiller_raw([2026.07, 2026.08, 2026.09], [40, 41, 40.5], [9, 9, 9], [0.012, 0.011, 0.010])
    assert parse_shiller(raw, today=date(2026, 10, 5)).index[-1] == pd.Timestamp("2026-08-01")
    kept = parse_shiller(_shiller_raw([2026.07, 2026.08, 2026.09], [40, 41, 40.5], [9, 9, 9],
                                      [0.012, 0.011, 0.010], note="Monthly average prices"), today=date(2026, 10, 5))
    assert kept.index[-1] == pd.Timestamp("2026-09-01")


def test_shiller_layout_change_is_refused():
    raw = _shiller_raw([2026.07], [40], [9], [0.012])
    raw.iloc[6, 12] = "P/E ratio"                                     # CAPE column renamed
    try:
        parse_shiller(raw, today=date(2026, 9, 16))
    except ValueError:
        return
    raise AssertionError("a renamed CAPE column was accepted")


def test_shiller_link_found_on_page():
    page = '<a href="//img1.wsimg.com/blobby/go/abc/downloads/123/ie_data.xls?ver=17">Download</a>'
    assert shiller_file_url(page) == "https://img1.wsimg.com/blobby/go/abc/downloads/123/ie_data.xls?ver=17"
    try:
        shiller_file_url("<html>no data link</html>")
    except ValueError:
        return
    raise AssertionError("a page without the data link was accepted")


def test_damodaran_reads_text_percent_cells():
    sheet = pd.DataFrame({
        "Start of month": [datetime(2024, 8, 1), datetime(2024, 9, 1), "Notes below"],
        "ERP (T12m)": [0.041, "4.06%", None],
        "T.Bond Rate": [0.039, 0.0378, None],
    })
    out = parse_damodaran_erp(sheet)
    assert list(out.index) == [pd.Timestamp("2024-08-01"), pd.Timestamp("2024-09-01")]
    assert abs(out.loc["2024-09-01", "erp"] - 4.06) < 1e-9
    assert abs(_fraction("6,36%") - 0.0636) < 1e-12


def test_damodaran_missing_column_is_refused():
    try:
        parse_damodaran_erp(pd.DataFrame({"Start of month": [datetime(2024, 8, 1)], "ERP": [0.04]}))
    except ValueError:
        return
    raise AssertionError("a sheet without ERP (T12m) was accepted")


def test_stale_valuation_file_fails():
    check_fresh(pd.Timestamp("2026-08-01"), 70, "ERP", today=date(2026, 9, 16))
    try:
        check_fresh(pd.Timestamp("2026-05-01"), 70, "ERP", today=date(2026, 9, 16))
    except ValueError:
        return
    raise AssertionError("a file four months old passed the freshness check")


# ── Damodaran country risk premiums ─────────────────────────────────────────

def _country_sheet(rows, frontier=True):
    width = 11
    blank = [np.nan] * width
    top = [["Country and Equity Risk Premiums"] + [np.nan] * 10,
           ["Date of update:", datetime(2026, 7, 1)] + [np.nan] * 9]
    header = ["Country", "Africa", "Moody's rating", "Rating-based Default Spread", "Total Equity Risk Premium",
              "Country Risk Premium", "Sovereign CDS, net of Swiss CDS", "Total Equity Risk Premium2",
              "Country Risk Premium3", np.nan, np.nan]
    body = [[c, region, rating, spread, erp, crp, cds, erp_cds, crp_cds, np.nan, np.nan]
            for c, region, rating, spread, erp, crp, cds, erp_cds, crp_cds in rows]
    below = []
    if frontier:   # unrated countries scored on PRS sit under their own header: never part of the rated table
        below = [["Frontier Markets (no rating)"] + [np.nan] * 10,
                 ["Country", "PRS Composite Risk Score", "ERP", "CRP"] + [np.nan] * 7,
                 ["Russia", 62.5, 0.079, 0.024] + [np.nan] * 7]
    return pd.DataFrame(top + [blank] + [header] + body + below)


def _rated_rows(n=100):
    rows = [("Germany", "Western Europe", "Aaa", 0.0, 0.042, 0.0, 0.0006, 0.0429, 0.0009),
            ("India", "Asia", "Baa3", 0.0175, 0.0692, 0.0272, 0.0072, 0.0532, 0.0112),
            ("Argentina", "Central and South America", "Caa1", 0.0597, 0.1348, 0.0928, np.nan, np.nan, np.nan)]
    rows += [(f"Country {i}", "Africa", "B2", 0.04, 0.10, 0.058, np.nan, np.nan, np.nan) for i in range(n - len(rows))]
    return rows


def test_country_table_stops_before_unrated_countries():
    table, mature = parse_country_erps(_country_sheet(_rated_rows()))
    assert "Russia" not in table.index and len(table) == 100
    assert abs(mature - 4.2) < 1e-9
    assert abs(table.loc["India", "crp"] - 2.72) < 1e-9 and abs(table.loc["India", "crp_cds"] - 1.12) < 1e-9
    assert np.isnan(table.loc["Argentina", "crp_cds"])                   # no CDS market: blank, never filled


def test_country_table_with_inconsistent_base_is_refused():
    rows = _rated_rows()
    rows[1] = ("India", "Asia", "Baa3", 0.0175, 0.0792, 0.0272, 0.0072, 0.0532, 0.0112)   # ERP − CRP ≠ 4.2%
    try:
        parse_country_erps(_country_sheet(rows))
    except ValueError:
        return
    raise AssertionError("a table whose premiums do not share one base was accepted")


def test_country_update_date_and_regions():
    assert parse_update_date(_country_sheet(_rated_rows())) == pd.Timestamp("2026-07-01")
    sheet = pd.DataFrame([["Angola", 100.0], [np.nan, np.nan], ["Region", "Weighted Average: ERP"],
                          ["Africa", 0.1158], ["Asia", 0.0561], ["North America", 0.044], ["Western Europe", 0.0513],
                          ["Middle East", 0.0613], ["Global", 0.055], [np.nan, np.nan], ["Japan", 0.0507]])
    regions = parse_regional_erps(sheet)
    assert list(regions.index)[-1] == "Global" and "Japan" not in regions.index
    assert abs(regions["Asia"] - 5.61) < 1e-9


def test_year_ago_update_is_about_twelve_months_back():
    dates = [pd.Timestamp(d) for d in ("2026-07-01", "2026-04-01", "2026-01-01", "2025-07-01")]
    assert pick_year_ago(dates, pd.Timestamp("2026-07-01")) == pd.Timestamp("2025-07-01")
    try:
        pick_year_ago(dates[:3], pd.Timestamp("2026-07-01"))
    except ValueError:
        return
    raise AssertionError("an update six months old was used as 'a year earlier'")


def test_country_risk_links_skip_old_layouts():
    page = ('<a href="https://x.edu/pc/datasets/ctryprem.xlsx">now</a> <a href="https://x.edu/pc/datasets/ctrypremJuly25.xlsx">'
            '</a> <a href="https://x.edu/pc/datasets/ctrypremJune13.xls"></a>')
    links = country_risk_links(page, today=date(2026, 9, 16))
    assert links == ["https://x.edu/pc/datasets/ctryprem.xlsx", "https://x.edu/pc/datasets/ctrypremJuly25.xlsx"]


def test_cli_phase_uses_level_and_last_month():
    s = lambda a, b: pd.Series([a, b])
    assert cli_phase(s(100.5, 100.6)) == "Expansion"
    assert cli_phase(s(100.6, 100.5)) == "Downturn"
    assert cli_phase(s(99.5, 99.4)) == "Slowdown"
    assert cli_phase(s(99.4, 99.5)) == "Recovery"


def test_cli_phase_over_three_months_ignores_a_one_month_wobble():
    rising = pd.Series([100.1, 100.5, 100.9, 100.8])     # up over three months, down on the last
    assert cli_phase(rising, months=3) == "Expansion"
    assert cli_phase(rising) == "Downturn"               # the one-month reading the OECD itself uses
    assert cli_phase(pd.Series([100.9, 100.5]), months=3) == "Downturn"   # too short: falls back to what it has


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
