"""Compatible clinical-only CLI; includes the separate immutable PDF root."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import uuid
import shutil
import sqlite3
from contextlib import closing

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from backend.app.core.config import AppSettings
from scripts.workspace_backup import backup, restore, upgrade_legacy, offline, entries, sha, verify as verify_v2


def copy_snapshot(source, target):
    """Legacy embedded-root API retained for existing callers, never the new CLI."""
    if target.exists():
        raise FileExistsError(target)
    settings = AppSettings()
    if source.resolve() == settings.clinical_dir.resolve() and not settings.reports_dir.resolve().is_relative_to(source.resolve()):
        raise RuntimeError('Use the clinical backup CLI to include the external report root')
    target.mkdir(parents=True, exist_ok=False)
    with closing(sqlite3.connect((source / 'clinical.sqlite3').resolve().as_uri() + '?mode=ro', uri=True)) as db, closing(sqlite3.connect(target / 'clinical.sqlite3')) as out:
        db.backup(out)
        out.execute('PRAGMA journal_mode=DELETE')
        if out.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('SQLite integrity check failed')
    for name in ('frames', 'bundles', 'reports'):
        if (source / name).is_dir():
            list(entries(source / name))  # Reject linked content before copying.
            shutil.copytree(source / name, target / name)
    manifest = {p.relative_to(target).as_posix(): sha(p) for p in entries(target)}
    (target / 'backup-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def verify(folder):
    manifest = json.loads((folder / 'backup-manifest.json').read_text(encoding='utf-8'))
    try:
        if manifest.get('version') == 2:
            return verify_v2(folder)
        actual = {p.relative_to(folder).as_posix() for p in entries(folder)} - {'backup-manifest.json'}
        if actual != set(manifest):
            raise ValueError('Missing or unlisted artifact')
        for relative, expected in manifest.items():
            path = folder / relative
            if not path.resolve().is_relative_to(folder.resolve()) or sha(path) != expected:
                raise ValueError('Backup integrity mismatch')
    except (ValueError, OSError) as exc:
        raise RuntimeError('Backup integrity check failed') from exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    settings = AppSettings()
    offline(settings)
    source = args.destination.resolve()
    if args.restore:
        manifest = json.loads((source / 'backup-manifest.json').read_text(encoding='utf-8'))
        if manifest.get('version') != 2:
            source = upgrade_legacy(source, settings.runtime_dir / 'backup-upgrade' / uuid.uuid4().hex)
        elif manifest.get('scope') != 'clinical':
            raise ValueError('Use workspace_backup.py for research/full restore')
        result = restore(source, settings)
    else:
        result = backup(source, settings, 'clinical')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
