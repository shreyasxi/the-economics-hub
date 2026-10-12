"""European ETF returns must share dates, retain dividends and fail closed."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from data.fetchers.europe_sectors import SECTORS, STEM, TTM_STEM, generate, prepare


@pytest.fixture
def histories():
    dates = pd.bdate_range('2024-09-01', '2026-10-09', tz='Europe/Berlin')
    result = {}
    for i, ticker in enumerate(SECTORS):
        result[ticker] = pd.Series(100 * np.exp(np.arange(len(dates)) * (i - 9) / 10000), index=dates)
        result[ticker].attrs['return_basis'] = 'adjusted total return'
    return result


def test_common_dates_exact_ratios_and_exchange_local_day(histories):
    r = prepare(histories, date(2026, 10, 10))
    assert r['latest_observation'] == '2026-10-09'
    assert r['week_start'] == '2026-10-02'
    assert r['ttm_start'] == '2025-10-09'
    assert len(r['rows']) == 19
    assert r['currency'] == 'EUR'
    for row in r['rows']:
        s = histories[row['ticker']]
        assert row['weekly'] == pytest.approx((s.loc['2026-10-09'] / s.loc['2026-10-02'] - 1) * 100)
        assert row['ttm'] == pytest.approx((s.loc['2026-10-09'] / s.loc['2025-10-09'] - 1) * 100)


def test_weekend_anniversary_uses_prior_common_session(histories):
    r = prepare(histories, date(2026, 10, 8))  # End 7 Oct; anniversary 7 Oct 2025 is a weekday.
    assert r['latest_observation'] == '2026-10-07'  # current session never enters the comparison
    # End on Tuesday 6 Oct 2026; its 2025 anniversary is Monday. Remove that
    # historical date from one ETF so every sector uses the prior Friday.
    ticker = next(iter(histories))
    histories[ticker] = histories[ticker].drop(pd.Timestamp('2025-10-06', tz='Europe/Berlin'))
    r = prepare(histories, date(2026, 10, 7))
    assert r['ttm_start'] == '2025-10-03'


def test_blank_latest_placeholders_are_not_observations(histories):
    for s in histories.values():
        s.iloc[-1] = np.nan
    r = prepare(histories, date(2026, 10, 10))
    assert r['latest_observation'] == '2026-10-08'
    assert r['week_start'] == '2026-10-01'


def test_shared_holiday_is_allowed_but_isolated_missing_session_is_rejected(histories):
    ticker = next(iter(histories))
    histories[ticker] = histories[ticker].drop(histories[ticker].index[-3])
    with pytest.raises(ValueError, match='missing session'):
        prepare(histories, date(2026, 10, 10))
    # A market-wide holiday is absent from every ETF, so count five observed sessions.
    for t, s in histories.items():
        histories[t] = s.drop(pd.Timestamp('2026-10-07', tz='Europe/Berlin'), errors='ignore')
    r = prepare(histories, date(2026, 10, 10))
    assert r['week_start'] == '2026-10-01'


def test_reject_missing_unadjusted_stale_and_invalid_data(histories):
    ticker = next(iter(histories))
    with pytest.raises(ValueError, match='all 19'):
        prepare({t: s for t, s in histories.items() if t != ticker}, date(2026, 10, 10))
    with pytest.raises(ValueError, match='stale'):
        prepare(histories, date(2026, 10, 20))
    histories[ticker].iloc[0] = 0
    with pytest.raises(ValueError, match='non-positive'):
        prepare(histories, date(2026, 10, 10))
    histories[ticker].attrs.clear()
    with pytest.raises(ValueError, match='dividend-adjusted'):
        prepare(histories, date(2026, 10, 10))


def test_failed_refresh_removes_both_charts(histories, tmp_path):
    for stem in (STEM, TTM_STEM):
        for ext in ('png', 'json'):
            (tmp_path / (stem + '.' + ext)).write_text('stale')
    histories[next(iter(histories))].attrs.clear()
    with pytest.raises(ValueError, match='dividend-adjusted'):
        generate(tmp_path, histories, date(2026, 10, 10))
    assert not list(tmp_path.iterdir())
