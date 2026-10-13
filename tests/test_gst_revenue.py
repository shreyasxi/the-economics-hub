import pandas as pd
import pytest

from data.processors.gst_revenue import DEFAULT_GST, load_gst_growth


def test_official_window_and_comparable_october():
    result = load_gst_growth()
    assert len(result) == 12
    assert result.date.iloc[0] == pd.Timestamp('2025-10-01')
    assert result.date.iloc[-1] == pd.Timestamp('2026-09-01')
    assert result.gross_yoy.iloc[0] == pytest.approx((188124 / 174796 - 1) * 100)
    assert result.net_yoy.iloc[0] == pytest.approx((161893 / 155999 - 1) * 100)
    assert result.gross_yoy.iloc[-1] == pytest.approx((203521 / 177365 - 1) * 100)
    assert result.net_yoy.iloc[-1] == pytest.approx((176520 / 149517 - 1) * 100)


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'basis', 'refunds'])
def test_rejects_incomplete_or_inconsistent_amounts(tmp_path, problem):
    data = pd.read_csv(DEFAULT_GST)
    if problem == 'missing':
        data = data[data.month != '2025-02']
    elif problem == 'duplicate':
        data = pd.concat([data, data.iloc[:1]])
    elif problem == 'basis':
        data.loc[0, 'basis'] = 'including_cess'
    else:
        data.loc[0, 'refunds_crore'] += 100
    path = tmp_path / 'gst.csv'
    data.to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_gst_growth(path)
