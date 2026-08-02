"""Copy-only image processing stages extracted from the desktop application."""

from __future__ import annotations

import os
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .contracts import CLASS_DIR_TO_INDEX, class_index_from_egfr, legacy_class_dir
from .models import MLDependencyError


IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif"})
PROCESS_STEPS = ("convert", "crop", "rb", "assort")
RECOMMENDED_ORDER = {name: index for index, name in enumerate(PROCESS_STEPS)}
CONVERT_COPY_WARNING = "convert 只會刪除工作副本中的 JFIF；使用者原始檔案不會被修改。"


class ProcessingPlanError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessingPlan:
    steps: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass
class ProcessingResult:
    workspace: Path
    output_dir: Path
    steps: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace": str(self.workspace),
            "output_dir": str(self.output_dir),
            "steps": self.steps,
            "warnings": self.warnings,
        }


def validate_processing_order(steps: Sequence[str]) -> ProcessingPlan:
    normalized = tuple(str(step).strip().lower() for step in steps if str(step).strip())
    if not normalized:
        raise ProcessingPlanError("At least one processing step is required.")
    unknown = [step for step in normalized if step not in PROCESS_STEPS]
    if unknown:
        raise ProcessingPlanError(f"Unknown processing steps: {unknown}")
    if len(set(normalized)) != len(normalized):
        raise ProcessingPlanError("A processing step may only appear once.")
    warnings: list[str] = []
    if "convert" in normalized:
        warnings.append(CONVERT_COPY_WARNING)
    ranks = [RECOMMENDED_ORDER[step] for step in normalized]
    if ranks != sorted(ranks):
        warnings.append("自訂順序不同於建議順序 convert → crop → rb → assort，結果可能不同。")
    if "assort" in normalized and normalized[-1] != "assort":
        warnings.append("assort 建議最後執行，避免後續步驟破壞資料分割結構。")
    if "rb" in normalized and "crop" in normalized and normalized.index("rb") < normalized.index("crop"):
        warnings.append("RB 的固定像素區域以裁切後影像為基準，先執行 RB 可能造成不相容結果。")
    return ProcessingPlan(normalized, tuple(warnings))


