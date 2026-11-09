"""三個 SQLite 資料庫的連線與遷移（遷移作法沿用腎超新：程式內呼叫 Alembic）。"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings

DATABASES = ('system', 'research', 'clinical')
MIGRATIONS = Path(__file__).resolve().parents[2] / 'migrations'


@lru_cache(maxsize=None)
def get_engine(name: str) -> Engine:
    if name not in DATABASES:
        raise KeyError(name)
    path = get_settings().database_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f'sqlite:///{path.as_posix()}', connect_args={'check_same_thread': False, 'timeout': 30})

    @event.listens_for(engine, 'connect')
    def _pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.close()

    return engine


@lru_cache(maxsize=None)
def _factory(name: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(name), autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(name: str) -> Iterator[Session]:
    session = _factory(name)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def system_db() -> Iterator[Session]:
    with session_scope('system') as s:
        yield s


def research_db() -> Iterator[Session]:
    with session_scope('research') as s:
        yield s


def migrate_all() -> None:
    from alembic import command
    from alembic.config import Config

    for name in DATABASES:
        config = Config()
        config.set_main_option('script_location', str(MIGRATIONS / name))
        with get_engine(name).begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')


def healthcheck() -> bool:
    for name in DATABASES:
        with get_engine(name).connect() as c:
            c.execute(text('SELECT 1'))
    return True


def dispose_all() -> None:
    """關閉所有連線並清除快取（測試切換工作區、備份前使用）。"""
    if get_engine.cache_info().currsize:
        for name in DATABASES:
            get_engine(name).dispose()
    get_engine.cache_clear()
    _factory.cache_clear()
