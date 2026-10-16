from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.config import AppSettings, get_settings
from ...core.errors import AppError
from ...core.security import relative_path, remove_tree_contained, safe_resolve, sanitize_filename, save_upload_file
from ...db.models import Job, ModelRecord, uuid_str
from ...db.session import get_db
from ...schemas.common import Page
from ...schemas.model import ModelDetail, ModelManifest, ModelOut, ModelRename
from ...services import model_catalog

router = APIRouter(prefix="/models", tags=["models"])

CLASSIFIER_ARCHITECTURES = {"resnet18", "mobilenetv2", "efficientnet_b3", "mlp-resnet18", "coral-resnet18", "coral-mlp-resnet18"}
SEGMENTATION_ARCHITECTURES = {"unet"}


def _model_out(model: ModelRecord) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "version": model.version,
        "task": model.task,
        "architecture": model.architecture,
        "class_count": model.class_count,
        "class_names": model.class_names or [],
        "metadata_columns": model.metadata_columns or [],
        "preprocessing": model.preprocessing or {},
        "sha256": model.sha256,
        "size_bytes": model.size_bytes,
        "status": model.status,
        "active": model.active,
        "source_training_job_id": model.source_training_job_id,
        "download_url": f"/api/models/{model.id}/download",
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


def _validate_manifest(manifest: ModelManifest) -> None:
    expected = CLASSIFIER_ARCHITECTURES if manifest.task == "classification" else SEGMENTATION_ARCHITECTURES
    if manifest.architecture.lower() not in expected:
        raise AppError(422, "UNSUPPORTED_ARCHITECTURE", "模型任務與架構不相容。", {"allowed": sorted(expected)})
    if len(manifest.class_names) != manifest.class_count:
        raise AppError(422, "CLASS_SCHEMA_MISMATCH", "class_names 數量必須等於 class_count。")
    if len(set(manifest.class_names)) != len(manifest.class_names):
        raise AppError(422, "DUPLICATE_CLASS_NAME", "類別名稱不可重複。")
    if manifest.task == "classification" and manifest.class_count not in (2, 3, 5):
        raise AppError(422, "CLASS_SCHEMA_MISMATCH", "分類模型僅支援二、三、五級 eGFR 輸出。")
    if manifest.task == "segmentation" and manifest.class_count != 2:
        raise AppError(422, "CLASS_SCHEMA_MISMATCH", "UNet 必須維持背景／前景兩類輸出。")
    if "mlp" in manifest.architecture.lower() and manifest.metadata_columns != [
        "age", "Length_px", "Contrast_Ratio", "has_diabetes"
    ]:
        raise AppError(422, "METADATA_SCHEMA_MISMATCH", "MLP-ResNet18 metadata 欄位或順序不相容。")
    if manifest.task == "classification":
        from ...ml.contracts import ModelMetadata
        try:
            ModelMetadata.from_dict(manifest.model_dump())
        except (ValueError, TypeError, KeyError) as exc:
            raise AppError(422, "INVALID_MODEL_METADATA", "模型配套設定不相容。") from exc


def _validate_weights_only(path: Path) -> None:
    try:
        import torch
    except ImportError as exc:
        raise AppError(503, "PYTORCH_UNAVAILABLE", "尚未安裝 PyTorch，無法安全驗證權重。") from exc
    try:
        try:
            state = torch.load(path, map_location="cpu", weights_only=True)
        except TypeError as exc:
            raise AppError(503, "PYTORCH_TOO_OLD", "PyTorch 版本不支援安全權重驗證。") from exc
    except AppError:
        raise
    except Exception as exc:
        raise AppError(422, "INVALID_MODEL_WEIGHTS", "模型檔不是可安全載入的 PyTorch 權重。") from exc
    if not isinstance(state, dict) or not state:
        raise AppError(422, "INVALID_MODEL_WEIGHTS", "模型權重必須是非空 state dictionary。")


def _validate_model_compatibility(path: Path, manifest: ModelManifest) -> None:
    try:
        if manifest.task == "segmentation":
            from ...ml.segmentation import load_unet

            model = load_unet(path, "cpu")
        else:
            from ...ml.contracts import canonical_classifier_name
            from ...ml.models import load_classifier

            architecture, coral = canonical_classifier_name(manifest.architecture)
            model = load_classifier(path, architecture, device="cpu", coral=coral, num_classes=manifest.class_count)
        del model
    except Exception as exc:
        raise AppError(422, "MODEL_ARCHITECTURE_MISMATCH", "權重與指定的模型架構不相容。") from exc


