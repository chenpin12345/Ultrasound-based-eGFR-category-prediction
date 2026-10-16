from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings
from .base import Base


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    connect_args = {"check_same_thread": False, "timeout": 30} if settings.resolved_database_url.startswith("sqlite") else {}
    engine = create_engine(settings.resolved_database_url, connect_args=connect_args, pool_pre_ping=True)
    if settings.resolved_database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option('script_location', str(Path(__file__).parent / 'migrations'))
    with get_engine().begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')


def db_healthcheck() -> bool:
    with get_session_factory()() as session:
        session.execute(text("SELECT 1"))
    return True


def get_db():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine_cache() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
