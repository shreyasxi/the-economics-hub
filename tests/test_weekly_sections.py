"""
Weekly Markets section regression tests.

Sections used to match keywords in filenames, and the first match won: Copper/Gold
and Gold/SPX landed in Commodities ("gold"), real yields in Fixed Income ("yield"),
and Inflation Signals was left with one chart. Sections are now explicit lists in
config/weekly_settings.py; these tests keep the list and the charts in step.

Run:  python tests/test_weekly_sections.py      (or: python -m pytest tests/test_weekly_sections.py -q)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from charts.loader import chart_key, get_charts, group_charts
from config.weekly_settings import SUMMARY_CHART, WEEKLY_SECTIONS


def test_chart_key_strips_numeric_prefix():
    assert chart_key("10b_india_sector_rotation.png") == "india_sector_rotation"
    assert chart_key("09_vix_trend.png") == "vix_trend"
    assert chart_key("22c_em_vix.png") == "em_vix"


def test_no_chart_is_listed_twice():
    keys = [k for _, ks in WEEKLY_SECTIONS for k in ks]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"listed in more than one section: {dupes}"


def test_group_keeps_config_order_and_reports_unlisted():
    charts = [Path(n) for n in ("01_b.png", "02_a.png", "03_new_chart.png")]
    grouped, unlisted = group_charts(charts, [("One", ["a", "b"]), ("Empty", ["missing"])])
    assert grouped == [("One", [Path("02_a.png"), Path("01_b.png")])]
    assert unlisted == [Path("03_new_chart.png")]


def test_latest_weekly_charts_match_the_config():
    """Fails when the generator adds, renames or drops a chart without updating config/weekly_settings.py."""
    charts, _ = get_charts("weekly")
    if not charts:
        return   # nothing generated on this machine
    on_disk = {chart_key(c.name) for c in charts} - {SUMMARY_CHART}
    listed = {k for _, ks in WEEKLY_SECTIONS for k in ks}
    assert not on_disk - listed, f"charts with no section (add to WEEKLY_SECTIONS): {sorted(on_disk - listed)}"
    assert not listed - on_disk, f"listed but not generated (renamed or removed?): {sorted(listed - on_disk)}"


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
