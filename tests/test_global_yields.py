"""Yield semantics, missing periods, source failures and section placement."""
from datetime import date
from pathlib import Path
import ast
import json
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.global_yields import COUNTRIES
from data.fetchers.global_yields import parse_oecd, prepare, validate_daily, parse_norges, collect, national_fetcher, parse_rba
from charts.world_charts.global_yields import panel, panel_rows, select_countries, history_percentile, ytd_change

TODAY = date(2026, 10, 10)


def monthly_csv():
    return pd.DataFrame([{"REF_AREA": c, "FREQ": "M", "MEASURE": "IRLT", "UNIT_MEASURE": "PA",
                          "UNIT_MULT": 0, "ACTIVITY": "_Z", "ADJUSTMENT": "_Z", "TRANSFORMATION": "_Z",
                          "TIME_HORIZ": "_Z", "METHODOLOGY": "N", "TIME_PERIOD": m, "OBS_VALUE": 3.}
                         for c in COUNTRIES
                         for m in ["2026-06", "2026-07", "2026-09"]])


def national():
    return {c: {"yield_type": "10-year benchmark", "url": "https://example.test",
                "retrieved_at": "2026-10-09T12:00:00Z", "observations": [
                    {"date": "2026-09-22", "value": 3.1}, {"date": "2026-10-08", "value": 3.2},
                    {"date": "2026-10-09", "value": 3.3}]} for c in ["NOR", "USA"]}


def test_monthly_units_dimensions_duplicates_and_future_are_rejected():
    frame = monthly_csv()
    for column, value in [("FREQ", "D"), ("MEASURE", "IR3TIB"), ("UNIT_MULT", 2),
                          ("TIME_PERIOD", "2026-13"), ("TIME_PERIOD", "2026-11"), ("OBS_VALUE", float("inf"))]:
        bad = frame.copy()
        bad.loc[0, column] = value
        with pytest.raises(ValueError):
            parse_oecd(bad.to_csv(index=False), TODAY)
    with pytest.raises(ValueError, match="Duplicate"):
        parse_oecd(pd.concat([frame, frame.iloc[:1]]).to_csv(index=False), TODAY)


def test_all_twenty_countries_india_and_weekly_actual_dates():
    report = prepare(parse_oecd(monthly_csv().to_csv(index=False), TODAY), national(), TODAY)
    assert len(report["countries"]) == 20
    assert {"NOR", "POL"} <= set(COUNTRIES)
    assert not {"SGP", "MYS"} & set(COUNTRIES)
    india = next(c for c in report["countries"] if c["code"] == "IND")
    assert india["latest_frequency"] == "OECD monthly average"
    assert india["latest"]["date"] == "2026-09-01"
    usa = report["countries"][0]
    assert [r["date"] for r in usa["weekly"]] == ["2026-09-22", "2026-10-09"]
    assert usa["latest"]["value"] == 3.3
    assert len(select_countries(report, "Asia")) == 3
    assert len(select_countries(report)) == 20


def test_one_series_uses_national_data_over_monthly_backfill_and_preserves_gaps():
    report = prepare(parse_oecd(monthly_csv().to_csv(index=False), TODAY), national(), TODAY)
    country = report["countries"][0]
    rows = panel_rows(country)
    assert [r["date"] for r in rows] == ["2026-06-01", "2026-07-01", "2026-09-22", "2026-10-09"]
    assert rows[1]["segment"] != rows[2]["segment"]  # Missing August.
    assert rows[2]["segment"] != rows[3]["segment"]  # Missing weekly observations.
    assert rows[2]["source"] == "National source"
    spec = panel(country, report["start_date"], report["as_of"]).to_dict()
    assert all("color" not in layer["encoding"] for layer in spec["layer"])
    assert spec["layer"][0]["mark"]["color"] == spec["layer"][1]["mark"]["color"]


def test_retained_national_observation_stays_preferred_when_newer_than_oecd():
    records = national()
    records["USA"]["observations"] = [{"date": "2026-09-22", "value": 4.}]
    records["USA"]["error"] = "National refresh failed"
    report = prepare(parse_oecd(monthly_csv().to_csv(index=False), TODAY), records, TODAY)
    usa = report["countries"][0]
    assert usa["latest"]["date"] == "2026-09-22"
    assert usa["latest_frequency"].startswith("National") and usa["stale"]


def test_sorting_and_historical_rank_use_equal_month_weights():
    report = prepare(parse_oecd(monthly_csv().to_csv(index=False), TODAY), national(), TODAY)
    usa = report["countries"][0]
    usa["monthly"] = [{"date": f"2025-{m:02}-01", "value": float(m)} for m in range(1, 13)]
    usa["weekly"] = [{"date": "2026-10-09", "value": 13.}]
    usa["latest"] = usa["weekly"][-1]
    assert history_percentile(usa) == pytest.approx(100 * 12.5 / 13)
    usa["weekly"].insert(0, {"date": "2026-10-02", "value": 40.})
    assert history_percentile(usa) == pytest.approx(100 * 12.5 / 13)
    assert history_percentile(report["countries"][1]) is None
    assert select_countries(report)[0]["code"] == "USA"
    assert select_countries(report, sort="Highest versus own history")[0]["code"] == "USA"
    assert select_countries(report, sort="Lowest yield")[-1]["code"] == "USA"


