from __future__ import annotations

from pathlib import Path


def test_dataset_persists_corrupt_issue_and_links_uploaded_mask(client, make_image):
    valid = make_image(image_format="PNG")
    mask = make_image(color=(255, 255, 255), image_format="PNG")
    response = client.post(
        "/api/datasets",
        data={"name": "quality dataset", "k_folds": "0"},
        files=[
            ("files", ("valid.png", valid, "image/png")),
            ("files", ("patient-folder/broken.png", b"not an image", "image/png")),
            ("masks", ("valid_mask.png", mask, "image/png")),
        ],
    )
    assert response.status_code == 201, response.text
    dataset = response.json()
    assert dataset["status"] == "ready"
    assert dataset["sample_count"] == 1

    summary = client.get(f"/api/datasets/{dataset['id']}/summary")
    assert summary.status_code == 200
    assert summary.json()["corrupt_count"] == 1
    assert summary.json()["missing_mask_count"] == 0

    samples = client.get(f"/api/datasets/{dataset['id']}/samples").json()["items"]
    assert len(samples) == 1
    assert samples[0]["has_mask"] is True
    assert samples[0]["missing_mask"] is False
    assert samples[0]["mask_url"].endswith("/mask")
    mask_response = client.get(samples[0]["mask_url"])
    assert mask_response.status_code == 200
    assert mask_response.headers["content-type"].startswith("image/png")

    missing = client.get(f"/api/datasets/{dataset['id']}/samples?status=missing_mask")
    assert missing.status_code == 200
    assert missing.json()["total"] == 0

    issues = client.get(f"/api/datasets/{dataset['id']}/issues")
    assert issues.status_code == 200
    assert issues.json()["total"] == 1
    issue = issues.json()["items"][0]
    assert issue["display_name"] == "broken.png"
    assert issue["issue_type"] == "corrupt"
    assert issue["error_code"] == "INVALID_IMAGE"
    assert issue["sha256"]
    assert issue["size_bytes"] == len(b"not an image")
    assert "patient-folder" not in str(issue)

    from backend.app.core.config import get_settings

    dataset_root = Path(get_settings().datasets_dir) / dataset["id"]
    stored_files = [path for path in dataset_root.rglob("*") if path.is_file()]
    assert not any(path.read_bytes() == b"not an image" for path in stored_files)


def test_all_corrupt_dataset_remains_viewable_but_invalid(client):
    response = client.post(
        "/api/datasets",
        data={"name": "rejected only", "k_folds": "0"},
        files=[("files", ("broken.png", b"broken", "image/png"))],
    )
    assert response.status_code == 201, response.text
    dataset = response.json()
    assert dataset["status"] == "invalid"
    assert dataset["sample_count"] == 0
    summary = client.get(f"/api/datasets/{dataset['id']}/summary").json()
    assert summary["corrupt_count"] == 1
    assert summary["image_count"] == 0
    assert client.get(f"/api/datasets/{dataset['id']}/issues?issue_type=corrupt").json()["total"] == 1


def test_missing_mask_filter_is_backed_by_persisted_relationship(client, make_image):
    response = client.post(
        "/api/datasets",
        data={"name": "no masks", "k_folds": "0"},
        files=[("files", ("plain.png", make_image(image_format="PNG"), "image/png"))],
    )
    assert response.status_code == 201, response.text
    dataset_id = response.json()["id"]
    summary = client.get(f"/api/datasets/{dataset_id}/summary").json()
    assert summary["missing_mask_count"] == 1
    filtered = client.get(f"/api/datasets/{dataset_id}/samples?status=missing_mask").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["missing_mask"] is True
    assert filtered["items"][0]["mask_url"] is None
