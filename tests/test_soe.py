"""
RBI Bulletin — State of the Economy: parser regression tests.

Every case here came from a real edition:

  * The article table was found by searching for "transmission" anywhere on the
    page, which matched the page table wrapping the whole article and read the
    article's own words as column headers.
  * Header rows hold as many cells as the table has columns, so a row filter
    that counted cells tried to read "Repo Rate" as a number (Feb-Jun 2025).
  * Some editions put the cycle's name on one row and its dates on the next
    (Jul, Oct and Nov 2025), and print month names with footnote marks
    ("Jul* 2025", Aug-Dec 2025).
  * The "overall interest rate effect" column was added during 2025, so earlier
    editions have eight columns, not nine.
  * Two editions restate the same data month with different figures (Sep and
    Oct 2025 both report August 2025); the newer edition's figure wins.

No network: the fixtures in tests/fixtures/soe are saved article tables.

Run:  python tests/test_soe.py      (or: python -m pytest tests/test_soe.py -q)
"""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.rbi_soe import (
    Edition, SoeError, parse_briefing, parse_conclusion, parse_summary,
    parse_transmission, published_date,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "soe"


def fixture(month: str) -> str:
    return (FIXTURES / f"{month}.html").read_text(encoding="utf-8")


def edition(month: str) -> Edition:
    return Edition(month=month, article_id="0",
                   url=f"https://rbi.org.in/scripts/BS_ViewBulletin.aspx?Id=0#{month}")


# ── The briefing ───────────────────────────────────────────────────────────

def test_summary_is_rbis_own_opening_paragraph():
    summary = parse_summary(fixture("2026-08"))
    assert summary.startswith("The global economy is confronting a fragile geopolitical environment")
    assert summary.endswith("Foreign capital inflows rebounded, reinforcing the external sector.")
    assert len(summary.split()) == 81


def test_summary_is_quoted_not_rewritten():
    """Every sentence shown must appear in the article itself."""
    page = fixture("2026-08")
    for sentence in parse_summary(page).split(". "):
        assert sentence.strip(". ")[:60] in " ".join(page.split())


def test_published_date_and_conclusion():
    page = fixture("2026-08")
    assert published_date(page).isoformat() == "2026-08-25"
    conclusion = parse_conclusion(page)
    assert len(conclusion) == 1
    assert conclusion[0].startswith("The global economic outlook continues to be shaped by")


def test_an_edition_filed_under_the_wrong_month_is_refused():
    try:
        parse_briefing(fixture("2026-08"), edition("2026-07"))
    except SoeError as exc:
        assert "disagree" in str(exc)
    else:
        raise AssertionError("an article dated August was accepted as the July edition")


def test_a_page_that_is_not_the_article_is_refused():
    try:
        parse_summary("<html><body><p>Some other RBI page</p></body></html>")
    except SoeError as exc:
        assert "not a State of the Economy article" in str(exc)
    else:
        raise AssertionError("a page without the article was read as one")


def test_a_changed_layout_is_refused_rather_than_guessed():
    """
    A page whose summary paragraph has gone is a layout change, not a licence to
    quote the next paragraph, which belongs to a section and would read as the
    month's summary.
    """
    page = fixture("2026-08")
    page = page.replace(parse_summary(page), "Summary to follow.", 1)
    try:
        parse_summary(page)
    except SoeError as exc:
        assert "layout has changed" in str(exc)
    else:
        raise AssertionError("a truncated opening paragraph was published as the summary")


# ── The transmission table ─────────────────────────────────────────────────

def test_current_layout_reads_both_cycles_and_the_monthly_block():
    table = parse_transmission(fixture("2026-08"))
    easing = [c for c in table["cycles"] if c["cycle_type"] == "easing"][0]
    assert (easing["cycle_start"], easing["cycle_end"]) == ("2025-02", "2026-06")
    assert easing["repo_bps"] == -125
    assert easing["wadtdr_fresh_bps"] == -63        # deposits gave part of the cut back
    assert easing["walr_fresh_bps"] == -80
    assert easing["overall_bps"] == -91

    tightening = [c for c in table["cycles"] if c["cycle_type"] == "tightening"][0]
    assert (tightening["cycle_start"], tightening["cycle_end"]) == ("2022-05", "2025-01")
    assert tightening["repo_bps"] == 250

    assert [m["month"] for m in table["monthly"]] == ["2026-05", "2026-06"]
    assert table["monthly"][-1]["wadtdr_fresh_bps"] == 16


def test_cycle_name_on_its_own_row_and_months_with_footnote_marks():
    """July 2025: "Easing Phase" then "Feb 2025 to Jun* 2025", and no overall column."""
    table = parse_transmission(fixture("2025-07"))
    easing = [c for c in table["cycles"] if c["cycle_type"] == "easing"][0]
    assert (easing["cycle_start"], easing["cycle_end"]) == ("2025-02", "2025-06")
    assert easing["repo_bps"] == -100
    assert easing["walr_fresh_bps"] == -26
    assert "overall_bps" not in easing           # the column did not exist yet

    tightening = [c for c in table["cycles"] if c["cycle_type"] == "tightening"][0]
    assert tightening["repo_bps"] == 250         # printed "+250"


def test_an_edition_without_the_table_is_not_an_error():
    assert parse_transmission(fixture("2026-02")) is None


def test_header_rows_are_never_read_as_figures():
    """The column header row has one cell per column; it must not become a rate change."""
    for month in ("2026-08", "2025-07"):
        for cycle in parse_transmission(fixture(month))["cycles"]:
            assert all(isinstance(v, int) for k, v in cycle.items() if k.endswith("_bps"))
            assert abs(cycle["repo_bps"]) <= 500


def test_a_renamed_column_stops_the_run():
    page = fixture("2026-08").replace("WALR - Fresh Rupee Loans", "Fresh advances", 1)
    try:
        parse_transmission(page)
    except SoeError as exc:
        assert "columns have changed" in str(exc)
    else:
        raise AssertionError("a renamed column was silently mapped to the wrong field")


def test_a_row_with_the_wrong_number_of_figures_stops_the_run():
    cell = '<td align="right" valign="top">-63</td>'
    page = fixture("2026-08").replace(cell, cell + '<td align="right">-7</td>', 1)
    try:
        parse_transmission(page)
    except SoeError as exc:
        assert "layout has changed" in str(exc)
    else:
        raise AssertionError("a row with an extra figure was read anyway")


def test_implausible_units_stop_the_run():
    page = fixture("2026-08").replace('<td align="right" valign="top">-125</td>',
                                      '<td align="right" valign="top">-12500</td>', 1)
    try:
        parse_transmission(page)
    except SoeError as exc:
        assert "plausible" in str(exc) or "units" in str(exc)
    else:
        raise AssertionError("a figure far too large for basis points was accepted")


# ── The history the chart reads ────────────────────────────────────────────

HISTORY_HEADER = ("month,published,cycle_type,cycle_start,cycle_end,repo_bps,wadtdr_fresh_bps,"
                  "wadtdr_outstanding_bps,eblr_bps,mclr_bps,walr_fresh_bps,walr_outstanding_bps,"
                  "overall_bps,url\n")


def _history(rows: str) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "rbi_transmission.csv"
    tmp.write_text(HISTORY_HEADER + rows, encoding="utf-8")
    return tmp


def test_chart_keeps_the_newest_edition_of_a_restated_month():
    """Sep and Oct 2025 both report August 2025; RBI's later figure is the one drawn."""
    from generate_india import load_transmission

    df = load_transmission(_history(
        "2025-09,2025-09-23,easing,2025-02,2025-08,-100,-101,-22,-100,-40,-53,-71,-55,u\n"
        "2025-10,2025-10-21,easing,2025-02,2025-08,-100,-106,-22,-100,-40,-58,-71,-55,u\n"
        "2026-08,2026-08-25,easing,2025-02,2026-06,-125,-63,-51,-125,-50,-80,-79,-91,u\n"
    ))
    assert len(df) == 2                                   # one row per data month
    august = df[df["cycle_end"] == "2025-08"].iloc[0]
    assert august["wadtdr_fresh_bps"] == -106             # the October edition's figure


def test_chart_draws_only_the_current_cycle():
    from generate_india import load_transmission

    df = load_transmission(_history(
        "2026-08,2026-08-25,tightening,2022-05,2025-01,250,259,206,250,175,182,191,115,u\n"
        "2026-07,2026-07-22,easing,2025-02,2026-05,-125,-78,-52,-125,-35,-82,-85,-90,u\n"
        "2026-08,2026-08-25,easing,2025-02,2026-06,-125,-63,-51,-125,-50,-80,-79,-91,u\n"
    ))
    assert set(df["cycle_start"]) == {"2025-02"}
    assert list(df["cycle_end"]) == ["2026-05", "2026-06"]


def test_a_blank_figure_in_the_history_stops_the_run():
    from generate_india import TransmissionDataError, load_transmission

    try:
        load_transmission(_history(
            "2026-08,2026-08-25,easing,2025-02,2026-06,-125,,-51,-125,-50,-80,-79,-91,u\n"))
    except TransmissionDataError as exc:
        assert "Fresh deposits" in str(exc)
    else:
        raise AssertionError("a blank figure was drawn as if it were data")


def test_no_history_file_means_no_chart_not_a_crash():
    from generate_india import load_transmission

    assert load_transmission(Path(tempfile.mkdtemp()) / "missing.csv") is None


def test_the_published_history_matches_the_published_editions():
    """The tracked CSV must hold what the parser reads, not hand-edited figures."""
    from config.soe_settings import TRANSMISSION_CSV

    if not TRANSMISSION_CSV.exists():
        return
    with TRANSMISSION_CSV.open(newline="", encoding="utf-8") as fh:
        rows = {(r["month"], r["cycle_type"]): r for r in csv.DictReader(fh)}
    for month in ("2026-08", "2025-07"):
        if not (FIXTURES / f"{month}.html").exists():
            continue
        for cycle in parse_transmission(fixture(month))["cycles"]:
            row = rows.get((month, cycle["cycle_type"]))
            if row is None:
                continue
            assert int(row["repo_bps"]) == cycle["repo_bps"], f"{month} {cycle['cycle_type']} repo"
            assert int(row["walr_fresh_bps"]) == cycle["walr_fresh_bps"], f"{month} fresh loans"


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
