"""FX bars use matched universes and calendar return anchors, without filling gaps."""
from datetime import date

import pandas as pd
import pytest

from charts.weekly_fx import fx_returns, generate_fx_charts
from config.weekly_settings import WEEKLY_FX


def histories():
    # The annual date is a Thursday, and extra rows prevent positional shortcuts.
    return {name: pd.Series([99., 100., 110., 115., 120., 126., 999.],
                           index=pd.to_datetime(["2025-10-02", "2025-10-09", "2026-04-01", "2026-09-25", "2026-10-02",
                                                 "2026-10-09", "2026-10-12"]))
            for name in WEEKLY_FX}


def test_returns_use_completed_week_and_calendar_year_for_all_ten_rates():
    end, rows = fx_returns(histories(), date(2026, 10, 12))
    assert end == date(2026, 10, 9)
    assert len(rows) == 10
    for name, weekly, annual in rows:
        assert weekly == pytest.approx(5.)
        assert annual == pytest.approx(26.)
    assert fx_returns(histories(), date(2026, 10, 9))[0] == date(2026, 10, 2)


def test_holiday_uses_observed_close_before_anchor_and_preserves_quote_direction():
    data = histories()
    data["EUR/USD"] = pd.Series([2., 1.8, 1.6],
                                index=pd.to_datetime(["2025-10-08", "2026-10-01", "2026-10-08"]))
    _, rows = fx_returns(data, date(2026, 10, 12))
    eur = next(r for r in rows if r[0] == "EUR/USD")
    assert eur[1] == pytest.approx((1.6 / 1.8 - 1) * 100)
    assert eur[2] == pytest.approx(-20.)


def test_missing_annual_baseline_is_rejected_instead_of_shortening_ttm():
    data = histories()
    data["USD/CHF"] = data["USD/CHF"].loc["2026-04-01":]
    with pytest.raises(ValueError, match="USD/CHF: no close near 2025-10-09"):
        fx_returns(data, date(2026, 10, 12))


def test_two_charts_share_all_ten_pairs_and_bar_renderer(monkeypatch, tmp_path):
    import charts.weekly_fx as fx
    from unittest.mock import Mock
    fetcher = Mock()
    fetcher.get_close_series.side_effect = list(histories().values())
    render = Mock(return_value=object())
    save = Mock()
    monkeypatch.setattr(fx, "render_change_bars", render)
    monkeypatch.setattr(fx.EconStyle, "save_chart", save)
    generate_fx_charts(tmp_path, fetcher, date(2026, 10, 12))
    assert fetcher.get_close_series.call_count == 10
    assert render.call_count == 2
    assert render.call_args_list[0].args[0] == render.call_args_list[1].args[0] == list(WEEKLY_FX)
    assert [c.args[1].name for c in save.call_args_list] == ["03_fx_weekly.png", "04_fx_trend.png"]