def test_retained_national_date_stays_stale_and_monthly_fallback_is_explicit():
    records = national()
    for item in records.values():
        item["observations"] = [{"date": "2026-06-01", "value": 4.}]
        item["error"] = "National refresh failed"
    report = prepare(parse_oecd(monthly_csv().to_csv(index=False), TODAY), records, TODAY)
    usa = report["countries"][0]
    assert usa["latest_frequency"] == "OECD monthly average" and not usa["stale"]
    norway = next(c for c in report["countries"] if c["code"] == "NOR")
    assert norway["latest_frequency"].startswith("OECD")
    assert norway["national"]["retrieved_at"] == "2026-10-09T12:00:00Z"


def test_daily_observations_reject_duplicate_dates_nonfinite_and_future():
    for rows in [[{"date": "2026-10-11", "value": 3}], [{"date": "2026-10-09", "value": float("nan")}],
                 [{"date": "2026-10-09", "value": 3}] * 2]:
        with pytest.raises(ValueError):
            validate_daily(rows, TODAY)


def test_us_holidays_remain_missing_and_zero_yields_are_retained():
    from types import SimpleNamespace
    def get(url, params):
        return SimpleNamespace(text="observation_date,DGS10\n2026-10-07,0\n2026-10-08,.\n2026-10-09,4.95\n")
    result = national_fetcher("USA", TODAY, get)
    assert result["observations"] == [{"date": "2026-10-07", "value": 0.}, {"date": "2026-10-09", "value": 4.95}]


def test_failed_collection_retains_retrieval_time_and_reports_errors(tmp_path):
    previous = {"monthly": parse_oecd(monthly_csv().to_csv(index=False), TODAY), "national": national(),
                "monthly_retrieved_at": "2026-10-01T12:00:00Z"}
    path = tmp_path / "store.json"
    path.write_text(json.dumps(previous))
    with patch("data.fetchers.global_yields.requests.get", side_effect=RuntimeError("offline")), \
         patch("data.fetchers.global_yields.national_fetcher", side_effect=RuntimeError("offline")), \
         patch("data.fetchers.global_yields.DATA_CACHE", tmp_path):
        report, store = collect(TODAY, path)
    assert len(report["countries"]) == 20
    assert report["monthly_retrieved_at"] == previous["monthly_retrieved_at"]
    assert store["national"]["NOR"]["retrieved_at"] == "2026-10-09T12:00:00Z"
    assert len(report["issues"]) == 13


def test_world_section_follows_us_equity_valuations():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "page_world")
    body = ast.get_source_segment(source, node)
    assert body.index('_section("US Equity Valuations"') < body.index('_render_global_yields(chart_path, snapshot)')
    assert body.index('_render_global_yields(chart_path, snapshot)') < body.index('_section("Country and Supply Chain Risks"')


def test_dashboard_country_filter_and_sorting_render_without_frequency_labels():
    from streamlit.testing.v1 import AppTest
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_render_global_yields")
    report = prepare(parse_oecd(monthly_csv().to_csv(index=False), TODAY), national(), TODAY)
    report["countries"][0]["monthly"].insert(0, {"date": "2025-12-01", "value": 3.1})
    report["countries"][1]["monthly"].insert(0, {"date": "2025-12-01", "value": 4.})
    script = "import streamlit as st\nimport json,html\nfrom pathlib import Path\n"
    script += "def _chart_anchor(path): pass\ndef get_insight(path): return None\n"
    script += ast.get_source_segment(source, node)
    script += f"\nreport=json.loads({json.dumps(json.dumps(report))})\n"
    script += "_render_global_yields(Path('chart.png'), {'global_yields':report})\n"
    app = AppTest.from_string(script).run()
    assert not app.exception
    app.selectbox(key="global-yields-region").select("Asia").run()
    assert not app.exception
    assert any("Showing 3 countries" in c.value for c in app.caption)
    app.selectbox(key="global-yields-sort").select("Highest versus own history").run()
    assert not app.exception
    assert any("Showing 3 countries" in c.value for c in app.caption)
    assert any("Sep 2026" == c.value for c in app.caption)
    assert all("OECD monthly average" not in c.value and "National weekly observation" not in c.value for c in app.caption)
    app.selectbox(key="global-yields-sort").select("Largest YTD rise (bp)").run()
    assert not app.exception
    assert any("YTD baseline unavailable" in m.value for m in app.markdown)
    assert all("bp YTD" not in c.value for c in app.caption)
    app.selectbox(key="global-yields-region").select("All regions").run()
    assert not app.exception
    for label, yield_text, change_text in [("United States", "3.30%", "+20 bp YTD"),
                                           ("Canada", "3.00%", "-100 bp YTD")]:
        header = next(m.value for m in app.markdown if f'<span>{label}</span>' in m.value)
        assert header.index(yield_text) < header.index(change_text)
        assert "flex-direction:column;align-items:flex-end" in header
    app.selectbox(key="global-yields-sort").select("Highest yield").run()
    assert all("bp YTD" not in m.value and "YTD baseline unavailable" not in m.value for m in app.markdown)
    assert len(app.selectbox) == 2


