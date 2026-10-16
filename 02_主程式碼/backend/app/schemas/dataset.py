from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .common import ORMModel


class DatasetOut(ORMModel):
    id: str
    name: str
    description: str | None
    status: str
    source_name: str | None
    sample_count: int
    total_bytes: int
    image_count: int
    size_bytes: int
    metadata_columns: list[str]
    split_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DatasetSampleOut(ORMModel):
    id: str
    dataset_id: str
    display_name: str
    sha256: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    class_index: int | None
    class_name: str | None
    egfr: float | None
    metadata_json: dict[str, Any]
    metadata: dict[str, Any]
    split: str | None
    fold: int | None
    duplicate_of_id: str | None
    is_duplicate: bool
    missing_label: bool
    missing_metadata: bool
    has_mask: bool
    missing_mask: bool
    status: str
    file_url: str
    thumbnail_url: str
    mask_url: str | None


class DatasetImportIssueOut(ORMModel):
    id: str
    dataset_id: str
    display_name: str
    issue_type: str
    error_code: str
    message: str
    sha256: str | None
    size_bytes: int
    created_at: datetime


class DatasetSummary(BaseModel):
    dataset_id: str
    sample_count: int
    total_bytes: int
    classes: dict[str, int]
    splits: dict[str, int]
    folds: dict[str, int]
    unlabeled: int
    duplicates: int
    image_count: int
    total_samples: int
    total_size_bytes: int
    class_distribution: list[dict[str, Any]]
    split_counts: dict[str, int]
    corrupt_count: int
    duplicate_count: int
    missing_label_count: int
    missing_metadata_count: int
    missing_mask_count: int
    is_imbalanced: bool
    warnings: list[str]


class SplitOptions(BaseModel):
    train_ratio: float = Field(default=0.7, ge=0, le=1)
    val_ratio: float = Field(default=0.2, ge=0, le=1)
    test_ratio: float = Field(default=0.1, ge=0, le=1)
    seed: int = 42
    k_folds: int = Field(default=5, ge=0, le=20)
