"""Deployment integrity, fail-closed activation and private URL handling."""
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch
import zipfile

import pytest

from portfolio_lab.deployment import active_root, download, install


def package(tmp_path, members=None):
    members = members or {'CURRENT': 'global', 'global/manifest.json': '{}',
                          'macro/CURRENT': 'macro', 'india/CURRENT': 'india'}
    receipt = {'schema': 1, 'files': {
        name: hashlib.sha256(content.encode()).hexdigest() for name, content in members.items()}}
    path = tmp_path / 'release.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in members.items():
            archive.writestr(name, content)
        archive.writestr('deployment.json', json.dumps(receipt))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_validated_package_activates_as_one_immutable_root(tmp_path):
    path, digest = package(tmp_path)
    root = tmp_path / 'store'
    with patch('portfolio_lab.deployment.validate') as check:
        installed = install(path, digest, root)
    check.assert_called_once()
    assert active_root(root) == installed
    assert (root / 'DEPLOYED_CURRENT').read_text() == digest
    assert (installed / 'macro/CURRENT').read_text() == 'macro'
    assert (installed / 'india/CURRENT').read_text() == 'india'
    with patch('portfolio_lab.deployment.validate') as check:
        assert install(path, digest, root) == installed
    check.assert_called_once_with(installed)


def test_failed_validation_preserves_previous_activation(tmp_path):
    path, digest = package(tmp_path)
    root = tmp_path / 'store'
    root.mkdir()
    before = 'a' * 64
    (root / 'DEPLOYED_CURRENT').write_text(before)
    with patch('portfolio_lab.deployment.validate', side_effect=ValueError('Bad India bundle')):
        with pytest.raises(ValueError, match='Bad India'):
            install(path, digest, root)
    assert (root / 'DEPLOYED_CURRENT').read_text() == before
    assert not (root / 'deployments' / digest).exists()


def test_checksum_rejects_before_any_activation(tmp_path):
    path, _ = package(tmp_path)
    root = tmp_path / 'store'
    with pytest.raises(ValueError, match='checksum'):
        install(path, '0' * 64, root)
    assert not root.exists()


@pytest.mark.parametrize('member', ['../escape', '/absolute', 'global\\escape'])
def test_archive_paths_cannot_escape_installation(tmp_path, member):
    path, digest = package(tmp_path, {member: 'malicious'})
    root = tmp_path / 'store'
    with pytest.raises(ValueError, match='Unsafe'):
        install(path, digest, root)
    assert not (root / 'DEPLOYED_CURRENT').exists()
    assert not (root / 'deployments' / 'escape').exists()


def test_file_inventory_and_individual_checksums_are_verified(tmp_path):
    path, _ = package(tmp_path)
    with zipfile.ZipFile(path, 'a') as archive:
        archive.writestr('extra.csv', 'unlisted')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='inventory'):
        install(path, digest, tmp_path / 'store')
    path, _ = package(tmp_path)
    with zipfile.ZipFile(path) as archive:
        members = {e.filename: archive.read(e) for e in archive.infolist()}
    members['CURRENT'] = b'changed'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='file checksum'):
        install(path, digest, tmp_path / 'store')


def test_download_requires_https_and_pinned_checksum(tmp_path):
    with patch('requests.get') as get:
        with pytest.raises(ValueError, match='HTTPS'):
            download('http://private.example/snapshot', '0' * 64, tmp_path)
        with pytest.raises(ValueError, match='SHA-256'):
            download('https://private.example/snapshot', '', tmp_path)
    get.assert_not_called()


def test_private_download_installs_verified_package_without_redirects(tmp_path):
    path, digest = package(tmp_path)
    response = Mock(status_code=200)
    response.iter_content.return_value = [path.read_bytes()]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with patch('requests.get', return_value=response) as get, patch('portfolio_lab.deployment.validate'):
        result = download('https://private.example/snapshot?token=private', digest, tmp_path / 'store')
    assert result == active_root(tmp_path / 'store')
    assert get.call_args.kwargs['allow_redirects'] is False


def test_bootstrap_download_is_cached_and_failure_does_not_leak_url():
    from streamlit.testing.v1 import AppTest
    from portfolio_lab.bootstrap import _install
    _install.clear()
    with patch.dict('os.environ', {'PORTFOLIO_SNAPSHOT_URL': 'https://private.example?token=hidden',
                                  'PORTFOLIO_SNAPSHOT_SHA256': '0' * 64}), \
            patch('portfolio_lab.bootstrap.download', return_value=Path('/private/installed')) as fetch:
        app = AppTest.from_string('from portfolio_lab.bootstrap import ensure_snapshot\nensure_snapshot()').run()
        app.run()
        assert not app.exception
        assert fetch.call_count == 1
    _install.clear()
    with patch.dict('os.environ', {'PORTFOLIO_SNAPSHOT_URL': 'https://private.example?token=hidden',
                                  'PORTFOLIO_SNAPSHOT_SHA256': '0' * 64}), \
            patch('portfolio_lab.bootstrap.download', side_effect=ValueError('token=hidden')):
        app = AppTest.from_string('from portfolio_lab.bootstrap import ensure_snapshot\nensure_snapshot()').run()
        assert not app.exception
        assert app.warning and 'hidden' not in app.warning[0].value
    _install.clear()


def test_real_active_snapshots_export_and_install_in_fresh_store(tmp_path):
    from portfolio_lab.deployment import export
    from data.fetchers.portfolio_prices import snapshot_path, load_bundle
    try:
        snapshot_path()
    except ValueError:
        pytest.skip('Private prepared snapshots are not present in public CI')
    destination = tmp_path / 'release.zip'
    digest = export(destination)
    root = tmp_path / 'clean-store'
    installed = install(destination, digest, root)
    assert active_root(root) == installed
    prices, manifest = load_bundle(snapshot_path(root))
    assert {'SPY', 'BTC', 'USO'} <= set(manifest['assets'])
    assert not prices.empty
