"""NFCI must count overlapping memberships once and preserve official values."""
import io
from datetime import date
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from charts.world_charts.nfci import draw
from charts.style import EconStyle
from data.fetchers.nfci import parse_sources


def sources(residual=0):
    dates = pd.date_range('2021-10-01', '2026-10-02', freq='W-FRI')
    f = pd.DataFrame({'R': np.linspace(-.2, .1, len(dates)), 'C': -.1, 'L': .04,
                      'HH': -.003, 'NFC': -.004}, index=dates)
    f.index.name = 'Date'
    key = pd.DataFrame({'Mnemonic': f.columns,
                        'Subindex': ['Risk', 'Credit', 'Leverage',
                                     'Leverage; Nonfinancial Leverage', 'Leverage; Nonfinancial Leverage']})
    book = io.BytesIO()
    with pd.ExcelWriter(book, engine='openpyxl') as writer:
        key.to_excel(writer, sheet_name='Key', index=False)
        f.to_excel(writer, sheet_name='NFCI')
    a = pd.DataFrame({'NFCI': f.sum(axis=1) - residual, 'Risk': f.R, 'Credit': f.C, 'Leverage': f.L})
    a.index.name = 'Friday_of_Week'
    index = pd.DataFrame({'NFCI': a.NFCI.round(3)}, index=dates)
    return {'workbook': book.getvalue(), 'aggregate': a.to_csv().encode(), 'index': index.to_csv().encode()}


def test_compound_leverage_classifications_count_once_without_altering_aggregate():
    report = parse_sources(sources(.0001), date(2026, 10, 10))
    assert report['group_counts'] == {'Risk': 1, 'Credit': 1, 'Leverage': 3}
    assert len(report['rows']) == 261
    latest = report['rows'][-1]
    assert latest['Leverage'] == pytest.approx(.033)
    assert latest['NFCI'] == pytest.approx(.0329)
    assert report['reconciliation']['latest'] == pytest.approx(.0001)
    assert not report['warnings']
    warned = parse_sources(sources(.0003), date(2026, 10, 10))
    assert warned['warnings']
    with pytest.raises(ValueError, match='publication limit'):
        parse_sources(sources(.0011), date(2026, 10, 10))


def test_alignment_rounding_and_freshness_fail_closed():
    raw = sources()
    with pytest.raises(ValueError, match='stale'):
        parse_sources(raw, date(2026, 11, 10))
    index = pd.read_csv(io.BytesIO(raw['index']), index_col=0)
    index.iloc[-1, 0] += .01
    with pytest.raises(ValueError, match='rounding tolerance'):
        parse_sources({**raw, 'index': index.to_csv().encode()}, date(2026, 10, 10))
    with pytest.raises(ValueError, match='dates or release endpoints'):
        parse_sources({**raw, 'index': index.iloc[:-1].to_csv().encode()}, date(2026, 10, 10))


def test_diverging_areas_and_line_preserve_weekly_observations(tmp_path):
    report = parse_sources(sources(.0001), date(2026, 10, 10))
    with patch.object(EconStyle, 'save_chart') as save:
        draw(report, tmp_path / 'nfci.png')
    fig = save.call_args.args[0]
    try:
        ax = fig.axes[0]
        np.testing.assert_array_equal(ax.lines[0].get_ydata(), [r['NFCI'] for r in report['rows']])
        assert len(ax.collections) == 7  # three positive/negative areas plus endpoint
        assert 'Historical average' in [t.get_text() for t in ax.texts]
        assert ax.get_ylim()[0] < min(r['NFCI'] for r in report['rows'])
        assert ax.get_ylim()[1] > .1
    finally:
        plt.close(fig)
