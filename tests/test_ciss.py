"""Fail closed on incorrect CISS identity, alignment or decomposition."""
from datetime import date
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from charts.style import EconStyle
from charts.world_charts.ciss import draw, draw_drivers
from data.fetchers.ciss import COMPONENTS, KEYS, STEM, DRIVERS_STEM, generate, parse_source

TODAY = date(2026, 10, 10)


@pytest.fixture
def source():
    dates = pd.bdate_range('2010-10-01', '2026-10-08')
    values = dict(zip(COMPONENTS, [.04, .025, .017, .042, .008, -.115]))
    values['SS_CIN'] = sum(values.values())
    return pd.concat([pd.DataFrame({
        'KEY': key, 'TIME_PERIOD': dates.strftime('%Y-%m-%d'), 'OBS_VALUE': values[code],
        'TITLE': 'NEW CISS - official series', 'UNIT': 'PURE_NUMB', 'UNIT_MULT': 0, 'DECIMALS': 4,
    }) for code, key in KEYS.items()], ignore_index=True)


def raw(frame):
    return frame.to_csv(index=False).encode()


def test_reconciliation_keeps_official_signed_values_and_daily_history(source):
    report = parse_source(raw(source), TODAY)
    assert report['latest_observation'] == '2026-10-08'
    assert report['window_start'] == '2011-10-08'
    assert report['latest']['SS_CON'] == -.115
    assert report['latest']['SS_CIN'] == pytest.approx(.017)
    assert abs(report['reconciliation']['latest']) < 1e-14
    # Missing old contributions do not remove published timeline observations.
    old = source[(source.KEY == KEYS['SS_FIN']) & (source.TIME_PERIOD == '2015-01-02')].index
    sparse = parse_source(raw(source.drop(old)), TODAY)
    assert sparse['rows'] == report['rows']
    assert sparse['reconciliation']['observations'] == report['reconciliation']['observations'] - 1
    rounded = source.copy()
    rounded.loc[rounded.KEY == KEYS['SS_CIN'], 'OBS_VALUE'] += .0003
    assert parse_source(raw(rounded), TODAY)['latest']['SS_CIN'] == pytest.approx(.0173)


@pytest.mark.parametrize('problem', ['wrong_key', 'wrong_units', 'wrong_method', 'endpoint',
                                    'duplicate', 'missing', 'residual'])
def test_invalid_sources_are_rejected(source, problem):
    aggregate = source.KEY == KEYS['SS_CIN']
    if problem == 'wrong_key':
        source.loc[aggregate, 'KEY'] = 'CISS.W.U2.Z0Z.4F.EC.SS_CI.IDX'
    elif problem == 'wrong_units':
        source.loc[aggregate, 'UNIT_MULT'] = 2
    elif problem == 'wrong_method':
        source.loc[aggregate, 'TITLE'] = 'Composite Indicator of Sovereign Stress'
    elif problem == 'endpoint':
        source = source.drop(source[source.KEY == KEYS['SS_FIN']].index[-1])
    elif problem == 'duplicate':
        source = pd.concat([source, source.iloc[[-1]]])
    elif problem == 'missing':
        source.loc[source.index[-1], 'OBS_VALUE'] = np.nan
    elif problem == 'residual':
        source.loc[aggregate, 'OBS_VALUE'] += .001
    with pytest.raises(ValueError, match='CISS:'):
        parse_source(raw(source), TODAY)


def test_staleness_history_and_failed_generation(source, tmp_path):
    with pytest.raises(ValueError, match='stale'):
        parse_source(raw(source), date(2026, 11, 10))
    with pytest.raises(ValueError, match='future'):
        parse_source(raw(source), date(2026, 10, 1))
    with pytest.raises(ValueError, match='15-year'):
        parse_source(raw(source[source.TIME_PERIOD >= '2012-01-01']), TODAY)
    for stem in (STEM, DRIVERS_STEM):
        for ext in ('png', 'json'):
            (tmp_path / f'{stem}.{ext}').write_text('old output')
    source.loc[source.KEY == KEYS['SS_CIN'], 'OBS_VALUE'] += .01
    with pytest.raises(ValueError, match='reconcile'):
        generate(tmp_path, raw(source), TODAY)
    assert not list(tmp_path.iterdir())


