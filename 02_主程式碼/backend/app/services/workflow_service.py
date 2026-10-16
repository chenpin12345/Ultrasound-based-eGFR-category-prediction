"""Managed, byte-preserving handoffs. No model or training implementation lives here."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.errors import AppError
from ..core.security import safe_resolve, relative_path, sha256_file, validate_image, IMAGE_EXTENSIONS
from ..db.models import Dataset, DatasetSample, DatasetMask, Job, uuid_str
from ..ml.contracts import legacy_class_dir, METADATA_FIELDS


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["dataset", "job"]
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class InputSources(BaseModel):
    model_config = ConfigDict(extra="forbid")
    images: SourceRef
    masks: SourceRef | None = None
    metadata: SourceRef | None = None
    features: SourceRef | None = None


class DerivedDatasetRequest(BaseModel):
    input_sources: InputSources
    name: str = Field(min_length=1, max_length=200)


def fail(message, code="INVALID_HANDOFF"):
    raise AppError(422, code, message)


def read_rows(path):
    if not path:
        return {}
    for encoding in ("utf-8-sig", "cp950"):
        try:
            with Path(path).open(encoding=encoding, newline="") as stream:
                rows = list(csv.DictReader(stream))
            break
        except UnicodeDecodeError:
            continue
    else:
        fail("CSV 編碼不支援。")
    result = {}
    for row in rows:
        key = row.get("image_name") or row.get("file") or row.get("filename")
        if not key:
            fail("CSV 缺少影像名稱。")
        key = Path(key).name
        if key in result:
            fail("CSV 影像名稱重複，無法安全配對。")
        result[key] = row
    return result


def _checked_entries(entries, settings):
    names = set()
    for entry in entries:
        path = safe_resolve(settings.data_dir, entry["image"])
        if not path.is_file():
            fail("來源影像已不存在。", "SOURCE_MISSING")
        validate_image(path, settings.max_image_pixels)
        key = path.stem.casefold()
        if key in names:
            fail("来源影像有重名，請先以不同檔名匯入，避免遮罩或特徵錯配。", "AMBIGUOUS_SOURCE")
        names.add(key)
    if not entries:
        fail("來源沒有可使用的影像。")
    if len(entries) > settings.max_zip_entries:
        fail("來源影像數量超過工作上限。")
    return entries


def resolve_source(db, settings, ref: SourceRef, *, verify=True):
    """Return private entries, preserving stable sample identities across jobs."""
    if ref.kind == "dataset":
        dataset = db.get(Dataset, ref.id)
        if not dataset:
            raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
        if dataset.status != "ready":
            fail("資料集尚未就緒。")
        root = safe_resolve(settings.data_dir, dataset.root_path) if verify else Path(dataset.root_path)
        entries = []
        for row in db.scalars(select(DatasetSample).options(selectinload(DatasetSample.mask)).where(DatasetSample.dataset_id == ref.id).order_by(DatasetSample.id)):
            entries.append({
                "sample_id": row.id, "image": relative_path(safe_resolve(root, row.relative_path), settings.data_dir) if verify else (root / row.relative_path).as_posix(),
                "display_name": row.display_name, "metadata": dict(row.metadata_json or {}),
                "class_index": row.class_index, "class_name": row.class_name, "egfr": row.egfr,
                "split": row.split, "fold": row.fold,
                "mask": (relative_path(safe_resolve(root, row.mask.relative_path), settings.data_dir) if verify else (root / row.mask.relative_path).as_posix()) if row.mask else None,
            })
        has_features = bool(entries) and all(
            all(entry["metadata"].get(field) not in (None, "") for field in METADATA_FIELDS)
            for entry in entries
        )
        return {"dataset_id": dataset.id, "name": dataset.name, "entries": _checked_entries(entries, settings) if verify else entries, "has_features": has_features}
    job = db.get(Job, ref.id)
    if not job:
        raise AppError(404, "JOB_NOT_FOUND", "找不到來源工作。")
    if job.status != "completed":
        raise AppError(409, "SOURCE_NOT_COMPLETED", "來源工作尚未成功完成。")
    workspace = safe_resolve(settings.data_dir, job.workspace_path)
    manifest = workspace / "handoff.json"
    config, result = job.config_json or {}, job.result_json or {}
    if manifest.is_file():
        if verify:
            bundle = json.loads(manifest.read_text(encoding="utf-8"))
        else:
            from .display_cache import display_json
            bundle = display_json(manifest)
    elif job.dataset_id:
        bundle = resolve_source(db, settings, SourceRef(kind="dataset", id=job.dataset_id), verify=verify)
    else:
        paths = config.get("input_paths") or []
        rows = read_rows(safe_resolve(settings.data_dir, config["metadata_csv"])) if config.get("metadata_csv") else {}
        entries = [{"sample_id": f"{job.id}:{index}", "image": path, "display_name": Path(path).name,
                    "metadata": rows.get(Path(path).name, {}), "mask": None,
                    "class_index": None, "class_name": None, "egfr": None, "split": None, "fold": None}
                   for index, path in enumerate(paths)]
        bundle = {"dataset_id": None, "entries": entries, "has_features": bool(config.get("feature_csv"))}
    bundle["name"] = config.get("name") or f"{job.kind} · {job.id[:8]}"
    entries = bundle["entries"]
    if job.kind == "process":
        output = safe_resolve(workspace, Path(result.get("output_dir", "")).relative_to(Path(job.workspace_path)))
        candidates = [p for p in output.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
        by_stem = {}
        for path in candidates:
            by_stem.setdefault(path.stem.casefold(), []).append(path)
        for entry in entries:
            matched = by_stem.get(Path(entry["image"]).stem.casefold(), [])
            if len(matched) != 1:
                fail("前處理產物不完整或有重名，無法交接。")
            entry["image"] = relative_path(matched[0], settings.data_dir) if verify else matched[0].relative_to(settings.data_dir).as_posix()
            entry["mask"] = None  # Changed geometry requires a new matching mask.
        bundle["has_features"] = False
    elif job.kind == "masks":
        bundle["has_features"] = False
        previews = {item["name"]: item for item in result.get("previews", [])}
        if len(previews) != len(entries):
            fail("遮罩產物數量不符，無法交接。")
        for entry in entries:
            item = previews.get(Path(entry["image"]).name)
            if not item:
                fail("遮罩缺少對應來源。")
            entry["mask"] = relative_path(safe_resolve(workspace, item["mask_file"]), settings.data_dir) if verify else (Path(job.workspace_path) / item['mask_file']).as_posix()
    elif job.kind == "features":
        rows = read_rows(safe_resolve(settings.data_dir, result["output_csv"]))
        if result.get("missing_masks") or result.get("missing_features") or result.get("failed_features") or result.get("errors"):
            fail("特徵工作有缺漏，請修正來源後再交接。")
        for entry in entries:
            row = rows.get(Path(entry["image"]).name)
            if not row:
                fail("特徵 CSV 缺少對應影像。")
            entry["metadata"] = {**entry.get("metadata", {}), **row}
        bundle["has_features"] = True
    elif job.kind not in {"inference"}:
        fail("此工作類型尚不支援結果交接。")
    if verify:
        _checked_entries(entries, settings)
    return bundle


def resolve_inputs(db, settings, sources):
    bundle = resolve_source(db, settings, sources.images)
    for role in ("masks", "metadata", "features"):
        ref = getattr(sources, role)
        if ref is None:
            continue
        auxiliary = resolve_source(db, settings, ref)
        mapping = {item["sample_id"]: item for item in auxiliary["entries"]}
        if set(mapping) != {item["sample_id"] for item in bundle["entries"]}:
            fail("附加來源與影像的樣本不一致。")
        for item in bundle["entries"]:
            other = mapping[item["sample_id"]]
            if sha256_file(safe_resolve(settings.data_dir, item["image"])) != sha256_file(safe_resolve(settings.data_dir, other["image"])):
                fail("附加來源使用不同版本影像，請選擇同一工作流程的產物。")
            if role == "masks":
                if not other.get("mask"):
                    fail("附加來源缺少遮罩。")
                item["mask"] = other["mask"]
            else:
                item["metadata"] = dict(other.get("metadata", {}))
        if role == "features":
            if not auxiliary.get("has_features"):
                fail("來源沒有已完成的特徵。")
            bundle["has_features"] = True
    return bundle


def snapshot_inputs(db, settings, sources, workspace, operation):
    bundle = resolve_inputs(db, settings, sources)
    size = 0
    for item in bundle["entries"]:
        image = safe_resolve(settings.data_dir, item["image"])
        size += image.stat().st_size
        folder = legacy_class_dir(item["class_index"]) if operation == "process" and item.get("class_index") is not None else "images"
        destination = safe_resolve(workspace, "input", folder, image.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, destination)
        item["image"] = relative_path(destination, settings.data_dir)
        if item.get("mask"):
            mask = safe_resolve(settings.data_dir, item["mask"])
            validate_image(mask, settings.max_image_pixels)
            target = safe_resolve(workspace, "input", "masks", image.stem + mask.suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            size += mask.stat().st_size
            shutil.copy2(mask, target)
            item["mask"] = relative_path(target, settings.data_dir)
        if size > settings.max_zip_uncompressed_bytes:
            fail("來源總大小超過工作上限。")
    if operation == "features" and any(not e.get("mask") for e in bundle["entries"]):
        fail("交接至特徵擷取前，請先提供每張影像的對應遮罩。")
    rows = [{**e.get("metadata", {}), "image_name": Path(e["image"]).name} for e in bundle["entries"]]
    columns = ["image_name"] + sorted({k for row in rows for k in row if k != "image_name"})
    csv_path = workspace / "input" / "metadata.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    bundle["input_sources"] = sources.model_dump(exclude_none=True)
    (workspace / "handoff.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    config = {"input_paths": [e["image"] for e in bundle["entries"]], "metadata_csv": relative_path(csv_path, settings.data_dir)}
    if any(e.get("mask") for e in bundle["entries"]):
        config["mask_dir"] = relative_path(workspace / "input" / "masks", settings.data_dir)
    if bundle.get("has_features"):
        config["feature_csv"] = config["metadata_csv"]
    return bundle, config


def source_summary(db, settings, ref):
    # Inventory only; snapshot_inputs still uses the default strict resolution.
    bundle = resolve_source(db, settings, ref, verify=False)
    entries = bundle["entries"]
    return {"source": ref.model_dump(), "dataset_id": bundle.get("dataset_id"), "name": bundle.get("name"),
            "image_count": len(entries), "mask_count": sum(bool(e.get("mask")) for e in entries),
            "metadata_count": sum(bool(e.get("metadata")) for e in entries), "has_features": bundle.get("has_features", False),
            "labeled_count": sum(e.get("class_index") is not None for e in entries)}


def create_derived_dataset(db, settings, payload):
    from ..api.routes.datasets import _thumbnail, _dataset_out
    bundle = resolve_inputs(db, settings, payload.input_sources)
    if not payload.name.strip():
        fail("資料集名稱不可空白。")
    if any(e.get("class_index") is None or not e.get("split") for e in bundle["entries"]):
        fail("訓練用資料集需要既有標籤與資料分割；請先從資料集管理匯入有標籤的資料。")
    dataset_id = uuid_str()
    root = safe_resolve(settings.datasets_dir, dataset_id)
    root.mkdir(parents=True, exist_ok=False)
    try:
        base = db.get(Dataset, bundle.get("dataset_id")) if bundle.get("dataset_id") else None
        dataset = Dataset(id=dataset_id, name=payload.name.strip(), root_path=relative_path(root, settings.data_dir),
                          status="ready", source_name="workflow-results", split_config=dict(base.split_config) if base else {},
                          metadata_columns=sorted({k for e in bundle["entries"] for k in e.get("metadata", {})}),
                          sample_count=len(bundle["entries"]), total_bytes=0)
        db.add(dataset)
        seen = {}
        for entry in bundle["entries"]:
            src = safe_resolve(settings.data_dir, entry["image"])
            target = safe_resolve(root, "images", src.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            info = validate_image(target, settings.max_image_pixels)
            digest = sha256_file(target)
            sample_id = uuid_str()
            thumbnail = root / "thumbnails" / (sample_id + ".jpg")
            _thumbnail(target, thumbnail, settings.thumbnail_size)
            sample = DatasetSample(id=sample_id, dataset_id=dataset_id, relative_path=relative_path(target, root),
                                   display_name=entry["display_name"], stored_name=target.name, sha256=digest,
                                   mime_type=info.mime_type, size_bytes=target.stat().st_size, width=info.width, height=info.height,
                                   class_index=entry["class_index"], class_name=entry["class_name"], egfr=entry.get("egfr"),
                                   split=entry["split"], fold=entry.get("fold"), metadata_json=entry.get("metadata", {}),
                                   thumbnail_path=relative_path(thumbnail, root), duplicate_of_id=seen.get(digest))
            db.add(sample)
            seen.setdefault(digest, sample_id)
            dataset.total_bytes += sample.size_bytes
            if entry.get("mask"):
                mask_src = safe_resolve(settings.data_dir, entry["mask"])
                mask_target = root / "masks" / (sample_id + mask_src.suffix)
                mask_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(mask_src, mask_target)
                mi = validate_image(mask_target, settings.max_image_pixels)
                db.add(DatasetMask(sample_id=sample_id, relative_path=relative_path(mask_target, root),
                                   display_name=mask_target.name, sha256=sha256_file(mask_target), mime_type=mi.mime_type,
                                   size_bytes=mask_target.stat().st_size, width=mi.width, height=mi.height))
        (root / "lineage.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        db.commit()
        db.refresh(dataset)
        return _dataset_out(dataset)
    except Exception:
        db.rollback()
        from ..core.security import remove_tree_contained
        remove_tree_contained(root, settings.datasets_dir)
        raise