def test_rba_uses_nominal_ten_year_yield_not_indexed_bond():
    text = ("F2 CAPITAL MARKET YIELDS\n"
            "Title,Australian Government 10 year bond,Australian Government Indexed Bond\n"
            "Frequency,Daily,Daily\nUnits,Per cent per annum,Per cent per annum\n"
            "Series ID,FCMYGBAG10D,FCMYGBAGID\n08-Oct-2026,4.9,2.1\n09-Oct-2026,,2.2\n")
    assert parse_rba(text) == [{"date": "2026-10-08", "value": 4.9}]
    with pytest.raises(ValueError):
        parse_rba(text.replace("Per cent per annum", "Index"))


def test_ytd_sort_uses_prior_year_baseline_in_basis_points_and_leaves_missing_last():
    report = prepare(parse_oecd(monthly_csv().to_csv(index=False), TODAY), national(), TODAY)
    usa, canada = report["countries"][:2]
    usa["monthly"].insert(0, {"date": "2025-12-01", "value": 3.1})
    canada["monthly"].insert(0, {"date": "2025-12-01", "value": 4.})
    assert ytd_change(usa, report["as_of"]) == pytest.approx(20.)
    assert ytd_change(canada, report["as_of"]) == pytest.approx(-100.)
    ranked = select_countries(report, sort="Largest YTD rise (bp)")
    assert [c["code"] for c in ranked[:2]] == ["USA", "CAN"]
    assert ytd_change(ranked[-1], report["as_of"]) is None
    canada["latest"] = {"date": "2025-12-01", "value": 4.}
    assert ytd_change(canada, report["as_of"]) is None


def test_india_uses_newer_dated_dbie_or_oecd_observation():
    monthly = parse_oecd(monthly_csv().to_csv(index=False), TODAY)
    records = national()
    records["IND"] = {"yield_type": "FBIL 10-year G-Sec", "source": "RBI DBIE", "observations": [
        {"date": "2026-09-25", "value": 7.14}]}
    report = prepare(monthly, records, TODAY)
    india = next(c for c in report["countries"] if c["code"] == "IND")
    assert india["latest"] == {"date": "2026-09-25", "value": 7.14}
    monthly["IND"].append({"date": "2026-10-01", "value": 7.2})
    report = prepare(monthly, records, TODAY)
    india = next(c for c in report["countries"] if c["code"] == "IND")
    assert india["latest"]["value"] == 7.2 and india["latest_frequency"].startswith("OECD")
    assert panel_rows(india)[-1]["yield"] == 7.2


def test_india_dbie_adapter_reads_named_fbil_column_and_retains_workbook_provenance(tmp_path):
    path = tmp_path / "DBIE.xlsx"
    frame = pd.DataFrame({"Period": [pd.Timestamp("2026-09-25")],
                          "10-Year G-Sec Yield (FBIL) (%)": [7.14], "91-day Treasury bill": [5.2]})
    frame.to_excel(path, sheet_name="Weekly", startrow=3, index=False)
    with patch("data.paths.DBIE_WORKBOOK", path):
        result = national_fetcher("IND", TODAY, lambda *args: pytest.fail("DBIE should use the local workbook"))
    assert result["observations"] == [{"date": "2026-09-25", "value": 7.14}]
    assert result["collection_mode"] == "Manually refreshed DBIE workbook"
    assert len(result["sha256"]) == 64


def test_norway_selects_daily_ten_year_government_bond_not_other_instruments():
    text = ("FREQ;TENOR;INSTRUMENT_TYPE;TIME_PERIOD;OBS_VALUE\n"
            "B;10Y;GBON;2026-10-08;4.641\nB;3Y;GBON;2026-10-08;4.84\n"
            "B;12M;TBIL;2026-10-08;4.818\nM;10Y;GBON;2026-09;4.5\n")
    assert parse_norges(text) == [{"date": "2026-10-08", "value": 4.641}]
    with pytest.raises(ValueError):
        parse_norges(text.replace("B;10Y;GBON", "B;10Y;TBIL"))
    with pytest.raises(ValueError):
        parse_norges(text.replace("TENOR", "OTHER"))


def test_removed_countries_do_not_survive_in_retained_store(tmp_path):
    previous = {"monthly": parse_oecd(monthly_csv().to_csv(index=False), TODAY), "national": national(),
                "monthly_retrieved_at": "2026-10-01T12:00:00Z"}
    previous["national"]["SGP"] = {"observations": [{"date": "2026-10-08", "value": 2.5}]}
    path = tmp_path / "store.json"
    path.write_text(json.dumps(previous))
    with patch("data.fetchers.global_yields.requests.get", side_effect=RuntimeError("offline")), \
         patch("data.fetchers.global_yields.national_fetcher", side_effect=RuntimeError("offline")), \
         patch("data.fetchers.global_yields.DATA_CACHE", tmp_path):
        report, store = collect(TODAY, path)
    assert "SGP" not in store["national"]
    assert len(report["countries"]) == 20
