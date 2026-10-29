"""Guard source fields, calendar weights, date matching and World integration."""
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from charts.style import EconStyle
from charts.world_charts.banking_liquidity import draw, prepare, weighted_monthly_reserves
from data.fetchers.fedwire import parse_monthly, fetch_monthly, FIELD
from config.macro_settings import MACRO_INDICATORS
from generate_macro import chart_banking_liquidity


def inputs():
    dates = pd.bdate_range('2026-08-03', '2026-10-08').difference(pd.DatetimeIndex(['2026-09-07']))
    iorb = pd.Series(4.4, index=pd.date_range('2026-08-01', '2026-10-10'))
    iorb.loc['2026-09-17':] = 3.9
    effr = iorb.reindex(dates) - .02
    sofr = iorb.reindex(dates) - .03
    sofr.loc['2026-09-30'] += .75
    reserves = pd.Series(3_000_000., index=pd.date_range('2026-07-01', '2026-10-07', freq='W-WED'))
    return effr, sofr, iorb, reserves


def payments():
    return pd.Series(4_500_000., index=pd.period_range('2026-07', '2026-08', freq='M'))


def test_units_policy_changes_holidays_and_publication_lag():
    spreads, averages, ratio, start, end = prepare(*inputs(), payments(), '2026-10-10')
    np.testing.assert_allclose(spreads['EFFR'], -2)
    assert spreads['SOFR'].loc['2026-09-30'] == pytest.approx(72)
    assert averages['SOFR'].iloc[-1] == pytest.approx(.75)
    assert averages['SOFR'].iloc[:19].isna().all()
    assert pd.Timestamp('2026-09-07') not in spreads['EFFR'].index
    assert ratio.iloc[-1] == pytest.approx(66.6666667)
    assert ratio.index[-1] == pd.Timestamp('2026-08-31')
    assert start == pd.Timestamp('2021-10-10')
    assert end == pd.Timestamp('2026-10-10')


def test_calendar_weights_boundary_weeks_and_missing_coverage():
    weekly = pd.Series([70., 140., 210., 280., 350., 420.],
                       index=pd.date_range('2026-01-07', periods=6, freq='W-WED'))
    monthly = weighted_monthly_reserves(weekly)
    assert monthly.loc['2026-01'] == pytest.approx((7*70+7*140+7*210+7*280+3*350)/31)
    assert pd.Period('2026-02') not in monthly.index  # partial month is omitted
    assert weighted_monthly_reserves(weekly.drop(weekly.index[2])).empty
    assert weighted_monthly_reserves(weekly.mask(weekly.index == weekly.index[2])).empty


def test_warm_up_and_iorb_inception():
    dates = pd.bdate_range('2021-07-01', '2021-10-08')
    rate = pd.Series(.15, index=dates)
    ref = pd.Series(.15, index=pd.date_range('2021-07-01', '2021-10-10'))
    weekly = pd.Series(3_000_000., index=pd.date_range('2021-07-07', '2021-10-06', freq='W-WED'))
    p = pd.Series(4_500_000., index=pd.period_range('2021-08', '2021-09', freq='M'))
    result = prepare(rate, rate, ref, weekly, p, '2021-10-10')
    assert result[3] == pd.Timestamp('2021-07-29')
    assert result[0]['EFFR'].index[0] == pd.Timestamp('2021-07-29')
    rate = pd.Series(.15, index=pd.bdate_range('2021-08-02', '2026-10-08'))
    ref = pd.Series(.15, index=pd.date_range('2021-08-01', '2026-10-10'))
    result = prepare(rate, rate, ref, inputs()[-1], payments(), '2026-10-10')
    assert result[1]['EFFR'].iloc[0] == 0


