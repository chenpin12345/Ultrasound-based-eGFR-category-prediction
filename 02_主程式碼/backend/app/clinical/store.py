from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..core.config import get_settings

_migration_lock = threading.Lock()


def root() -> Path:
    path = get_settings().clinical_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def uid() -> str:
    return uuid.uuid4().hex


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def migrate():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    with _migration_lock:
        cfg = Config()
        cfg.set_main_option('script_location', str(Path(__file__).parent / 'migrations'))
        engine = create_engine('sqlite:///' + str(root() / 'clinical.sqlite3'))
        with engine.begin() as connection:
            cfg.attributes['connection'] = connection
            command.upgrade(cfg, 'head')
        engine.dispose()


@contextmanager
def read_transaction():
    """Read-only snapshot; authentication must not reserve SQLite's write lock."""
    path=get_settings().clinical_dir/'clinical.sqlite3'
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=15)
    db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN')
        yield db
    finally:
        db.close()


@contextmanager
def transaction():
    db = sqlite3.connect(root() / 'clinical.sqlite3', timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def audit(db, actor, action, entity):
    db.execute('INSERT INTO audit VALUES(?,?,?,?,?)', (uid(), actor, action, entity, time.time()))


def rowdict(row):
    if row is None:
        return None
    value = dict(row)
    for key in ('payload', 'result', 'profile', 'snapshot', 'roles'):
        if key in value and value[key] is not None:
            value[key] = json.loads(value[key])
    return value


def managed(relative: str) -> Path:
    base = root().resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise ValueError('Invalid managed path')
    return target
