"""Cached, batched classification inference and downloadable reports."""

from __future__ import annotations

import csv
import json
import threading
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .contracts import (
    CLASS_NAMES,
    INFERENCE_CSV_FIELDS,
    METADATA_FIELDS,
    ModelMetadata,
    metadata_path_for_weights,
    normalize_metadata,
    classification_labels,
)
from .features import metadata_by_name
from .models import (
    MLDependencyError,
    single_image_probabilities,
    image_transform,
    load_classifier,
)


class ModelUnavailableError(FileNotFoundError):
    pass


@dataclass
class InferenceItem:
    file: str
    predicted_index: int
    predicted_class: str
    confidence: float
    probabilities: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "predicted_index": self.predicted_index,
            "predicted_class": self.predicted_class,
            "confidence": self.confidence,
            "probabilities": self.probabilities,
        }


@dataclass
class InferenceReport:
    model_path: Path
    architecture: str
    items: list[InferenceItem] = field(default_factory=list)
    csv_path: Path | None = None
    zip_path: Path | None = None
    class_names: dict[int, str] = field(default_factory=lambda: dict(CLASS_NAMES))
    class_count: int = 5

    def summary(self) -> dict[str, Any]:
        counts = {name: 0 for name in self.class_names.values()}
        confidence: dict[str, list[float]] = {name: [] for name in self.class_names.values()}
        for item in self.items:
            # Legacy manifests can carry valid display-label spellings that are
            # not byte-for-byte equal to the current canonical labels. Preserve
            # those results instead of failing the whole report during summary.
            counts[item.predicted_class] = counts.get(item.predicted_class, 0) + 1
            confidence.setdefault(item.predicted_class, []).append(item.confidence)
        return {
            "total": len(self.items),
            "counts": counts,
            "average_confidence": {
                name: (sum(values) / len(values) if values else 0.0)
                for name, values in confidence.items()
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "architecture": self.architecture,
            "class_count": self.class_count,
            "class_names": [self.class_names[i] for i in range(self.class_count)],
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary(),
            "csv": self.csv_path.name if self.csv_path else None,
            "zip": self.zip_path.name if self.zip_path else None,
        }


def read_model_metadata(
    weights_path: str | Path,
    *,
    architecture: str | None = None,
    coral: bool = False,
    train_stats: Mapping[str, Mapping[str, float]] | None = None,
) -> ModelMetadata:
    path = metadata_path_for_weights(weights_path)
    if path.exists():
        with path.open("r", encoding="utf-8-sig") as handle:
            return ModelMetadata.from_dict(json.load(handle))
    if not architecture:
        raise ModelUnavailableError(
            "模型缺少 model_metadata.json；外部模型必須指定 architecture。"
        )
    return ModelMetadata(architecture=architecture, coral=coral, train_stats=train_stats)


def discover_models(models_root: str | Path) -> list[dict[str, Any]]:
    root = Path(models_root)
    if not root.exists():
        return []
    result: list[dict[str, Any]] = []
    for weights in sorted(root.rglob("*.pth")):
        if weights.name == "last_checkpoint.pth":
            continue
        metadata_path = metadata_path_for_weights(weights)
        metadata = None
        error = None
        if metadata_path.exists():
            try:
                with metadata_path.open("r", encoding="utf-8-sig") as handle:
                    metadata = ModelMetadata.from_dict(json.load(handle)).to_dict()
            except Exception as exc:
                error = str(exc)
        result.append(
            {
                "name": weights.parent.name if weights.name == "best_model.pth" else weights.stem,
                "weights": str(weights.relative_to(root)),
                "metadata": metadata,
                "available": metadata is not None,
                "error": error or (None if metadata else "尚未安裝模型資訊"),
            }
        )
    return result


class ModelCache:
    def __init__(self, max_items: int = 3):
        self.max_items = max(1, int(max_items))
        self._items: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
        self._lock = threading.RLock()

    def _key(self, path: Path, metadata: ModelMetadata, device: Any) -> tuple[Any, ...]:
        stat = path.stat()
        return (
            str(path.resolve()),
            stat.st_mtime_ns,
            stat.st_size,
            metadata.architecture,
            metadata.coral,
            metadata.class_count,
            str(device),
        )

    def get(self, path: str | Path, metadata: ModelMetadata, device: Any):
        path = Path(path)
        if not path.is_file():
            raise ModelUnavailableError(f"Model weights are unavailable: {path.name}")
        key = self._key(path, metadata, device)
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
            model = load_classifier(
                path,
                metadata.architecture,
                device=device,
                coral=metadata.coral,
                num_classes=metadata.class_count,
            )
            self._items[key] = model
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
            return model

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


DEFAULT_MODEL_CACHE = ModelCache()


def write_inference_csv(path: str | Path, items: Iterable[InferenceItem], class_names: Mapping[int, str] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        extras = (["class_count"] + [f"probability_{i}:{class_names[i]}" for i in range(len(class_names))]) if class_names else []
        writer = csv.DictWriter(handle, fieldnames=[*INFERENCE_CSV_FIELDS, *extras])
        writer.writeheader()
        for item in items:
            payload = item.to_dict()
            row = {field: payload[field] for field in INFERENCE_CSV_FIELDS}
            if class_names:
                row["class_count"] = len(class_names)
                row.update({f"probability_{i}:{class_names[i]}": item.probabilities[i] for i in range(len(class_names))})
            writer.writerow(row)
    return path


def write_inference_zip(
    path: str | Path,
    report: InferenceReport,
    *,
    include_files: Iterable[str | Path] = (),
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if report.csv_path is None:
        raise ValueError("CSV report must be written before ZIP creation.")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(report.csv_path, "inference_results.csv")
        json_payload = report.to_dict()
        json_payload["csv"] = "inference_results.csv"
        json_payload["zip"] = path.name
        archive.writestr(
            "inference_results.json",
            json.dumps(json_payload, ensure_ascii=False, indent=2),
        )
        used_names: set[str] = set()
        for index, source in enumerate(include_files):
            source = Path(source)
            if not source.is_file():
                continue
            name = source.name
            if name in used_names:
                name = f"{index:06d}_{name}"
            used_names.add(name)
            archive.write(source, f"images/{name}")
    return path


def run_batch_inference(
    image_paths: Iterable[str | Path],
    *,
    model_path: str | Path,
    output_dir: str | Path,
    architecture: str | None = None,
    coral: bool = False,
    metadata_csv: str | Path | None = None,
    train_stats: Mapping[str, Mapping[str, float]] | None = None,
    device: Any = None,
    cache: ModelCache = DEFAULT_MODEL_CACHE,
    progress: Callable[[int, int, str], None] | None = None,
    include_images_in_zip: bool = True,
) -> InferenceReport:
    try:
        import torch
        from PIL import Image
    except ImportError as exc:
        raise MLDependencyError("PyTorch and Pillow are required for inference.") from exc
    paths = [Path(path) for path in image_paths]
    if not paths:
        raise ValueError("No images supplied for inference.")
    model_path = Path(model_path)
    metadata = read_model_metadata(
        model_path, architecture=architecture, coral=coral, train_stats=train_stats
    )
    if device is None or str(device).lower() == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ModelUnavailableError("CUDA was requested but is unavailable.")
    model = cache.get(model_path, metadata, device)
    transform = image_transform()
    source_metadata = metadata_by_name(metadata_csv)
    uses_metadata = metadata.architecture.lower().replace("_", "-") == "mlp-resnet18"
    class_names = dict(metadata.class_names or classification_labels(metadata.class_count))
    report = InferenceReport(model_path, metadata.architecture, class_names=class_names, class_count=metadata.class_count)

    try:
        with torch.inference_mode():
            for index, path in enumerate(paths, 1):
                with Image.open(path) as source:
                    image_tensor = transform(source.convert("RGB")).unsqueeze(0).to(device)
                if uses_metadata:
                    values = normalize_metadata(source_metadata.get(path.name), metadata.train_stats)
                    metadata_tensor = torch.tensor(values, dtype=torch.float32, device=device).unsqueeze(0)
                    logits = model(image_tensor, metadata_tensor)
                else:
                    logits = model(image_tensor)
                probabilities,predicted=single_image_probabilities(logits,metadata.class_count,metadata.coral)
                numeric = [float(value) for value in probabilities.detach().cpu()]
                report.items.append(
                    InferenceItem(
                        file=path.name,
                        predicted_index=predicted,
                        predicted_class=class_names[predicted],
                        confidence=numeric[predicted],
                        probabilities=numeric,
                    )
                )
                if progress:
                    progress(index, len(paths), f"inference {index}/{len(paths)}")
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise ModelUnavailableError("CUDA 記憶體不足，請降低批次大小或改用 CPU 後重試。") from exc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report.csv_path = write_inference_csv(output_dir / "inference_results.csv", report.items, class_names)
    report.zip_path = write_inference_zip(
        output_dir / "inference_results.zip",
        report,
        include_files=paths if include_images_in_zip else (),
    )
    return report
