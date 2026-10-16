"""Offline versioned backups and journaled multi-root restore.

Backup manifests contain relative artifacts, never restoration destinations.
Destinations come exclusively from the local application settings. Old roots
are preserved on restore; a crash blocks startup until explicit recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import uuid
from contextlib import closing
from functools import wraps
from inspect import signature
import threading

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from backend.app.core.config import AppSettings

GROUPS = {'research': ('research', 'models', 'reference_features'),
          'clinical': ('clinical', 'reports'),
          'full': ('research', 'models', 'reference_features', 'clinical', 'reports')}

_local_operations = threading.local()


def guard_operation(function):
    """Cross-process startup interlock; a crashed lock requires explicit recovery."""
    @wraps(function)
    def guarded(*args, **kwargs):
        settings = signature(function).bind(*args, **kwargs).arguments['settings']
        lock = settings.runtime_dir / 'maintenance-operation.json'
        owned = getattr(_local_operations, 'locks', set())
        if str(lock) in owned:
            return function(*args, **kwargs)
        no_links(lock)
        lock.parent.mkdir(parents=True, exist_ok=True)
        import psutil
        if lock.exists() and function.__name__ == 'recover':
            prior = json.loads(lock.read_text(encoding='utf-8'))
            try:
                process = psutil.Process(prior['pid'])
                if abs(process.create_time() - prior['create_time']) <= 1:
                    raise RuntimeError('Maintenance owner is still alive; do not interrupt it')
            except psutil.NoSuchProcess:
                pass
            lock.rename(lock.with_name('maintenance-abandoned-' + uuid.uuid4().hex + '.json'))
        token = uuid.uuid4().hex
        with lock.open('x', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'create_time': psutil.Process().create_time(),
                       'operation': function.__name__, 'token': token}, stream)
            stream.flush(); os.fsync(stream.fileno())
        _local_operations.locks = owned | {str(lock)}
        try:
            return function(*args, **kwargs)
        finally:
            _local_operations.locks = owned
            if json.loads(lock.read_text(encoding='utf-8')).get('token') == token:
                lock.unlink()
    return guarded


def roots(settings):
    return {'research': settings.data_dir, 'models': settings.models_dir,
            'reference_features': settings.reference_features_dir,
            'clinical': settings.clinical_dir, 'reports': settings.reports_dir}


def io_path(path):
    """Extended Windows syntax only for already validated absolute I/O paths.

    Keep ordinary paths in manifests and containment checks. No OS-wide long
    path setting is changed and this does not grant access to another root.
    """
    value=str(path.resolve())
    if os.name=='nt' and not value.startswith('\\\\?\\'):
        value='\\\\?\\UNC\\'+value[2:] if value.startswith('\\\\') else '\\\\?\\'+value
    return Path(value)


def sha(path):
    with io_path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def no_links(path):
    for part in (path, *path.parents):
        physical=io_path(part)
        if physical.exists() and physical.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Linked backup paths are not supported: ' + str(part))


def rename_path(source,target):
    source,target=Path(source),Path(target)
    if os.name=='nt' and max(len(str(source)),len(str(target)))>=240:
        return io_path(source).rename(io_path(target))
    return source.rename(target)


def entries(folder):
    no_links(folder)
    for entry in sorted(folder.iterdir()):
        no_links(entry)
        if entry.is_dir():
            yield from entries(entry)
        elif entry.is_file():
            yield entry


def offline(settings):
    import psutil
    for proc in psutil.process_iter(['pid', 'cmdline']):
        if proc.pid == os.getpid():
            continue
        command = ' '.join(proc.info['cmdline'] or []).lower()
        if str(CODE).lower() in command and any(
            token in command for token in ('run_server.py', 'uvicorn', 'spawn_main', 'app.py')
        ):
            raise RuntimeError('Stop project writers and receiver children before backup/restore')


def write_json(path, value):
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def copy_root(source, target, database_name=None):
    target.mkdir(parents=True, exist_ok=False)
    if database_name and not (source / database_name).is_file():
        raise RuntimeError('Required database is missing')
    if not source.exists():
        return
    for path in entries(source):
        relative = path.relative_to(source)
        if database_name and relative.as_posix() in {database_name + '-wal', database_name + '-shm'}:
            continue
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if database_name and relative.as_posix() == database_name:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db, closing(sqlite3.connect(dest)) as out:
                db.backup(out)
                out.execute('PRAGMA journal_mode=DELETE')
                if out.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Database integrity check failed')
        else:
            shutil.copy2(path, dest)
            if sha(path) != sha(dest):
                raise RuntimeError('Copy integrity mismatch')


def check_roots(mapping):
    resolved = list(mapping.values())
    for i, root in enumerate(resolved):
        no_links(root)
        if not root.is_absolute():
            raise ValueError('Roots must be absolute')
        for other in resolved[i + 1:]:
            if root.is_relative_to(other) or other.is_relative_to(root):
                raise ValueError('Backup roots must not overlap; configure separate clinical/reports roots')


@guard_operation
def backup(destination, settings, scope='full'):
    offline(settings)
    mapping = {k: roots(settings)[k].resolve() for k in GROUPS[scope]}
    check_roots(mapping)
    destination = destination.resolve()
    no_links(destination)
    if any(destination.is_relative_to(p) or p.is_relative_to(destination) for p in mapping.values()):
        raise ValueError('Backup destination overlaps live data')
    destination.mkdir(parents=True, exist_ok=False)
    for key, source in mapping.items():
        copy_root(source, destination / key, {'research': 'isu_ai.sqlite3', 'clinical': 'clinical.sqlite3'}.get(key))
    items = {p.relative_to(destination).as_posix(): {'sha256': sha(p), 'size': p.stat().st_size}
             for p in entries(destination)}
    write_json(destination / 'backup-manifest.json', {'version': 2, 'scope': scope, 'roots': list(mapping), 'files': items})
    verify(destination)
    return {'scope': scope, 'files': len(items)}


def verify(folder):
    folder = folder.resolve()
    no_links(folder)
    manifest = json.loads((folder / 'backup-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 2 or manifest.get('scope') not in GROUPS:
        raise ValueError('Unsupported backup format; do not partially restore a legacy backup')
    if manifest.get('roots') != list(GROUPS[manifest['scope']]):
        raise ValueError('Incomplete logical backup unit')
    actual = {p.relative_to(folder).as_posix() for p in entries(folder)} - {'backup-manifest.json'}
    if actual != set(manifest['files']):
        raise ValueError('Unlisted or missing backup artifacts')
    for relative, expected in manifest['files'].items():
        path = folder / relative
        if Path(relative).is_absolute() or not path.resolve().is_relative_to(folder) or Path(relative).parts[0] not in manifest['roots']:
            raise ValueError('Invalid backup path')
        if path.stat().st_size != expected['size'] or sha(path) != expected['sha256']:
            raise ValueError('Backup integrity mismatch: ' + relative)
    for root, filename in [('research', 'isu_ai.sqlite3'), ('clinical', 'clinical.sqlite3')]:
        if root not in manifest['roots']:
            continue
        database = folder / root / filename
        if not database.is_file():
            raise ValueError('Missing database')
        # Verified snapshots have no uncommitted WAL. Immutable mode prevents
        # a read-only integrity check from creating new -wal/-shm artifacts.
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Database relational integrity failed')
    return manifest


def journal_path(settings):
    return settings.runtime_dir / 'restore-journal.json'


def upgrade_legacy(folder, destination):
    """Verify and convert v1 clinical backup without changing original PDF bytes."""
    import re
    folder = folder.resolve()
    expected = json.loads((folder / 'backup-manifest.json').read_text(encoding='utf-8'))
    if not isinstance(expected, dict) or 'version' in expected:
        raise ValueError('Not a v1 clinical backup')
    actual = {p.relative_to(folder).as_posix() for p in entries(folder)} - {'backup-manifest.json'}
    if actual != set(expected):
        raise ValueError('Legacy backup has missing or unlisted artifacts')
    for relative, checksum in expected.items():
        path = folder / relative
        if not path.resolve().is_relative_to(folder) or sha(path) != checksum:
            raise ValueError('Legacy backup integrity failed')
    destination.mkdir(parents=True, exist_ok=False)
    clinical, reports = destination / 'clinical', destination / 'reports'
    clinical.mkdir(); reports.mkdir()
    with closing(sqlite3.connect((folder / 'clinical.sqlite3').as_uri() + '?mode=ro', uri=True)) as db:
        for relative in expected:
            parts = Path(relative).parts
            if parts[0] == 'reports':
                if len(parts) != 3 or not re.fullmatch(r'v[1-9][0-9]*(?:-void)?\.(?:pdf|sha256)', parts[2]):
                    raise ValueError('Unrecognized legacy report artifact')
                row = db.execute('SELECT exams.kind, exams.id FROM reports JOIN exams ON exams.id=reports.exam_id WHERE reports.id=?', (parts[1],)).fetchone()
                if not row or row[0] not in {'patient', 'demo'} or any(not re.fullmatch(r'[A-Za-z0-9-]{1,64}', value) for value in (row[1], parts[1])):
                    raise ValueError('Orphan legacy report must be investigated')
                target = reports / row[0] / row[1] / parts[1] / parts[2]
            elif parts[0] in {'frames', 'bundles', 'clinical.sqlite3'}:
                target = clinical / relative
            else:
                raise ValueError('Unknown legacy clinical artifact')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / relative, target)
    items = {p.relative_to(destination).as_posix(): {'sha256': sha(p), 'size': p.stat().st_size} for p in entries(destination)}
    write_json(destination / 'backup-manifest.json', {'version': 2, 'scope': 'clinical', 'roots': list(GROUPS['clinical']), 'files': items})
    verify(destination)
    return destination


@guard_operation
def restore(folder, settings):
    offline(settings)
    manifest = verify(folder)
    mapping = {k: roots(settings)[k].resolve() for k in manifest['roots']}
    check_roots(mapping)
    journal = journal_path(settings)
    if journal.exists():
        raise RuntimeError('Unfinished restore exists; recover it before retrying')
    if any(folder.resolve().is_relative_to(p) or p.is_relative_to(folder.resolve()) for p in mapping.values()):
        raise ValueError('Restore source overlaps live data')
    identifier = uuid.uuid4().hex
    records = []
    for key, target in mapping.items():
        stage = target.with_name(target.name + '.restore-' + identifier)
        previous = target.with_name(target.name + '.before-restore-' + identifier)
        no_links(stage); no_links(previous)
        if io_path(stage).exists() or io_path(previous).exists():
            raise ValueError('Restore staging conflict')
        shutil.copytree(io_path(folder / key), io_path(stage))
        for relative, expected in manifest['files'].items():
            if Path(relative).parts[0] == key and sha(stage / Path(*Path(relative).parts[1:])) != expected['sha256']:
                raise ValueError('Restore staging integrity failed')
        records.append({'root': key, 'stage': str(stage), 'previous': str(previous), 'had_target': io_path(target).exists()})
    state = {'version': 1, 'id': identifier, 'records': records, 'phase': 'publishing'}
    journal.parent.mkdir(parents=True, exist_ok=True)
    write_json(journal, state)
    try:
        for record in records:
            target = mapping[record['root']]
            if io_path(target).exists():
                rename_path(target,record['previous'])
            rename_path(record['stage'],target)
        state['phase'] = 'complete'
        write_json(journal, state)
        journal.rename(journal.with_name('restore-complete-' + identifier + '.json'))
    except BaseException:
        recover(settings)
        raise
    return {'restored_roots': list(mapping), 'previous_data_retained': True}


@guard_operation
def recover(settings):
    offline(settings)
    journal = journal_path(settings)
    if not journal.exists():
        return {'recovered': True, 'no_pending_restore': True}
    state = json.loads(journal.read_text(encoding='utf-8'))
    identifier = state['id']
    if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('Invalid recovery identifier')
    mapping = roots(settings)
    for record in reversed(state['records']):
        target = mapping[record['root']].resolve()
        previous = target.with_name(target.name + '.before-restore-' + identifier)
        stage = target.with_name(target.name + '.restore-' + identifier)
        if str(previous) != record['previous'] or str(stage) != record['stage']:
            raise ValueError('Restore settings changed; do not guess recovery targets')
        no_links(target); no_links(previous); no_links(stage)
        if io_path(previous).exists():
            if io_path(target).exists():
                rename_path(target,target.with_name(target.name + '.failed-restore-' + identifier))
            rename_path(previous,target)
        elif not record['had_target'] and io_path(target).exists() and not io_path(stage).exists():
            rename_path(target,target.with_name(target.name + '.failed-restore-' + identifier))
    journal.rename(journal.with_name('restore-recovered-' + identifier + '.json'))
    return {'recovered': True, 'partial_artifacts_retained': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['backup', 'verify', 'restore', 'recover'])
    parser.add_argument('destination', type=Path, nargs='?')
    parser.add_argument('--scope', choices=list(GROUPS), default='full')
    args = parser.parse_args()
    settings = AppSettings()
    if args.command == 'recover':
        result = recover(settings)
    elif args.destination is None:
        parser.error('destination is required')
    elif args.command == 'verify':
        manifest = verify(args.destination)
        result = {'verified_files': len(manifest['files']), 'scope': manifest['scope']}
    elif args.command == 'backup':
        result = backup(args.destination, settings, args.scope)
    else:
        result = restore(args.destination, settings)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
