from __future__ import annotations


def test_job_mask_results_expose_only_workspace_scoped_image_urls(client, make_image):
    from backend.app.core.config import get_settings
    from backend.app.db.models import Job, uuid_str
    from backend.app.db.session import get_session_factory

    settings = get_settings()
    job_id = uuid_str()
    workspace = settings.jobs_dir / job_id
    source = workspace / "input" / "scan.jpg"
    mask = workspace / "masks" / "scan.png"
    source.parent.mkdir(parents=True)
    mask.parent.mkdir(parents=True)
    source.write_bytes(make_image((30, 90, 160), "JPEG"))
    mask.write_bytes(make_image((255, 255, 255), "PNG"))

    with get_session_factory()() as db:
        db.add(
            Job(
                id=job_id,
                dataset_id=None,
                kind="masks",
                status="completed",
                progress=100,
                config_json={},
                workspace_path=f"jobs/{job_id}",
                result_json={
                    "operation": "masks",
                    "previews": [
                        {
                            "name": "scan.jpg",
                            "source_file": "input/scan.jpg",
                            "mask_file": "masks/scan.png",
                        }
                    ],
                },
            )
        )
        db.commit()

    response = client.get(f"/api/jobs/{job_id}/results")
    assert response.status_code == 200, response.text
    result = response.json()["results"]
    assert "previews" not in result
    pair = result["mask_previews"][0]
    assert pair["name"] == "scan.jpg"
    assert set(pair) == {"name", "source_url", "mask_url"}
    assert not any(str(value).startswith(("/tmp", "C:\\")) for value in pair.values())

    original = client.get(pair["source_url"])
    generated = client.get(pair["mask_url"])
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/jpeg"
    assert generated.status_code == 200
    assert generated.headers["content-type"] == "image/png"

    traversal = client.get(f"/api/jobs/{job_id}/files/%2e%2e%2foutside.png")
    assert traversal.status_code in {400, 404}
    non_image = workspace / "input" / "notes.txt"
    non_image.write_text("private", encoding="utf-8")
    rejected = client.get(f"/api/jobs/{job_id}/files/input/notes.txt")
    assert rejected.status_code == 404
    assert rejected.json()["error"]["code"] == "JOB_IMAGE_MISSING"
