from __future__ import annotations

import csv
import io
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image


def _training_records():
    from backend.app.core.config import get_settings
    from backend.app.db.models import (
        Dataset,
        Job,
        JobEvent,
        TrainingJob,
        TrainingMetric,
    )
    from backend.app.db.session import get_session_factory

    dataset_id = str(uuid4())
    job_id = str(uuid4())
    training_id = str(uuid4())
    settings = get_settings()
    artifact_dir = settings.models_dir / training_id
    artifact_dir.mkdir(parents=True)
    absolute_secret = str(settings.data_dir / "private" / "resume-checkpoint.pth")
    files = {
        "best_model.pth": b"best-weights",
        "last_checkpoint.pth": b"last-checkpoint",
        "model_metadata.json": json.dumps({"architecture": "resnet18"}).encode(),
        "training_config.json": json.dumps({"resume_checkpoint": absolute_secret}).encode(),
        "metrics.json": json.dumps({"best_epoch": 1, "validation_loss": 0.25}).encode(),
        "history.csv": b"epoch,train_loss,val_loss\r\n1,0.5,0.25\r\n",
    }
    for filename, content in files.items():
        (artifact_dir / filename).write_bytes(content)

    with get_session_factory()() as db:
        db.add(Dataset(
            id=dataset_id,
            name="artifact dataset",
            status="ready",
            root_path=f"datasets/{dataset_id}",
            sample_count=1,
            total_bytes=1,
        ))
        db.add(Job(
            id=job_id,
            dataset_id=dataset_id,
            kind="training",
            status="completed",
            progress=100,
            config_json={},
            workspace_path=f"training/{training_id}",
        ))
        db.add(TrainingJob(
            id=training_id,
            job_id=job_id,
            dataset_id=dataset_id,
            model_name="artifact model",
            architecture="resnet18",
            status="completed",
            config_json={},
            device="cpu",
            total_epochs=1,
            best_checkpoint_path=f"{training_id}/best_model.pth",
            last_checkpoint_path=f"{training_id}/last_checkpoint.pth",
        ))
        db.add_all([
            JobEvent(
                job_id=job_id,
                event_type="training_started",
                data_json={"checkpoint": absolute_secret},
            ),
            JobEvent(job_id=job_id, event_type="training_completed", data_json={"epoch": 1}),
            TrainingMetric(
                training_job_id=training_id,
                epoch=1,
                split="train",
                loss=0.5,
                accuracy=0.8,
                precision=0.75,
                recall=0.7,
                f1=0.72,
                learning_rate=0.001,
                confusion_matrix=[[1, 0], [0, 1]],
            ),
            TrainingMetric(
                training_job_id=training_id,
                epoch=1,
                split="validation",
                loss=0.25,
                accuracy=0.9,
                precision=0.88,
                recall=0.85,
                f1=0.86,
                learning_rate=0.001,
                confusion_matrix=[[2, 0], [0, 2]],
            ),
        ])
        db.commit()
    return training_id, absolute_secret


def test_training_artifacts_and_metrics_csv_download(client):
    training_id, absolute_secret = _training_records()

    metrics = client.get(f"/api/training/jobs/{training_id}/metrics")
    assert metrics.status_code == 200
    assert len(metrics.json()["items"]) == 2

    download = client.get(f"/api/training/jobs/{training_id}/metrics?download=1")
    assert download.status_code == 200
    assert download.content.startswith(b"\xef\xbb\xbf")
    assert download.headers["content-type"].startswith("text/csv")
    assert "attachment" in download.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(download.content.decode("utf-8-sig"))))
    assert [row["split"] for row in rows] == ["train", "validation"]
    assert json.loads(rows[0]["confusion_matrix"]) == [[1, 0], [0, 1]]

    listing = client.get(f"/api/training/jobs/{training_id}/artifacts")
    assert listing.status_code == 200
    by_kind = {item["kind"]: item for item in listing.json()["items"]}
    assert set(by_kind) == {"best", "last", "metadata", "config", "metrics", "history", "events"}
    assert by_kind["events"]["event_count"] == 2
    assert all(item["download_url"].startswith("/api/training/jobs/") for item in by_kind.values())

    assert client.get(by_kind["best"]["download_url"]).content == b"best-weights"
    assert client.get(by_kind["last"]["download_url"]).content == b"last-checkpoint"
    assert b"epoch,train_loss,val_loss" in client.get(by_kind["history"]["download_url"]).content

    config_download = client.get(by_kind["config"]["download_url"])
    assert config_download.status_code == 200
    assert absolute_secret not in config_download.text
    assert config_download.json()["resume_checkpoint"] == "<path>"

    event_download = client.get(by_kind["events"]["download_url"])
    assert event_download.status_code == 200
    assert absolute_secret not in event_download.text
    assert event_download.json()["events"][0]["data"]["checkpoint"] == "<path>"
    assert client.get(f"/api/training/jobs/{training_id}/artifacts/unknown").status_code == 404


