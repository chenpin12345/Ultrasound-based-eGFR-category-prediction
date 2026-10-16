"""Human-attested reference provenance, never an automatically invented ground truth."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from ..core.errors import AppError
from ..core.security import safe_resolve, sha256_file
from ..db.models import Dataset, DatasetSample, MaskProvenance
from .evaluation_service import digest


def preflight(db, settings, payload):
    import numpy as np
    from PIL import Image
    dataset = db.get(Dataset, payload.dataset_id)
    sample = db.get(DatasetSample, payload.sample_id)
    if not dataset or not sample or sample.dataset_id != dataset.id:
        raise AppError(404, 'REFERENCE_SAMPLE_MISSING', '找不到此資料集的指定影像。')
    if dataset.status != 'ready' or not sample.mask:
        raise AppError(422, 'REFERENCE_MASK_MISSING', '資料集未就緒或此影像沒有匯入的參考 Mask。')
    mask = sample.mask
    if db.get(MaskProvenance, mask.id):
        raise AppError(409, 'REFERENCE_ALREADY_REGISTERED', '此 Mask 已有不可變來源紀錄，不能覆寫或改稱獨立參考。')
    root = safe_resolve(settings.data_dir, dataset.root_path)
    image_path, mask_path = safe_resolve(root, sample.relative_path), safe_resolve(root, mask.relative_path)
    try:
        if sha256_file(image_path) != sample.sha256 or sha256_file(mask_path) != mask.sha256:
            raise AppError(409, 'REFERENCE_HASH_CHANGED', '影像或 Mask 已改變，不能登錄來源。')
        with Image.open(image_path) as image, Image.open(mask_path) as reference:
            size = list(image.size)
            if image.size != reference.size or size != [512,512] or size != [mask.width,mask.height]:
                raise AppError(422, 'REFERENCE_MASK_ALIGNMENT', '僅支援同一 512×512 座標的參考 Mask，不自動拉伸。')
            pixels = np.asarray(reference)
            if pixels.ndim != 2 or not np.isin(pixels,[0,255]).all():
                raise AppError(422, 'REFERENCE_MASK_BINARY', '參考 Mask 必須是單通道 0／255 二值影像。')
    except (OSError, ValueError) as exc:
        raise AppError(422, 'REFERENCE_FILE_INVALID', '影像或參考 Mask 無法驗證。') from exc
    evidence = {
        **payload.model_dump(exclude={'expected_preflight_sha256'}),
        'evidence_version':'human-reference-attestation-v1',
        'verification':'file_hash_and_grid_verified; independence_human_attested',
        'image_sha256':sample.sha256, 'mask_sha256':mask.sha256, 'size':size,
        'mask_id':mask.id, 'image_name':sample.display_name,
    }
    return evidence, digest(evidence)


def register(db, settings, payload, actor_id):
    evidence, fingerprint = preflight(db, settings, payload)
    if fingerprint != payload.expected_preflight_sha256:
        raise AppError(409, 'REFERENCE_PREFLIGHT_CHANGED', '請先確認來源與雜湊；資料改變後須重新預檢。')
    record = MaskProvenance(mask_id=evidence['mask_id'],kind='independent_reference',
                            evidence_json={**evidence,'local_actor_id':actor_id})
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, 'REFERENCE_ALREADY_REGISTERED', '已有其他操作登錄此 Mask，請重新讀取。') from exc
    return {'mask_id':record.mask_id,'kind':record.kind,'evidence':record.evidence_json,'created_at':record.created_at}
