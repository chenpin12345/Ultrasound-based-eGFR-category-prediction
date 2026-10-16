"""Real PyTorch training loop with safe stop/resume and atomic artifacts."""

from __future__ import annotations

import csv
import json
import math
import os
import random
import shutil
import statistics
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .contracts import (
    CLASS_COUNT,
    CLASS_NAMES,
    IMAGENET_MEAN,
    IMAGENET_STD,
    METADATA_FIELDS,
    ModelMetadata,
    normalize_metadata,
    utc_now_iso,
    validate_train_stats,
)
from .models import MLDependencyError, build_classifier, coral_logits_to_probs


class TrainingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrainingSample:
    image_path: Path
    class_index: int
    split: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    fold: int | None = None
    group_id: str | None = None


@dataclass
class TrainingConfig:
    architecture: str = "resnet18"
    epochs: int = 10
    batch_size: int = 8
    learning_rate: float = 2e-4
    weight_decay: float = 1e-4
    optimizer: str = "adamw"
    scheduler: str = "plateau"
    early_stopping: bool = True
    patience: int = 10
    random_seed: int = 32008
    augmentation: bool = True
    class_weights: bool = True
    device: str = "cpu"
    checkpoint_interval: int = 1
    coral: bool = False
    k_fold: int | None = None
    resume_checkpoint: str | None = None
    train_stats: Mapping[str, Mapping[str, float]] | None = None

    def validate(self) -> None:
        from .models import canonical_architecture

        self.architecture = canonical_architecture(self.architecture)
        if self.coral and self.architecture not in {"resnet18", "mlp-resnet18"}:
            raise TrainingError("CORAL supports ResNet18 and MLP-ResNet18 only.")
        if not 1 <= int(self.epochs) <= 10_000:
            raise TrainingError("epochs must be between 1 and 10000")
        if not 2 <= int(self.batch_size) <= 1024:
            raise TrainingError("batch_size must be between 2 and 1024")
        if not 0 < float(self.learning_rate) <= 1:
            raise TrainingError("learning_rate must be in (0, 1]")
        if not 0 <= float(self.weight_decay) <= 1:
            raise TrainingError("weight_decay must be in [0, 1]")
        if int(self.patience) < 1:
            raise TrainingError("patience must be positive")
        if self.optimizer.lower() not in {"adam", "adamw", "sgd"}:
            raise TrainingError("optimizer must be adam, adamw or sgd")
        if self.scheduler.lower() not in {"none", "plateau", "cosine", "step"}:
            raise TrainingError("scheduler must be none, plateau, cosine or step")
        if self.device not in {"cpu", "cuda"}:
            raise TrainingError("device must be cpu or cuda")
        if int(self.checkpoint_interval) < 1:
            raise TrainingError("checkpoint_interval must be positive")
        if self.k_fold is not None and not 2 <= int(self.k_fold) <= 20:
            raise TrainingError("k_fold must be null or between 2 and 20")


@dataclass
class TrainingCallbacks:
    event: Callable[[str, Mapping[str, Any]], None] | None = None
    progress: Callable[[int, int, int, int], None] | None = None
    metric: Callable[[Mapping[str, Any]], None] | None = None
    resource: Callable[[Mapping[str, Any]], None] | None = None
    should_stop: Callable[[], bool] | None = None


