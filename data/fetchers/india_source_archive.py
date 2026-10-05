"""Immutable source bytes and update journals for official India GVA/IIP."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


class Archive:
    def __init__(self, root, previous):
        self.root = Path(root)
        self.run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid4().hex[:8]
        self.path = self.root / 'runs' / (self.run_id + '.json')
        current = self.root / 'current.json'
        bootstrap = self.root / 'bootstrap.json'
        self.previous = json.loads(current.read_text()) if current.exists() else (
            json.loads(bootstrap.read_text()) if bootstrap.exists() else None)
        if self.previous:
            for source in self.previous['sources']:
                if sha256((self.root/source['raw']).read_bytes()) != source['sha256']:
                    raise ValueError('Previous official source checksum mismatch; review required')
        # This snapshot is sealed BEFORE requesting the new official vintage.
        self.manifest = dict(run_id=self.run_id, fetched_at=datetime.now(timezone.utc).isoformat(),
                             status='pending', previous=self.previous, previous_records=previous, sources=[])
        write_json(self.path, self.manifest)
        write_json(self.root / 'status.json', dict(run_id=self.run_id,status='pending'))

    def retain(self, blob, url, request=None, role=None):
        checksum = sha256(blob)
        path = self.root / 'raw' / checksum
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if sha256(path.read_bytes()) != checksum:
                raise ValueError('Archived official source checksum mismatch')
        else:
            path.write_bytes(blob)
        source = dict(url=url, request=request, role=role, sha256=checksum,
                      raw=str(path.relative_to(self.root)), retrieved_at=datetime.now(timezone.utc).isoformat())
        self.manifest['sources'].append(source)
        write_json(self.path, self.manifest)
        return source

    def finish(self, status, **details):
        self.manifest.update(status=status, **details)
        write_json(self.path, self.manifest)
        write_json(self.root / 'status.json', dict(run_id=self.run_id,status=status,**details))
        if status == 'accepted':
            # Keep only a reference to the old run, not an exponentially growing chain.
            current = {k:v for k,v in self.manifest.items() if k not in ('previous', 'previous_records')}
            write_json(self.root / 'current.json', current)


def read_connection(db):
    """Read a live WAL when present, or a standalone committed SQLite snapshot."""
    import sqlite3
    path = Path(db).resolve()
    # A committed WAL-mode DB without its runtime sidecars cannot be opened
    # read-only on older SQLite. There is no WAL to ignore in this case.
    suffix = '' if Path(str(path)+'-wal').exists() else '&immutable=1'
    return sqlite3.connect(f'file:{path}?mode=ro{suffix}', uri=True)
