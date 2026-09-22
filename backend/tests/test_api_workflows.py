from __future__ import annotations

import csv
import io
import json
import time
import zipfile

import pytest


TERMINAL_JOB_STATUSES = {"completed", "failed", "stopped", "interrupted"}
LEGACY_CLASS_NAMES = (
    "eGFR -15",
    "eGFR 15-29",
    "eGFR 30-59",
    "eGFR 60-89",
    "eGFR 90-",
)


def _wait_for_job(client, job_id: str, *, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    current: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        current = response.json()
        if current["status"] in TERMINAL_JOB_STATUSES:
            return current
        time.sleep(0.05)
    pytest.fail(f"job {job_id} did not finish within {timeout}s; last response={current}")


def _import_five_class_dataset(client, make_image, *, images_per_class: int = 5) -> dict:
    files = []
    for class_index, class_name in enumerate(LEGACY_CLASS_NAMES):
        for image_index in range(images_per_class):
            # Unique lossless pixels ensure the duplicate-aware splitter has
            # enough independent groups in every class for train/val/test.
            color = (
                15 + class_index * 40,
                10 + image_index * 35,
                20 + class_index * 12 + image_index,
            )
            files.append(
                (
                    "files",
                    (
                        f"{class_name}/class-{class_index}-{image_index}.png",
                        make_image(color, "PNG"),
                        "image/png",
                    ),
                )
            )
    response = client.post(
        "/api/datasets",
        data={
            "name": "five-class-training-fixture",
            "train_ratio": "0.7",
            "val_ratio": "0.15",
            "test_ratio": "0.15",
            "seed": "17",
            "k_folds": "5",
        },
        files=files,
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["sample_count"] == 5 * images_per_class
    return payload


def test_multipart_process_job_completes_downloads_zip_and_deletes(client, make_image):
    response = client.post(
        "/api/jobs",
        data={
            "kind": "process",
            "name": "uploaded-process",
            "config": json.dumps({"steps": ["convert"]}),
        },
        files=[("files", ("scan.jpg", make_image((22, 77, 144)), "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    created = response.json()
    assert created["dataset_id"] is None
    assert created["config_json"]["name"] == "uploaded-process"
    assert all(not value.startswith(("/", "\\")) for value in created["config_json"]["input_paths"])

    completed = _wait_for_job(client, created["id"])
    assert completed["status"] == "completed", completed
    assert completed["progress"] == 100
    assert completed["result_json"]["operation"] == "process"

    results = client.get(f"/api/jobs/{created['id']}/results")
    assert results.status_code == 200, results.text
    assert results.json()["results"]["steps"][0]["name"] == "convert"

    download = client.get(f"/api/jobs/{created['id']}/download?format=zip")
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = archive.namelist()
        assert names
        assert any(name.endswith("scan.jpg") for name in names)
        assert all(not name.startswith(("/", "\\")) and ".." not in name.split("/") for name in names)

    deleted = client.delete(f"/api/jobs/{created['id']}")
    assert deleted.status_code == 204, deleted.text
    missing = client.get(f"/api/jobs/{created['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_frontend_training_payload_persists_prevents_duplicate_and_stops_resumes(
    client, make_image, monkeypatch
):
    dataset = _import_five_class_dataset(client, make_image)

    import backend.app.api.routes.training as training_routes
    from backend.app.api.worker_bridge import call_worker as bridge_call_worker
    from backend.app.core.config import get_settings
    from backend.app.db.models import Job, TrainingJob
    from backend.app.db.session import get_session_factory
    from backend.app.workers.manager import get_worker_manager

    submitted: list[str] = []

    def dispatch_without_training(method: str, identifier: str):
        if method == "submit_training":
            submitted.append(identifier)
            return None
        return bridge_call_worker(method, identifier)

    monkeypatch.setattr(training_routes, "call_worker", dispatch_without_training)
    payload = {
        "dataset_id": dataset["id"],
        "name": "frontend MobileNet run",
        "architecture": "mobilenet_v2",
        "mode": "advanced",
        "classification_mode": "multiclass",
        "batch_size": 4,
        "epochs": 2,
        "learning_rate": 0.0003,
        "optimizer": "adamw",
        "weight_decay": 0.0001,
        "scheduler": "cosine",
        "early_stopping": True,
        "patience": 3,
        "random_seed": 17,
        "train_ratio": 0.7,
        "validation_ratio": 0.15,
        "test_ratio": 0.15,
        "data_augmentation": False,
        "class_weights": True,
        "device": "cpu",
        "k_folds": 1,
        "checkpoint_interval": 1,
    }
    response = client.post("/api/training/jobs", json=payload)
    assert response.status_code == 202, response.text
    created = response.json()
    assert submitted == [created["id"]]
    assert created["model_name"] == payload["name"]
    assert created["architecture"] == "mobilenetv2"
    assert created["device"] == "cpu"
    assert created["total_epochs"] == 2
    assert created["config_json"]["seed"] == 17
    assert created["config_json"]["val_ratio"] == pytest.approx(0.15)
    assert created["config_json"]["augmentation"] is False
    assert created["config_json"]["k_fold"] is None
    assert created["config_json"]["split_counts"] == {
        "train": 15,
        "validation": 5,
        "test": 5,
    }

    persisted = client.get(f"/api/training/jobs/{created['id']}")
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["job_id"] == created["job_id"]
    listing = client.get(f"/api/training/jobs?dataset_id={dataset['id']}")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [created["id"]]

    duplicate = client.post("/api/training/jobs", json=payload)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "DUPLICATE_TRAINING_JOB"
    assert submitted == [created["id"]]

    stopped = client.post(f"/api/training/jobs/{created['id']}/stop")
    assert stopped.status_code == 202, stopped.text
    assert stopped.json()["status"] == "stopped"

    checkpoint_relative = f"{created['id']}/last_checkpoint.pth"
    checkpoint = get_settings().models_dir / checkpoint_relative
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"managed checkpoint fixture")
    with get_session_factory()() as db:
        training = db.get(TrainingJob, created["id"])
        training.last_checkpoint_path = checkpoint_relative
        db.commit()

    resumed_submissions: list[str] = []
    manager = get_worker_manager()
    monkeypatch.setattr(manager, "submit_training", lambda training_id: resumed_submissions.append(training_id))
    resumed = client.post(f"/api/training/jobs/{created['id']}/resume")
    assert resumed.status_code == 202, resumed.text
    assert resumed.json()["status"] == "queued"
    assert resumed_submissions == [created["id"]]
    with get_session_factory()() as db:
        training = db.get(TrainingJob, created["id"])
        parent = db.get(Job, created["job_id"])
        assert training.config_json["resume_checkpoint"] == checkpoint_relative
        assert parent.status == "queued"
        assert parent.stop_requested is False


def test_real_inference_returns_prediction_and_csv_zip_downloads(client, make_image):
    import torch

    from backend.app.ml.contracts import CLASS_NAMES
    from backend.app.ml.models import build_classifier

    model = build_classifier("mobilenetv2")
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
    weights = io.BytesIO()
    torch.save(model.state_dict(), weights)
    manifest = {
        "name": "small-compatible-mobilenetv2",
        "version": "workflow-test-1",
        "task": "classification",
        "architecture": "mobilenetv2",
        "class_count": 5,
        "class_names": [CLASS_NAMES[index] for index in range(5)],
        "metadata_columns": [],
        "preprocessing": {
            "mode": "RGB",
            "size": [224, 224],
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
    }
    upload = client.post(
        "/api/models",
        data={"manifest_json": json.dumps(manifest)},
        files={"weights": ("mobilenetv2.pth", weights.getvalue(), "application/octet-stream")},
    )
    assert upload.status_code == 201, upload.text
    registered = upload.json()
    activated = client.post(f"/api/models/{registered['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["active"] is True

    response = client.post(
        "/api/jobs",
        data={
            "kind": "inference",
            "name": "real-inference",
            "config": json.dumps({"model_id": registered["id"], "device": "cpu"}),
        },
        files=[("files", ("kidney.jpg", make_image((90, 20, 150)), "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    completed = _wait_for_job(client, response.json()["id"], timeout=30.0)
    assert completed["status"] == "completed", completed
    result = completed["result_json"]
    assert result["operation"] == "inference"
    assert result["summary"]["total"] == 1
    assert len(result["items"]) == 1
    prediction = result["items"][0]
    assert prediction["predicted_index"] == 0
    assert prediction["predicted_class"] == CLASS_NAMES[0]
    assert prediction["confidence"] == pytest.approx(0.2, abs=1e-5)
    assert sum(prediction["probabilities"]) == pytest.approx(1.0, abs=1e-5)

    results_response = client.get(f"/api/jobs/{completed['id']}/results")
    assert results_response.status_code == 200, results_response.text
    displayed = results_response.json()["results"]["items"]
    assert [{key: item[key] for key in result["items"][0]} for item in displayed] == result["items"]
    assert displayed[0]['file_name'] == 'kidney.jpg'
    assert client.get(displayed[0]['thumbnail_url']).status_code == 200
    assert 'evaluation' not in results_response.json()['results']

    csv_download = client.get(f"/api/jobs/{completed['id']}/download?format=csv")
    assert csv_download.status_code == 200, csv_download.text
    rows = list(csv.DictReader(io.StringIO(csv_download.content.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["predicted_index"] == "0"
    assert rows[0]["predicted_class"] == CLASS_NAMES[0]

    zip_download = client.get(f"/api/jobs/{completed['id']}/download?format=zip")
    assert zip_download.status_code == 200, zip_download.text
    with zipfile.ZipFile(io.BytesIO(zip_download.content)) as archive:
        assert {"inference_results.csv", "inference_results.json"}.issubset(archive.namelist())
        assert any(name.startswith("images/") and name.endswith("kidney.jpg") for name in archive.namelist())