def test_monthly_means_use_identical_dates_and_exclude_partial_month(source):
    # Make the daily series vary while preserving exact additive reconciliation.
    jan = source.TIME_PERIOD.str.startswith('2026-01')
    first = source.TIME_PERIOD == '2026-01-02'
    source.loc[jan & (source.KEY == KEYS['SS_FIN']), 'OBS_VALUE'] += .1
    source.loc[jan & (source.KEY == KEYS['SS_CIN']), 'OBS_VALUE'] += .1
    source.loc[first & (source.KEY == KEYS['SS_FIN']), 'OBS_VALUE'] += .4
    source.loc[first & (source.KEY == KEYS['SS_CIN']), 'OBS_VALUE'] += .4
    # Omit a high-valued aggregate date from one component; every mean must omit it.
    source = source.drop(source[first & (source.KEY == KEYS['SS_EMN'])].index)
    report = parse_source(raw(source), TODAY)
    monthly = report['monthly']
    assert monthly['latest_month'] == '2026-09'
    assert [r['month'] for r in monthly['rows']] == [str(m) for m in pd.period_range('2025-10', '2026-09', freq='M')]
    january = next(r for r in monthly['rows'] if r['month'] == '2026-01')
    assert january['SS_FIN'] == pytest.approx(.14)
    assert january['SS_CIN'] == pytest.approx(.117)
    assert january['excluded_dates'] == 1
    assert january['observations'] == len(pd.bdate_range('2026-01-01', '2026-01-31')) - 1
    assert monthly['reconciliation']['max_abs'] < 1e-14
    assert report['rows']  # daily timeline remains independent of the intersection


def test_monthly_window_advances_and_requires_all_twelve_months(source):
    extra = source.groupby('KEY').tail(1).copy()
    extra.TIME_PERIOD = '2026-11-02'
    advanced = parse_source(raw(pd.concat([source, extra])), date(2026, 11, 3))
    assert advanced['monthly']['latest_month'] == '2026-10'
    assert advanced['monthly']['rows'][0]['month'] == '2025-11'
    month_end = parse_source(raw(source[source.TIME_PERIOD <= '2026-09-30']), date(2026, 10, 4))
    assert month_end['monthly']['latest_month'] == '2026-09'
    before_month_end = parse_source(raw(source[source.TIME_PERIOD <= '2026-09-29']), date(2026, 10, 4))
    assert before_month_end['monthly']['latest_month'] == '2026-08'
    # No monthly data is manufactured when a component has no valid dates.
    missing = source[(source.KEY == KEYS['SS_EMN']) & source.TIME_PERIOD.str.startswith('2026-05')].index
    with pytest.raises(ValueError, match='missing completed month'):
        parse_source(raw(source.drop(missing)), TODAY)


def test_standalone_timeline_preserves_daily_observations(source, tmp_path):
    report = parse_source(raw(source), TODAY)
    with patch.object(EconStyle, 'save_chart') as save:
        draw(report, tmp_path / 'ciss.png')
    fig = save.call_args.args[0]
    try:
        assert len(fig.axes) == 1
        np.testing.assert_array_equal(fig.axes[0].lines[1].get_ydata(), [r['CISS'] for r in report['rows']])
        assert fig.axes[0].get_ylabel() == 'CISS index units'
    finally:
        plt.close(fig)


def test_monthly_chart_stacks_signs_separately_and_preserves_aggregate(source, tmp_path):
    report = parse_source(raw(source), TODAY)
    # Exercise sign changes inside a component, not only the always-negative correlation.
    report['monthly']['rows'][0]['SS_FIN'] = -.04
    with patch.object(EconStyle, 'save_chart') as save:
        draw_drivers(report, tmp_path / 'drivers.png')
    fig = save.call_args.args[0]
    try:
        assert len(fig.axes) == 1
        ax = fig.axes[0]
        pos, neg = np.zeros(12), np.zeros(12)
        for code, container in zip(COMPONENTS, ax.containers):
            values = np.array([r[code] for r in report['monthly']['rows']])
            np.testing.assert_allclose([b.get_height() for b in container], values, rtol=0, atol=1e-15)
            np.testing.assert_array_equal([b.get_y() for b in container], np.where(values >= 0, pos, neg))
            assert all(b.get_linewidth() == EconStyle.BAR_EDGE_WIDTH for b in container)
            pos += np.maximum(values, 0)
            neg += np.minimum(values, 0)
        np.testing.assert_array_equal(ax.lines[0].get_ydata(), [r['SS_CIN'] for r in report['monthly']['rows']])
        assert len(ax.get_xticks()) == 12
        assert ax.get_ylim()[0] < neg.min() and ax.get_ylim()[1] > pos.max()
    finally:
        plt.close(fig)
