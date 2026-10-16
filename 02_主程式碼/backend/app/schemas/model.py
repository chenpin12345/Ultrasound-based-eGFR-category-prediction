from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .common import ORMModel


class ModelManifest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1", min_length=1, max_length=64)
    task: str = Field(pattern="^(classification|segmentation)$")
    architecture: str = Field(min_length=1, max_length=64)
    class_count: int = Field(ge=1, le=1000)
    class_names: list[str]
    metadata_columns: list[str] = Field(default_factory=list)
    preprocessing: dict[str, Any] = Field(default_factory=dict)
    train_stats: dict[str, dict[str, float]] | None = None


class ModelRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("模型名稱不可為空白。")
        return normalized


class ModelEvaluationSummary(BaseModel):
    selection: Literal['latest_created_not_best'] = 'latest_created_not_best'
    evaluation_id: str | None = None
    status: str = 'not_evaluated'
    reason: str | None = '尚未建立本機評估；不以 0% 代替。'
    weight_sha256: str | None = None
    configuration_sha256: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    split: str | None = None
    scope: str | None = None
    sample_count: int | None = None
    evaluated_sample_count: int | None = None
    completed_at: datetime | None = None
    metric_version: str | None = None
    unit: Literal['fraction'] = 'fraction'
    metrics: dict[str, float | None] = Field(default_factory=dict)


class ModelOut(ORMModel):
    id: str
    name: str
    version: str
    task: str
    architecture: str
    class_count: int
    class_names: list[str]
    metadata_columns: list[str]
    preprocessing: dict[str, Any]
    sha256: str
    size_bytes: int
    status: str
    active: bool
    source_training_job_id: str | None
    download_url: str
    created_at: datetime
    updated_at: datetime
    evaluation_summary: ModelEvaluationSummary = Field(default_factory=ModelEvaluationSummary)


class ModelConfiguration(BaseModel):
    status: Literal['consistent', 'unverified']
    reason: str | None
    sha256: str | None
    train_stats: dict[str, dict[str, float]] | None


class ModelClassSchema(BaseModel):
    version: str
    task: str
    class_count: int
    class_names: list[str]
    sha256: str
    status: Literal['consistent', 'unverified']


class ModelSource(BaseModel):
    kind: Literal['local_training', 'imported']
    status: Literal['unverified','verified_record']
    reason: str
    training_job_id: str | None


class ModelReference(BaseModel):
    kind: Literal['default', 'research_job', 'clinical_plan', 'evaluation']
    id: str
    name: str
    status: str


class ModelTrainingRecord(BaseModel):
    job_id: str
    training_job_id: str
    status: str
    selection_metric: Literal['validation_loss']
    selection_direction: Literal['minimize']
    recorded_best_validation_loss: float | None
    completed_epoch: int
    checkpoint_source: dict[str, Any] = Field(default_factory=dict)
    note: str


class ModelDetail(ModelOut):
    configuration: ModelConfiguration
    class_schema: ModelClassSchema
    source_info: ModelSource
    training_record: ModelTrainingRecord | None
    references: list[ModelReference]
