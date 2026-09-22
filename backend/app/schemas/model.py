from __future__ import annotations

from datetime import datetime
from typing import Any

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
