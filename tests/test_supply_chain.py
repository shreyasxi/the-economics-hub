"""Protect official monthly GSCPI semantics and ten-year chart gap handling."""
import io
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from data.fetchers.supply_chain import STEM, generate, parse_workbook
from charts.world_charts.supply_chain import ten_year_series

TODAY = date(2026, 10, 9)


def frame():
    months = pd.period_range("1998-01", "2026-09", freq="M")
    return pd.DataFrame({"Date": [m.end_time.strftime("%d-%b-%Y") for m in months],
                         "GSCPI": [0.123456789] * len(months)})


def workbook(data):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        data.to_excel(writer, sheet_name="GSCPI Monthly Data", index=False)
    return output.getvalue()


def test_full_precision_rates_and_invalid_source_observations():
    original = frame()
    report = parse_workbook(workbook(original), TODAY)
    assert report["rows"][-1] == {"month": "2026-09", "value": .123456789}
    for column, value in [("Date", "31-Oct-2026"), ("GSCPI", float("inf")),
                          ("GSCPI", float("nan")), ("Date", "not a date")]:
        bad = original.copy()
        bad.loc[0, column] = value
        with pytest.raises(ValueError):
            parse_workbook(workbook(bad), TODAY)
    with pytest.raises(ValueError, match="duplicate"):
        parse_workbook(workbook(pd.concat([original, original.iloc[:1]])), TODAY)
    with pytest.raises(ValueError, match="stale"):
        parse_workbook(workbook(original.iloc[:-5]), TODAY)


def test_latest_vintage_history_is_not_rebased_and_gaps_are_not_connected():
    data = frame()
    data = data[data.Date != "31-May-2026"]
    data.loc[data.Date == "30-Jun-2026", "GSCPI"] = -1.2
    report = parse_workbook(workbook(data), TODAY)
    series = ten_year_series(report)
    assert len(series) == 120
    assert series.index[0] == pd.Timestamp("2016-10-01")
    assert series.index[-1] == pd.Timestamp("2026-09-01")
    assert series.loc["2026-06-01"] == -1.2
    assert pd.isna(series.loc["2026-05-01"])
    assert series.loc["2026-04-01"] == .123456789



def test_failed_refresh_removes_same_edition_chart_and_audit(tmp_path):
    for extension in ("png", "json"):
        (tmp_path / (STEM + "." + extension)).write_text("old")
    with patch("data.processors.world_snapshot._get", side_effect=ValueError("source failed")):
        with pytest.raises(ValueError, match="source failed"):
            generate(tmp_path)
    assert not list(tmp_path.iterdir())
