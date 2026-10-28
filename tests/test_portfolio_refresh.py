"""Publication isolation, freshness gates, schedule grace and failure recovery."""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

import pandas as pd
import pytest

from portfolio_lab.refresh import collect_tri, coverage, refresh, validate_freshness
from portfolio_lab.status import update_delayed


def test_yahoo_timestamp_metadata_keeps_its_epoch_and_is_json_serializable():
    from data.fetchers.portfolio_prices import source_epoch
    instant = pd.Timestamp('2026-10-23 09:30', tz='America/New_York')
    epoch = int(instant.timestamp())
    assert source_epoch(instant) == epoch
    assert source_epoch(epoch) == epoch
    assert source_epoch(None) is None
    json.dumps({'firstTradeDate': source_epoch(instant)})


def test_incomplete_trailing_source_labels_use_the_last_verified_close():
    from data.fetchers.portfolio_prices import closed_history, validate_history
    dates = pd.DatetimeIndex(['2026-10-22', '2026-10-23', '2026-10-26', '2026-10-27'])
    frame = pd.DataFrame({key: [100., 100., float('nan'), 110.]
                          for key in ('Open', 'High', 'Low', 'Close', 'Adj Close')}, index=dates)
    frame['Volume'] = [200000., 200000., 0., 200000.]
    frame['Dividends'] = frame['Stock Splits'] = 0.
    # Interior missing observations remain invalid.
    kept, excluded = closed_history(frame, 'Asia/Kolkata', date(2026, 10, 28))
    assert not excluded
    with pytest.raises(ValueError, match='missing price/action'):
        validate_history('TEST', kept)
    # Exclude today's unfinished row and the trailing empty source label.
    kept, excluded = closed_history(frame, 'Asia/Kolkata', date(2026, 10, 27))
    assert excluded == ['2026-10-26']
    assert list(kept.index) == list(dates[:2])
    assert validate_history('TEST', kept)[0].iloc[0]['Close'] == 100.
    # Trading activity without a complete closing price is omitted only at the tail.
    partial = frame.iloc[:3].copy()
    partial.loc[dates[2], ['Open', 'High', 'Low', 'Close', 'Volume']] = [101., 102., 100., 101., 200000.]
    kept, excluded = closed_history(partial, 'Asia/Kolkata', date(2026, 10, 28))
    assert excluded == ['2026-10-26']
    assert kept.index[-1] == dates[1]
    assert validate_history('TEST', kept)[0].iloc[-1]['Close'] == 100.
    assert pd.isna(partial.loc[dates[2], 'Adj Close'])  # No invented price in source evidence.
    corrupt = partial.copy()
    corrupt.loc[dates[2], 'Dividends'] = -1.
    kept, excluded = closed_history(corrupt, 'Asia/Kolkata', date(2026, 10, 28))
    assert excluded == []
    with pytest.raises(ValueError):
        validate_history('TEST', kept)
    interior = pd.concat([partial, frame.iloc[-1:]])
    kept, excluded = closed_history(interior, 'Asia/Kolkata', date(2026, 10, 28))
    assert excluded == []
    with pytest.raises(ValueError, match='missing price/action'):
        validate_history('TEST', kept)


def test_header_separates_market_date_refresh_time_and_weekly_fx_cutoffs(tmp_path):
    from portfolio_lab.status import banner_html, data_timing_text
    manifest = {'retrieved_utc': '2026-10-24T11:00:00Z', 'fx_latest': '2026-10-23'}
    (tmp_path / 'refresh.json').write_text(json.dumps({'checked_utc': '2026-10-28T10:50:00Z'}))
    header = banner_html('2026-10-26', tmp_path, manifest, '2026-10-21',
                         datetime(2026, 10, 28, 18, tzinfo=timezone.utc))
    assert 'Analysis through' in header and '21 Oct 2026' in header
    assert 'Updated 28 Oct · 16:20 IST' in header
    assert '26 Oct 2026' not in header and 'FX through' not in header and 'Auto refresh' not in header
    details = data_timing_text('2026-10-26', manifest, '2026-10-21')
    assert 'Market prices through 26 Oct 2026' in details
    assert 'Weekly calculation cutoff 21 Oct 2026' in details
    assert 'FX through 23 Oct 2026' in details and 'Wednesday and Saturday at 16:15 IST' in details
    assert 'Update delayed' not in header
    assert 'Data details' not in header


