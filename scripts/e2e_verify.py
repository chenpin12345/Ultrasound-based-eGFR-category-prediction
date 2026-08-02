"""Run an isolated, real end-to-end acceptance check against the FastAPI app.

The verifier creates only deterministic synthetic images and stores the SQLite
database, datasets, jobs and model artifacts below a temporary directory.  It
does not read or mutate the application's normal ``data`` or ``models`` trees.

Run from the repository root with::

    .venv\\Scripts\\python.exe scripts\\e2e_verify.py

Use ``--keep-temp`` when inspecting generated artifacts after the run.
"""

from __future__ import annotations

import argparse
import gc
import io
import json
import math
import os
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

LEGACY_CLASS_NAMES = (
    "eGFR -15",
    "eGFR 15-29",
    "eGFR 30-59",
    "eGFR 60-89",
    "eGFR 90-",
)
TERMINAL_STATUSES = {"completed", "failed", "stopped", "interrupted"}


class AcceptanceFailure(RuntimeError):
    """Raised when an acceptance condition is not met."""


@dataclass
class AcceptanceReport:
    started: float = field(default_factory=time.monotonic)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def pass_check(self, name: str, started: float, **details: Any) -> None:
        item = {
            "name": name,
            "status": "passed",
            "seconds": round(time.monotonic() - started, 3),
            **details,
        }
        self.checks.append(item)
        suffix = " ".join(f"{key}={value}" for key, value in details.items())
        print(f"[PASS] {name} ({item['seconds']:.3f}s){' ' + suffix if suffix else ''}", flush=True)

    def skip_check(self, name: str, started: float, reason: str) -> None:
        item = {
            "name": name,
            "status": "skipped",
            "seconds": round(time.monotonic() - started, 3),
            "reason": reason,
        }
        self.checks.append(item)
        print(f"[SKIP] {name} ({item['seconds']:.3f}s) {reason}", flush=True)

    def to_dict(self, *, isolated_root: Path, kept: bool) -> dict[str, Any]:
        return {
            "status": "passed",
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "isolated_root": str(isolated_root) if kept else None,
            "temporary_artifacts_kept": kept,
            "checks": self.checks,
        }


def _response_json(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def _expect(response: Any, status_code: int, context: str) -> dict[str, Any]:
    if response.status_code != status_code:
        raise AcceptanceFailure(
            f"{context}: expected HTTP {status_code}, received {response.status_code}: "
            f"{_response_json(response)!r}"
        )
    payload = _response_json(response)
    if not isinstance(payload, dict):
        raise AcceptanceFailure(f"{context}: expected a JSON object, received {payload!r}")
    return payload


def _synthetic_png(class_index: int, image_index: int, *, size: int = 72) -> bytes:
    """Return a deterministic, non-clinical image with a non-empty texture."""

    from PIL import Image, ImageDraw

    base = (
        24 + class_index * 38,
        18 + image_index * 42,
        30 + class_index * 13 + image_index * 7,
    )
    image = Image.new("RGB", (size, size), base)
    draw = ImageDraw.Draw(image)
    accent = tuple(min(255, value + 65) for value in base)
    inverse = tuple(255 - value for value in base)
    margin = 6 + image_index
    draw.ellipse((margin, 9, size - 8, size - margin), fill=accent, outline=inverse, width=2)
    draw.rectangle((9 + class_index, 12 + image_index, 24 + image_index, 55), fill=inverse)
    for offset in range(class_index + 1):
        y = 5 + offset * 8 + image_index
        draw.line((3, y, size - 4, size - y), fill=(255, 255, 255), width=1)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=False)
    return buffer.getvalue()


