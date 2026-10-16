from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from .common import ORMModel


class JobCreate(BaseModel):
    kind: Literal["process", "masks", "features", "inference", "quick_analysis"]
    dataset_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class JobAction(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class JobOut(ORMModel):
    id: str
    dataset_id: str | None
    kind: str
    status: str
    progress: float
    config_json: dict[str, Any]
    result_json: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    stop_requested: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobEventOut(ORMModel):
    id: int
    job_id: str
    event_type: str
    data_json: dict[str, Any]
    created_at: datetime


class TrainingCreate(BaseModel):
    dataset_id: str
    model_name: str = Field(min_length=1, max_length=200, validation_alias=AliasChoices("model_name", "name"))
    architecture: str
    classification_mode: Literal["multiclass", "coral"] = "multiclass"
    mode: Literal["quick", "advanced"] = "quick"
    epochs: int = Field(default=30, ge=1, le=10_000)
    batch_size: int = Field(default=8, ge=2, le=1024)
    learning_rate: float = Field(default=2e-4, gt=0, le=1)
    optimizer: Literal["adam", "adamw", "sgd"] = "adamw"
    weight_decay: float = Field(default=1e-4, ge=0, le=1)
    scheduler: Literal["none", "plateau", "reduce_on_plateau", "cosine", "step"] | None = "reduce_on_plateau"
    early_stopping: bool = True
    patience: int = Field(default=10, ge=1)
    seed: int = Field(default=42, validation_alias=AliasChoices("seed", "random_seed"), ge=0)
    device: Literal["auto", "cpu", "cuda"] = "auto"
    class_weights: bool = True
    augmentation: bool = Field(default=True, validation_alias=AliasChoices("augmentation", "data_augmentation"))
    k_fold: int | None = Field(default=None, validation_alias=AliasChoices("k_fold", "k_folds"), ge=1, le=20)
    checkpoint_interval: int = Field(default=1, ge=1, le=10_000)
    resume_checkpoint: str | None = Field(default=None, validation_alias=AliasChoices("resume_checkpoint", "resume_from"))
    train_ratio: float = Field(default=0.7, ge=0, le=1)
    val_ratio: float = Field(default=0.2, validation_alias=AliasChoices("val_ratio", "validation_ratio"), ge=0, le=1)
    test_ratio: float = Field(default=0.1, ge=0, le=1)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("architecture", mode="before")
    @classmethod
    def normalize_architecture(cls, value: object) -> str:
        normalized = str(value).strip().lower().replace("_", "-")
        aliases = {
            "mobilenet-v2": "mobilenetv2",
            "efficientnet-b3": "efficientnet_b3",
            "mlp-resnet18": "mlp-resnet18",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"resnet18", "mobilenetv2", "efficientnet_b3", "mlp-resnet18"}:
            raise ValueError("不支援的分類模型架構。")
        return normalized

    @model_validator(mode="after")
    def validate_combination(self) -> "TrainingCreate":
        if abs(self.train_ratio + self.val_ratio + self.test_ratio - 1.0) > 1e-6:
            raise ValueError("train / validation / test 比例總和必須為 1。")
        if self.val_ratio <= 0:
            raise ValueError("validation 比例必須大於 0。")
        if self.classification_mode == "coral" and self.architecture not in {"resnet18", "mlp-resnet18"}:
            raise ValueError("CORAL 僅支援 ResNet18 與 MLP-ResNet18。")
        if self.k_fold == 1:
            self.k_fold = None
        return self


class TrainingOut(ORMModel):
    id: str
    job_id: str
    dataset_id: str
    model_name: str
    architecture: str
    status: str
    config_json: dict[str, Any]
    device: str
    current_epoch: int
    total_epochs: int
    current_batch: int
    total_batches: int
    best_metric: float | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class TrainingMetricOut(ORMModel):
    id: int
    training_job_id: str
    epoch: int
    split: str
    loss: float | None
    accuracy: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    learning_rate: float | None
    confusion_matrix: list[list[int]] | None
    created_at: datetime
