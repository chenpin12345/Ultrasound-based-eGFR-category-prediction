from __future__ import annotations

import io
import json
import time
import zipfile

import torch


def _import_dataset(client, make_image):
    metadata = "image_name,age,matched_eGFR\nmeta.jpg,55,62.5\n".encode()
    response = client.post(
        "/api/datasets",
        data={"name": "測試資料集", "seed": "7", "k_folds": "2"},
        files=[
            ("files", ("eGFR -15/low.jpg", make_image((255, 0, 0)), "image/jpeg")),
            ("files", ("meta.jpg", make_image((0, 255, 0)), "image/jpeg")),
            ("metadata", ("metadata.csv", metadata, "text/csv")),
        ],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_settings_and_error_envelope(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    updated = client.put("/api/settings", json={"language": "zh-TW", "cpu_workers": 3})
    assert updated.status_code == 200
    assert updated.json()["cpu_workers"] == 3
    missing = client.get("/api/datasets/not-found")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DATASET_NOT_FOUND"
    assert missing.headers["x-request-id"]
    unknown = client.get("/api/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "HTTP_ERROR"


def test_dataset_import_summary_files_and_delete(client, make_image):
    dataset = _import_dataset(client, make_image)
    assert dataset["sample_count"] == 2
    assert not any("\\" in str(value) or ":\\" in str(value) for value in dataset.values())
    samples = client.get(f"/api/datasets/{dataset['id']}/samples").json()
    assert samples["total"] == 2
    labels = {item["class_name"] for item in samples["items"]}
    assert labels == {"eGFR -15", "eGFR 60-89"}
    sample = samples["items"][0]
    assert client.get(sample["file_url"]).status_code == 200
    thumb = client.get(sample["thumbnail_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"].startswith("image/jpeg")
    summary = client.get(f"/api/datasets/{dataset['id']}/summary").json()
    assert summary["sample_count"] == 2
    assert sum(summary["splits"].values()) == 2
    download = client.get(f"/api/datasets/{dataset['id']}/summary?download=1")
    assert download.status_code == 200
    assert download.json() == summary
    assert "attachment" in download.headers["content-disposition"]
    assert "summary.json" in download.headers["content-disposition"]
    assert client.delete(f"/api/datasets/{dataset['id']}").status_code == 204


def test_zip_dataset_import_preserves_exact_folder_label(client, make_image):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cohort/eGFR 90-/high.png", make_image((1, 2, 3), "PNG"))
    response = client.post(
        "/api/datasets",
        data={"name": "ZIP 資料集", "k_folds": "2"},
        files={"archive": ("dataset.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 201, response.text
    dataset = response.json()
    samples = client.get(f"/api/datasets/{dataset['id']}/samples").json()["items"]
    assert samples[0]["class_index"] == 4
    assert samples[0]["class_name"] == "eGFR 90-"


def test_model_registry_safe_upload_activation_and_download(client):
    from backend.app.ml.models import build_classifier

    buffer = io.BytesIO()
    torch.save(build_classifier("mobilenetv2").state_dict(), buffer)
    manifest = {
        "name": "分類模型", "version": "1", "task": "classification", "architecture": "mobilenetv2",
        "class_count": 5, "class_names": ["eGFR -15", "eGFR 15-29", "eGFR 30-59", "eGFR 60-89", "eGFR 90-"],
        "metadata_columns": [], "preprocessing": {"size": [224, 224]},
    }
    response = client.post(
        "/api/models",
        data={"manifest_json": json.dumps(manifest, ensure_ascii=False)},
        files={"weights": ("model.pth", buffer.getvalue(), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    model = response.json()
    assert "weights_path" not in model
    assert client.get(model["download_url"]).status_code == 200
    assert client.post(f"/api/models/{model['id']}/activate").json()["active"] is True
    conflict = client.delete(f"/api/models/{model['id']}")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "MODEL_ACTIVE"


def test_model_rename_normalizes_and_enforces_unique_name_per_version(client):
    from backend.app.db.models import ModelRecord
    from backend.app.db.session import get_session_factory

    class_names = ["eGFR -15", "eGFR 15-29", "eGFR 30-59", "eGFR 60-89", "eGFR 90-"]
    with get_session_factory()() as db:
        for model_id, name, digest in (
            ("model-a", "原始名稱", "a" * 64),
            ("model-b", "已存在名稱", "b" * 64),
        ):
            db.add(ModelRecord(
                id=model_id,
                name=name,
                version="1",
                task="classification",
                architecture="resnet18",
                class_count=5,
                class_names=class_names,
                metadata_columns=[],
                preprocessing={},
                weights_path=f"{model_id}/weights.pth",
                metadata_path=f"{model_id}/model_metadata.json",
                sha256=digest,
                size_bytes=1,
                status="ready",
            ))
        db.commit()

    renamed = client.patch("/api/models/model-a", json={"name": "  新名稱  "})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "新名稱"

    blank = client.patch("/api/models/model-a", json={"name": "   "})
    assert blank.status_code == 422

    duplicate = client.patch("/api/models/model-a", json={"name": "已存在名稱"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "MODEL_VERSION_EXISTS"
    assert client.get("/api/models/model-a").json()["name"] == "新名稱"


def test_job_creation_persists_real_event_contract(client, make_image, monkeypatch):
    dataset = _import_dataset(client, make_image)
    import backend.app.api.routes.jobs as jobs_routes

    class Manager:
        pass

    submitted = []
    monkeypatch.setattr(jobs_routes, "get_worker_manager", lambda: Manager())
    monkeypatch.setattr(jobs_routes, "call_worker", lambda method, job_id: submitted.append((method, job_id)))
    response = client.post("/api/jobs", json={"kind": "process", "dataset_id": dataset["id"], "config": {"steps": ["crop"]}})
    assert response.status_code == 202, response.text
    job = response.json()
    assert submitted == [("submit_job", job["id"])]
    assert job["config_json"]["operation"] == "process"
    assert len(job["config_json"]["sample_ids"]) == 2
    rejected = client.post(
        "/api/jobs",
        json={"kind": "features", "dataset_id": dataset["id"], "config": {"metadata_csv": r"C:\\secret\\metadata.csv"}},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "ABSOLUTE_PATH_FORBIDDEN"


def test_real_background_processing_job_completes(client, make_image):
    dataset = _import_dataset(client, make_image)
    response = client.post(
        "/api/jobs",
        json={"kind": "process", "dataset_id": dataset["id"], "config": {"steps": ["convert"]}},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    for _ in range(100):
        current = client.get(f"/api/jobs/{job['id']}").json()
        if current["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert current["status"] == "completed", current
    assert current["result_json"]["operation"] == "process"
    events = client.get(f"/api/jobs/{job['id']}/events")
    assert events.status_code == 200
    assert '"status": "completed"' in events.text
    event_ids = [int(line.removeprefix("id: ")) for line in events.text.splitlines() if line.startswith("id: ")]
    assert event_ids == sorted(event_ids) and len(event_ids) >= 2
    resumed = client.get(f"/api/jobs/{job['id']}/events", headers={"Last-Event-ID": str(event_ids[-2])})
    resumed_ids = [int(line.removeprefix("id: ")) for line in resumed.text.splitlines() if line.startswith("id: ")]
    assert resumed_ids == [event_ids[-1]]
