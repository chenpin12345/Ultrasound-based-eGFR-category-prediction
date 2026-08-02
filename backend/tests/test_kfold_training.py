from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.ml import training as training_module
from backend.app.ml.contracts import ModelMetadata
from backend.app.ml.training import (
    TrainingCallbacks,
    TrainingConfig,
    TrainingOutcome,
    TrainingSample,
)


def _row(epoch: int, loss: float) -> dict:
    confusion = [[1 if row == column else 0 for column in range(5)] for row in range(5)]
    return {
        "epoch": epoch,
        "train_loss": loss + 0.1,
        "train_accuracy": 0.7,
        "train_precision": 0.7,
        "train_recall": 0.7,
        "train_f1": 0.7,
        "train_mean_absolute_error": 0.3,
        "train_within_one_accuracy": 0.9,
        "train_quadratic_weighted_kappa": 0.6,
        "val_loss": loss,
        "val_accuracy": 0.6,
        "val_precision": 0.6,
        "val_recall": 0.6,
        "val_f1": 0.6,
        "val_mean_absolute_error": 0.4,
        "val_within_one_accuracy": 0.8,
        "val_quadratic_weighted_kappa": 0.5,
        "learning_rate": 0.001,
        "epoch_seconds": 0.01,
        "train_confusion_matrix": confusion,
        "val_confusion_matrix": confusion,
    }


def _samples(tmp_path: Path) -> list[TrainingSample]:
    rows: list[TrainingSample] = []
    for fold in range(3):
        for index in range(2):
            rows.append(
                TrainingSample(
                    image_path=tmp_path / f"fold-{fold}-{index}.png",
                    class_index=(fold + index) % 5,
                    split="train" if index else "val",
                    fold=fold,
                    group_id=f"group-{fold}-{index}",
                )
            )
    rows.append(
        TrainingSample(
            image_path=tmp_path / "holdout.png",
            class_index=4,
            split="test",
            fold=2,
            group_id="holdout",
        )
    )
    return rows


def _fake_completed(config, samples, artifact_dir, *, dataset_id=None, callbacks=None):
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    validation = [sample for sample in samples if sample.split == "val"]
    fold = int(validation[0].fold)
    loss = 0.2 + fold
    row = _row(1, loss)
    if callbacks and callbacks.progress:
        callbacks.progress(1, config.epochs, 1, 1)
    if callbacks and callbacks.metric:
        callbacks.metric(row)
    (artifact_dir / "best_model.pth").write_bytes(f"best-{fold}".encode())
    (artifact_dir / "last_checkpoint.pth").write_bytes(f"last-{fold}".encode())
    training_module._write_history(artifact_dir / "history.csv", [row])
    training_module._atomic_json(
        artifact_dir / "model_metadata.json",
        ModelMetadata(architecture=config.architecture, dataset_id=dataset_id).to_dict(),
    )
    metrics = {
        "best_epoch": 1,
        "best_validation_loss": loss,
        "final_validation": {
            "accuracy": 0.6 + fold * 0.1,
            "precision": 0.6,
            "recall": 0.6,
            "f1": 0.6,
            "mean_absolute_error": 0.4,
            "within_one_accuracy": 0.8,
            "quadratic_weighted_kappa": 0.5,
        },
        "test": {"loss": 0.3, "accuracy": 0.5, "precision": 0.5, "recall": 0.5, "f1": 0.5},
    }
    return TrainingOutcome("completed", artifact_dir, 1, loss, metrics, [row], 0.01)


def test_kfold_trains_all_folds_aggregates_and_selects_best(monkeypatch, tmp_path):
    monkeypatch.setattr(training_module, "_train_single_classifier", _fake_completed)
    progress: list[tuple[int, int]] = []
    metrics: list[dict] = []
    outcome = training_module.train_classifier(
        TrainingConfig(architecture="resnet18", epochs=2, k_fold=3),
        _samples(tmp_path),
        tmp_path / "artifacts",
        dataset_id="dataset-1",
        callbacks=TrainingCallbacks(
            progress=lambda epoch, epochs, _batch, _batches: progress.append((epoch, epochs)),
            metric=lambda row: metrics.append(dict(row)),
        ),
    )

    assert outcome.status == "completed"
    assert progress == [(1, 6), (3, 6), (5, 6)]
    assert [item["epoch"] for item in metrics] == [1, 3, 5]
    assert [item["fold"] for item in metrics] == [0, 1, 2]
    cross_validation = outcome.metrics["cross_validation"]
    assert cross_validation["fold_count"] == 3
    assert cross_validation["selected_fold"] == 0
    assert cross_validation["aggregate"]["validation_accuracy"]["mean"] == pytest.approx(0.7)
    assert (tmp_path / "artifacts" / "best_model.pth").read_bytes() == b"best-0"
    history = (tmp_path / "artifacts" / "history.csv").read_text(encoding="utf-8-sig")
    assert history.startswith("fold,epoch,")
    metadata = json.loads((tmp_path / "artifacts" / "model_metadata.json").read_text(encoding="utf-8"))
    assert metadata["cross_validation"] == {
        "fold_count": 3,
        "selected_fold": 0,
        "epochs_per_fold": 2,
    }


def test_kfold_stop_persists_active_fold_and_resume_skips_completed(monkeypatch, tmp_path):
    calls: list[tuple[int, str | None]] = []

    def stop_on_second_fold(config, samples, artifact_dir, *, dataset_id=None, callbacks=None):
        fold = int(next(sample.fold for sample in samples if sample.split == "val"))
        calls.append((fold, config.resume_checkpoint))
        if fold != 1:
            return _fake_completed(
                config, samples, artifact_dir, dataset_id=dataset_id, callbacks=callbacks
            )
        artifact_dir = Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "last_checkpoint.pth").write_bytes(b"stopped-fold-1")
        return TrainingOutcome("stopped", artifact_dir, 0, float("inf"), {}, [], 0.01)

    monkeypatch.setattr(training_module, "_train_single_classifier", stop_on_second_fold)
    artifact_dir = tmp_path / "artifacts"
    config = TrainingConfig(architecture="resnet18", epochs=2, k_fold=3)
    stopped = training_module.train_classifier(config, _samples(tmp_path), artifact_dir)
    assert stopped.status == "stopped"
    assert calls == [(0, None), (1, None)]
    assert (artifact_dir / "last_checkpoint.pth").read_bytes() == b"stopped-fold-1"
    state = json.loads((artifact_dir / "kfold_state.json").read_text(encoding="utf-8"))
    assert state["active_fold"] == 1
    assert [item["fold"] for item in state["completed_folds"]] == [0]

    resumed_calls: list[tuple[int, str | None]] = []

    def completed_after_resume(config, samples, artifact_dir, *, dataset_id=None, callbacks=None):
        fold = int(next(sample.fold for sample in samples if sample.split == "val"))
        resumed_calls.append((fold, config.resume_checkpoint))
        return _fake_completed(
            config, samples, artifact_dir, dataset_id=dataset_id, callbacks=callbacks
        )

    monkeypatch.setattr(training_module, "_train_single_classifier", completed_after_resume)
    resumed = training_module.train_classifier(
        replace(config, resume_checkpoint=str(artifact_dir / "last_checkpoint.pth")),
        _samples(tmp_path),
        artifact_dir,
    )
    assert resumed.status == "completed"
    assert [fold for fold, _checkpoint in resumed_calls] == [1, 2]
    assert resumed_calls[0][1] == str(artifact_dir / "last_checkpoint.pth")
    assert resumed_calls[1][1] is None
