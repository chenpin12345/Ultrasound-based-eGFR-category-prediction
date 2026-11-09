"""路徑、資料庫與共用工具。資料都放在網站自己的 `資料/`，輸出放 `輸出/`。"""
from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

BACKUP_EVERY = timedelta(minutes=30)
BACKUP_KEEP = 30


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / '資料'

    @property
    def images(self) -> Path:
        return self.data / '影像'

    @property
    def backups(self) -> Path:
        return self.data / '備份'

    @property
    def database(self) -> Path:
        return self.data / '圈選.sqlite3'

    @property
    def output(self) -> Path:
        return self.root / '輸出'


def default_root() -> Path:
    """打包後是執行檔所在資料夾；開發時是 `醫師圈選網站/`。"""
    if os.environ.get('CIRCLE_ROOT'):
        return Path(os.environ['CIRCLE_ROOT'])
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def frontend_dist() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'dist'  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / 'frontend' / 'dist'


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS structures (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    meaning TEXT NOT NULL,
    color TEXT NOT NULL,
    line TEXT NOT NULL DEFAULT 'solid',
    kind TEXT NOT NULL,
    sort INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL,
    file TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    side TEXT,
    status TEXT NOT NULL DEFAULT 'todo',
    shapes_json TEXT NOT NULL DEFAULT '[]',
    states_json TEXT NOT NULL DEFAULT '{}',
    grade INTEGER,
    grade_unsure INTEGER NOT NULL DEFAULT 0,
    grade_reason TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    discuss INTEGER NOT NULL DEFAULT 0,
    unusable_reason TEXT NOT NULL DEFAULT '',
    circler TEXT NOT NULL DEFAULT '',
    seconds REAL NOT NULL DEFAULT 0,
    updated_at TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS images_seq ON images (seq);
"""


class Store:
    """每次操作開一個連線：FastAPI 的同步路由在執行緒池裡跑。"""

    def __init__(self, paths: Paths):
        self.paths = paths
        for folder in (paths.images, paths.backups, paths.output):
            folder.mkdir(parents=True, exist_ok=True)
        self._last_backup: datetime | None = None
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.paths.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def get_meta(self, key: str, default: str = '') -> str:
        with self.connect() as db:
            row = db.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
        return row['value'] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute('INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value', (key, value))

    def backup(self, force: bool = False) -> Path | None:
        """定時備份資料庫；影像不用備份，可以從主系統重新匯出。"""
        now = datetime.now()
        if not force and self._last_backup and now - self._last_backup < BACKUP_EVERY:
            return None
        self._last_backup = now
        target = self.paths.backups / f'圈選-{now:%Y%m%d-%H%M%S}.sqlite3'
        source = sqlite3.connect(self.paths.database)
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
            source.close()
        for old in sorted(self.paths.backups.glob('圈選-*.sqlite3'))[:-BACKUP_KEEP]:
            old.unlink()
        return target
