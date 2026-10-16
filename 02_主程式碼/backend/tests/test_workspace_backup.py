import json
import sqlite3
from pathlib import Path
from contextlib import closing

import pytest

from backend.app.core.config import AppSettings
from scripts import workspace_backup as backup


@pytest.fixture
def layout(tmp_path, monkeypatch):
    settings = AppSettings(data_dir=tmp_path / 'research', models_dir=tmp_path / 'models',
                           clinical_dir=tmp_path / 'clinical', reports_dir=tmp_path / 'reports',
                           reference_features_dir=tmp_path / 'features', runtime_dir=tmp_path / 'runtime', _env_file=None)
    monkeypatch.setattr(backup, 'offline', lambda settings: None)
    for path in backup.roots(settings).values():
        path.mkdir()
    for folder, name in [(settings.data_dir, 'isu_ai.sqlite3'), (settings.clinical_dir, 'clinical.sqlite3')]:
        with closing(sqlite3.connect(folder / name)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)')
            db.execute("INSERT INTO sample VALUES(1,'baseline')")
    for folder in backup.roots(settings).values():
        (folder / 'artifact.bin').write_bytes(b'original')
    return settings


@pytest.mark.parametrize('scope', ['research', 'clinical', 'full'])
def test_backup_and_real_restore_all_logical_units(tmp_path, layout, scope):
    dest = tmp_path / 'backup'
    backup.backup(dest, layout, scope)
    before = {p.relative_to(dest).as_posix() for p in backup.entries(dest)}
    backup.verify(dest)
    assert {p.relative_to(dest).as_posix() for p in backup.entries(dest)} == before
    for key in backup.GROUPS[scope]:
        (backup.roots(layout)[key] / 'artifact.bin').write_bytes(b'changed')
    result = backup.restore(dest, layout)
    assert result['previous_data_retained']
    for key in backup.GROUPS[scope]:
        root = backup.roots(layout)[key]
        assert (root / 'artifact.bin').read_bytes() == b'original'
        assert next(root.parent.glob(root.name + '.before-restore-*')).joinpath('artifact.bin').read_bytes() == b'changed'
    assert not backup.journal_path(layout).exists()


def test_corruption_and_unlisted_files_rejected(tmp_path, layout):
    dest = tmp_path / 'backup'
    backup.backup(dest, layout)
    (dest / 'reports/artifact.bin').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='integrity'):
        backup.restore(dest, layout)
    assert (layout.reports_dir / 'artifact.bin').read_bytes() == b'original'


def test_partial_multi_root_publication_rolls_back(tmp_path, layout, monkeypatch):
    dest = tmp_path / 'backup'
    backup.backup(dest, layout)
    for folder in backup.roots(layout).values():
        (folder / 'artifact.bin').write_bytes(b'new live data')
    real_rename = Path.rename
    failed = False
    def interrupted(path, target):
        nonlocal failed
        if '.restore-' in path.name and Path(target) == layout.clinical_dir and not failed:
            failed = True
            raise OSError('simulated publication interruption')
        return real_rename(path, target)
    monkeypatch.setattr(Path, 'rename', interrupted)
    with pytest.raises(OSError, match='interruption'):
        backup.restore(dest, layout)
    for folder in backup.roots(layout).values():
        assert (folder / 'artifact.bin').read_bytes() == b'new live data'
    assert not backup.journal_path(layout).exists()


def test_unfinished_restore_blocks_application_initialization(layout):
    layout.runtime_dir.mkdir()
    backup.journal_path(layout).write_text('{}')
    with pytest.raises(RuntimeError, match='Unfinished multi-root'):
        layout.ensure_directories()


def test_manifest_cannot_choose_destination(tmp_path, layout):
    dest = tmp_path / 'backup'
    backup.backup(dest, layout)
    manifest_path = dest / 'backup-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['roots'].append('../../outside')
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='logical backup unit'):
        backup.verify(dest)


def test_legacy_report_upgrade_preserves_pdf_and_db_relationship(tmp_path):
    legacy = tmp_path / 'legacy'; legacy.mkdir()
    with closing(sqlite3.connect(legacy / 'clinical.sqlite3')) as db, db:
        db.execute('CREATE TABLE exams(id TEXT PRIMARY KEY, kind TEXT)')
        db.execute('CREATE TABLE reports(id TEXT PRIMARY KEY, exam_id TEXT)')
        db.execute("INSERT INTO exams VALUES('exam1','demo')")
        db.execute("INSERT INTO reports VALUES('report1','exam1')")
    pdf = legacy / 'reports/report1/v2.pdf'; pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b'original immutable PDF bytes')
    manifest = {p.relative_to(legacy).as_posix(): backup.sha(p) for p in backup.entries(legacy)}
    (legacy / 'backup-manifest.json').write_text(json.dumps(manifest))
    converted = backup.upgrade_legacy(legacy, tmp_path / 'converted')
    backup.verify(converted)
    assert (converted / 'reports/demo/exam1/report1/v2.pdf').read_bytes() == pdf.read_bytes()


def test_backup_rejects_overlapping_roots(tmp_path, layout):
    layout.reports_dir = layout.clinical_dir / 'reports'
    with pytest.raises(ValueError, match='overlap'):
        backup.backup(tmp_path / 'backup', layout)


def test_backup_blocks_startup_and_cleans_its_lock(tmp_path, layout, monkeypatch):
    copy_root = backup.copy_root
    def checked_copy(*args, **kwargs):
        with pytest.raises(RuntimeError, match='Offline backup/restore'):
            layout.ensure_directories()
        return copy_root(*args, **kwargs)
    monkeypatch.setattr(backup, 'copy_root', checked_copy)
    backup.backup(tmp_path / 'backup', layout)
    assert not (layout.runtime_dir / 'maintenance-operation.json').exists()


def test_recovery_cannot_clear_an_active_owner_lock(layout):
    import os
    import psutil
    layout.runtime_dir.mkdir()
    lock = layout.runtime_dir / 'maintenance-operation.json'
    lock.write_text(json.dumps({'pid': os.getpid(), 'create_time': psutil.Process().create_time()}))
    with pytest.raises(RuntimeError, match='still alive'):
        backup.recover(layout)
    assert lock.exists()