def test_both_investor_modes_show_header_updates_without_data_details():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('from portfolio_lab.page import render\nrender()', default_timeout=40).run()
    app.button(key='pl_enter_global').click().run()
    assert not app.exception
    markup = '\n'.join(item.value for item in [*app.markdown, *app.caption])
    header = next(item.value for item in app.markdown if 'pl-refresh-meta">' in item.value)
    assert 'Analysis through' in header and 'Updated ' in header
    assert 'Auto refresh' not in header and 'Auto refresh' in markup
    assert not any(item.label.lower() == 'data details' for item in app.expander)
    app.radio(key='pl_mode').set_value('Indian Investor — INR').run()
    assert not app.exception
    markup = '\n'.join(item.value for item in [*app.markdown, *app.caption])
    header = next(item.value for item in app.markdown if 'pl-refresh-meta">' in item.value)
    assert 'Analysis through' in header and 'FX through' not in header
    assert 'Weekly calculation cutoff' in markup and 'FX through' in markup
    assert not any(item.label.lower() == 'data details' for item in app.expander)


def candidate(tmp_path):
    for namespace, manifest in [
        ('', {'assets': {'SPY': {'latest_observation': '2026-10-23'}}}),
        ('macro', {'series': {'DGS10': {'latest': '2026-10-22'}, 'CPIAUCSL': {'latest': '2026-09-01'}}}),
        ('india', {'assets': {'nifty-50': {'last': '2026-10-23'}}, 'fx_latest': '2026-10-16'}),
    ]:
        root = tmp_path / namespace
        bundle = root / 'bundle'
        bundle.mkdir(parents=True)
        (root / 'CURRENT').write_text('bundle')
        (bundle / 'manifest.json').write_text(json.dumps(manifest))
    pd.DataFrame({'nifty-50': [100.]}, index=pd.DatetimeIndex(['2026-10-21'], name='Date')).to_csv(
        tmp_path / 'india/bundle/prices.csv')
    return tmp_path


def test_daily_monthly_and_weekly_sources_have_separate_age_limits(tmp_path):
    root = candidate(tmp_path)
    assert validate_freshness(root, today=date(2026, 10, 24))['global/SPY'] == '2026-10-23'
    with pytest.raises(ValueError, match='global/SPY'):
        validate_freshness(root, today=date(2026, 11, 1))
    with pytest.raises(ValueError, match='outside'):
        validate_freshness(root, today=date(2026, 10, 22))


def test_fresh_download_cannot_regress_coverage(tmp_path):
    with pytest.raises(ValueError, match='regress'):
        validate_freshness(candidate(tmp_path), previous={'global/SPY': '2026-10-24'}, today=date(2026, 10, 24))


def test_fresh_sources_do_not_hide_an_old_or_empty_india_common_window(tmp_path):
    root = candidate(tmp_path)
    path = root / 'india/bundle/prices.csv'
    pd.DataFrame({'A': [100.], 'B': [float('nan')]}, index=pd.DatetimeIndex(['2026-10-21'], name='Date')).to_csv(path)
    with pytest.raises(ValueError, match='checkpoint'):
        validate_freshness(root, today=date(2026, 10, 24))
    pd.DataFrame({'A': [100.]}, index=pd.DatetimeIndex(['2026-09-30'], name='Date')).to_csv(path)
    with pytest.raises(ValueError, match='checkpoint'):
        validate_freshness(root, today=date(2026, 10, 24))


def test_schedule_allows_six_hours_and_detects_a_missed_run():
    previous = '2026-10-24T11:00:00+00:00'
    assert not update_delayed(previous, datetime(2026, 10, 28, 16, 44, tzinfo=timezone.utc))
    assert update_delayed(previous, datetime(2026, 10, 28, 16, 45, tzinfo=timezone.utc))
    assert not update_delayed('2026-10-28T12:00:00Z', datetime(2026, 10, 28, 18, tzinfo=timezone.utc))
    # The Saturday publication still covers Monday/Tuesday; no daily alarm.
    assert not update_delayed(previous, datetime(2026, 10, 27, 18, tzinfo=timezone.utc))


def test_missing_key_leaves_the_release_untouched(tmp_path):
    with patch.dict(os.environ, {'FRED_API_KEY': ''}), patch('portfolio_lab.refresh.run_step') as run, \
            patch('portfolio_lab.refresh.publish') as publish:
        with pytest.raises(ValueError, match='FRED_API_KEY'):
            refresh(tmp_path)
    run.assert_not_called()
    publish.assert_not_called()


