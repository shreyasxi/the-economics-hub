"""Package and install the three validated active snapshots, never old runs.

Private HTTPS delivery uses a separately configured SHA-256. Installation is
immutable; a single atomic pointer activates Global, macro and India together.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import uuid
import zipfile

from data.paths import PORTFOLIO_STORE_DIR

MAX_BYTES = 256 * 1024 * 1024


def active_root(root=PORTFOLIO_STORE_DIR):
    root = Path(root)
    pointer = root / "DEPLOYED_CURRENT"
    if not pointer.exists():
        return root
    name = pointer.read_text().strip()
    if not re.fullmatch(r"[a-f0-9]{64}", name):
        raise ValueError("Invalid deployment pointer")
    installed = root / "deployments" / name
    if not installed.is_dir():
        raise ValueError("Deployment snapshot is missing")
    return installed


def _bundle(root):
    name = (Path(root) / "CURRENT").read_text().strip()
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("Invalid snapshot pointer")
    return Path(root) / name


def validate(root):
    from data.fetchers.portfolio_prices import load_bundle
    from data.fetchers.portfolio_macro import load as load_macro
    from data.fetchers.portfolio_india import load as load_india
    root = Path(root)
    load_bundle(_bundle(root))
    load_macro(_bundle(root / "macro"))
    load_india(_bundle(root / "india"))


def export(destination, root=PORTFOLIO_STORE_DIR):
    """Export active source evidence and derived data needed by all loaders."""
    root = active_root(root)
    validate(root)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        release = Path(temporary)
        for namespace in ("", "macro", "india"):
            source = _bundle(root / namespace)
            target = release / namespace
            target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target / source.name)
            (target / "CURRENT").write_text(source.name)
        files = sorted(p for p in release.rglob("*") if p.is_file())
        if any(p.is_symlink() for p in release.rglob("*")):
            raise ValueError("Snapshot symlinks are unsupported")
        receipt = {"schema": 1, "files": {
            p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}}
        (release / "deployment.json").write_text(json.dumps(receipt, indent=2) + "\n")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(release.rglob("*")):
                if p.is_file():
                    archive.write(p, p.relative_to(release).as_posix())
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(digest + "\n")
    return digest


def install(archive_path, expected_sha256, root=PORTFOLIO_STORE_DIR):
    """Reject malformed packages; previous deployment stays active on failure."""
    root = Path(root)
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("A lowercase SHA-256 digest is required")
    archive_path = Path(archive_path)
    if archive_path.stat().st_size > MAX_BYTES:
        raise ValueError("Deployment archive exceeds size limit")
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("Deployment archive checksum mismatch")
    installed = root / "deployments" / expected_sha256
    installed.parent.mkdir(parents=True, exist_ok=True)
    if not installed.exists():
        with tempfile.TemporaryDirectory(dir=installed.parent) as temporary:
            unpacked = Path(temporary) / "snapshot"
            unpacked.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                entries = archive.infolist()
                names = [e.filename for e in entries]
                if len(names) != len(set(names)) or sum(e.file_size for e in entries) > MAX_BYTES:
                    raise ValueError("Duplicate members or oversized deployment archive")
                for entry in entries:
                    path = PurePosixPath(entry.filename)
                    if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                            or not path.parts or stat.S_ISLNK(entry.external_attr >> 16)):
                        raise ValueError("Unsafe deployment archive member")
                    archive.extract(entry, unpacked)
            receipt = json.loads((unpacked / "deployment.json").read_text())
            actual = {p.relative_to(unpacked).as_posix() for p in unpacked.rglob("*")
                      if p.is_file() and p.name != "deployment.json"}
            if receipt.get("schema") != 1 or set(receipt.get("files", {})) != actual:
                raise ValueError("Deployment file inventory mismatch")
            for name, digest in receipt["files"].items():
                if hashlib.sha256((unpacked / name).read_bytes()).hexdigest() != digest:
                    raise ValueError("Deployment file checksum mismatch")
            validate(unpacked)
            unpacked.rename(installed)
    else:
        validate(installed)
    pointer = root / ("DEPLOYED_CURRENT-" + uuid.uuid4().hex + ".tmp")
    pointer.write_text(expected_sha256)
    os.replace(str(pointer), str(root / "DEPLOYED_CURRENT"))
    return installed


def download(url, expected_sha256, root=PORTFOLIO_STORE_DIR):
    """Fetch a configured deployment package, never market sources on reruns."""
    import requests
    from urllib.parse import urlsplit
    if urlsplit(url).scheme != "https":
        raise ValueError("Deployment download requires HTTPS")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("A lowercase SHA-256 digest is required")
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "snapshot.zip"
        # Reject redirects: credentials in a signed URL must not reach another host.
        with requests.get(url, stream=True, timeout=(10, 60), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError("Deployment download failed")
            total = 0
            with path.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("Deployment download exceeds size limit")
                    handle.write(chunk)
        return install(path, expected_sha256, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--install", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--download", action="store_true", help="Use PORTFOLIO_SNAPSHOT_URL and PORTFOLIO_SNAPSHOT_SHA256 from the environment")
    parser.add_argument("--root", type=Path, default=PORTFOLIO_STORE_DIR)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.export:
        print("SHA-256:", export(args.export, args.root))
    if args.install:
        if not args.sha256:
            parser.error("--install requires --sha256")
        install(args.install, args.sha256, args.root)
    if args.download:
        url = os.environ.get('PORTFOLIO_SNAPSHOT_URL', '')
        digest = os.environ.get('PORTFOLIO_SNAPSHOT_SHA256', '')
        if not url or not digest:
            parser.error('Configure PORTFOLIO_SNAPSHOT_URL and PORTFOLIO_SNAPSHOT_SHA256')
        try:
            download(url, digest, args.root)
        except Exception:
            # Provider exceptions may contain a signed URL or authentication token.
            parser.exit(1, 'Private snapshot download or validation failed; previous data retained.\n')
    if args.validate:
        validate(active_root(args.root))
        print("Global, macro and India snapshots validated")


if __name__ == "__main__":
    main()
