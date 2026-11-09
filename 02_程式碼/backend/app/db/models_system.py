from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import SystemBase


class LocalSession(SystemBase):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf: Mapped[str] = mapped_column(String(64))
    boot_id: Mapped[str] = mapped_column(String(32))
    created: Mapped[float] = mapped_column(Float)
    expires: Mapped[float] = mapped_column(Float)
    revoked: Mapped[float | None] = mapped_column(Float, nullable=True)


class Person(SystemBase):
    """醫師與操作者名單。沒有帳號與密碼，只用來記錄是誰做的。"""

    __tablename__ = 'people'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))  # physician / operator
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(32))


class Setting(SystemBase):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(32))


class Job(SystemBase):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    target: Mapped[str] = mapped_column(String(120), default='')
    status: Mapped[str] = mapped_column(String(16), index=True)  # queued running stopping stopped completed failed interrupted
    progress: Mapped[float] = mapped_column(Float, default=0)
    message: Mapped[str] = mapped_column(String(200), default='')
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    result_json: Mapped[str] = mapped_column(Text, default='{}')
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_of: Mapped[str | None] = mapped_column(String(32), nullable=True)


class JobEvent(SystemBase):
    __tablename__ = 'job_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'))
    type: Mapped[str] = mapped_column(String(40))
    data_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[str] = mapped_column(String(32))

    __table_args__ = (Index('ix_job_events_job_id_id', 'job_id', 'id'),)


class AuditEntry(SystemBase):
    __tablename__ = 'audit_log'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str] = mapped_column(String(40), default='')
    target_id: Mapped[str] = mapped_column(String(80), default='')
    detail_json: Mapped[str] = mapped_column(Text, default='{}')
    result: Mapped[str] = mapped_column(String(16), default='成功')


class TrashGroup(SystemBase):
    """單一回收桶。entries_json 記錄被移入的物件：[{db, table, id, label}]。"""

    __tablename__ = 'trash_groups'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(200))
    entries_json: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(200), default='')
    created_by: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(16), default='trashed')  # trashed / restored / purged
    closed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
