"""Versioned, import-light machine-learning contracts.

This module is deliberately free of torch/numpy imports so the API can start on
machines where the optional ML runtime has not been installed yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = 1
CLASS_COUNT = 5
CLASS_NAMES: dict[int, str] = {
    0: "eGFR < 15",
    1: "eGFR 15–29",
    2: "eGFR 30–59",
    3: "eGFR 60–89",
    4: "eGFR ≥ 90",
}
# Names used by the legacy directory layout and raw model UI.
LEGACY_CLASS_NAMES: dict[int, str] = {
    0: "eGFR -15",
    1: "eGFR 15-29",
    2: "eGFR 30-59",
    3: "eGFR 60-89",
    4: "eGFR 90-",
}
CLASS_DIR_TO_INDEX: dict[str, int] = {
    **{name: index for index, name in LEGACY_CLASS_NAMES.items()},
    **{name: index for index, name in CLASS_NAMES.items()},
}
CLASS_SHORT_NAMES = ("<15", "15–29", "30–59", "60–89", "≥90")

# Inference-only schemes. Training keeps its existing CLASS_COUNT/defaults.
CLASSIFICATION_SCHEMES = {
    2: {0: "eGFR < 60", 1: "eGFR ≥ 60"},
    3: {0: "eGFR < 30", 1: "eGFR 30–59", 2: "eGFR ≥ 60"},
    5: CLASS_NAMES,
}


def classification_labels(class_count: int) -> dict[int, str]:
    if class_count not in CLASSIFICATION_SCHEMES:
        raise ValueError("Classification supports 2, 3 or 5 classes.")
    return dict(CLASSIFICATION_SCHEMES[class_count])


def remap_five_class(index: int, class_count: int) -> int:
    if index not in range(5):
        raise ValueError("Invalid original five-class label.")
    return {2: (0, 0, 0, 1, 1), 3: (0, 0, 1, 2, 2), 5: (0, 1, 2, 3, 4)}[class_count][index]

IMAGE_SIZE = (224, 224)
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
METADATA_FIELDS = ("age", "Length_px", "Contrast_Ratio", "has_diabetes")
BINARY_METADATA_FIELDS = frozenset({"has_diabetes"})
FEATURE_CSV_FIELDS = (
    "image_name",
    "age",
    "gender",
    "Length_px",
    "Entropy",
    "Contrast_Ratio",
    "has_diabetes",
)
INFERENCE_CSV_FIELDS = (
    "file",
    "predicted_index",
    "predicted_class",
    "confidence",
)
DEFAULT_TRAIN_STATS: dict[str, dict[str, float]] = {
    "age": {"mean": 64.91591591591592, "std": 11.620004224714933},
    "Length_px": {"mean": 619.5902873070673, "std": 88.34058061971373},
    "Contrast_Ratio": {"mean": 0.8805828618474454, "std": 0.1729770181087057},
}
SUPPORTED_CLASSIFIERS = (
    "resnet18",
    "mobilenetv2",
    "efficientnetb3",
    "mlp-resnet18",
)


class ContractError(ValueError):
    """Raised when persisted model/data metadata violates the fixed contract."""


def canonical_classifier_name(value: str) -> tuple[str, bool]:
    """Return the base architecture and whether a legacy CORAL prefix was used."""

    normalized = str(value).strip().lower().replace("_", "-")
    coral = normalized.startswith("coral-")
    if coral:
        normalized = normalized.removeprefix("coral-")
    compact = normalized.replace("-", "")
    aliases = {
        "resnet": "resnet18",
        "resnet18": "resnet18",
        "mobilenetv2": "mobilenetv2",
        "efficientnetb3": "efficientnetb3",
        "mlp": "mlp-resnet18",
        "mlpresnet18": "mlp-resnet18",
    }
    try:
        return aliases[compact], coral
    except KeyError as exc:
        raise ContractError(f"Unsupported architecture: {value!r}") from exc


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def class_index_from_egfr(value: float) -> int:
    if value < 15:
        return 0
    if value < 30:
        return 1
    if value < 60:
        return 2
    if value < 90:
        return 3
    return 4


def legacy_class_dir(index: int) -> str:
    try:
        return LEGACY_CLASS_NAMES[int(index)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"Invalid class index: {index!r}") from exc


def validate_train_stats(
    stats: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, float]]:
    source = stats or DEFAULT_TRAIN_STATS
    normalized: dict[str, dict[str, float]] = {}
    for field in METADATA_FIELDS:
        if field in BINARY_METADATA_FIELDS:
            continue
        if field not in source:
            raise ContractError(f"Training statistics are missing {field!r}.")
        try:
            mean = float(source[field]["mean"])
            std = float(source[field]["std"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"Invalid statistics for {field!r}.") from exc
        if std < 0:
            raise ContractError(f"Standard deviation for {field!r} cannot be negative.")
        normalized[field] = {"mean": mean, "std": std}
    return normalized


def normalize_metadata(
    values: Mapping[str, Any] | None,
    stats: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[float]:
    """Return metadata in the exact legacy training order.

    Missing continuous values use their training mean (normalizing to zero), and
    missing binary values use zero.
    """

    values = values or {}
    checked = validate_train_stats(stats)
    output: list[float] = []
    for field in METADATA_FIELDS:
        if field in BINARY_METADATA_FIELDS:
            raw = values.get(field, 0.0)
            try:
                output.append(float(raw or 0.0))
            except (TypeError, ValueError) as exc:
                raise ContractError(f"Invalid binary metadata {field!r}: {raw!r}") from exc
            continue
        field_stats = checked[field]
        raw = values.get(field, field_stats["mean"])
        if raw in (None, ""):
            raw = field_stats["mean"]
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise ContractError(f"Invalid metadata {field!r}: {raw!r}") from exc
        output.append((number - field_stats["mean"]) / (field_stats["std"] + 1e-10))
    return output


@dataclass(frozen=True)
class ModelMetadata:
    architecture: str
    dataset_id: str | None = None
    created_at: str = ""
    best_metric: Mapping[str, Any] | None = None
    coral: bool = False
    model_version: str = "1"
    contract_version: int = CONTRACT_VERSION
    class_names: Mapping[int, str] | None = None
    legacy_class_names: Mapping[int, str] | None = None
    metadata_fields: Sequence[str] = METADATA_FIELDS
    train_stats: Mapping[str, Mapping[str, float]] | None = None
    image_size: Sequence[int] = IMAGE_SIZE
    image_mode: str = "RGB"
    normalization_mean: Sequence[float] = IMAGENET_MEAN
    normalization_std: Sequence[float] = IMAGENET_STD
    class_count: int = CLASS_COUNT

    def __post_init__(self) -> None:
        architecture, prefixed_coral = canonical_classifier_name(self.architecture)
        object.__setattr__(self, "architecture", architecture)
        if prefixed_coral:
            object.__setattr__(self, "coral", True)
        labels = classification_labels(self.class_count)
        if self.class_names is not None and set(self.class_names) != set(labels):
            raise ContractError("Class indices do not match the model class count.")
        if tuple(self.metadata_fields) != METADATA_FIELDS:
            raise ContractError("Model metadata field order does not match the fixed contract.")
        if tuple(self.image_size) != IMAGE_SIZE or self.image_mode != "RGB":
            raise ContractError("Model image preprocessing does not match RGB 224x224.")
        validate_train_stats(self.train_stats)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at or utc_now_iso()
        payload["class_names"] = dict(self.class_names or classification_labels(self.class_count))
        payload["legacy_class_names"] = dict(self.legacy_class_names or (LEGACY_CLASS_NAMES if self.class_count == 5 else classification_labels(self.class_count)))
        payload["metadata_fields"] = list(METADATA_FIELDS)
        payload["train_stats"] = validate_train_stats(self.train_stats)
        payload["image_size"] = list(IMAGE_SIZE)
        payload["normalization_mean"] = list(IMAGENET_MEAN)
        payload["normalization_std"] = list(IMAGENET_STD)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelMetadata":
        class_names = payload.get("class_names")
        legacy_names = payload.get("legacy_class_names")
        if isinstance(class_names, Sequence) and not isinstance(class_names, (str, bytes)):
            class_names = {index: str(value) for index, value in enumerate(class_names)}
        preprocessing = payload.get("preprocessing")
        preprocessing = preprocessing if isinstance(preprocessing, Mapping) else {}
        metadata_fields = payload.get("metadata_fields") or payload.get("metadata_columns")
        metadata_fields = tuple(metadata_fields) if metadata_fields else METADATA_FIELDS
        architecture, prefixed_coral = canonical_classifier_name(str(payload["architecture"]))
        return cls(
            architecture=architecture,
            class_count=int(payload.get("class_count", CLASS_COUNT)),
            dataset_id=payload.get("dataset_id"),
            created_at=str(payload.get("created_at") or ""),
            best_metric=payload.get("best_metric"),
            coral=bool(payload.get("coral", prefixed_coral)),
            model_version=str(payload.get("model_version", payload.get("version", "1"))),
            contract_version=int(payload.get("contract_version", CONTRACT_VERSION)),
            class_names={int(k): str(v) for k, v in class_names.items()} if class_names else None,
            legacy_class_names={int(k): str(v) for k, v in legacy_names.items()} if legacy_names else None,
            metadata_fields=metadata_fields,
            train_stats=payload.get("train_stats"),
            image_size=tuple(payload.get("image_size") or preprocessing.get("size") or IMAGE_SIZE),
            image_mode=str(payload.get("image_mode") or preprocessing.get("mode") or "RGB"),
            normalization_mean=tuple(
                payload.get("normalization_mean") or preprocessing.get("mean") or IMAGENET_MEAN
            ),
            normalization_std=tuple(
                payload.get("normalization_std") or preprocessing.get("std") or IMAGENET_STD
            ),
        )


def metadata_path_for_weights(weights_path: str | Path) -> Path:
    weights_path = Path(weights_path)
    return weights_path.parent / "model_metadata.json"
