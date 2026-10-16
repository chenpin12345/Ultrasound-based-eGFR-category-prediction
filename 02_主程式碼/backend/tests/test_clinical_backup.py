from pathlib import Path
import sqlite3
import pytest
from scripts.clinical_backup import copy_snapshot,verify

def test_backup_copies_consistent_database_and_exact_images(tmp_path):
    source=tmp_path/'clinical';source.mkdir()
    with sqlite3.connect(source/'clinical.sqlite3') as db:
        db.execute('CREATE TABLE version(value TEXT)');db.execute("INSERT INTO version VALUES('original')")
    (source/'frames').mkdir();(source/'frames'/'original.jpg').write_bytes(b'original bytes')
    backup=tmp_path/'backup';copy_snapshot(source,backup);verify(backup)
    with sqlite3.connect(backup/'clinical.sqlite3') as db:assert db.execute('SELECT value FROM version').fetchone()[0]=='original'
    assert (backup/'frames'/'original.jpg').read_bytes()==b'original bytes'
    (backup/'frames'/'original.jpg').write_bytes(b'changed')
    with pytest.raises(RuntimeError):verify(backup)

def test_backup_never_overwrites_existing_destination(tmp_path):
    with pytest.raises(FileExistsError):copy_snapshot(tmp_path/'source',tmp_path)