def list_images(source: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(source, (str, Path)):
        source = [source]
    images: list[Path] = []
    for item in source:
        path = Path(item)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            images.append(path)
        elif path.is_dir():
            images.extend(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES
            )
    return sorted(dict.fromkeys(path.resolve() for path in images))


def copy_inputs(source: str | Path | Iterable[str | Path], destination: str | Path) -> Path:
    images = list_images(source)
    if not images:
        raise ProcessingPlanError("No supported images were found.")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if isinstance(source, (str, Path)) and Path(source).is_dir():
        root = Path(source).resolve()
    else:
        parents = [str(path.parent) for path in images]
        root = Path(os.path.commonpath(parents))
    for index, image in enumerate(images):
        try:
            relative = image.relative_to(root)
        except ValueError:
            relative = Path(f"{index:06d}_{image.name}")
        target = destination / relative
        if target.exists():
            target = target.with_name(f"{target.stem}_{index}{target.suffix}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, target)
    return destination


def convert_jfif(source: str | Path, output: str | Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise MLDependencyError("Pillow is required for JFIF conversion.") from exc
    source, output = Path(source), Path(output)
    copy_inputs(source, output)
    success = failure = 0
    for path in list(output.rglob("*.jfif")):
        try:
            with Image.open(path) as image:
                image.convert("RGB").save(path.with_suffix(".jpg"), "JPEG", quality=95)
            path.unlink()  # Only the stage copy is removed.
            success += 1
        except Exception:
            failure += 1
    return success, failure


def crop_images(source: str | Path, output: str | Path) -> tuple[int, int]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise MLDependencyError("OpenCV and NumPy are required for cropping.") from exc
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    success = failure = 0
    for path in list_images(source):
        try:
            relative = path.relative_to(source.resolve())
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("decode failed")
            if image.shape[1] != 1600 or image.shape[0] != 1200:
                image = cv2.resize(image, (1600, 1200), interpolation=cv2.INTER_LANCZOS4)
            cropped = image[90 : 90 + 1024, 235 : 235 + 1024]
            suffix = ".jpg" if path.suffix.lower() == ".jfif" else path.suffix.lower()
            target = (output / relative).with_suffix(suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            encoded, buffer = cv2.imencode(suffix, cropped)
            if not encoded:
                raise ValueError("encode failed")
            buffer.tofile(str(target))
            success += 1
        except Exception:
            failure += 1
    return success, failure


def _rb_mask(image):
    import cv2
    import numpy as np

    values = image.astype(np.float32)
    color = (
        (np.abs(values[:, :, 0] - values[:, :, 1]) > 20)
        | (np.abs(values[:, :, 0] - values[:, :, 2]) > 20)
        | (np.abs(values[:, :, 1] - values[:, :, 2]) > 20)
    ).astype(np.uint8) * 255
    color = cv2.morphologyEx(
        color, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    color = cv2.dilate(color, np.ones((3, 3), np.uint8), iterations=2)
    white = (
        (values[:, :, 0] > 240) & (values[:, :, 1] > 240) & (values[:, :, 2] > 240)
    ).astype(np.uint8) * 255
    white = cv2.dilate(white, np.ones((3, 3), np.uint8), iterations=4)
    return cv2.bitwise_or(color, white)


def remove_blue_lines(source: str | Path, output: str | Path) -> tuple[int, int]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise MLDependencyError("OpenCV and NumPy are required for RB processing.") from exc
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    success = failure = 0
    for path in list_images(source):
        try:
            relative = path.relative_to(source.resolve())
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("decode failed")
            height = image.shape[0]
            result = cv2.inpaint(image, _rb_mask(image), 3, cv2.INPAINT_TELEA)
            result[:40, :] = 0
            result[height - 100 :, :] = 0
            result[:, :25] = 0
            result[400:485, 20:40] = 0
            result[50:105, 800:920] = 0
            result[0:105, 1000:1024] = 0
            suffix = ".jpg" if path.suffix.lower() == ".jfif" else path.suffix.lower()
            target = (output / relative).with_suffix(suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            encoded, buffer = cv2.imencode(suffix, result)
            if not encoded:
                raise ValueError("encode failed")
            buffer.tofile(str(target))
            success += 1
        except Exception:
            failure += 1
    return success, failure


def _class_for_image(path: Path) -> int:
    if path.parent.name in CLASS_DIR_TO_INDEX:
        return CLASS_DIR_TO_INDEX[path.parent.name]
    try:
        return class_index_from_egfr(float(path.stem.split("_")[0]))
    except (IndexError, ValueError) as exc:
        raise ProcessingPlanError(f"Cannot determine eGFR class for {path.name!r}.") from exc


def assort_classification(
    source: str | Path,
    output: str | Path,
    *,
    ratios: tuple[float, float, float] = (0.7, 0.2, 0.1),
    seed: int = 32008,
) -> dict[str, int]:
    if len(ratios) != 3 or any(value < 0 for value in ratios) or sum(ratios) <= 0:
        raise ProcessingPlanError("Invalid train/validation/test ratios.")
    total_ratio = sum(ratios)
    ratios = tuple(value / total_ratio for value in ratios)
    grouped: dict[int, list[Path]] = {index: [] for index in range(5)}
    for path in list_images(source):
        grouped[_class_for_image(path)].append(path)
    output = Path(output) / "method2"
    counts = {"train": 0, "val": 0, "test": 0}
    rng = random.Random(seed)
    for class_index, paths in grouped.items():
        rng.shuffle(paths)
        train_end = int(len(paths) * ratios[0])
        val_end = train_end + int(len(paths) * ratios[1])
        assignments = {
            "train": paths[:train_end],
            "val": paths[train_end:val_end],
            "test": paths[val_end:],
        }
        for split, split_paths in assignments.items():
            target_dir = output / split / legacy_class_dir(class_index)
            target_dir.mkdir(parents=True, exist_ok=True)
            for path in split_paths:
                shutil.copy2(path, target_dir / path.name)
                counts[split] += 1
    return counts


def run_processing_pipeline(
    source: str | Path | Iterable[str | Path],
    workspace: str | Path,
    steps: Sequence[str],
    *,
    source_overrides: Mapping[str, str | Path | Iterable[str | Path]] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    seed: int = 32008,
) -> ProcessingResult:
    plan = validate_processing_order(steps)
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    original_copy = copy_inputs(source, workspace / "original")
    current = original_copy
    result = ProcessingResult(workspace, current, warnings=list(plan.warnings))
    overrides = source_overrides or {}
    for index, step in enumerate(plan.steps, 1):
        stage = workspace / "stages" / f"{index:02d}_{step}"
        stage_source = stage / "input"
        copy_inputs(overrides.get(step, current), stage_source)
        output = stage / "output"
        if step == "convert":
            success, failure = convert_jfif(stage_source, output)
        elif step == "crop":
            success, failure = crop_images(stage_source, output)
        elif step == "rb":
            success, failure = remove_blue_lines(stage_source, output)
        else:
            counts = assort_classification(stage_source, output, seed=seed)
            success, failure = sum(counts.values()), 0
        result.steps.append(
            {"name": step, "success": success, "failure": failure, "output": str(output)}
        )
        current = output
        if progress:
            progress(index, len(plan.steps), step)
    result.output_dir = current
    return result

