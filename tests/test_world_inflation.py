"""Guard monthly CPI semantics, classification selection and breadth counts."""
from datetime import date
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.fetchers.world_inflation import DIMENSIONS, STEM, generate, parse_source, prepare

TODAY = date(2026, 10, 9)
CODES = ["USA", "CHN", "IND", "GBR", "JPN", "CAN", "AUT", "BEL", "BRA", "CHE",
         "DEU", "ESP", "FRA", "ITA", "MEX", "KOR", "NOR", "POL", "PRT", "TUR"]


def fixture():
    # Test-only values; no synthetic observation is written to production stores.
    rows = []
    for code in CODES + ["EA", "OECD"]:
        for month in pd.period_range("2025-01", "2026-09", freq="M"):
            for category in ("_T", "_TXCP01_NRG"):
                rows.append(dict(DIMENSIONS, REF_AREA=code, **{"Reference area": code},
                                 EXPENDITURE=category, TIME_PERIOD=str(month), OBS_VALUE=2.,
                                 OBS_STATUS="A", UNIT_MULT=0))
    return pd.DataFrame(rows)


def test_parser_rejects_ambiguous_series_units_and_future_periods():
    original = fixture()
    for column, value in [("FREQ", "Q"), ("UNIT_MEASURE", "IX"), ("UNIT_MULT", 2),
                          ("TIME_PERIOD", "2026-11"), ("OBS_VALUE", float("inf"))]:
        invalid = original.copy()
        invalid.loc[0, column] = value
        with pytest.raises(ValueError):
            parse_source(invalid.to_csv(index=False), "1999", TODAY)
    with pytest.raises(ValueError, match="duplicate"):
        parse_source(pd.concat([original, original.iloc[:1]]).to_csv(index=False), "1999", TODAY)


def test_new_classification_wins_overlap_and_history_join_is_explicit():
    old = fixture()
    new = old[old.TIME_PERIOD >= "2026-01"].copy()
    new.loc[new.REF_AREA == "AUT", "OBS_VALUE"] = 3.
    report = prepare({"1999": old.to_csv(index=False), "2018": new.to_csv(index=False)}, TODAY)
    austria = next(c for c in report["countries"] if c["code"] == "AUT")
    rates = {r["month"]: r for r in austria["series"]["headline"]}
    assert rates["2025-12"]["value"] == 2
    assert rates["2026-01"]["value"] == 3
    assert rates["2026-01"]["classification"] == "2018"
    assert austria["transitions"]["headline"] == "2026-01"
    assert report["breadth"]["total_countries"] == 20  # Neither OECD nor euro area counted.


def test_breadth_uses_common_month_and_exact_three_month_comparison():
    frame = fixture()
    # September has insufficient coverage, so use August. A missing May
    # must not cause April or June to substitute for the matched comparison.
    frame = frame[~((frame.TIME_PERIOD == "2026-09") & ~frame.REF_AREA.isin(CODES[:5]))]
    frame = frame[~((frame.REF_AREA == "USA") & (frame.TIME_PERIOD == "2026-05"))]
    frame.loc[(frame.REF_AREA == "CHN") & (frame.TIME_PERIOD == "2026-08"), "OBS_VALUE"] = 1.
    report = prepare({"1999": frame.to_csv(index=False)}, TODAY)
    b = report["breadth"]
    assert b["month"] == "2026-08"
    assert b["comparison_month"] == "2026-05"
    assert b["reporting"] == 20 and b["matched"] == 19
    assert b["easing"] == 1 and b["little_changed"] == 18
    usa = next(c for c in report["countries"] if c["code"] == "USA")
    assert "2026-05" not in {r["month"] for r in usa["series"]["headline"]}


def test_stale_country_and_core_are_disclosed_without_stale_fallback():
    frame = fixture()
    frame = frame[~((frame.REF_AREA == "CAN") & (frame.TIME_PERIOD > "2026-01"))]
    frame = frame[~((frame.REF_AREA == "JPN") & (frame.EXPENDITURE == "_TXCP01_NRG")
                    & (frame.TIME_PERIOD > "2026-01"))]
    report = prepare({"1999": frame.to_csv(index=False)}, TODAY)
    assert "CAN" in {c["code"] for c in report["excluded"]}
    japan = next(c for c in report["countries"] if c["code"] == "JPN")
    assert not japan["series"]["core"] and "2026-01" in japan["core_note"]


def test_failed_refresh_removes_previous_same_edition_output(tmp_path):
    for extension in ("png", "svg", "json"):
        (tmp_path / (STEM + "." + extension)).write_text("old output")
    with patch("data.fetchers.world_inflation.fetch_sources", side_effect=ValueError("source failed")):
        with pytest.raises(ValueError, match="source failed"):
            generate(tmp_path)
    assert not list(tmp_path.iterdir())