@pytest.mark.parametrize('failure_step', [0, 1, 2, 3, 4, 5, 6, 7, 8])
def test_collection_tests_or_verifier_failure_cannot_publish(tmp_path, failure_step):
    destination = tmp_path / 'published'
    destination.mkdir()
    marker = destination / 'unchanged'
    marker.write_text('previous release')
    calls = []

    def run(args, env, attempts=1):
        assert env['MONETARIA_PORTFOLIO_STORE'] != str(destination)
        assert Path(env['MONETARIA_PORTFOLIO_TRI']).parent == Path(env['MONETARIA_PORTFOLIO_STORE'])
        calls.append(args)
        if len(calls) - 1 == failure_step:
            raise subprocess.CalledProcessError(1, args)

    with patch.dict(os.environ, {'FRED_API_KEY': 'test-only'}), \
            patch('portfolio_lab.refresh.PORTFOLIO_STORE_DIR', tmp_path / 'staging'), \
            patch('portfolio_lab.refresh.coverage', return_value={}), \
            patch('portfolio_lab.refresh.validate'), \
            patch('portfolio_lab.refresh.validate_freshness', return_value={}), \
            patch('portfolio_lab.refresh.run_step', side_effect=run), \
            patch('portfolio_lab.refresh.publish') as publish:
        with pytest.raises(subprocess.CalledProcessError):
            refresh(destination)
    publish.assert_not_called()
    assert marker.read_text() == 'previous release'
    assert not list((tmp_path / 'staging').iterdir())


def test_one_publication_follows_all_validation_and_uses_new_global_bundle(tmp_path):
    calls = []
    with patch.dict(os.environ, {'FRED_API_KEY': 'test-only'}), \
            patch('portfolio_lab.refresh.PORTFOLIO_STORE_DIR', tmp_path / 'staging'), \
            patch('portfolio_lab.refresh.validate'), \
            patch('portfolio_lab.refresh.validate_freshness', return_value={'global/SPY': '2026-10-23'}), \
            patch('portfolio_lab.refresh.run_step', side_effect=lambda args, env, attempts=1: calls.append(args)), \
            patch('portfolio_lab.refresh.publish') as publish, \
            patch('portfolio_lab.refresh.write_summary'):
        refresh(tmp_path / 'published')
    assert [args[1] for args in calls[:4]] == [
        'portfolio_lab.refresh', 'data.fetchers.portfolio_prices',
        'data.fetchers.portfolio_macro', 'data.fetchers.portfolio_india']
    assert len(calls) == 9  # collection + portfolio tests + four independent verifiers
    publish.assert_called_once()
    assert publish.call_args.kwargs['refresh_metadata']['coverage'] == {'global/SPY': '2026-10-23'}


def test_published_receipt_covers_refresh_metadata_and_detects_tampering(tmp_path):
    from portfolio_lab.deployment import active_root, publish, validate
    source = active_root()
    metadata = {'schema': 1, 'checked_utc': '2026-10-24T11:00:00+00:00'}
    published = publish(tmp_path / 'release', source, refresh_metadata=metadata)
    assert json.loads((published / 'refresh.json').read_text()) == metadata
    validate(published)
    (published / 'refresh.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        validate(published)


def test_benchmark_collection_is_limited_to_four_required_indices(tmp_path):
    from config.portfolio_india_settings import INDEX_IDS
    from tests.test_india_equity_matrix import snapshot
    saved = snapshot()
    by_id = {row['id']: row for row in saved['series']}
    with patch('data.paths.INDIA_STORE_DIR', tmp_path / 'absent'), \
            patch('data.fetchers.india_equity_tri.IndiaTRIFetcher') as source:
        source.return_value.mapping.return_value = 'source-hash'
        source.return_value.history.side_effect = lambda spec, cutoff: by_id[spec['id']]
        collect_tri(tmp_path / 'tri.json', datetime(2026, 10, 10, 10, 45, tzinfo=timezone.utc))
    output = json.loads((tmp_path / 'tri.json').read_text())
    assert {row['id'] for row in output['series']} == set(INDEX_IDS)
    assert source.return_value.history.call_count == 4


def test_workflow_has_twice_weekly_schedule_and_scoped_publication():
    source = (Path(__file__).resolve().parents[1] / '.github/workflows/portfolio_refresh.yml').read_text()
    assert "45 10 * * 3,6" in source
    assert 'workflow_dispatch:' in source
    assert 'repository-publication-${{ github.ref }}' in source
    assert 'python -m portfolio_lab.refresh' in source
    assert 'git add -A -- data/published/portfolio_lab/' in source
    assert 'HEAD:$TARGET_BRANCH' in source
