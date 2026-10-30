"""Window and denominator contracts for the sector-only comparison."""
import copy
import pytest
from data.processors.sector_flows import period_dates, rank_sectors


def dataset():
    days = period_dates('2026-10-15', 'Six months')
    return dict(as_of='2026-09-30', flows_as_of='2026-10-15', flows=[
        dict(date=d, equity_flow_cr=(-10 if i == 11 else 20), opening_equity_auc_cr=1000 + i * 100)
        for i, d in enumerate(days)])


def test_latest_complete_month_uses_september_not_partial_october():
    assert period_dates('2026-10-15', 'Latest complete month') == ['2026-09-15', '2026-09-30']
    assert period_dates('2026-09-30', 'Latest complete month') == ['2026-09-15', '2026-09-30']
    rows, start, end, cutoff = rank_sectors({'Services': dataset()}, 'Latest complete month')
    assert (start, end, cutoff) == ('2026-09-01', '2026-09-30', '2026-10-15')
    assert rows[0]['net_cr'] == 40
    assert rows[0]['relative_pct'] == pytest.approx(40 / 1900 * 100)


def test_rolling_windows_and_opening_denominator():
    d = dataset()
    rows, start, end, _ = rank_sectors({'Services': d}, 'Six months')
    assert (start, end) == ('2026-04-16', '2026-10-15')
    assert rows[0]['net_cr'] == 210
    assert rows[0]['relative_pct'] == 21
    assert len(period_dates(end, 'Three months')) == 6
    rows, start, _, _ = rank_sectors({'Services': d}, 'Latest fortnight')
    assert start == '2026-10-01'
    assert rows[0]['relative_pct'] == pytest.approx(-10 / 2100 * 100)


def test_missing_periods_and_missing_opening_holdings_stay_unavailable():
    d = dataset(); d['flows'].pop(5)
    rows, *_ = rank_sectors({'Services': d}, 'Six months')
    assert rows[0]['net_cr'] is None and rows[0]['relative_pct'] is None
    d = dataset(); d['flows'][0]['opening_equity_auc_cr'] = None
    rows, *_ = rank_sectors({'Services': d}, 'Six months')
    assert rows[0]['net_cr'] == 210 and rows[0]['relative_pct'] is None


def test_sector_dates_duplicates_and_nonfinite_values_are_rejected():
    d = dataset(); other = copy.deepcopy(d); other['flows_as_of'] = '2026-09-30'
    with pytest.raises(ValueError, match='cutoffs'):
        rank_sectors({'A': d, 'B': other}, 'Six months')
    d['flows'].append(d['flows'][0])
    with pytest.raises(ValueError, match='Duplicate'):
        rank_sectors({'A': d}, 'Six months')
    d = dataset(); d['flows'][0]['equity_flow_cr'] = float('nan')
    with pytest.raises(ValueError, match='Non-finite'):
        rank_sectors({'A': d}, 'Six months')