def test_native_panel_breaks_lines_at_missing_months_and_exposes_official_rates():
    from charts.world_charts.world_inflation_dashboard import panel, panel_notes
    frame = fixture()
    frame = frame[~((frame.REF_AREA == "USA") & (frame.TIME_PERIOD == "2026-05"))]
    report = prepare({"1999": frame.to_csv(index=False)}, TODAY)
    usa = next(c for c in report["countries"] if c["code"] == "USA")
    spec = panel(usa, report["start_month"], report["end_month"]).to_dict()
    rows = spec["data"]["values"]
    headline = [r for r in rows if r["series"] == "Headline CPI"]
    april = next(r for r in headline if r["date"].startswith("2026-04"))
    june = next(r for r in headline if r["date"].startswith("2026-06"))
    assert april["segment"] != june["segment"]
    assert not any(r["date"].startswith("2026-05") for r in rows)
    assert all(r["classification"] == "1999" and r["rate"] == 2 for r in rows)
    assert spec["layer"][0]["encoding"]["tooltip"][2]["field"] == "rate"
    usa["series"]["core"] = []
    assert panel_notes(usa) == "Core not available"


def test_region_filters_cover_membership_dates_unknown_areas_and_sorting():
    from copy import deepcopy
    from charts.world_charts.world_inflation_dashboard import region_options, select_countries

    report = prepare({"1999": fixture().to_csv(index=False)}, TODAY)
    countries = report["countries"]
    original = deepcopy(countries)
    asia = select_countries(countries, "Asia", "Country A–Z", report["as_of"])
    assert [c["code"] for c in asia] == ["CHN", "IND", "JPN", "KOR", "TUR"]
    euro = select_countries(countries, "Euro area", as_of=report["as_of"])
    assert {c["code"] for c in euro} == {"EA", "AUT", "BEL", "DEU", "ESP", "FRA", "ITA", "PRT"}
    assert {c["code"] for c in euro} < {c["code"] for c in select_countries(countries, "Europe")}
    assert select_countries(countries) == countries
    assert countries == original

    extra = [{"code": code, "label": code, "series": {"headline": [{"value": value}]}}
             for code, value in [("BGR", 3), ("USA", 1), ("XYZ", 2)]]
    assert "Other regions" in region_options(extra, "2026-10-09")
    assert "Asia" not in region_options(extra, "2026-10-09")
    assert [c["code"] for c in select_countries(extra, "Other regions")] == ["XYZ"]
    assert not select_countries(extra, "Euro area", as_of="2025-12-31")
    assert [c["code"] for c in select_countries(extra, "Euro area", as_of="2026-01-01")] == ["BGR"]
    assert [c["code"] for c in select_countries(extra, sort="Inflation: highest first")] == ["BGR", "XYZ", "USA"]
    assert [c["code"] for c in select_countries(extra, sort="Inflation: lowest first")] == ["USA", "XYZ", "BGR"]


def test_region_dropdown_rerenders_only_selected_panels():
    import ast
    import json
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[1]
    source = (root / "app.py").read_text()
    render = next(n for n in ast.parse(source).body
                  if isinstance(n, ast.FunctionDef) and n.name == "_render_global_inflation")
    report = prepare({"1999": fixture().to_csv(index=False)}, TODAY)
    script = (
        "import streamlit as st\nimport json, html\nfrom pathlib import Path\n"
        "def _chart_anchor(path): pass\ndef get_insight(path): return None\n"
        + ast.get_source_segment(source, render)
        + f"\nreport = json.loads({json.dumps(json.dumps(report))})\n"
        + "_render_global_inflation(Path('/missing/chart.png'), {'inflation_breadth': report})\n"
    )
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert "Showing 21 panels · All regions" in [c.value for c in app.caption]
    app.selectbox(key="global-inflation-region").select("Asia").run()
    assert not app.exception
    assert "Showing 5 panels · Asia" in [c.value for c in app.caption]
    titles = [m.value for m in app.markdown if "margin-top:22px" in m.value]
    assert len(titles) == 5
    assert not any("United States" in title for title in titles)
    assert any("Global ·" in m.value for m in app.markdown)
    app.selectbox(key="global-inflation-region").select("All regions").run()
    assert not app.exception
    assert "Showing 21 panels · All regions" in [c.value for c in app.caption]


def test_render_preserves_missing_month_as_line_break(tmp_path):
    from charts.world_charts.world_inflation import draw
    frame = fixture()
    frame = frame[~((frame.REF_AREA == "USA") & (frame.TIME_PERIOD == "2026-05"))]
    report = prepare({"1999": frame.to_csv(index=False)}, TODAY)
    with patch("charts.world_charts.world_inflation.EconStyle.save_chart") as save:
        draw(report, tmp_path / "test.png")
        fig = save.call_args[0][0]
        line = fig.axes[0].lines[0]
        index = list(pd.period_range(report["start_month"], report["end_month"], freq="M")).index(pd.Period("2026-05"))
        assert pd.isna(line.get_ydata()[index])
        assert len(fig.axes) == 24
        vector = (tmp_path / "test.svg").read_text()
        assert "<svg" in vector and "<path" in vector
        assert "<image" not in vector  # No embedded raster to blur on zoom.
        import matplotlib.pyplot as plt
        plt.close(fig)