def test_invalid_rates_reserves_and_monthly_source_fail():
    effr, sofr, iorb, weekly = inputs()
    def run(e=effr, s=sofr, i=iorb, w=weekly, p=None):
        return prepare(e, s, i, w, payments() if p is None else p, '2026-10-10')
    with pytest.raises(ValueError, match='same-date IORB'):
        run(i=iorb.drop(pd.Timestamp('2026-09-17')))
    with pytest.raises(ValueError, match='stale'):
        run(e=effr.loc[:'2026-09-01'])
    with pytest.raises(ValueError, match='duplicate'):
        run(e=pd.concat([effr, effr.iloc[-1:]]))
    with pytest.raises(ValueError, match='Wednesday'):
        run(w=weekly.set_axis(weekly.index + pd.Timedelta(days=1)))
    with pytest.raises(ValueError, match='non-finite'):
        run(w=weekly * np.inf)
    with pytest.raises(ValueError, match='coverage'):
        run(w=weekly.drop(pd.Timestamp('2026-08-12')))
    with pytest.raises(ValueError, match='stale'):
        run(p=pd.Series([4e6], index=pd.period_range('2026-05', periods=1, freq='M')))
    with pytest.raises(ValueError, match='invalid'):
        run(p=payments()*0)
    with pytest.raises(ValueError, match='unpublished'):
        run(p=pd.Series([4e6], index=pd.period_range('2026-10', periods=1, freq='M')))


def html(rows, header=FIELD+' ($millions)'):
    return ('<h1>Fedwire Funds Service</h1><table><thead><tr><th>Month</th>'
            '<th>Value of transfers originated ($millions)</th><th>'+header+'</th>'
            '</tr></thead><tbody>'+''.join('<tr><th>'+m+'</th><td>100,000,000</td><td>'+v+'</td></tr>'
                                        for m,v in rows)+'</tbody></table>')


def test_fedwire_field_selection_sorting_and_known_source_typo():
    source = html([('2023:March','4,800,000'), ('2023: Feburary','4,500,000')])
    s = parse_monthly(source)
    assert s.index.equals(pd.period_range('2023-02','2023-03',freq='M'))
    assert s.iloc[0] == 4_500_000  # not monthly value
    # Column reordering is resolved by headers rather than fixed positions.
    source = source.replace('<th>Month</th>', '<th>Extra</th><th>Month</th>')
    source = source.replace('<tr><th>2023:', '<tr><td>7</td><th>2023:')
    pd.testing.assert_series_equal(parse_monthly(source), s)


@pytest.mark.parametrize('rows,header,match', [
    ([('2026:August','0')], FIELD+' ($millions)', 'nonpositive'),
    ([('2026:August','NaN')], FIELD+' ($millions)', 'invalid'),
    ([('2026:August','4,50,000')], FIELD+' ($millions)', 'invalid'),
    ([('2026:Nonesuch','4,500,000')], FIELD+' ($millions)', 'month'),
    ([('2026:August','4,500,000')]*2, FIELD+' ($millions)', 'duplicate'),
    ([('2026:June','4,500,000'),('2026:August','4,500,000')], FIELD+' ($millions)', 'missing'),
    ([('2026:August','4,500,000')], 'Average daily volume of transfers (number)', 'column'),
])
def test_fedwire_bad_data_fails(rows, header, match):
    with pytest.raises(ValueError, match=match):
        parse_monthly(html(rows, header))


def test_retrieval_failure_is_explicit():
    import requests
    with patch('data.fetchers.fedwire.requests.get', side_effect=requests.ConnectionError('offline')):
        with pytest.raises(ValueError, match='source/parsing error'):
            fetch_monthly()


def test_research_discrepancy_prevents_publication():
    rate = pd.Series(4., index=pd.bdate_range('2025-02-03','2025-04-08'))
    weekly = pd.Series(1e6, index=pd.date_range('2025-02-05','2025-04-09',freq='W-WED'))
    p = pd.Series(4e6, index=pd.period_range('2025-02','2025-03',freq='M'))
    with pytest.raises(ValueError, match='reconciliation'):
        prepare(rate, rate, rate, weekly, p, '2025-04-10')


