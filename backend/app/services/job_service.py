"""Route-callable facade for durable image-analysis jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def submit_job(job_id: str, *, manager: Any = None) -> str:
    """Enqueue a Job row that has already been committed to the database."""

    if manager is None:
        from ..workers import get_worker_manager

        manager = get_worker_manager()
    manager.submit_job(job_id)
    return job_id


def process_images(
    image_paths: Iterable[str | Path],
    workspace: str | Path,
    *,
    steps: Sequence[str] = ("convert", "crop", "rb", "assort"),
    source_overrides: Mapping[str, Any] | None = None,
    seed: int = 32008,
    progress: Any = None,
):
    from ..ml.processing import run_processing_pipeline

    return run_processing_pipeline(
        image_paths,
        workspace,
        steps,
        source_overrides=source_overrides,
        seed=seed,
        progress=progress,
    )


def generate_image_masks(image_paths: Iterable[str | Path], **kwargs: Any):
    from ..ml.segmentation import generate_masks

    return generate_masks(image_paths, **kwargs)


def extract_features(image_paths: Iterable[str | Path], output_csv: str | Path, **kwargs: Any):
    from ..ml.features import generate_feature_csv

    return generate_feature_csv(image_paths, output_csv, **kwargs)


def infer_images(image_paths: Iterable[str | Path], **kwargs: Any):
    from ..ml.inference import run_batch_inference

    return run_batch_inference(image_paths, **kwargs)


__all__ = [
    "extract_features",
    "generate_image_masks",
    "infer_images",
    "process_images",
    "submit_job",
]
