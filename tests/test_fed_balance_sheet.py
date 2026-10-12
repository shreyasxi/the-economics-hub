"""Check the balance-sheet chart's units and published policy boundaries."""
from unittest.mock import Mock, patch

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from charts.style import EconStyle
from generate_macro import chart_fed_balance_sheet


def test_walcl_units_observation_date_and_qt_end(tmp_path):
    # WALCL is published in USD millions, not billions.
    series = pd.Series([4_000_000, 8_900_000, 6_747_560],
                       index=pd.to_datetime(['2019-01-02', '2022-03-30', '2026-10-07']))
    engine = Mock()
    engine.get_transformed.return_value = series
    with patch.object(EconStyle, 'save_chart') as save:
        chart_fed_balance_sheet(engine, tmp_path)
    fig = save.call_args.args[0]
    try:
        ax = fig.axes[0]
        assert ax.lines[0].get_ydata()[-1] == pytest.approx(6.747560)
        labels = [t.get_text() for t in ax.texts]
        assert '07 Oct 2026  $6.75T' in labels
        assert all('$6.7T  6.75' not in label for label in labels)
        def x_bounds(shading):
            display = shading.get_transform().transform(shading.get_path().vertices)
            return ax.transData.inverted().transform(display)[:, 0]

        qt = x_bounds(ax.patches[1])
        assert qt.min() == pytest.approx(mdates.date2num(pd.Timestamp('2022-06-01')))
        assert qt.max() == pytest.approx(mdates.date2num(pd.Timestamp('2025-12-01')))
        qe = x_bounds(ax.patches[0])
        assert qe.max() == pytest.approx(mdates.date2num(pd.Timestamp('2022-03-01')))
    finally:
        plt.close(fig)