def _large_image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (240, 120), (20, 80, 140)).save(output, "JPEG")
    return output.getvalue()


def test_runtime_settings_control_import_and_job_defaults(client, monkeypatch):
    updated = client.put(
        "/api/settings",
        json={"thumbnail_size": 64, "default_seed": 777, "gpu_enabled": False},
    )
    assert updated.status_code == 200

    imported = client.post(
        "/api/datasets",
        data={"name": "runtime settings", "k_folds": "2"},
        files={"files": ("eGFR -15/large.jpg", _large_image_bytes(), "image/jpeg")},
    )
    assert imported.status_code == 201, imported.text
    dataset = imported.json()
    assert dataset["split_config"]["seed"] == 777
    sample = client.get(f"/api/datasets/{dataset['id']}/samples").json()["items"][0]
    thumbnail = client.get(sample["thumbnail_url"])
    with Image.open(io.BytesIO(thumbnail.content)) as image:
        assert image.size == (64, 32)

    import backend.app.api.routes.jobs as jobs_routes

    submitted = []
    monkeypatch.setattr(jobs_routes, "get_worker_manager", lambda: object())
    monkeypatch.setattr(jobs_routes, "call_worker", lambda method, job_id: submitted.append((method, job_id)))
    created = client.post(
        "/api/jobs",
        json={"kind": "process", "dataset_id": dataset["id"], "config": {"steps": ["convert"]}},
    )
    assert created.status_code == 202, created.text
    assert created.json()["config_json"]["random_seed"] == 777
    assert created.json()["config_json"]["device"] == "cpu"
    disabled = client.post(
        "/api/jobs",
        json={"kind": "process", "dataset_id": dataset["id"], "config": {"device": "cuda"}},
    )
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "GPU_DISABLED"


def test_training_uses_persisted_seed_and_gpu_switch(client, make_image, monkeypatch):
    assert client.put(
        "/api/settings", json={"default_seed": 991, "gpu_enabled": False}
    ).status_code == 200
    labels = ["eGFR -15", "eGFR 15-29", "eGFR 30-59", "eGFR 60-89", "eGFR 90-"]
    files = []
    for class_index, label in enumerate(labels):
        for sample_index in range(3):
            color = (class_index * 35 + sample_index, sample_index * 40 + 1, class_index * 20 + 2)
            files.append((
                "files",
                (f"{label}/sample-{sample_index}.jpg", make_image(color), "image/jpeg"),
            ))
    imported = client.post(
        "/api/datasets",
        data={"name": "training defaults", "k_folds": "2"},
        files=files,
    )
    assert imported.status_code == 201, imported.text

    import backend.app.api.routes.training as training_routes

    submitted = []
    monkeypatch.setattr(training_routes, "get_worker_manager", lambda: object())
    monkeypatch.setattr(training_routes, "call_worker", lambda method, job_id: submitted.append((method, job_id)))
    payload = {
        "dataset_id": imported.json()["id"],
        "model_name": "seeded model",
        "architecture": "resnet18",
        "epochs": 1,
        "batch_size": 2,
        "device": "auto",
    }
    created = client.post("/api/training/jobs", json=payload)
    assert created.status_code == 202, created.text
    config = created.json()["config_json"]
    assert config["seed"] == 991
    assert config["random_seed"] == 991
    assert config["device"] == "cpu"
    assert submitted == [("submit_training", created.json()["id"])]

    payload["device"] = "cuda"
    rejected = client.post("/api/training/jobs", json=payload)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "GPU_DISABLED"


def test_persisted_cpu_workers_are_used_at_startup(client):
    assert client.put("/api/settings", json={"cpu_workers": 3}).status_code == 200

    from backend.app.main import create_app
    import backend.app.workers.manager as manager_module

    captured = {}
    original_configure = manager_module.configure_worker_manager
    original_shutdown = manager_module.worker_shutdown
    try:
        manager_module.configure_worker_manager = lambda **kwargs: captured.update(kwargs)
        manager_module.worker_shutdown = lambda: None
        with TestClient(create_app(testing=True)) as restarted:
            assert restarted.get("/api/health").status_code == 200
    finally:
        manager_module.configure_worker_manager = original_configure
        manager_module.worker_shutdown = original_shutdown
    assert captured["cpu_workers"] == 3