def test_side_by_side_alignment_and_unclipped_daily_spike(tmp_path):
    effr, sofr, iorb, reserves = inputs()
    data = prepare(effr, sofr.iloc[:-1], iorb, reserves, payments(), '2026-10-10')
    with patch.object(EconStyle, 'save_chart') as save:
        draw(data, tmp_path / 'chart.png')
    fig = save.call_args.args[0]
    try:
        left, right = fig.axes
        assert left.get_xlim() == right.get_xlim()
        assert len(right.lines[0].get_xdata()) == len(effr)
        assert max(right.lines[2].get_ydata()) == pytest.approx(72)
        assert right.get_ylim()[1] > 72
        assert left.lines[0].get_ydata()[-1] == pytest.approx(66.6666667)
        assert left.get_position().height == right.get_position().height
        assert left.get_position().x1 < right.get_position().x0
        assert left.get_ylim()[0] < 65 < left.get_ylim()[1]
        labels = [text.get_text() for text in fig.texts]
        assert any('EFFR−IORB' in t and '08 Oct 2026' in t for t in labels)
        assert any('SOFR−IORB' in t and '07 Oct 2026' in t for t in labels)
        assert any('August 2026' in t for t in labels)
        assert any('0 bp · Equal to IORB' == t.get_text() for t in right.texts)
    finally:
        plt.close(fig)


def test_generator_series_and_world_section_contract(tmp_path):
    keys = ('us_effr', 'us_sofr', 'us_iorb', 'us_reserves')
    assert [MACRO_INDICATORS[k]['series'] for k in keys] == ['EFFR', 'SOFR', 'IORB', 'WRESBAL']
    engine = Mock()
    engine.fetch_raw.side_effect = inputs()
    fixture_pandas = SimpleNamespace(**vars(pd))
    fixture_pandas.Timestamp = Mock(wraps=pd.Timestamp)
    fixture_pandas.Timestamp.now.side_effect = AssertionError('Fixture must not read the wall clock')
    # Keep the real preparation and freshness checks tied to the fixture date.
    with patch('charts.world_charts.banking_liquidity.draw') as render, patch(
            'data.fetchers.fedwire.fetch_monthly', return_value=payments()), patch(
            'charts.world_charts.banking_liquidity.prepare',
            wraps=partial(prepare, today='2026-10-10')), patch(
            'charts.world_charts.banking_liquidity.pd', fixture_pandas):
        chart_banking_liquidity(engine, tmp_path)
    assert [c.args[0] for c in engine.fetch_raw.call_args_list] == list(keys)
    assert render.call_args.args[0][-1] == pd.Timestamp('2026-10-10')
    assert render.call_args.args[1].name == '07b_macro_banking_liquidity.png'
    root = Path(__file__).resolve().parents[1]
    assert '("United States", ("inflation", "labour", "balance_sheet", "banking_liquidity",' in (root / 'app.py').read_text()


def test_world_page_renders_monitor_in_us_section_with_insights(tmp_path):
    import ast
    from streamlit.testing.v1 import AppTest

    source = (Path(__file__).resolve().parents[1] / 'app.py').read_text()
    functions = {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body
                 if isinstance(n, ast.FunctionDef)}
    path = tmp_path / '07b_macro_banking_liquidity.png'
    plt.imsave(path, np.ones((2, 2, 3)))
    script = '''import streamlit as st
from pathlib import Path
from datetime import datetime
from charts.loader import clean_title as _chart_title
from config.insights import get_insight
def _chart_anchor(path): pass
def _anchor(*args): return '-'.join(args)
def _section(title, **kwargs): st.subheader(title)
def _pop_summary(charts, keys): return None, charts
def _load_world_snapshot(charts): return {'generated_at': '2026-10-10 10:00'}
def _load_cycle_brief(): return None
def _page_header_html(*args, **kwargs): return ''
def _fmt_day(day): return str(day)
def _central_bank_strip_html(*args): return ''
def _calendar_html(*args): return ''
def _scoreboard_html(*args): return ''
'''
    script += f"def get_charts(subdir): return [Path({str(path)!r})], '2026-10'\n"
    script += '\n\n'.join(functions[name] for name in ('_render_chart', '_render_grid', 'page_world'))
    script += '\npage_world()\n'
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert 'United States' in [s.value for s in app.subheader]
    assert 'Other' not in [s.value for s in app.subheader]
    assert len(app.get('imgs')) == 1
    assert any('**What to investigate:**' in m.value for m in app.markdown)
