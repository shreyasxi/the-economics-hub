"""Protect the different units of the rate-cycle switch and partial-month handling."""
from copy import deepcopy
from datetime import date

import pytest

from charts.world_charts.world_rate_cycle_dashboard import chart, frames, latest_summary


def sample():
    return {'start': '2026-01', 'hikes': [3] * 6 + [9], 'cuts': [1] * 7,
            'reporting': [10] * 7, 'banks': 10,
            'weighted': {'hikes_bp': [7.5] * 6 + [50], 'cuts_bp': [2.5] * 7,
                         'equal_bp': [4.] * 7, 'cap_bp': 200, 'gdp_year': 2025}}


def test_counts_and_bp_switch_use_source_values_without_mutating_snapshot():
    cycle = sample()
    original = deepcopy(cycle)
    bars, lines, partial = frames(cycle, today=date(2026, 7, 10))
    assert partial
    assert bars[0]['magnitude'] == 3
    assert bars[1]['value'] == -1
    assert len(lines) == 1
    assert lines[0]['value'] == 2  # Six completed months: (3 - 1), not July's surge.
    weighted_bars, weighted_lines, _ = frames(cycle, True, today=date(2026, 7, 10))
    assert weighted_bars[0]['magnitude'] == 7.5
    assert weighted_bars[1]['value'] == -2.5
    assert [r['value'] for r in weighted_lines] == [5., 4.]
    assert cycle == original
    assert 'July 2026 so far: 9 hiking' in latest_summary(cycle, today=date(2026, 7, 10))


def test_completed_month_is_included_only_when_reporting_is_complete():
    cycle = sample()
    _, lines, partial = frames(cycle, today=date(2026, 8, 1))
    assert not partial
    assert len(lines) == 2
    assert lines[-1]['value'] == pytest.approx(3.)
    cycle['reporting'][-1] = 9
    bars, lines, partial = frames(cycle, today=date(2026, 8, 1))
    assert partial and len(lines) == 1
    assert bars[-1]['status'] == 'Partial month'
    assert bars[-1]['opacity'] < bars[0]['opacity']


def test_native_chart_exposes_correct_units_and_legend_for_each_mode():
    for weighted, unit, legend_size in [(False, 'Central banks', 3), (True, 'Basis points', 4)]:
        spec = chart(sample(), weighted, today=date(2026, 7, 10)).to_dict()
        encoding = spec['layer'][1]['encoding']
        assert encoding['y']['title'] == unit
        assert len(encoding['color']['scale']['domain']) == legend_size
