from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready", index=True)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    source_name: Mapped[str | None] = mapped_column(String(255))
    source_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_columns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    split_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    samples: Mapped[list["DatasetSample"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")
    import_issues: Mapped[list["DatasetImportIssue"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    training_jobs: Mapped[list["TrainingJob"]] = relationship(back_populates="dataset")
    jobs: Mapped[list["Job"]] = relationship(back_populates="dataset")

    __table_args__ = (
        CheckConstraint("sample_count >= 0", name="ck_dataset_sample_count"),
        CheckConstraint("total_bytes >= 0", name="ck_dataset_total_bytes"),
    )


class DatasetSample(Base):
    __tablename__ = "dataset_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    class_index: Mapped[int | None] = mapped_column(Integer, index=True)
    class_name: Mapped[str | None] = mapped_column(String(100), index=True)
    egfr: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    split: Mapped[str | None] = mapped_column(String(20), index=True)
    fold: Mapped[int | None] = mapped_column(Integer, index=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024))
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_samples.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="samples")
    duplicate_of: Mapped["DatasetSample | None"] = relationship(remote_side=[id])
    mask: Mapped["DatasetMask | None"] = relationship(
        back_populates="sample", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("dataset_id", "relative_path", name="uq_sample_dataset_path"),
        CheckConstraint("size_bytes >= 0", name="ck_sample_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_sample_dimensions"),
        CheckConstraint("class_index IS NULL OR (class_index >= 0 AND class_index <= 4)", name="ck_sample_class"),
        CheckConstraint("fold IS NULL OR fold >= 0", name="ck_sample_fold"),
    )


class DatasetMask(Base):
    """A validated mask managed alongside one imported dataset sample."""

    __tablename__ = "dataset_masks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    sample_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_samples.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    sample: Mapped[DatasetSample] = relationship(back_populates="mask")

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_dataset_mask_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_dataset_mask_dimensions"),
    )


class DatasetImportIssue(Base):
    """Safe, durable audit record for a rejected import candidate.

    The rejected bytes and source path are deliberately not retained.  Only a
    sanitized basename, a digest, size, and controlled error fields are stored.
    """

    __tablename__ = "dataset_import_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="import_issues")

    __table_args__ = (CheckConstraint("size_bytes >= 0", name="ck_dataset_issue_size"),)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    workspace_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    stop_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list["JobEvent"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    training_job: Mapped["TrainingJob | None"] = relationship(back_populates="job", uselist=False)
    dataset: Mapped["Dataset | None"] = relationship(back_populates="jobs")

    __table_args__ = (CheckConstraint("progress >= 0 AND progress <= 100", name="ck_job_progress"),)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="progress")
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job: Mapped[Job] = relationship(back_populates="events")

    __table_args__ = (Index("ix_job_events_job_cursor", "job_id", "id"),)


class TrainingJob(Base, TimestampMixin):
    __tablename__ = "training_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    architecture: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    device: Mapped[str] = mapped_column(String(32), nullable=False, default="cpu")
    current_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_epochs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_metric: Mapped[float | None] = mapped_column(Float)
    best_checkpoint_path: Mapped[str | None] = mapped_column(String(1024))
    last_checkpoint_path: Mapped[str | None] = mapped_column(String(1024))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(back_populates="training_job")
    dataset: Mapped[Dataset] = relationship(back_populates="training_jobs")
    metrics: Mapped[list["TrainingMetric"]] = relationship(back_populates="training_job", cascade="all, delete-orphan")
    models: Mapped[list["ModelRecord"]] = relationship(back_populates="source_training_job")


class TrainingMetric(Base):
    __tablename__ = "training_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_job_id: Mapped[str] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    split: Mapped[str] = mapped_column(String(20), nullable=False)
    loss: Mapped[float | None] = mapped_column(Float)
    accuracy: Mapped[float | None] = mapped_column(Float)
    precision: Mapped[float | None] = mapped_column(Float)
    recall: Mapped[float | None] = mapped_column(Float)
    f1: Mapped[float | None] = mapped_column(Float)
    learning_rate: Mapped[float | None] = mapped_column(Float)
    confusion_matrix: Mapped[list[list[int]] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    training_job: Mapped[TrainingJob] = relationship(back_populates="metrics")
    __table_args__ = (UniqueConstraint("training_job_id", "epoch", "split", name="uq_metric_epoch_split"),)


class ModelRecord(Base, TimestampMixin):
    __tablename__ = "model_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    task: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    architecture: Mapped[str] = mapped_column(String(64), nullable=False)
    class_count: Mapped[int] = mapped_column(Integer, nullable=False)
    class_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_columns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    preprocessing: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    weights_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    metadata_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready", index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source_training_job_id: Mapped[str | None] = mapped_column(ForeignKey("training_jobs.id", ondelete="SET NULL"))

    source_training_job: Mapped[TrainingJob | None] = relationship(back_populates="models")

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_model_name_version"),
        CheckConstraint("class_count > 0", name="ck_model_class_count"),
        CheckConstraint("size_bytes >= 0", name="ck_model_size"),
        Index("ix_model_active_task", "task", "active"),
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class EvaluationRecord(Base):
    __tablename__ = 'evaluation_records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    model_id: Mapped[str] = mapped_column(ForeignKey('model_records.id', ondelete='RESTRICT'), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='RESTRICT'), unique=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(ForeignKey('datasets.id', ondelete='RESTRICT'), nullable=False)
    retry_of_id: Mapped[str | None] = mapped_column(ForeignKey('evaluation_records.id', ondelete='RESTRICT'))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='queued')
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    cohort_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint('sample_count > 0 AND completed_count >= 0 AND completed_count <= sample_count', name='ck_evaluation_counts'),
        CheckConstraint("status IN ('queued','running','completed','partial','failed','stopped','interrupted')", name='ck_evaluation_status'),
        Index('ix_evaluation_model','model_id','created_at'),
    )


class EvaluationPrediction(Base):
    __tablename__ = 'evaluation_predictions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey('evaluation_records.id', ondelete='RESTRICT'), nullable=False)
    sample_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('evaluation_id','sample_id',name='uq_evaluation_sample'),)


class MaskProvenance(Base):
    __tablename__ = 'mask_provenance'
    mask_id: Mapped[str] = mapped_column(ForeignKey('dataset_masks.id', ondelete='RESTRICT'), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    __table_args__ = (CheckConstraint("kind IN ('independent_reference','model_generated','unknown')", name='ck_mask_provenance_kind'),)
