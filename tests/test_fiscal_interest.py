import pandas as pd
import pytest
from data.processors.fiscal_interest import ANNUAL, MONTHLY, load_interest_data


def test_official_ratios_and_statuses():
    annual, monthly = load_interest_data()
    assert len(annual) == 12
    assert annual.status.tolist() == ['Actual'] * 10 + ['Provisional', 'Budget']
    assert annual.iloc[-3].interest_share == pytest.approx(1115575 / 3036619 * 100)
    assert annual.iloc[-2].interest_share == pytest.approx(1242575 / 3302225 * 100)
    assert annual.iloc[-1].interest_share == pytest.approx(1403972 / 3533150 * 100)
    assert monthly.date.tolist() == pd.date_range('2026-04-01', '2026-09-01', freq='MS').tolist()
    assert monthly.iloc[-1].interest_share == pytest.approx(646010 / (1276088 + 480732) * 100)
    # May is cumulative. Using only May increments would produce a different ratio.
    assert monthly.iloc[1].interest_share == pytest.approx(181461 / 699005 * 100)


@pytest.mark.parametrize('problem', ['missing_month', 'missing_revenue', 'duplicate', 'zero_receipts'])
def test_monthly_input_rejects_gaps_and_invalid_denominators(tmp_path, problem):
    data = pd.read_csv(MONTHLY, comment='#')
    mask = (data.fy == '2026-27') & (data.month == 'Aug-26')
    if problem == 'missing_month':
        data = data[~((data.fy == '2026-27') & (data.month == 'Jun-26'))]
    elif problem == 'missing_revenue':
        data.loc[mask, 'net_tax_revenue'] = None
    elif problem == 'duplicate':
        data = pd.concat([data, data[mask]])
    else:
        data.loc[mask, ['net_tax_revenue', 'non_tax_revenue']] = 0
    path = tmp_path / 'monthly.csv'
    data.to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_interest_data(ANNUAL, path)