@router.get("", response_model=Page[ModelOut])
def list_models(
    task: str | None = Query(default=None, pattern="^(classification|segmentation)$"),
    active: bool | None = None,
    search: str | None = Query(default=None, max_length=200),
    exact_name: str | None = Query(default=None, max_length=200),
    analysis_mode: str | None = Query(default=None, pattern='^(mlp|image_only)$'),
    architecture: str | None = Query(default=None, max_length=64),
    class_count: int | None = Query(default=None, ge=1, le=1000),
    version: str | None = Query(default=None, max_length=64),
    source: str | None = Query(default=None, pattern='^(training|external)$'),
    training_job_id: str | None = Query(default=None, max_length=36),
    status_filter: str | None = Query(default=None, alias='status', max_length=32),
    sort: str = Query(default='newest', pattern='^(newest|oldest|name)$'),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    query = select(ModelRecord)
    count_query = select(func.count()).select_from(ModelRecord)
    if task:
        query, count_query = query.where(ModelRecord.task == task), count_query.where(ModelRecord.task == task)
    if active is not None:
        query, count_query = query.where(ModelRecord.active == active), count_query.where(ModelRecord.active == active)
    filters = []
    if search and search.strip():
        filters.append(ModelRecord.name.icontains(search.strip(), autoescape=True))
    if exact_name is not None:
        filters.append(ModelRecord.name == exact_name)
    if analysis_mode:
        mlp = ModelRecord.architecture.contains('mlp')
        filters.append(mlp if analysis_mode == 'mlp' else ~mlp)
    for field, value in ((ModelRecord.architecture, architecture), (ModelRecord.class_count, class_count),
                         (ModelRecord.version, version), (ModelRecord.status, status_filter)):
        if value is not None:
            filters.append(field == value)
    if source:
        filters.append(ModelRecord.source_training_job_id.is_not(None) if source == 'training' else ModelRecord.source_training_job_id.is_(None))
    if training_job_id:
        filters.append(ModelRecord.source_training_job_id == training_job_id)
    query, count_query = query.where(*filters), count_query.where(*filters)
    total = db.scalar(count_query) or 0
    ordering = {'newest': ModelRecord.created_at.desc(), 'oldest': ModelRecord.created_at.asc(), 'name': func.lower(ModelRecord.name)}[sort]
    models = db.scalars(query.order_by(ordering, ModelRecord.id).offset(offset).limit(limit)).all()
    summaries = model_catalog.evaluation_summaries(db, models)
    return {"items": [{**_model_out(item), 'evaluation_summary': summaries.get(item.id, {})} for item in models], "total": total, "offset": offset, "limit": limit}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ModelOut)
async def upload_model(
    manifest_json: str = Form(...),
    weights: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    try:
        manifest = ModelManifest.model_validate_json(manifest_json)
    except Exception as exc:
        raise AppError(422, "INVALID_MODEL_MANIFEST", "模型描述 JSON 格式錯誤。") from exc
    _validate_manifest(manifest)
    clean_name = sanitize_filename(weights.filename or "weights.pth", "weights.pth")
    extension = Path(clean_name).suffix.lower()
    if extension not in {".pth", ".pt"}:
        raise AppError(422, "UNSUPPORTED_MODEL_FILE", "模型權重必須是 .pth 或 .pt。")
    model_id = uuid_str()
    model_dir = safe_resolve(settings.models_dir, model_id)
    model_dir.mkdir(parents=True, exist_ok=False)
    weight_path = safe_resolve(model_dir, f"weights{extension}")
    metadata_path = safe_resolve(model_dir, "model_metadata.json")
    try:
        size, digest = await save_upload_file(weights, weight_path, settings.max_upload_bytes)
        if db.scalar(select(ModelRecord).where(ModelRecord.sha256 == digest)):
            raise AppError(409, "MODEL_ALREADY_EXISTS", "相同權重已存在模型庫。")
        _validate_weights_only(weight_path)
        _validate_model_compatibility(weight_path, manifest)
        metadata = manifest.model_dump()
        metadata.update({"model_id": model_id, "sha256": digest, "size_bytes": size})
        temporary = metadata_path.with_name(f".{metadata_path.name}.{uuid4().hex}.part")
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, metadata_path)
        record = ModelRecord(
            id=model_id,
            name=manifest.name,
            version=manifest.version,
            task=manifest.task,
            architecture=manifest.architecture.lower(),
            class_count=manifest.class_count,
            class_names=manifest.class_names,
            metadata_columns=manifest.metadata_columns,
            preprocessing=manifest.preprocessing,
            weights_path=relative_path(weight_path, settings.models_dir),
            metadata_path=relative_path(metadata_path, settings.models_dir),
            sha256=digest,
            size_bytes=size,
            status="ready",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return _model_out(record)
    except IntegrityError as exc:
        db.rollback()
        remove_tree_contained(model_dir, settings.models_dir)
        raise AppError(409, "MODEL_VERSION_EXISTS", "模型名稱與版本已存在。") from exc
    except Exception:
        db.rollback()
        remove_tree_contained(model_dir, settings.models_dir)
        raise


@router.get("/{model_id}", response_model=ModelDetail)
def get_model(model_id: str, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)) -> dict:
    model = db.get(ModelRecord, model_id)
    if not model:
        raise AppError(404, "MODEL_NOT_FOUND", "找不到指定模型。")
    return {**_model_out(model), **model_catalog.detail(db, model, settings),
            'evaluation_summary': model_catalog.evaluation_summaries(db, [model]).get(model.id, {})}


