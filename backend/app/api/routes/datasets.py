from __future__ import annotations

import csv
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import AppSettings, get_settings
from ...core.errors import AppError
from ...core.security import (
    IMAGE_EXTENSIONS,
    ZipLimits,
    extract_zip_safe,
    relative_path,
    remove_tree_contained,
    safe_resolve,
    sanitize_filename,
    save_upload_file,
    sha256_file,
    validate_image,
)
from ...core.splitting import detect_label, deterministic_stratified_split
from ...db.models import (
    Dataset,
    DatasetImportIssue,
    DatasetMask,
    DatasetSample,
    Job,
    TrainingJob,
    uuid_str,
)
from ...db.session import get_db
from ...schemas.common import Page
from ...schemas.dataset import DatasetImportIssueOut, DatasetOut, DatasetSampleOut, DatasetSummary
from ...services.settings_service import persisted_setting

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _dataset_out(dataset: Dataset) -> dict:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "description": dataset.description,
        "status": dataset.status,
        "source_name": dataset.source_name,
        "sample_count": dataset.sample_count,
        "total_bytes": dataset.total_bytes,
        "image_count": dataset.sample_count,
        "size_bytes": dataset.total_bytes,
        "metadata_columns": dataset.metadata_columns or [],
        "split_config": dataset.split_config or {},
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def _sample_out(sample: DatasetSample) -> dict:
    base = f"/api/datasets/{sample.dataset_id}/samples/{sample.id}"
    return {
        "id": sample.id,
        "dataset_id": sample.dataset_id,
        "display_name": sample.display_name,
        "sha256": sample.sha256,
        "mime_type": sample.mime_type,
        "size_bytes": sample.size_bytes,
        "width": sample.width,
        "height": sample.height,
        "class_index": sample.class_index,
        "class_name": sample.class_name,
        "egfr": sample.egfr,
        "metadata_json": sample.metadata_json or {},
        "metadata": sample.metadata_json or {},
        "split": sample.split,
        "fold": sample.fold,
        "duplicate_of_id": sample.duplicate_of_id,
        "is_duplicate": sample.duplicate_of_id is not None,
        "missing_label": sample.class_index is None,
        "missing_metadata": not bool(sample.metadata_json),
        "has_mask": sample.mask is not None,
        "missing_mask": sample.mask is None,
        "status": "ready",
        "file_url": f"{base}/file",
        "thumbnail_url": f"{base}/thumbnail",
        "mask_url": f"{base}/mask" if sample.mask is not None else None,
    }


def _issue_out(issue: DatasetImportIssue) -> dict:
    return {
        "id": issue.id,
        "dataset_id": issue.dataset_id,
        "display_name": issue.display_name,
        "issue_type": issue.issue_type,
        "error_code": issue.error_code,
        "message": issue.message,
        "sha256": issue.sha256,
        "size_bytes": issue.size_bytes,
        "created_at": issue.created_at,
    }


def _is_mask_logical_name(value: str) -> bool:
    parts = [part.casefold() for part in Path(value.replace("\\", "/")).parts[:-1]]
    return any(part in {"img_mask", "mask", "masks"} for part in parts)