@dataclass
class TrainingOutcome:
    status: str
    artifact_dir: Path
    best_epoch: int
    best_validation_loss: float
    metrics: dict[str, Any]
    history: list[dict[str, Any]]
    elapsed_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "artifact_dir": str(self.artifact_dir),
            "best_epoch": self.best_epoch,
            "best_validation_loss": self.best_validation_loss,
            "metrics": self.metrics,
            "history": self.history,
            "elapsed_seconds": self.elapsed_seconds,
        }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _atomic_torch_save(torch: Any, path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    torch.save(payload, temporary)
    os.replace(temporary, path)


HISTORY_FIELDS = (
        "epoch",
        "train_loss",
        "train_accuracy",
        "train_precision",
        "train_recall",
        "train_f1",
        "train_mean_absolute_error",
        "train_within_one_accuracy",
        "train_quadratic_weighted_kappa",
        "val_loss",
        "val_accuracy",
        "val_precision",
        "val_recall",
        "val_f1",
        "val_mean_absolute_error",
        "val_within_one_accuracy",
        "val_quadratic_weighted_kappa",
        "learning_rate",
        "epoch_seconds",
)


def _write_history(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = HISTORY_FIELDS
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _write_kfold_history(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=("fold", *HISTORY_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ("fold", *HISTORY_FIELDS)})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_history(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def _seed_everything(torch: Any, seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def compute_training_stats(samples: Sequence[TrainingSample]) -> dict[str, dict[str, float]]:
    from .contracts import BINARY_METADATA_FIELDS, DEFAULT_TRAIN_STATS

    stats: dict[str, dict[str, float]] = {}
    for field in METADATA_FIELDS:
        if field in BINARY_METADATA_FIELDS:
            continue
        numbers: list[float] = []
        for sample in samples:
            value = sample.metadata.get(field)
            if value in (None, ""):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isnan(number):
                numbers.append(number)
        if numbers:
            mean = sum(numbers) / len(numbers)
            variance = (
                sum((value - mean) ** 2 for value in numbers) / (len(numbers) - 1)
                if len(numbers) > 1
                else 0.0
            )
            stats[field] = {"mean": mean, "std": math.sqrt(variance)}
        else:
            stats[field] = dict(DEFAULT_TRAIN_STATS[field])
    return validate_train_stats(stats)


def _classification_metrics(targets: Sequence[int], predictions: Sequence[int]) -> dict[str, Any]:
    confusion = [[0 for _ in range(CLASS_COUNT)] for _ in range(CLASS_COUNT)]
    for target, prediction in zip(targets, predictions):
        if 0 <= target < CLASS_COUNT and 0 <= prediction < CLASS_COUNT:
            confusion[target][prediction] += 1
    per_class: dict[str, dict[str, float | int]] = {}
    precision_values: list[float] = []
    recall_values: list[float] = []
    f1_values: list[float] = []
    for index in range(CLASS_COUNT):
        true_positive = confusion[index][index]
        false_positive = sum(confusion[row][index] for row in range(CLASS_COUNT)) - true_positive
        false_negative = sum(confusion[index]) - true_positive
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        support = sum(confusion[index])
        per_class[str(index)] = {
            "name": CLASS_NAMES[index],
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        precision_values.append(precision)
        recall_values.append(recall)
        f1_values.append(f1)
    correct = sum(confusion[index][index] for index in range(CLASS_COUNT))
    total = sum(sum(row) for row in confusion)
    absolute_error = sum(abs(target - prediction) for target, prediction in zip(targets, predictions))
    within_one = sum(abs(target - prediction) <= 1 for target, prediction in zip(targets, predictions))
    true_histogram = [sum(confusion[index]) for index in range(CLASS_COUNT)]
    predicted_histogram = [sum(confusion[row][index] for row in range(CLASS_COUNT)) for index in range(CLASS_COUNT)]
    observed_weighted = sum(
        ((row - column) ** 2) * confusion[row][column]
        for row in range(CLASS_COUNT)
        for column in range(CLASS_COUNT)
    )
    expected_weighted = (
        sum(
            ((row - column) ** 2) * true_histogram[row] * predicted_histogram[column]
            for row in range(CLASS_COUNT)
            for column in range(CLASS_COUNT)
        )
        / total
        if total
        else 0.0
    )
    return {
        "accuracy": correct / total if total else 0.0,
        "precision": sum(precision_values) / CLASS_COUNT,
        "recall": sum(recall_values) / CLASS_COUNT,
        "f1": sum(f1_values) / CLASS_COUNT,
        "per_class": per_class,
        "confusion_matrix": confusion,
        "sample_count": total,
        "mean_absolute_error": absolute_error / total if total else 0.0,
        "within_one_accuracy": within_one / total if total else 0.0,
        "quadratic_weighted_kappa": (
            1.0 - observed_weighted / expected_weighted if expected_weighted else 0.0
        ),
    }


def resource_snapshot(torch: Any, device: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"timestamp": utc_now_iso()}
    try:
        import psutil

        process = psutil.Process()
        result.update(
            {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": process.memory_percent(),
                "memory_bytes": process.memory_info().rss,
            }
        )
    except ImportError:
        pass
    if str(device).startswith("cuda") and torch.cuda.is_available():
        index = device.index if getattr(device, "index", None) is not None else torch.cuda.current_device()
        result.update(
            {
                "gpu_name": torch.cuda.get_device_name(index),
                "gpu_memory_allocated": torch.cuda.memory_allocated(index),
                "gpu_memory_reserved": torch.cuda.memory_reserved(index),
            }
        )
        try:
            if hasattr(torch.cuda, "utilization"):
                result["gpu_percent"] = float(torch.cuda.utilization(index))
            properties = torch.cuda.get_device_properties(index)
            result["gpu_memory_total"] = int(properties.total_memory)
            result["gpu_memory_percent"] = (
                float(result["gpu_memory_reserved"]) / max(1, int(properties.total_memory)) * 100.0
            )
        except (RuntimeError, TypeError, ValueError):
            pass
    return result


def _build_loaders(torch: Any, samples: Sequence[TrainingSample], config: TrainingConfig, stats):
    try:
        from PIL import Image
        from torch.utils.data import DataLoader, Dataset
        from torchvision import transforms
    except ImportError as exc:
        raise MLDependencyError("Pillow and Torchvision are required for training.") from exc

    train_transform_items: list[Any] = [transforms.Resize((224, 224))]
    if config.augmentation:
        train_transform_items.extend(
            [
                transforms.RandomHorizontalFlip(0.5),
                transforms.ColorJitter(brightness=0.2, contrast=0.2),
                transforms.RandomRotation(20),
                transforms.RandomAffine(
                    degrees=0, translate=(0.05, 0.05), scale=(0.9, 1.1), shear=5
                ),
            ]
        )
    train_transform_items.extend(
        [transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)]
    )
    if config.augmentation:
        train_transform_items.append(
            transforms.RandomErasing(p=0.3, scale=(0.02, 0.15), ratio=(0.3, 3.3))
        )
    train_transform = transforms.Compose(train_transform_items)
    eval_transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )

    class SampleDataset(Dataset):
        def __init__(self, rows, transform):
            self.rows = list(rows)
            self.transform = transform

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            row = self.rows[index]
            with Image.open(row.image_path) as source:
                image = self.transform(source.convert("RGB"))
            metadata = torch.tensor(
                normalize_metadata(row.metadata, stats), dtype=torch.float32
            )
            return image, metadata, int(row.class_index)

    by_split = {
        split: [sample for sample in samples if sample.split.lower() == split]
        for split in ("train", "val", "test")
    }
    if len(by_split["train"]) < 2:
        raise TrainingError("Training split needs at least two valid samples.")
    if not by_split["val"]:
        raise TrainingError("Validation split is empty.")
    datasets = {
        "train": SampleDataset(by_split["train"], train_transform),
        "val": SampleDataset(by_split["val"], eval_transform),
        "test": SampleDataset(by_split["test"], eval_transform),
    }
    generator = torch.Generator().manual_seed(config.random_seed)
    return {
        "train": DataLoader(
            datasets["train"],
            batch_size=config.batch_size,
            shuffle=True,
            num_workers=0,
            pin_memory=str(config.device).startswith("cuda"),
            drop_last=len(datasets["train"]) % config.batch_size == 1,
            generator=generator,
        ),
        "val": DataLoader(datasets["val"], batch_size=config.batch_size, shuffle=False, num_workers=0),
        "test": DataLoader(datasets["test"], batch_size=config.batch_size, shuffle=False, num_workers=0),
    }


def _class_weights(torch: Any, samples: Sequence[TrainingSample], device: Any):
    counts = [0] * CLASS_COUNT
    for sample in samples:
        if sample.split.lower() == "train":
            counts[sample.class_index] += 1
    if any(count == 0 for count in counts):
        return None
    total = sum(counts)
    weights = [total / (CLASS_COUNT * math.sqrt(count)) for count in counts]
    scale = CLASS_COUNT / sum(weights)
    return torch.tensor([weight * scale for weight in weights], dtype=torch.float32, device=device)


def _optimizer(torch: Any, model: Any, config: TrainingConfig):
    kwargs = {"lr": config.learning_rate, "weight_decay": config.weight_decay}
    if config.optimizer.lower() == "adam":
        return torch.optim.Adam(model.parameters(), **kwargs)
    if config.optimizer.lower() == "sgd":
        return torch.optim.SGD(model.parameters(), momentum=0.9, **kwargs)
    return torch.optim.AdamW(model.parameters(), **kwargs)


def _scheduler(torch: Any, optimizer: Any, config: TrainingConfig):
    if config.scheduler.lower() == "plateau":
        return torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=0.8, patience=max(1, config.patience // 4), min_lr=1e-6
        )
    if config.scheduler.lower() == "cosine":
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)
    if config.scheduler.lower() == "step":
        return torch.optim.lr_scheduler.StepLR(
            optimizer, step_size=max(1, config.epochs // 3), gamma=0.1
        )
    return None


def _cumulative_labels(torch: Any, labels: Any):
    thresholds = torch.arange(CLASS_COUNT - 1, device=labels.device).unsqueeze(0)
    return (labels.unsqueeze(1) > thresholds).float()


def _run_epoch(
    torch: Any,
    *,
    model: Any,
    loader: Any,
    device: Any,
    optimizer: Any | None,
    class_weights: Any,
    config: TrainingConfig,
    epoch: int,
    callbacks: TrainingCallbacks,
) -> tuple[float, dict[str, Any], bool]:
    training = optimizer is not None
    model.train(training)
    loss_total = 0.0
    item_total = 0
    targets: list[int] = []
    predictions: list[int] = []
    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for batch_index, (images, metadata, labels) in enumerate(loader, 1):
            images = images.to(device, non_blocking=True)
            metadata = metadata.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True).long()
            if training:
                optimizer.zero_grad(set_to_none=True)
            uses_metadata = config.architecture == "mlp-resnet18"
            logits = model(images, metadata) if uses_metadata else model(images)
            if config.coral:
                loss_values = torch.nn.functional.binary_cross_entropy_with_logits(
                    logits, _cumulative_labels(torch, labels), reduction="none"
                ).mean(dim=1)
                if class_weights is not None:
                    loss_values = loss_values * class_weights[labels]
                loss = loss_values.mean()
                probabilities = coral_logits_to_probs(logits)
            else:
                loss = torch.nn.functional.cross_entropy(logits, labels, weight=class_weights)
                probabilities = torch.softmax(logits, dim=1)
            if training:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            size = labels.size(0)
            loss_total += float(loss.detach().item()) * size
            item_total += size
            targets.extend(int(value) for value in labels.detach().cpu())
            predictions.extend(int(value) for value in torch.argmax(probabilities, dim=1).detach().cpu())
            if training and callbacks.progress:
                callbacks.progress(epoch, config.epochs, batch_index, len(loader))
            if training and callbacks.should_stop and callbacks.should_stop():
                return loss_total / max(1, item_total), _classification_metrics(targets, predictions), True
    return loss_total / max(1, item_total), _classification_metrics(targets, predictions), False


def _checkpoint_payload(
    model: Any,
    optimizer: Any,
    scheduler: Any,
    config: TrainingConfig,
    stats: Mapping[str, Any],
    epoch: int,
    best_epoch: int,
    best_loss: float,
    history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict() if scheduler else None,
        "epoch": epoch,
        "best_epoch": best_epoch,
        "best_validation_loss": best_loss,
        "history": list(history),
        "training_config": asdict(config),
        "train_stats": dict(stats),
        "contract_version": 1,
    }


def _train_single_classifier(
    config: TrainingConfig,
    samples: Iterable[TrainingSample],
    artifact_dir: str | Path,
    *,
    dataset_id: str | None = None,
    callbacks: TrainingCallbacks | None = None,
) -> TrainingOutcome:
    try:
        import torch
    except ImportError as exc:
        raise MLDependencyError("PyTorch is required for training.") from exc
    callbacks = callbacks or TrainingCallbacks()
    config.validate()
    if config.device == "cuda" and not torch.cuda.is_available():
        raise TrainingError("CUDA was requested but is unavailable.")
    device = torch.device(config.device)
    rows = list(samples)
    if any(not 0 <= sample.class_index < CLASS_COUNT for sample in rows):
        raise TrainingError("All class indices must be in the fixed range 0..4.")
    missing_files = [sample.image_path.name for sample in rows if not sample.image_path.is_file()]
    if missing_files:
        raise TrainingError(f"Missing training images: {len(missing_files)}")
    train_rows = [sample for sample in rows if sample.split.lower() == "train"]
    stats = validate_train_stats(config.train_stats) if config.train_stats else compute_training_stats(train_rows)
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    config_payload = asdict(config)
    config_payload["train_stats"] = stats
    _atomic_json(artifact_dir / "training_config.json", config_payload)
    _seed_everything(torch, config.random_seed)
    loaders = _build_loaders(torch, rows, config, stats)
    model = build_classifier(config.architecture, coral=config.coral).to(device)
    optimizer = _optimizer(torch, model, config)
    scheduler = _scheduler(torch, optimizer, config)
    weights = _class_weights(torch, rows, device) if config.class_weights else None
    history: list[dict[str, Any]] = []
    start_epoch = 1
    best_epoch = 0
    best_loss = float("inf")

    if config.resume_checkpoint:
        try:
            checkpoint = torch.load(
                config.resume_checkpoint, map_location=device, weights_only=True
            )
            model.load_state_dict(checkpoint["model_state_dict"], strict=True)
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
            if scheduler and checkpoint.get("scheduler_state_dict"):
                scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
            start_epoch = int(checkpoint["epoch"]) + 1
            best_epoch = int(checkpoint.get("best_epoch", 0))
            best_loss = float(checkpoint.get("best_validation_loss", float("inf")))
            history = list(checkpoint.get("history", []))
        except Exception as exc:
            raise TrainingError("Checkpoint is invalid or incompatible with this training config.") from exc

    if callbacks.event:
        callbacks.event(
            "training_started",
            {"architecture": config.architecture, "device": str(device), "start_epoch": start_epoch},
        )
    started = time.monotonic()
    patience_count = 0
    final_metrics: dict[str, Any] = {}

    try:
        for epoch in range(start_epoch, config.epochs + 1):
            epoch_started = time.monotonic()
            train_loss, train_metrics, stopped = _run_epoch(
                torch,
                model=model,
                loader=loaders["train"],
                device=device,
                optimizer=optimizer,
                class_weights=weights,
                config=config,
                epoch=epoch,
                callbacks=callbacks,
            )
            if stopped:
                payload = _checkpoint_payload(
                    # The current epoch is incomplete.  Saving epoch - 1 makes
                    # resume repeat it instead of silently skipping its
                    # remaining batches and validation phase.
                    model, optimizer, scheduler, config, stats, epoch - 1, best_epoch, best_loss, history
                )
                _atomic_torch_save(torch, artifact_dir / "last_checkpoint.pth", payload)
                _write_history(artifact_dir / "history.csv", history)
                return TrainingOutcome(
                    "stopped", artifact_dir, best_epoch, best_loss, final_metrics, history,
                    time.monotonic() - started,
                )
            val_loss, val_metrics, _ = _run_epoch(
                torch,
                model=model,
                loader=loaders["val"],
                device=device,
                optimizer=None,
                class_weights=weights,
                config=config,
                epoch=epoch,
                callbacks=callbacks,
            )
            learning_rate = float(optimizer.param_groups[0]["lr"])
            epoch_row = {
                "epoch": epoch,
                "train_loss": train_loss,
                "train_accuracy": train_metrics["accuracy"],
                "train_precision": train_metrics["precision"],
                "train_recall": train_metrics["recall"],
                "train_f1": train_metrics["f1"],
                "train_mean_absolute_error": train_metrics["mean_absolute_error"],
                "train_within_one_accuracy": train_metrics["within_one_accuracy"],
                "train_quadratic_weighted_kappa": train_metrics["quadratic_weighted_kappa"],
                "val_loss": val_loss,
                "val_accuracy": val_metrics["accuracy"],
                "val_precision": val_metrics["precision"],
                "val_recall": val_metrics["recall"],
                "val_f1": val_metrics["f1"],
                "val_mean_absolute_error": val_metrics["mean_absolute_error"],
                "val_within_one_accuracy": val_metrics["within_one_accuracy"],
                "val_quadratic_weighted_kappa": val_metrics["quadratic_weighted_kappa"],
                "learning_rate": learning_rate,
                "epoch_seconds": time.monotonic() - epoch_started,
                "train_confusion_matrix": train_metrics["confusion_matrix"],
                "train_per_class": train_metrics["per_class"],
                "val_confusion_matrix": val_metrics["confusion_matrix"],
                "val_per_class": val_metrics["per_class"],
            }
            history.append(epoch_row)
            if callbacks.metric:
                callbacks.metric(epoch_row)
            resources = resource_snapshot(torch, device)
            if callbacks.resource:
                callbacks.resource(resources)
            if callbacks.event:
                callbacks.event("epoch_completed", {**epoch_row, "resources": resources})

            if val_loss < best_loss:
                best_loss = val_loss
                best_epoch = epoch
                patience_count = 0
                _atomic_torch_save(torch, artifact_dir / "best_model.pth", model.state_dict())
            else:
                patience_count += 1
            if scheduler:
                if config.scheduler.lower() == "plateau":
                    scheduler.step(val_loss)
                else:
                    scheduler.step()
            if epoch % config.checkpoint_interval == 0 or epoch == config.epochs:
                payload = _checkpoint_payload(
                    model, optimizer, scheduler, config, stats, epoch, best_epoch, best_loss, history
                )
                _atomic_torch_save(torch, artifact_dir / "last_checkpoint.pth", payload)
                _write_history(artifact_dir / "history.csv", history)
            if config.early_stopping and patience_count >= config.patience:
                if callbacks.event:
                    callbacks.event("early_stopping", {"epoch": epoch, "best_epoch": best_epoch})
                break

        best_path = artifact_dir / "best_model.pth"
        if not best_path.exists():
            _atomic_torch_save(torch, best_path, model.state_dict())
            best_epoch = history[-1]["epoch"] if history else 0
            best_loss = history[-1]["val_loss"] if history else float("inf")
        model.load_state_dict(torch.load(best_path, map_location=device, weights_only=True), strict=True)
        test_loss, test_metrics, _ = _run_epoch(
            torch,
            model=model,
            loader=loaders["test"],
            device=device,
            optimizer=None,
            class_weights=weights,
            config=config,
            epoch=best_epoch,
            callbacks=callbacks,
        ) if len(loaders["test"].dataset) else (0.0, _classification_metrics([], []), False)
        final_metrics = {
            "best_epoch": best_epoch,
            "best_validation_loss": best_loss,
            "final_train": {
                key.removeprefix("train_"): value
                for key, value in history[-1].items()
                if key.startswith("train_")
            } if history else {},
            "final_validation": {
                key.removeprefix("val_"): value
                for key, value in history[-1].items()
                if key.startswith("val_")
            } if history else {},
            "test": {"loss": test_loss, **test_metrics},
            "elapsed_seconds": time.monotonic() - started,
        }
        _atomic_json(artifact_dir / "metrics.json", final_metrics)
        _write_history(artifact_dir / "history.csv", history)
        model_metadata = ModelMetadata(
            architecture=config.architecture,
            dataset_id=dataset_id,
            created_at=utc_now_iso(),
            best_metric={"validation_loss": best_loss, "epoch": best_epoch},
            coral=config.coral,
            train_stats=stats,
        )
        _atomic_json(artifact_dir / "model_metadata.json", model_metadata.to_dict())
        if callbacks.event:
            callbacks.event("training_completed", final_metrics)
        return TrainingOutcome(
            "completed",
            artifact_dir,
            best_epoch,
            best_loss,
            final_metrics,
            history,
            time.monotonic() - started,
        )
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise TrainingError("CUDA 記憶體不足，請降低 batch size 後重試。") from exc


def _nested_number(payload: Mapping[str, Any], *keys: str) -> float | None:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _aggregate_fold_metrics(folds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    paths = {
        "best_validation_loss": ("best_validation_loss",),
        "validation_accuracy": ("metrics", "final_validation", "accuracy"),
        "validation_precision": ("metrics", "final_validation", "precision"),
        "validation_recall": ("metrics", "final_validation", "recall"),
        "validation_f1": ("metrics", "final_validation", "f1"),
        "validation_mean_absolute_error": (
            "metrics", "final_validation", "mean_absolute_error",
        ),
        "validation_within_one_accuracy": (
            "metrics", "final_validation", "within_one_accuracy",
        ),
        "validation_quadratic_weighted_kappa": (
            "metrics", "final_validation", "quadratic_weighted_kappa",
        ),
        "test_loss": ("metrics", "test", "loss"),
        "test_accuracy": ("metrics", "test", "accuracy"),
        "test_precision": ("metrics", "test", "precision"),
        "test_recall": ("metrics", "test", "recall"),
        "test_f1": ("metrics", "test", "f1"),
    }
    aggregate: dict[str, Any] = {}
    for name, path in paths.items():
        values = [value for fold in folds if (value := _nested_number(fold, *path)) is not None]
        if not values:
            continue
        aggregate[name] = {
            "mean": statistics.fmean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0,
            "minimum": min(values),
            "maximum": max(values),
            "count": len(values),
        }
    return aggregate


def _load_kfold_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TrainingError("K-fold resume state is invalid.") from exc
    if not isinstance(value, dict):
        raise TrainingError("K-fold resume state is invalid.")
    return value


def _kfold_callbacks(
    callbacks: TrainingCallbacks,
    *,
    fold: int,
    fold_count: int,
    epochs_per_fold: int,
) -> TrainingCallbacks:
    def emit(event_type: str, data: Mapping[str, Any]) -> None:
        if callbacks.event:
            callbacks.event(
                event_type,
                {**dict(data), "fold": fold, "fold_number": fold + 1, "fold_count": fold_count},
            )

    def progress(epoch: int, _epochs: int, batch: int, batches: int) -> None:
        if callbacks.progress:
            callbacks.progress(
                fold * epochs_per_fold + epoch,
                fold_count * epochs_per_fold,
                batch,
                batches,
            )

    def metric(row: Mapping[str, Any]) -> None:
        if callbacks.metric:
            local_epoch = int(row["epoch"])
            callbacks.metric(
                {
                    **dict(row),
                    "fold": fold,
                    "fold_epoch": local_epoch,
                    "epoch": fold * epochs_per_fold + local_epoch,
                }
            )

    return TrainingCallbacks(
        event=emit,
        progress=progress,
        metric=metric,
        resource=callbacks.resource,
        should_stop=callbacks.should_stop,
    )


def _train_kfold_classifier(
    config: TrainingConfig,
    rows: Sequence[TrainingSample],
    artifact_dir: Path,
    *,
    dataset_id: str | None,
    callbacks: TrainingCallbacks,
) -> TrainingOutcome:
    fold_count = int(config.k_fold or 0)
    if fold_count < 2:
        raise TrainingError("K-fold must contain at least two folds.")

    # Keep the ordinary test split as an untouched holdout. Cross-validation
    # rotates validation only across the original train+validation pool.
    cross_validation_rows = [row for row in rows if row.split.lower() != "test"]
    holdout_rows = [row for row in rows if row.split.lower() == "test"]
    available_folds = {row.fold for row in cross_validation_rows if row.fold is not None}
    expected_folds = set(range(fold_count))
    if available_folds != expected_folds:
        raise TrainingError(
            "K-fold 資料不足：train/validation pool 必須在每個 fold 都至少有一張影像；"
            "請降低 fold 數或增加資料。"
        )
    for fold in range(fold_count):
        validation_count = sum(row.fold == fold for row in cross_validation_rows)
        training_count = len(cross_validation_rows) - validation_count
        if validation_count < 1 or training_count < 2:
            raise TrainingError(
                f"Fold {fold + 1} 至少需要 2 張 training 與 1 張 validation 影像。"
            )

    artifact_dir.mkdir(parents=True, exist_ok=True)
    root_config = asdict(config)
    if root_config.get("resume_checkpoint"):
        root_config["resume_checkpoint"] = Path(str(root_config["resume_checkpoint"])).name
    root_config["cross_validation"] = {
        "fold_count": fold_count,
        "epochs_per_fold": config.epochs,
        "holdout_test_samples": len(holdout_rows),
    }
    _atomic_json(artifact_dir / "training_config.json", root_config)

    state_path = artifact_dir / "kfold_state.json"
    state = _load_kfold_state(state_path) if config.resume_checkpoint else {}
    completed: list[dict[str, Any]] = [
        dict(item) for item in state.get("completed_folds", []) if isinstance(item, Mapping)
    ]
    completed_by_fold = {int(item["fold"]): item for item in completed if "fold" in item}
    active_fold = int(state.get("active_fold", min(set(range(fold_count)) - set(completed_by_fold), default=0)))
    combined_history: list[dict[str, Any]] = []
    started = time.monotonic()

    for fold in range(fold_count):
        fold_dir = artifact_dir / "folds" / f"fold-{fold + 1}"
        if fold in completed_by_fold:
            for row in _read_history(fold_dir / "history.csv"):
                combined_history.append({"fold": fold, **row})
            continue

        if callbacks.event:
            callbacks.event(
                "fold_started",
                {"fold": fold, "fold_number": fold + 1, "fold_count": fold_count},
            )
        fold_rows = [
            replace(row, split="val" if row.fold == fold else "train")
            for row in cross_validation_rows
        ] + [replace(row, split="test") for row in holdout_rows]
        resume_checkpoint = config.resume_checkpoint if fold == active_fold else None
        fold_config = replace(
            config,
            k_fold=None,
            random_seed=int(config.random_seed) + fold,
            resume_checkpoint=resume_checkpoint,
        )
        outcome = _train_single_classifier(
            fold_config,
            fold_rows,
            fold_dir,
            dataset_id=dataset_id,
            callbacks=_kfold_callbacks(
                callbacks,
                fold=fold,
                fold_count=fold_count,
                epochs_per_fold=config.epochs,
            ),
        )
        for row in outcome.history:
            combined_history.append({"fold": fold, **dict(row)})

        if outcome.status == "stopped":
            checkpoint = fold_dir / "last_checkpoint.pth"
            if checkpoint.is_file():
                _atomic_copy(checkpoint, artifact_dir / "last_checkpoint.pth")
            partial_state = {
                "status": "stopped",
                "fold_count": fold_count,
                "active_fold": fold,
                "completed_folds": list(completed_by_fold.values()),
            }
            _atomic_json(state_path, partial_state)
            _write_kfold_history(artifact_dir / "history.csv", combined_history)
            partial_metrics = {
                "cross_validation": {
                    "fold_count": fold_count,
                    "completed_fold_count": len(completed_by_fold),
                    "active_fold": fold,
                    "folds": list(completed_by_fold.values()),
                    "aggregate": _aggregate_fold_metrics(list(completed_by_fold.values())),
                },
                "elapsed_seconds": time.monotonic() - started,
            }
            _atomic_json(artifact_dir / "metrics.json", partial_metrics)
            return TrainingOutcome(
                "stopped",
                artifact_dir,
                outcome.best_epoch,
                outcome.best_validation_loss,
                partial_metrics,
                combined_history,
                time.monotonic() - started,
            )

        summary = {
            "fold": fold,
            "fold_number": fold + 1,
            "best_epoch": outcome.best_epoch,
            "best_validation_loss": outcome.best_validation_loss,
            "elapsed_seconds": outcome.elapsed_seconds,
            "metrics": outcome.metrics,
        }
        completed_by_fold[fold] = summary
        _atomic_json(
            state_path,
            {
                "status": "running" if fold + 1 < fold_count else "completed",
                "fold_count": fold_count,
                "active_fold": min(fold + 1, fold_count - 1),
                "completed_folds": [completed_by_fold[index] for index in sorted(completed_by_fold)],
            },
        )
        if callbacks.event:
            callbacks.event(
                "fold_completed",
                {
                    "fold": fold,
                    "fold_number": fold + 1,
                    "fold_count": fold_count,
                    "best_validation_loss": outcome.best_validation_loss,
                },
            )

    folds = [completed_by_fold[index] for index in range(fold_count)]
    selected = min(folds, key=lambda item: float(item["best_validation_loss"]))
    selected_fold = int(selected["fold"])
    selected_dir = artifact_dir / "folds" / f"fold-{selected_fold + 1}"
    for filename in ("best_model.pth", "last_checkpoint.pth"):
        source = selected_dir / filename
        if source.is_file():
            _atomic_copy(source, artifact_dir / filename)

    metadata_path = selected_dir / "model_metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        metadata = ModelMetadata(
            architecture=config.architecture,
            dataset_id=dataset_id,
            created_at=utc_now_iso(),
            best_metric=None,
            coral=config.coral,
        ).to_dict()
    metadata["best_metric"] = {
        "validation_loss": selected["best_validation_loss"],
        "epoch": selected["best_epoch"],
        "fold": selected_fold,
    }
    metadata["cross_validation"] = {
        "fold_count": fold_count,
        "selected_fold": selected_fold,
        "epochs_per_fold": config.epochs,
    }
    _atomic_json(artifact_dir / "model_metadata.json", metadata)
    _write_kfold_history(artifact_dir / "history.csv", combined_history)

    selected_metrics = dict(selected.get("metrics") or {})
    final_metrics = {
        **selected_metrics,
        "best_epoch": selected["best_epoch"],
        "best_validation_loss": selected["best_validation_loss"],
        "cross_validation": {
            "fold_count": fold_count,
            "selected_fold": selected_fold,
            "folds": folds,
            "aggregate": _aggregate_fold_metrics(folds),
        },
        "elapsed_seconds": time.monotonic() - started,
    }
    _atomic_json(artifact_dir / "metrics.json", final_metrics)
    _atomic_json(
        state_path,
        {
            "status": "completed",
            "fold_count": fold_count,
            "active_fold": selected_fold,
            "selected_fold": selected_fold,
            "completed_folds": folds,
        },
    )
    if callbacks.event:
        callbacks.event("kfold_completed", final_metrics["cross_validation"])
    return TrainingOutcome(
        "completed",
        artifact_dir,
        int(selected["best_epoch"]),
        float(selected["best_validation_loss"]),
        final_metrics,
        combined_history,
        time.monotonic() - started,
    )


def train_classifier(
    config: TrainingConfig,
    samples: Iterable[TrainingSample],
    artifact_dir: str | Path,
    *,
    dataset_id: str | None = None,
    callbacks: TrainingCallbacks | None = None,
) -> TrainingOutcome:
    """Train one classifier or execute deterministic grouped K-fold CV.

    ``epochs`` remains the number of epochs per fold.  In K-fold mode the
    public progress total is therefore ``epochs * k_fold`` and the original
    test split stays untouched as a shared holdout set.
    """

    callbacks = callbacks or TrainingCallbacks()
    config.validate()
    rows = list(samples)
    if config.k_fold:
        return _train_kfold_classifier(
            config,
            rows,
            Path(artifact_dir),
            dataset_id=dataset_id,
            callbacks=callbacks,
        )
    return _train_single_classifier(
        config,
        rows,
        artifact_dir,
        dataset_id=dataset_id,
        callbacks=callbacks,
    )
