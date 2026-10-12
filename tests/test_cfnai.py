"""Keep official CFNAI and CFNAIMA3 values aligned without synthetic observations."""
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from charts.world_charts.cfnai import draw, prepare
from charts.style import EconStyle
from generate_macro import monotone_curve


def test_published_ma3_is_not_recomputed_and_missing_calendar_months_remain_gaps():
    dates = pd.date_range('2025-01-01', periods=8, freq='MS')
    monthly = pd.Series(range(8), index=dates)
    average = pd.Series([.01, -.03, .09, -.08, .12, -.11, .2, -.04],
                        index=dates + pd.offsets.MonthEnd())
    monthly = monthly.drop(pd.Timestamp('2025-04-01'))
    frame = prepare(monthly, average)
    assert frame.index[0] == pd.Timestamp('2022-01-01')
    assert len(frame) == 44
    assert pd.isna(frame.loc['2025-04-01', 'monthly'])
    assert frame.loc['2025-04-01', 'ma3'] == -.08
    assert frame.loc['2025-08-01', 'monthly'] == 7
    assert frame.loc['2025-08-01', 'ma3'] == -.04
    with pytest.raises(ValueError, match='duplicate'):
        prepare(pd.concat([monthly, monthly.iloc[:1]]), average)
    with pytest.raises(ValueError, match='both published series'):
        prepare(monthly, pd.Series(dtype=float, index=pd.DatetimeIndex([])))


def test_plot_retains_extreme_monthly_values_and_labels_the_official_average(tmp_path):
    dates = pd.date_range('2020-01-01', periods=8, freq='MS')
    monthly = pd.Series([.2, -.1, -4.5, -17.7, 3.5, 7.1, 2.2, -.04], index=dates)
    average = pd.Series([.03, .01, -1.4, -7.5, -6.2, -2.3, 4.1, .01], index=dates)
    frame = prepare(monthly, average, start='2020-01')
    with patch.object(EconStyle, 'save_chart') as save:
        draw(frame, tmp_path / 'chart.png', smoother=monotone_curve)
    fig = save.call_args.args[0]
    try:
        ax = fig.axes[0]
        assert min(patch.get_height() for patch in ax.patches) == -17.7
        assert ax.lines[0].get_ydata()[-1] == .01
        assert 'Aug 2020  +0.01\nCFNAI-MA3' in [t.get_text() for t in ax.texts]
        assert any('−0.70 · Historical recession signal (3M average)' == t.get_text() for t in ax.texts)
        assert ax.get_ylim()[0] < -17.7
    finally:
        plt.close(fig)