def _mask_match_key(value: str) -> str:
    stem = Path(value.replace("\\", "/")).stem.casefold().strip()
    for suffix in ("_mask", "-mask", " mask"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def _record_import_issue(
    db: Session,
    *,
    dataset_id: str,
    logical_name: str,
    issue_type: str,
    error_code: str,
    message: str,
    source: Path | None = None,
) -> DatasetImportIssue:
    issue = DatasetImportIssue(
        dataset_id=dataset_id,
        display_name=sanitize_filename(Path(logical_name.replace("\\", "/")).name, "rejected-file"),
        issue_type=issue_type,
        error_code=error_code[:100],
        message=message[:500],
        sha256=sha256_file(source) if source is not None and source.is_file() else None,
        size_bytes=source.stat().st_size if source is not None and source.is_file() else 0,
    )
    db.add(issue)
    return issue


def _read_metadata_csv(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    rows: list[dict[str, str]] | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp950"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise AppError(422, "INVALID_METADATA", "Metadata CSV 缺少欄位名稱。")
                rows = list(reader)
                fields = [str(name).strip() for name in reader.fieldnames]
            break
        except UnicodeDecodeError:
            continue
    if rows is None:
        raise AppError(422, "INVALID_METADATA_ENCODING", "Metadata CSV 編碼不支援。")
    result: dict[str, dict[str, str]] = {}
    basename_candidates: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for row in rows:
        name = row.get("image_name") or row.get("file") or row.get("filename")
        if name:
            normalized_name = str(name).replace("\\", "/").strip().lstrip("/")
            normalized_name = "/".join(part for part in normalized_name.split("/") if part not in {"", "."})
            if ".." in normalized_name.split("/"):
                raise AppError(422, "INVALID_METADATA_PATH", "Metadata 包含不安全的圖片相對路徑。")
            values = {
                str(key): "" if value is None else str(value) for key, value in row.items() if key is not None
            }
            result[normalized_name] = values
            basename_candidates.setdefault(Path(normalized_name).name, []).append((normalized_name, values))
    # Basename matching is allowed only when unambiguous. Relative-path keys
    # always win, so same-name files in different folders cannot receive the
    # wrong patient's metadata silently.
    for basename, candidates in basename_candidates.items():
        if len(candidates) == 1:
            result.setdefault(basename, candidates[0][1])
    return result, fields


def _thumbnail(source: Path, destination: Path, size: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image.save(temporary, "JPEG", quality=85, optimize=True)
    os.replace(temporary, destination)


def _zip_limits(settings: AppSettings) -> ZipLimits:
    return ZipLimits(
        max_entries=settings.max_zip_entries,
        max_total_bytes=settings.max_zip_uncompressed_bytes,
        max_entry_bytes=settings.max_zip_entry_bytes,
        max_ratio=settings.max_zip_compression_ratio,
    )


@router.get("", response_model=Page[DatasetOut])
def list_datasets(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    total = db.scalar(select(func.count()).select_from(Dataset)) or 0
    items = db.scalars(select(Dataset).order_by(Dataset.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [_dataset_out(item) for item in items], "total": total, "offset": offset, "limit": limit}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DatasetOut)
async def import_dataset(
    name: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(default=None, max_length=2000),
    files: list[UploadFile] | None = File(default=None),
    masks: list[UploadFile] | None = File(default=None),
    archive: UploadFile | None = File(default=None),
    metadata: UploadFile | None = File(default=None),
    train_ratio: float = Form(default=0.7),
    val_ratio: float = Form(default=0.2),
    test_ratio: float = Form(default=0.1),
    seed: int | None = Form(default=None),
    k_folds: int = Form(default=5),
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    if seed is None:
        seed = int(persisted_setting(db, "default_seed", 42))
    thumbnail_size = int(persisted_setting(db, "thumbnail_size", settings.thumbnail_size))
    uploads = [item for item in (files or []) if item.filename]
    if not uploads and (archive is None or not archive.filename):
        raise AppError(422, "NO_IMAGES", "請上傳影像或 ZIP 檔案。")
    dataset_id = uuid_str()
    staging = safe_resolve(settings.temp_dir, f"dataset-{dataset_id}")
    dataset_root = safe_resolve(settings.datasets_dir, dataset_id)
    staging.mkdir(parents=True, exist_ok=False)
    dataset_root.mkdir(parents=True, exist_ok=False)
    candidates: list[tuple[Path, str]] = []
    mask_candidates: list[tuple[Path, str]] = []
    source_name = None
    source_sha256 = None
    try:
        if not name.strip():
            raise AppError(422, "INVALID_DATASET_NAME", "資料集名稱不可空白。")
        uploaded_total = 0
        if archive and archive.filename:
            clean_archive = sanitize_filename(archive.filename, "dataset.zip")
            if Path(clean_archive).suffix.lower() != ".zip":
                raise AppError(422, "INVALID_ARCHIVE", "資料集壓縮檔必須是 ZIP。")
            archive_path = safe_resolve(staging, "upload.zip")
            archive_size, _archive_digest = await save_upload_file(archive, archive_path, settings.max_upload_bytes)
            uploaded_total += archive_size
            source_name = clean_archive
            source_sha256 = sha256_file(archive_path)
            extracted_root = safe_resolve(staging, "archive")
            extracted = extract_zip_safe(archive_path, extracted_root, _zip_limits(settings), IMAGE_EXTENSIONS)
            for path in extracted:
                logical_name = path.relative_to(extracted_root).as_posix()
                target_list = mask_candidates if _is_mask_logical_name(logical_name) else candidates
                target_list.append((path, logical_name))

        for index, upload in enumerate(uploads):
            logical_name = (upload.filename or f"image-{index}").replace("\\", "/")
            extension = Path(logical_name).suffix.lower()
            if extension not in IMAGE_EXTENSIONS:
                await upload.close()
                raise AppError(422, "UNSUPPORTED_IMAGE", f"不支援的影像格式：{sanitize_filename(logical_name)}")
            target = safe_resolve(staging, "files", f"{index:06d}{extension}")
            file_size, _file_digest = await save_upload_file(upload, target, settings.max_upload_bytes)
            uploaded_total += file_size
            if uploaded_total > settings.max_zip_uncompressed_bytes:
                raise AppError(413, "UPLOAD_TOTAL_TOO_LARGE", "本次上傳總大小超過限制。")
            target_list = mask_candidates if _is_mask_logical_name(logical_name) else candidates
            target_list.append((target, logical_name))

        for index, upload in enumerate(item for item in (masks or []) if item.filename):
            logical_name = (upload.filename or f"mask-{index}.png").replace("\\", "/")
            extension = Path(logical_name).suffix.lower()
            if extension not in IMAGE_EXTENSIONS:
                await upload.close()
                raise AppError(422, "UNSUPPORTED_MASK", "遮罩必須是 JPEG 或 PNG 影像。")
            target = safe_resolve(staging, "mask-files", f"{index:06d}{extension}")
            file_size, _file_digest = await save_upload_file(upload, target, settings.max_upload_bytes)
            uploaded_total += file_size
            if uploaded_total > settings.max_zip_uncompressed_bytes:
                raise AppError(413, "UPLOAD_TOTAL_TOO_LARGE", "本次上傳總大小超過限制。")
            mask_candidates.append((target, logical_name))

        metadata_rows: dict[str, dict[str, str]] = {}
        metadata_columns: list[str] = []
        if metadata and metadata.filename:
            metadata_path = safe_resolve(staging, "metadata.csv")
            await save_upload_file(metadata, metadata_path, settings.max_metadata_bytes)
            metadata_rows, metadata_columns = _read_metadata_csv(metadata_path)

        if not candidates:
            raise AppError(422, "NO_IMAGES", "ZIP 中沒有支援的影像。")

        dataset = Dataset(
            id=dataset_id,
            name=name.strip(),
            description=description,
            status="importing",
            root_path=relative_path(dataset_root, settings.data_dir),
            source_name=source_name,
            source_sha256=source_sha256,
            metadata_columns=metadata_columns,
            split_config={
                "train_ratio": train_ratio, "val_ratio": val_ratio, "test_ratio": test_ratio,
                "seed": seed, "k_folds": k_folds, "strategy": "deterministic_stratified",
            },
        )
        db.add(dataset)
        samples: list[DatasetSample] = []
        sample_logical_names: dict[str, str] = {}
        first_hash: dict[str, str] = {}
        total_bytes = 0
        for source, logical_name in candidates:
            try:
                info = validate_image(source, settings.max_image_pixels)
            except AppError as exc:
                if exc.code not in {"INVALID_IMAGE", "UNSUPPORTED_IMAGE", "IMAGE_DIMENSIONS_INVALID"}:
                    raise
                _record_import_issue(
                    db,
                    dataset_id=dataset_id,
                    logical_name=logical_name,
                    issue_type="corrupt",
                    error_code=exc.code,
                    message=exc.message,
                    source=source,
                )
                continue
            sample_id = uuid_str()
            extension = ".png" if info.format == "PNG" else ".jpg"
            destination = safe_resolve(dataset_root, "images", f"{sample_id}{extension}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            digest = sha256_file(destination)
            size_bytes = destination.stat().st_size
            display_name = sanitize_filename(logical_name, f"{sample_id}{extension}")
            normalized_logical = logical_name.replace("\\", "/").strip().lstrip("/")
            row = metadata_rows.get(normalized_logical) or metadata_rows.get(Path(normalized_logical).name, {})
            class_index, class_name, egfr = detect_label(logical_name, row)
            thumbnail = safe_resolve(dataset_root, "thumbnails", f"{sample_id}.jpg")
            _thumbnail(destination, thumbnail, thumbnail_size)
            sample = DatasetSample(
                id=sample_id,
                dataset_id=dataset_id,
                relative_path=relative_path(destination, dataset_root),
                display_name=display_name,
                stored_name=destination.name,
                sha256=digest,
                mime_type=info.mime_type,
                size_bytes=size_bytes,
                width=info.width,
                height=info.height,
                class_index=class_index,
                class_name=class_name,
                egfr=egfr,
                metadata_json=row,
                thumbnail_path=relative_path(thumbnail, dataset_root),
                duplicate_of_id=first_hash.get(digest),
            )
            first_hash.setdefault(digest, sample_id)
            samples.append(sample)
            sample_logical_names[sample_id] = normalized_logical
            total_bytes += size_bytes

        try:
            assignments = deterministic_stratified_split(
                ((sample.id, sample.class_index, sample.sha256) for sample in samples),
                train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=test_ratio, seed=seed, k_folds=k_folds,
            )
        except ValueError as exc:
            raise AppError(422, "INVALID_SPLIT", str(exc)) from exc
        assignment_by_id = {item.sample_id: item for item in assignments}
        for sample in samples:
            assignment = assignment_by_id[sample.id]
            sample.split = assignment.split
            sample.fold = assignment.fold
            db.add(sample)
        db.flush()

        samples_by_mask_key: dict[str, list[DatasetSample]] = {}
        for sample in samples:
            key = _mask_match_key(sample_logical_names[sample.id])
            samples_by_mask_key.setdefault(key, []).append(sample)
        for source, logical_name in mask_candidates:
            try:
                info = validate_image(source, settings.max_image_pixels)
            except AppError as exc:
                if exc.code not in {"INVALID_IMAGE", "UNSUPPORTED_IMAGE", "IMAGE_DIMENSIONS_INVALID"}:
                    raise
                _record_import_issue(
                    db,
                    dataset_id=dataset_id,
                    logical_name=logical_name,
                    issue_type="corrupt_mask",
                    error_code=exc.code,
                    message=exc.message,
                    source=source,
                )
                continue
            matches = samples_by_mask_key.get(_mask_match_key(logical_name), [])
            if len(matches) != 1:
                _record_import_issue(
                    db,
                    dataset_id=dataset_id,
                    logical_name=logical_name,
                    issue_type="unmatched_mask" if not matches else "ambiguous_mask",
                    error_code="MASK_SAMPLE_NOT_FOUND" if not matches else "MASK_SAMPLE_AMBIGUOUS",
                    message=(
                        "找不到可配對的原圖，遮罩未匯入。"
                        if not matches
                        else "有多張同名原圖，無法安全判定遮罩配對。"
                    ),
                    source=source,
                )
                continue
            sample = matches[0]
            if sample.mask is not None:
                _record_import_issue(
                    db,
                    dataset_id=dataset_id,
                    logical_name=logical_name,
                    issue_type="duplicate_mask",
                    error_code="MASK_ALREADY_LINKED",
                    message="此原圖已有遮罩，重複遮罩未匯入。",
                    source=source,
                )
                continue
            mask_id = uuid_str()
            extension = ".png" if info.format == "PNG" else ".jpg"
            destination = safe_resolve(dataset_root, "masks", f"{mask_id}{extension}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            size_bytes = destination.stat().st_size
            mask = DatasetMask(
                id=mask_id,
                sample_id=sample.id,
                relative_path=relative_path(destination, dataset_root),
                display_name=sanitize_filename(Path(logical_name).name, f"{mask_id}{extension}"),
                sha256=sha256_file(destination),
                mime_type=info.mime_type,
                size_bytes=size_bytes,
                width=info.width,
                height=info.height,
            )
            db.add(mask)
            sample.mask = mask
            total_bytes += size_bytes
        dataset.sample_count = len(samples)
        dataset.total_bytes = total_bytes
        dataset.status = "ready" if samples else "invalid"
        db.commit()
        db.refresh(dataset)
        return _dataset_out(dataset)
    except Exception:
        db.rollback()
        remove_tree_contained(dataset_root, settings.datasets_dir)
        raise
    finally:
        remove_tree_contained(staging, settings.temp_dir)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)) -> dict:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
    return _dataset_out(dataset)


@router.get("/{dataset_id}/samples", response_model=Page[DatasetSampleOut])
def list_samples(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    class_index: int | None = Query(default=None, ge=0, le=4),
    split: str | None = Query(default=None, pattern="^(train|validation|test)$"),
    class_name: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    quality_status: str | None = Query(default=None, alias="status", pattern="^(duplicate|missing_label|missing_metadata|missing_mask)$"),
    page_size: int | None = Query(default=None, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    if not db.get(Dataset, dataset_id):
        raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
    query = select(DatasetSample).where(DatasetSample.dataset_id == dataset_id)
    count_query = select(func.count()).select_from(DatasetSample).where(DatasetSample.dataset_id == dataset_id)
    if class_index is not None:
        query, count_query = query.where(DatasetSample.class_index == class_index), count_query.where(DatasetSample.class_index == class_index)
    if split:
        query, count_query = query.where(DatasetSample.split == split), count_query.where(DatasetSample.split == split)
    if class_name:
        query, count_query = query.where(DatasetSample.class_name == class_name), count_query.where(DatasetSample.class_name == class_name)
    if search:
        escaped_search = search.replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped_search}%"
        query, count_query = query.where(DatasetSample.display_name.ilike(pattern, escape="\\")), count_query.where(DatasetSample.display_name.ilike(pattern, escape="\\"))
    if quality_status == "duplicate":
        query, count_query = query.where(DatasetSample.duplicate_of_id.is_not(None)), count_query.where(DatasetSample.duplicate_of_id.is_not(None))
    elif quality_status == "missing_label":
        query, count_query = query.where(DatasetSample.class_index.is_(None)), count_query.where(DatasetSample.class_index.is_(None))
    elif quality_status == "missing_metadata":
        query, count_query = query.where(DatasetSample.metadata_json == {}), count_query.where(DatasetSample.metadata_json == {})
    elif quality_status == "missing_mask":
        query, count_query = query.where(~DatasetSample.mask.has()), count_query.where(~DatasetSample.mask.has())
    effective_limit = page_size or limit
    total = db.scalar(count_query) or 0
    items = db.scalars(query.order_by(DatasetSample.display_name, DatasetSample.id).offset(offset).limit(effective_limit)).all()
    return {"items": [_sample_out(item) for item in items], "total": total, "offset": offset, "limit": effective_limit}


@router.get("/{dataset_id}/summary", response_model=DatasetSummary)
def dataset_summary(
    dataset_id: str,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
    samples = db.scalars(select(DatasetSample).where(DatasetSample.dataset_id == dataset_id)).all()
    issues = db.scalars(
        select(DatasetImportIssue).where(DatasetImportIssue.dataset_id == dataset_id)
    ).all()
    classes = dict(Counter(item.class_name for item in samples if item.class_name))
    splits = dict(Counter(item.split for item in samples if item.split))
    missing_metadata = sum(not bool(item.metadata_json) for item in samples)
    duplicates = sum(item.duplicate_of_id is not None for item in samples)
    unlabeled = sum(item.class_index is None for item in samples)
    corrupt = sum(item.issue_type in {"corrupt", "corrupt_mask"} for item in issues)
    missing_masks = sum(item.mask is None for item in samples)
    populated = [count for count in classes.values() if count]
    imbalanced = len(classes) < 5 or (bool(populated) and max(populated) / max(1, min(populated)) >= 1.5)
    warnings: list[str] = []
    if unlabeled:
        warnings.append(f"有 {unlabeled} 張圖片缺少可辨識的 eGFR 標籤。")
    if missing_metadata:
        warnings.append(f"有 {missing_metadata} 張圖片缺少 metadata。")
    if duplicates:
        warnings.append(f"偵測到 {duplicates} 張重複圖片；相同內容已固定在同一資料切割。")
    if corrupt:
        warnings.append(f"匯入時拒絕 {corrupt} 個損壞或不安全的影像檔；原始內容未保留。")
    if missing_masks:
        warnings.append(f"有 {missing_masks} 張圖片尚未連結 mask。")
    unmatched_masks = sum(item.issue_type in {"unmatched_mask", "ambiguous_mask", "duplicate_mask"} for item in issues)
    if unmatched_masks:
        warnings.append(f"有 {unmatched_masks} 個 mask 無法安全配對，請查看匯入問題。")
    if imbalanced:
        warnings.append("五級 eGFR 類別分布可能不平衡。")
    total = len(samples)
    distribution = [
        {"class_index": index, "class_name": name, "count": classes.get(name, 0), "percentage": (classes.get(name, 0) / total * 100 if total else 0)}
        for index, name in enumerate(("eGFR -15", "eGFR 15-29", "eGFR 30-59", "eGFR 60-89", "eGFR 90-"))
    ]
    payload = {
        "dataset_id": dataset_id,
        "sample_count": total,
        "total_bytes": sum(item.size_bytes for item in samples),
        "classes": classes,
        "splits": splits,
        "folds": {str(key): value for key, value in Counter(item.fold for item in samples if item.fold is not None).items()},
        "unlabeled": unlabeled,
        "duplicates": duplicates,
        "image_count": total,
        "total_samples": total,
        "total_size_bytes": sum(item.size_bytes for item in samples),
        "class_distribution": distribution,
        "split_counts": splits,
        "corrupt_count": corrupt,
        "duplicate_count": duplicates,
        "missing_label_count": unlabeled,
        "missing_metadata_count": missing_metadata,
        "missing_mask_count": missing_masks,
        "is_imbalanced": imbalanced,
        "warnings": warnings,
    }
    if download:
        filename = f"{sanitize_filename(dataset.name, 'dataset')}-summary.json"
        disposition = f"attachment; filename=\"dataset-summary.json\"; filename*=UTF-8''{quote(filename)}"
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": disposition},
        )
    return payload


@router.get("/{dataset_id}/issues", response_model=Page[DatasetImportIssueOut])
def dataset_import_issues(
    dataset_id: str,
    issue_type: str | None = Query(default=None, max_length=32),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    if not db.get(Dataset, dataset_id):
        raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
    query = select(DatasetImportIssue).where(DatasetImportIssue.dataset_id == dataset_id)
    count_query = select(func.count()).select_from(DatasetImportIssue).where(
        DatasetImportIssue.dataset_id == dataset_id
    )
    if issue_type:
        query = query.where(DatasetImportIssue.issue_type == issue_type)
        count_query = count_query.where(DatasetImportIssue.issue_type == issue_type)
    total = db.scalar(count_query) or 0
    items = db.scalars(
        query.order_by(DatasetImportIssue.created_at, DatasetImportIssue.id).offset(offset).limit(limit)
    ).all()
    return {
        "items": [_issue_out(item) for item in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def _sample_or_404(db: Session, dataset_id: str, sample_id: str) -> DatasetSample:
    sample = db.scalar(select(DatasetSample).where(DatasetSample.id == sample_id, DatasetSample.dataset_id == dataset_id))
    if not sample:
        raise AppError(404, "SAMPLE_NOT_FOUND", "找不到指定影像。")
    return sample


@router.get("/{dataset_id}/samples/{sample_id}/file")
def sample_file(dataset_id: str, sample_id: str, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)):
    sample = _sample_or_404(db, dataset_id, sample_id)
    dataset = db.get(Dataset, dataset_id)
    dataset_root = safe_resolve(settings.data_dir, dataset.root_path)
    path = safe_resolve(dataset_root, sample.relative_path)
    if not path.is_file():
        raise AppError(404, "SAMPLE_FILE_MISSING", "影像檔案不存在。")
    return FileResponse(path, media_type=sample.mime_type, filename=sample.display_name)


@router.get("/{dataset_id}/samples/{sample_id}/thumbnail")
def sample_thumbnail(dataset_id: str, sample_id: str, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)):
    sample = _sample_or_404(db, dataset_id, sample_id)
    if not sample.thumbnail_path:
        raise AppError(404, "THUMBNAIL_MISSING", "縮圖不存在。")
    dataset = db.get(Dataset, dataset_id)
    dataset_root = safe_resolve(settings.data_dir, dataset.root_path)
    path = safe_resolve(dataset_root, sample.thumbnail_path)
    if not path.is_file():
        raise AppError(404, "THUMBNAIL_MISSING", "縮圖不存在。")
    return FileResponse(path, media_type="image/jpeg", filename=f"{sample.id}.jpg")


@router.get("/{dataset_id}/samples/{sample_id}/mask")
def sample_mask(
    dataset_id: str,
    sample_id: str,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
):
    sample = _sample_or_404(db, dataset_id, sample_id)
    if sample.mask is None:
        raise AppError(404, "MASK_MISSING", "此影像尚未連結 mask。")
    dataset = db.get(Dataset, dataset_id)
    dataset_root = safe_resolve(settings.data_dir, dataset.root_path)
    path = safe_resolve(dataset_root, sample.mask.relative_path)
    if not path.is_file():
        raise AppError(404, "MASK_FILE_MISSING", "Mask 檔案不存在。")
    return FileResponse(path, media_type=sample.mask.mime_type, filename=sample.mask.display_name)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)) -> Response:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise AppError(404, "DATASET_NOT_FOUND", "找不到指定資料集。")
    dependent_jobs = db.scalar(select(func.count()).select_from(Job).where(Job.dataset_id == dataset_id)) or 0
    if dependent_jobs:
        raise AppError(409, "DATASET_IN_USE", "請先刪除使用此資料集的工作與訓練紀錄。")
    source = safe_resolve(settings.data_dir, dataset.root_path)
    trash = safe_resolve(settings.temp_dir, f"deleted-{dataset_id}-{uuid4().hex}")
    if source.exists():
        source.rename(trash)
    try:
        db.delete(dataset)
        db.commit()
    except Exception:
        db.rollback()
        if trash.exists() and not source.exists():
            trash.rename(source)
        raise
    remove_tree_contained(trash, settings.temp_dir)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
