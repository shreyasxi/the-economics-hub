"""Deployment integrity, fail-closed activation and public snapshot delivery."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest

from portfolio_lab.deployment import active_root, install, publish


@pytest.mark.parametrize('name', ['raw/GILT5YBEES.NS.csv', r'raw\GILT5YBEES.NS.csv'])
def test_india_receipts_resolve_windows_and_linux_paths_identically(name):
    from data.fetchers.portfolio_india import manifest_path
    assert manifest_path(name).parts == ('raw', 'GILT5YBEES.NS.csv')
    assert manifest_path(name).as_posix() == 'raw/GILT5YBEES.NS.csv'


@pytest.mark.parametrize('name', ['../escape', r'raw\..\escape', '/absolute',
                                  r'C:\escape', 'C:escape', r'\\host\share\escape', ''])
def test_india_receipts_reject_unsafe_paths_on_every_platform(name):
    from data.fetchers.portfolio_india import manifest_path
    with pytest.raises(ValueError, match='file path'):
        manifest_path(name)


def test_published_india_manifest_uses_portable_paths():
    from data.paths import PUBLIC_PORTFOLIO_DIR
    root = PUBLIC_PORTFOLIO_DIR / 'india'
    bundle = root / (root / 'CURRENT').read_text().strip()
    manifest = json.loads((bundle / 'manifest.json').read_text())
    assert manifest['files']
    assert all('\\' not in name for name in manifest['files'])
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest


def package(tmp_path, members=None):
    members = members or {'CURRENT': 'global', 'global/manifest.json': '{}',
                          'macro/CURRENT': 'macro', 'india/CURRENT': 'india'}
    receipt = {'schema': 1, 'files': {
        name: hashlib.sha256(content.encode()).hexdigest() for name, content in members.items()}}
    path = tmp_path / 'release.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in members.items():
            # ZipInfo normalises Windows backslashes when built from a name.
            # Preserve the raw member so the unsafe-path test is adversarial
            # on Windows as well as Linux.
            member = zipfile.ZipInfo()
            member.filename = name
            archive.writestr(member, content)
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


def test_real_active_snapshots_export_and_install_in_fresh_store(tmp_path):
    from portfolio_lab.deployment import export
    from data.fetchers.portfolio_prices import snapshot_path, load_bundle
    try:
        snapshot_path()
    except ValueError:
        pytest.skip('Prepared snapshots are unavailable')
    destination = tmp_path / 'release.zip'
    digest = export(destination)
    root = tmp_path / 'clean-store'
    installed = install(destination, digest, root)
    assert active_root(root) == installed
    prices, manifest = load_bundle(snapshot_path(root))
    assert {'SPY', 'BTC', 'USO'} <= set(manifest['assets'])
    assert not prices.empty


def test_public_release_loads_all_three_bundles_in_clean_checkout(tmp_path):
    from data.fetchers.portfolio_prices import load_bundle
    from data.fetchers.portfolio_macro import load as load_macro
    from data.fetchers.portfolio_india import load as load_india
    from portfolio_lab.deployment import _bundle, validate
    source = active_root()
    destination = publish(tmp_path / 'published', source)
    validate(destination)
    assert load_bundle(_bundle(destination))[1]['publication_status'].startswith('Public')
    assert load_macro(_bundle(destination / 'macro'))[0]
    assert not load_india(_bundle(destination / 'india'))[0].empty
    with patch('portfolio_lab.deployment.PUBLIC_PORTFOLIO_DIR', destination), \
            patch('portfolio_lab.deployment.PORTFOLIO_STORE_DIR', tmp_path / 'missing'):
        assert active_root(tmp_path / 'missing') == destination
    before = (destination / 'deployment.json').read_bytes()
    with patch('portfolio_lab.deployment.validate', side_effect=ValueError('Bad India data')):
        with pytest.raises(ValueError):
            publish(destination, source)
    assert (destination / 'deployment.json').read_bytes() == before