def _wait_for_training(
    client: Any,
    training_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float,
    description: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = _expect(
            client.get(f"/api/training/jobs/{training_id}"),
            200,
            f"poll training for {description}",
        )
        if predicate(latest):
            return latest
        if latest.get("status") in {"failed", "interrupted"}:
            raise AcceptanceFailure(
                f"training entered {latest.get('status')!r} while waiting for {description}: {latest}"
            )
        time.sleep(0.05)
    raise AcceptanceFailure(
        f"training did not reach {description} within {timeout:.0f}s; latest={latest}"
    )


def _wait_for_job(client: Any, job_id: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = _expect(client.get(f"/api/jobs/{job_id}"), 200, "poll background job")
        if latest.get("status") in TERMINAL_STATUSES:
            if latest.get("status") != "completed":
                raise AcceptanceFailure(
                    f"job {job_id} ended as {latest.get('status')!r}: "
                    f"{latest.get('error_code')} {latest.get('error_message')}"
                )
            return latest
        time.sleep(0.05)
    raise AcceptanceFailure(f"job {job_id} did not complete within {timeout:.0f}s; latest={latest}")


def _configure_isolated_environment(root: Path) -> None:
    data_dir = root / "data"
    models_dir = root / "models"
    project_root = root / "project"
    (project_root / "features").mkdir(parents=True, exist_ok=True)
    values = {
        "ISU_AI_PROJECT_ROOT": project_root,
        "ISU_AI_DATA_DIR": data_dir,
        "ISU_AI_MODELS_DIR": models_dir,
        "ISU_AI_FRONTEND_DIST": root / "frontend-dist",
        "ISU_AI_DATABASE_URL": f"sqlite:///{(data_dir / 'acceptance.sqlite3').as_posix()}",
        "ISU_AI_DEBUG": "false",
    }
    for key, value in values.items():
        os.environ[key] = str(value)


def _import_dataset(client: Any, report: AcceptanceReport) -> dict[str, Any]:
    started = time.monotonic()
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    images_per_class = 4
    for class_index, class_name in enumerate(LEGACY_CLASS_NAMES):
        for image_index in range(images_per_class):
            filename = f"{class_name}/synthetic-{class_index}-{image_index}.png"
            files.append(
                (
                    "files",
                    (filename, _synthetic_png(class_index, image_index), "image/png"),
                )
            )
    dataset = _expect(
        client.post(
            "/api/datasets",
            data={
                "name": "isolated synthetic five-class acceptance dataset",
                "description": "Generated shapes only; contains no patient or clinical data.",
                "train_ratio": "0.6",
                "val_ratio": "0.2",
                "test_ratio": "0.2",
                "seed": "1701",
                "k_folds": "0",
            },
            files=files,
        ),
        201,
        "import synthetic dataset",
    )
    if dataset.get("sample_count") != 20:
        raise AcceptanceFailure(f"dataset imported an unexpected sample count: {dataset}")
    summary = _expect(
        client.get(f"/api/datasets/{dataset['id']}/summary"),
        200,
        "read dataset summary",
    )
    distribution = summary.get("class_distribution") or summary.get("distribution") or []
    if isinstance(distribution, dict):
        populated_classes = [value for value in distribution.values() if int(value) > 0]
    else:
        populated_classes = [item for item in distribution if int(item.get("count", 0)) > 0]
    if len(populated_classes) != 5:
        raise AcceptanceFailure(f"dataset does not contain all five classes: {summary}")
    split_counts = summary.get("split_counts") or summary.get("splits") or {}
    report.pass_check(
        "synthetic_dataset_import",
        started,
        dataset_id=dataset["id"],
        samples=dataset["sample_count"],
        splits=split_counts,
    )
    return dataset


def _train_classifier(
    client: Any,
    dataset: dict[str, Any],
    report: AcceptanceReport,
    *,
    timeout: float,
    exercise_stop_resume: bool,
) -> tuple[dict[str, Any], bool]:
    started = time.monotonic()
    payload = {
        "dataset_id": dataset["id"],
        "name": "synthetic acceptance MobileNetV2",
        "architecture": "mobilenet_v2",
        "mode": "advanced",
        "classification_mode": "multiclass",
        "epochs": 1,
        "batch_size": 10,
        "learning_rate": 0.001,
        "optimizer": "sgd",
        "weight_decay": 0.0,
        "scheduler": "none",
        "early_stopping": False,
        "patience": 2,
        "random_seed": 1701,
        "device": "cpu",
        "class_weights": False,
        "data_augmentation": False,
        "checkpoint_interval": 1,
        "train_ratio": 0.6,
        "validation_ratio": 0.2,
        "test_ratio": 0.2,
        "k_folds": 1,
    }
    training = _expect(
        client.post("/api/training/jobs", json=payload),
        202,
        "create real CPU training job",
    )
    training_id = training["id"]
    resumed = False

    if exercise_stop_resume:
        stop_started = time.monotonic()
        current = _wait_for_training(
            client,
            training_id,
            lambda item: item.get("status") in {"running", "completed"},
            timeout=min(timeout, 60.0),
            description="running or completed",
        )
        if current.get("status") == "running":
            stop_response = client.post(f"/api/training/jobs/{training_id}/stop")
            if stop_response.status_code == 202:
                stopped = _wait_for_training(
                    client,
                    training_id,
                    lambda item: item.get("status") == "stopped",
                    timeout=timeout,
                    description="safe stopped checkpoint",
                )
                artifacts = _expect(
                    client.get(f"/api/training/jobs/{training_id}/artifacts"),
                    200,
                    "list stopped training artifacts",
                )
                kinds = {item.get("kind") for item in artifacts.get("items", [])}
                if "last" not in kinds:
                    raise AcceptanceFailure(
                        f"stopped training did not expose last_checkpoint.pth: {artifacts}"
                    )
                report.pass_check(
                    "safe_training_stop",
                    stop_started,
                    epoch=stopped.get("current_epoch"),
                    checkpoint="last_checkpoint.pth",
                )
                # The durable stopped state is committed immediately before the
                # worker future returns.  This short settle avoids racing the
                # manager's future-removal callback on very fast machines.
                time.sleep(0.25)
                resume_started = time.monotonic()
                resume_response = client.post(f"/api/training/jobs/{training_id}/resume")
                resumed_payload = _expect(resume_response, 202, "resume stopped training")
                if resumed_payload.get("status") != "queued":
                    raise AcceptanceFailure(f"resume did not queue training: {resumed_payload}")
                resumed = True
                report.pass_check("training_resume_queued", resume_started, training_id=training_id)
            elif stop_response.status_code == 409:
                report.skip_check(
                    "safe_training_stop_resume",
                    stop_started,
                    "the one-epoch job completed before the stop request won the race",
                )
            else:
                raise AcceptanceFailure(
                    f"stop training: expected HTTP 202 or completion race, received "
                    f"{stop_response.status_code}: {_response_json(stop_response)!r}"
                )
        else:
            report.skip_check(
                "safe_training_stop_resume",
                stop_started,
                "the one-epoch job completed before a stop request could be sent",
            )

    completed = _wait_for_training(
        client,
        training_id,
        lambda item: item.get("status") == "completed",
        timeout=timeout,
        description="completed epoch",
    )
    if int(completed.get("current_epoch") or 0) < 1:
        raise AcceptanceFailure(f"training completed without persisting epoch 1: {completed}")
    metrics = _expect(
        client.get(f"/api/training/jobs/{training_id}/metrics"),
        200,
        "read real training metrics",
    )
    metric_rows = metrics.get("items", [])
    if not {row.get("split") for row in metric_rows}.issuperset({"train", "val"}):
        raise AcceptanceFailure(f"training metrics are incomplete: {metrics}")
    report.pass_check(
        "real_cpu_training",
        started,
        training_id=training_id,
        architecture=completed.get("architecture"),
        epochs=completed.get("current_epoch"),
        resumed=resumed,
        metric_rows=len(metric_rows),
    )
    return completed, resumed


def _registered_training_model(
    client: Any, training: dict[str, Any], report: AcceptanceReport
) -> dict[str, Any]:
    started = time.monotonic()
    listing = _expect(
        client.get("/api/models?task=classification&limit=200"),
        200,
        "list registered classification models",
    )
    matches = [
        item
        for item in listing.get("items", [])
        if item.get("source_training_job_id") == training["id"]
    ]
    if len(matches) != 1:
        raise AcceptanceFailure(
            f"expected one model registered from training {training['id']}, found {matches}"
        )
    model = matches[0]
    if model.get("architecture") != "mobilenetv2" or model.get("class_count") != 5:
        raise AcceptanceFailure(f"trained model registry contract mismatch: {model}")
    active = _expect(
        client.post(f"/api/models/{model['id']}/activate"),
        200,
        "activate trained classifier",
    )
    if not active.get("active"):
        raise AcceptanceFailure(f"trained classifier was not activated: {active}")
    report.pass_check(
        "trained_model_registration_and_activation",
        started,
        model_id=model["id"],
        bytes=model.get("size_bytes"),
    )
    return active


def _train_real_kfold(
    client: Any,
    dataset: dict[str, Any],
    report: AcceptanceReport,
    *,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    payload = {
        "dataset_id": dataset["id"],
        "name": "synthetic acceptance 2-fold MobileNetV2",
        "architecture": "mobilenet_v2",
        "mode": "advanced",
        "classification_mode": "multiclass",
        "epochs": 1,
        "batch_size": 10,
        "learning_rate": 0.001,
        "optimizer": "sgd",
        "weight_decay": 0.0,
        "scheduler": "none",
        "early_stopping": False,
        "patience": 2,
        "random_seed": 1701,
        "device": "cpu",
        "class_weights": False,
        "data_augmentation": False,
        "checkpoint_interval": 1,
        "train_ratio": 0.6,
        "validation_ratio": 0.2,
        "test_ratio": 0.2,
        "k_folds": 2,
    }
    training = _expect(
        client.post("/api/training/jobs", json=payload),
        202,
        "create real 2-fold CPU training job",
    )
    completed = _wait_for_training(
        client,
        training["id"],
        lambda item: item.get("status") == "completed",
        timeout=timeout,
        description="completed 2-fold cross-validation",
    )
    artifacts = _expect(
        client.get(f"/api/training/jobs/{training['id']}/artifacts"),
        200,
        "list K-fold artifacts",
    )
    metrics_artifact = next(
        (item for item in artifacts.get("items", []) if item.get("kind") == "metrics"),
        None,
    )
    if not metrics_artifact or not metrics_artifact.get("download_url"):
        raise AcceptanceFailure(f"K-fold metrics artifact is missing: {artifacts}")
    metrics_response = client.get(metrics_artifact["download_url"])
    metrics = _expect(metrics_response, 200, "download K-fold aggregate metrics")
    cross_validation = metrics.get("cross_validation") or {}
    if cross_validation.get("fold_count") != 2:
        raise AcceptanceFailure(f"K-fold aggregate summary is invalid: {metrics}")
    if len(cross_validation.get("folds") or []) != 2:
        raise AcceptanceFailure(f"K-fold did not persist both fold results: {metrics}")
    if "validation_accuracy" not in (cross_validation.get("aggregate") or {}):
        raise AcceptanceFailure(f"K-fold validation aggregate is missing: {metrics}")
    report.pass_check(
        "real_two_fold_cross_validation",
        started,
        training_id=training["id"],
        folds=2,
        total_epochs=completed.get("total_epochs"),
        selected_fold=cross_validation.get("selected_fold"),
    )
    return completed


def _run_real_inference(
    client: Any, classifier: dict[str, Any], report: AcceptanceReport, *, timeout: float
) -> dict[str, Any]:
    started = time.monotonic()
    created = _expect(
        client.post(
            "/api/jobs",
            data={
                "kind": "inference",
                "name": "synthetic-trained-model-inference",
                "config": json.dumps(
                    {"model_id": classifier["id"], "device": "cpu"},
                    ensure_ascii=False,
                ),
            },
            files=[
                (
                    "files",
                    ("synthetic-inference.png", _synthetic_png(2, 2), "image/png"),
                )
            ],
        ),
        202,
        "create trained-model inference job",
    )
    completed = _wait_for_job(client, created["id"], timeout=timeout)
    result = completed.get("result_json") or {}
    items = result.get("items") or []
    if result.get("operation") != "inference" or len(items) != 1:
        raise AcceptanceFailure(f"real inference result is incomplete: {result}")
    item = items[0]
    probabilities = item.get("probabilities") or []
    if (
        item.get("predicted_index") not in range(5)
        or len(probabilities) != 5
        or not math.isclose(sum(float(value) for value in probabilities), 1.0, abs_tol=1e-5)
    ):
        raise AcceptanceFailure(f"real inference probabilities violate the five-class contract: {item}")
    report.pass_check(
        "real_trained_model_inference",
        started,
        job_id=completed["id"],
        predicted_index=item["predicted_index"],
        confidence=round(float(item["confidence"]), 6),
    )
    return completed


def _upload_random_unet(client: Any, report: AcceptanceReport) -> dict[str, Any]:
    started = time.monotonic()
    import torch

    from backend.app.ml.contracts import IMAGENET_MEAN, IMAGENET_STD
    from backend.app.ml.segmentation import build_unet

    torch.manual_seed(1701)
    unet = build_unet()
    weights = io.BytesIO()
    torch.save(unet.state_dict(), weights)
    del unet
    gc.collect()
    manifest = {
        "name": "synthetic random acceptance UNet",
        "version": "acceptance-1",
        "task": "segmentation",
        "architecture": "unet",
        "class_count": 2,
        "class_names": ["background", "kidney"],
        "metadata_columns": [],
        "preprocessing": {
            "mode": "RGB",
            "size": [512, 512],
            "mean": list(IMAGENET_MEAN),
            "std": list(IMAGENET_STD),
        },
    }
    uploaded = _expect(
        client.post(
            "/api/models",
            data={"manifest_json": json.dumps(manifest, ensure_ascii=False)},
            files={
                "weights": (
                    "synthetic-random-unet.pth",
                    weights.getvalue(),
                    "application/octet-stream",
                )
            },
        ),
        201,
        "import valid random UNet",
    )
    weights.close()
    active = _expect(
        client.post(f"/api/models/{uploaded['id']}/activate"),
        200,
        "activate random UNet",
    )
    if not active.get("active") or active.get("task") != "segmentation":
        raise AcceptanceFailure(f"UNet activation failed: {active}")
    report.pass_check(
        "valid_random_unet_import_and_activation",
        started,
        model_id=active["id"],
        bytes=active.get("size_bytes"),
    )
    return active


def _run_quick_analysis(
    client: Any,
    classifier: dict[str, Any],
    unet: dict[str, Any],
    report: AcceptanceReport,
    *,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    config = {
        "classifier_model_id": classifier["id"],
        "unet_model_id": unet["id"],
        "device": "cpu",
        "steps": [],
        "refine": False,
        "random_seed": 1701,
    }
    created = _expect(
        client.post(
            "/api/jobs",
            data={
                "kind": "quick_analysis",
                "name": "isolated-synthetic-quick-analysis",
                "config": json.dumps(config, ensure_ascii=False),
            },
            files=[
                (
                    "files",
                    ("synthetic-quick.png", _synthetic_png(3, 1), "image/png"),
                )
            ],
        ),
        202,
        "create quick analysis job",
    )
    completed = _wait_for_job(client, created["id"], timeout=timeout)
    result = completed.get("result_json") or {}
    if result.get("operation") != "quick_analysis":
        raise AcceptanceFailure(f"quick analysis operation is missing: {result}")
    masks = (result.get("masks") or {}).get("files") or []
    feature_rows = (result.get("features") or {}).get("rows")
    inference = result.get("inference") or {}
    if len(masks) != 1 or feature_rows != 1 or (inference.get("summary") or {}).get("total") != 1:
        raise AcceptanceFailure(
            "quick analysis did not complete processing -> UNet -> features -> classifier: "
            f"{result}"
        )
    download = client.get(f"/api/jobs/{completed['id']}/download?format=zip")
    if download.status_code != 200 or download.headers.get("content-type") != "application/zip":
        raise AcceptanceFailure(
            f"quick analysis archive is unavailable: HTTP {download.status_code} "
            f"{_response_json(download)!r}"
        )
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = archive.namelist()
        if not any(name.endswith("features.csv") for name in names):
            raise AcceptanceFailure(f"quick analysis archive is missing features.csv: {names}")
        if not any(name.endswith("inference_results.csv") for name in names):
            raise AcceptanceFailure(f"quick analysis archive is missing inference_results.csv: {names}")
        if not any(name.endswith(".png") and "mask" in name.lower() for name in names):
            raise AcceptanceFailure(f"quick analysis archive is missing a generated mask: {names}")
    report.pass_check(
        "quick_analysis_full_pipeline",
        started,
        job_id=completed["id"],
        masks=len(masks),
        feature_rows=feature_rows,
        inference_items=(inference.get("summary") or {}).get("total"),
        archive_entries=len(names),
    )
    return completed


def run_acceptance(args: argparse.Namespace, isolated_root: Path) -> dict[str, Any]:
    _configure_isolated_environment(isolated_root)

    import torch

    torch.set_num_threads(max(1, args.torch_threads))
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # Safe when another embedding initialized the inter-op pool first.
        pass

    from fastapi.testclient import TestClient

    from backend.app.core.config import get_settings
    from backend.app.db.session import reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    from backend.app.main import create_app

    report = AcceptanceReport()
    print(f"Isolated acceptance root: {isolated_root}", flush=True)
    print(
        f"Runtime: torch={torch.__version__} device=cpu threads={torch.get_num_threads()}",
        flush=True,
    )
    try:
        with TestClient(create_app()) as client:
            health_started = time.monotonic()
            health = _expect(client.get("/api/health"), 200, "system health")
            if health.get("status") != "ok":
                raise AcceptanceFailure(f"system health is not ok: {health}")
            report.pass_check("isolated_fastapi_health", health_started, database="sqlite")

            dataset = _import_dataset(client, report)
            training, _resumed = _train_classifier(
                client,
                dataset,
                report,
                timeout=args.timeout,
                exercise_stop_resume=not args.no_stop_resume,
            )
            classifier = _registered_training_model(client, training, report)
            _run_real_inference(client, classifier, report, timeout=args.timeout)
            _train_real_kfold(client, dataset, report, timeout=args.timeout)
            unet = _upload_random_unet(client, report)
            _run_quick_analysis(
                client,
                classifier,
                unet,
                report,
                timeout=args.timeout,
            )
    finally:
        reset_engine_cache()
        get_settings.cache_clear()
    return report.to_dict(isolated_root=isolated_root, kept=args.keep_temp)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated real FastAPI/ML end-to-end acceptance verifier."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Per training/background-job timeout in seconds (default: 300).",
    )
    parser.add_argument(
        "--torch-threads",
        type=int,
        default=min(4, os.cpu_count() or 1),
        help="PyTorch CPU intra-op threads (default: min(4, CPU count)).",
    )
    parser.add_argument(
        "--no-stop-resume",
        action="store_true",
        help="Skip the optional safe stop/checkpoint/resume exercise.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the isolated data/models directory and print its path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optionally write the final machine-readable report to this path.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.timeout <= 0:
        print("--timeout must be positive", file=sys.stderr)
        return 2
    if args.torch_threads <= 0:
        print("--torch-threads must be positive", file=sys.stderr)
        return 2

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.keep_temp:
        isolated_root = Path(tempfile.mkdtemp(prefix="isu-ai-e2e-acceptance-"))
    else:
        temporary = tempfile.TemporaryDirectory(prefix="isu-ai-e2e-acceptance-")
        isolated_root = Path(temporary.name)
    try:
        payload = run_acceptance(args, isolated_root)
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        print("\nACCEPTANCE PASSED", flush=True)
        print(rendered, flush=True)
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(rendered + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"\nACCEPTANCE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if args.keep_temp:
            print(f"Isolated artifacts retained at: {isolated_root}", file=sys.stderr, flush=True)
        return 1
    finally:
        if temporary is not None:
            temporary.cleanup()
        elif not args.keep_temp and isolated_root.exists():
            shutil.rmtree(isolated_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
