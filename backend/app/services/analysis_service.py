"""End-to-end quick analysis orchestration.

This module deliberately contains no eager torch imports, allowing FastAPI to
start and present the "尚未安裝模型" state on machines without model files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .artifact_service import create_result_archive


class QuickAnalysisError(RuntimeError):
    pass


def _managed(root: Path, relative: Any) -> Path:
    value = Path(str(relative))
    if value.is_absolute():
        raise QuickAnalysisError("分析設定不可包含本機絕對路徑。")
    root = root.resolve()
    result = (root / value).resolve()
    if not result.is_relative_to(root):
        raise QuickAnalysisError("分析設定路徑超出受管理目錄。")
    return result


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _metadata_architecture(weights: Path) -> str | None:
    metadata = weights.parent / "model_metadata.json"
    if not metadata.is_file():
        return None
    try:
        with metadata.open("r", encoding="utf-8-sig") as handle:
            return str(json.load(handle).get("architecture") or "").lower()
    except (OSError, ValueError, TypeError):
        return None


def _default_model(models_root: Path, *, segmentation: bool) -> Path:
    candidates = sorted(models_root.rglob("*.pth")) if models_root.exists() else []
    for candidate in candidates:
        if candidate.name == "last_checkpoint.pth":
            continue
        architecture = _metadata_architecture(candidate)
        looks_like_unet = architecture == "unet" or "unet" in candidate.as_posix().lower()
        if looks_like_unet == segmentation:
            return candidate
    kind = "UNet" if segmentation else "分類"
    raise QuickAnalysisError(f"尚未安裝{kind}模型。")


def _model_from_config(
    models_root: Path,
    config: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    segmentation: bool,
) -> Path:
    for key in keys:
        if config.get(key):
            result = _managed(models_root, config[key])
            if not result.is_file():
                raise QuickAnalysisError("尚未安裝模型，或指定的模型已被移除。")
            return result
    return _default_model(models_root, segmentation=segmentation)


def _phase(
    callback: Callable[[int, int, str], None] | None,
    start: int,
    end: int,
) -> Callable[[int, int, str], None] | None:
    if callback is None:
        return None

    def report(current: int, total: int, message: str) -> None:
        fraction = max(0.0, min(1.0, current / max(1, total)))
        callback(int(start + (end - start) * fraction), 100, message)

    return report


def run_quick_analysis(
    image_paths: Iterable[str | Path],
    *,
    workspace: str | Path,
    data_root: str | Path,
    models_root: str | Path,
    features_root: str | Path,
    config: Mapping[str, Any] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Process, segment, extract features and classify a managed image set."""

    from ..ml.features import generate_feature_csv
    from ..ml.inference import run_batch_inference
    from ..ml.processing import copy_inputs, list_images, run_processing_pipeline
    from ..ml.segmentation import generate_masks

    config = dict(config or {})
    data_root = Path(data_root).resolve()
    models_root = Path(models_root).resolve()
    features_root = Path(features_root).resolve()
    workspace = Path(workspace).resolve()
    if not workspace.is_relative_to(data_root):
        raise QuickAnalysisError("快速分析工作目錄不在 DATA_DIR 內。")
    workspace.mkdir(parents=True, exist_ok=True)
    inputs = [Path(path).resolve() for path in image_paths]
    if not inputs or any(not path.is_relative_to(data_root) for path in inputs):
        raise QuickAnalysisError("快速分析只能使用已匯入的圖片。")

    configured_steps = config.get("steps", config.get("processing_steps"))
    steps = ("convert", "crop", "rb") if configured_steps is None else tuple(configured_steps)
    if steps:
        raw_overrides = config.get("source_overrides")
        source_overrides: dict[str, Any] = {}
        if isinstance(raw_overrides, Mapping):
            for step, source in raw_overrides.items():
                if isinstance(source, (list, tuple)):
                    source_overrides[str(step)] = [_managed(data_root, item) for item in source]
                elif source:
                    source_overrides[str(step)] = _managed(data_root, source)
        processed = run_processing_pipeline(
            inputs,
            workspace / "processing",
            steps,
            source_overrides=source_overrides,
            seed=int(config.get("random_seed", config.get("seed", 32008))),
            progress=_phase(progress, 0, 30),
        )
        processed_dir = processed.output_dir
        processing_payload: dict[str, Any] = {
            "steps": [
                {
                    **step,
                    "output": _relative(data_root, Path(str(step["output"]))),
                }
                for step in processed.steps
            ],
            "warnings": processed.warnings,
        }
    else:
        processed_dir = copy_inputs(inputs, workspace / "processing" / "output")
        processing_payload = {"steps": [], "warnings": []}
        if progress:
            progress(30, 100, "copy inputs")
    processed_images = list_images(processed_dir)
    if not processed_images:
        raise QuickAnalysisError("影像處理後沒有可分析的圖片。")

    configured_masks = config.get("mask_dir")
    if configured_masks:
        masks_dir = _managed(data_root, configured_masks)
        if not masks_dir.is_dir():
            raise QuickAnalysisError("指定的遮罩目錄不存在。")
        masks: list[Path] = []
        if progress:
            progress(55, 100, "use supplied masks")
    else:
        unet_path = _model_from_config(
            models_root,
            config,
            ("unet_model_path", "segmentation_model_path", "mask_model_path"),
            segmentation=True,
        )
        masks_dir = workspace / "masks"
        masks = generate_masks(
            processed_images,
            source_root=processed_dir,
            output_root=masks_dir,
            model_path=unet_path,
            device=config.get("device"),
            refine=bool(config.get("refine", True)),
            progress=_phase(progress, 30, 55),
        )

    metadata_csv = (
        _managed(data_root, config["metadata_csv"])
        if config.get("metadata_csv")
        else None
    )
    diabetes_excel = (
        _managed(features_root, config["diabetes_excel"])
        if config.get("diabetes_excel")
        else features_root / "add_HbA1C.xlsx"
    )
    feature_report = generate_feature_csv(
        processed_images,
        workspace / "features" / "features.csv",
        mask_dir=masks_dir,
        metadata_csv=metadata_csv,
        diabetes_excel=diabetes_excel,
        progress=_phase(progress, 55, 75),
    )

    classifier_path = _model_from_config(
        models_root,
        config,
        ("classifier_model_path", "model_path"),
        segmentation=False,
    )
    inference_metadata = (
        _managed(data_root, config["feature_csv"])
        if config.get("feature_csv")
        else feature_report.output_csv
    )
    inference_report = run_batch_inference(
        processed_images,
        model_path=classifier_path,
        output_dir=workspace / "inference",
        architecture=config.get("architecture"),
        coral=bool(config.get("coral", False)),
        metadata_csv=inference_metadata,
        device=config.get("device"),
        progress=_phase(progress, 75, 100),
    )

    archive_sources: list[Path] = [processed_dir, feature_report.output_csv, workspace / "inference"]
    if masks_dir.is_relative_to(workspace):
        archive_sources.append(masks_dir)
    archive = create_result_archive(
        workspace,
        archive_sources,
        filename="quick_analysis.zip",
    )
    feature_payload = feature_report.to_dict()
    feature_payload["output_csv"] = _relative(data_root, feature_report.output_csv)
    inference_payload = inference_report.to_dict()
    inference_payload["csv"] = _relative(data_root, inference_report.csv_path)
    inference_payload["zip"] = _relative(data_root, inference_report.zip_path)
    return {
        "operation": "quick_analysis",
        "processing": {
            **processing_payload,
            "output_dir": _relative(data_root, processed_dir),
        },
        "masks": {
            "output_dir": _relative(data_root, masks_dir) if masks_dir.is_relative_to(data_root) else None,
            "files": [_relative(data_root, path) for path in masks],
        },
        "features": feature_payload,
        "inference": inference_payload,
        "archive_path": _relative(data_root, archive),
        "download": _relative(data_root, archive),
    }


__all__ = ["QuickAnalysisError", "run_quick_analysis"]
