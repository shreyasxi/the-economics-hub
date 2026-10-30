"""Guard the named datasets used by the live comparison view on period changes."""
import pandas as pd
import pytest
from streamlit.elements.vega_charts import _convert_altair_to_vega_lite_spec

from charts.india_charts.emerging_opportunity import _comparison_chart, _direction
from config.emerging_opportunity import EQUITY_SECTORS
from data.processors.emerging_publication import read_manifest, load_sector
from data.processors.sector_flows import PERIODS, rank_sectors


@pytest.fixture(scope='module')
def datasets():
    folder, manifest = read_manifest()
    return {sector: load_sector(sector, folder, manifest) for sector in EQUITY_SECTORS}


@pytest.mark.parametrize('period', PERIODS)
@pytest.mark.parametrize('column', ['net_cr', 'relative_pct'])
def test_comparison_updates_use_stable_datasets(datasets, period, column):
    rows, *_ = rank_sectors(datasets, period)
    frame = pd.DataFrame(rows).dropna(subset=[column]).sort_values(column, ascending=False)
    frame['direction'] = frame[column].map(_direction)
    spec = _convert_altair_to_vega_lite_spec(_comparison_chart(frame, column, 'unit'))
    bars, zero = spec['layer']
    # Content-hash names caused the browser's "Unrecognized data set" errors
    # when Streamlit updated an existing Vega view with a different ranking.
    assert bars['data']['name'] == 'sector_comparison'
    assert zero['data']['name'] == 'comparison_zero'
    assert not spec['datasets']
    assert bars['data']['values'] == frame.to_dict(orient='records')
    assert bars['encoding']['y']['sort'] == frame.sector.tolist()
    assert bars['encoding']['x']['field'] == column
    assert len(bars['data']['values']) == 22


@pytest.mark.parametrize('sector', ['Utilities', 'Services', 'Financial Services', 'Textiles'])
def test_history_sector_updates_preserve_axis_space(datasets, sector):
    from charts.india_charts.emerging_opportunity import _history_chart

    history = pd.DataFrame(datasets[sector]['flows']).sort_values('date')
    history['period_label'] = pd.to_datetime(history.date).dt.strftime('%d %b')
    history['direction'] = history.equity_flow_cr.map(_direction)
    spec = _convert_altair_to_vega_lite_spec(_history_chart(history))
    bars, zero = spec['layer']
    assert bars['data']['name'] == 'sector_history'
    assert bars['data']['values'] == history.to_dict(orient='records')
    assert not spec['datasets']
    # The axis must reserve room for the full formatted values when the scale
    # changes between hundreds and tens of thousands, including negative ticks.
    axis = bars['encoding']['y']['axis']
    assert axis['format'] == ',.0f'
    assert 'labelExpr' not in axis
    assert axis['minExtent'] >= 58
    assert spec['padding']['top'] >= 12
    assert zero['encoding']['y'] == {'datum': 0}