@router.patch("/{model_id}", response_model=ModelOut)
def rename_model(model_id: str, payload: ModelRename, db: Session = Depends(get_db)) -> dict:
    model = db.get(ModelRecord, model_id)
    if not model:
        raise AppError(404, "MODEL_NOT_FOUND", "找不到指定模型。")
    if model.name == payload.name:
        return _model_out(model)
    duplicate = db.scalar(
        select(ModelRecord).where(
            ModelRecord.id != model.id,
            ModelRecord.version == model.version,
            func.lower(ModelRecord.name) == payload.name.lower(),
        )
    )
    if duplicate:
        raise AppError(409, "MODEL_VERSION_EXISTS", "相同版本已有同名模型。")
    model.name = payload.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "MODEL_VERSION_EXISTS", "相同版本已有同名模型。") from exc
    db.refresh(model)
    return _model_out(model)


@router.post("/{model_id}/activate", response_model=ModelOut)
def activate_model(model_id: str, db: Session = Depends(get_db)) -> dict:
    model = db.get(ModelRecord, model_id)
    if not model:
        raise AppError(404, "MODEL_NOT_FOUND", "找不到指定模型。")
    if model.status not in {"ready", "completed"}:
        raise AppError(409, "MODEL_NOT_READY", "模型尚未就緒。")
    db.execute(update(ModelRecord).where(ModelRecord.task == model.task).values(active=False))
    model.active = True
    db.commit()
    db.refresh(model)
    return _model_out(model)


@router.get("/{model_id}/download")
def download_model(model_id: str, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)):
    model = db.get(ModelRecord, model_id)
    if not model:
        raise AppError(404, "MODEL_NOT_FOUND", "找不到指定模型。")
    path = safe_resolve(settings.models_dir, model.weights_path)
    if not path.is_file():
        raise AppError(404, "MODEL_FILE_MISSING", "模型權重檔案不存在。")
    return FileResponse(path, media_type="application/octet-stream", filename=f"{sanitize_filename(model.name)}-{sanitize_filename(model.version)}{path.suffix}")


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_model(model_id: str, db: Session = Depends(get_db), settings: AppSettings = Depends(get_settings)) -> Response:
    model = db.get(ModelRecord, model_id)
    if not model:
        raise AppError(404, "MODEL_NOT_FOUND", "找不到指定模型。")
    if model.active:
        raise AppError(409, "MODEL_ACTIVE", "請先啟用其他模型，再刪除此模型。")
    references = model_catalog.references(db, model, settings)
    if references:
        raise AppError(409, 'MODEL_REFERENCED', '此模型有研究工作或封存方案引用，必須保留追溯資料，不能刪除。', {'references': references})
    for job in db.scalars(select(Job).where(Job.status.in_(["queued", "running", "stopping"]))):
        config = job.config_json or {}
        if any(config.get(key) == model.weights_path for key in ("model_path", "classifier_model_path", "unet_model_path")):
            raise AppError(409, "MODEL_IN_USE", "此模型仍被進行中的工作使用，無法刪除。")
    weights_path = safe_resolve(settings.models_dir, model.weights_path)
    metadata_path = safe_resolve(settings.models_dir, model.metadata_path)
    # Imported models live under models/{model_id}; trained models live under
    # models/{training_job_id}. Remove the actual managed artifact directory.
    model_dir = weights_path.parent
    if metadata_path.parent != model_dir or model_dir == settings.models_dir.resolve():
        raise AppError(500, "MODEL_STORAGE_INVALID", "模型檔案與 metadata 不在同一受管理目錄。")
    trash = safe_resolve(settings.temp_dir, f"deleted-model-{model_id}-{uuid4().hex}")
    if model_dir.exists():
        model_dir.rename(trash)
    try:
        db.delete(model)
        db.commit()
    except Exception:
        db.rollback()
        if trash.exists() and not model_dir.exists():
            trash.rename(model_dir)
        raise
    remove_tree_contained(trash, settings.temp_dir)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
