"""醫師端的病人、檢查與影像（M3-1、M3-2）。

- 收到的原始檔存受限區 01_原始；去識別化沿用研究端的版面範本、OCR，並強制做殘留檢查（有殘留不顯示、不產生 PDF）。
- 醫師端規則：讀不到年齡、側別或尺時不擋分析，只標示缺了什麼（研究端則整張「待確認」）。
- 沒見過的影像尺寸：標「版面不符」並保留原檔；可以從最接近的範本按比例建立新範本後重新去識別化。
- 示範影像（D43）已去識別化：側別、像素間距用示範清單的值。
- 年齡、性別、糖尿病記在每次檢查；男／女轉成 M／F；糖尿病有、無、不明三種，不明不當成無。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, next_sequential, now_iso, short_uid
from ..data import deid
from ..db.models_clinical import ClinicalEdit, ClinicalExam, ClinicalImage, ClinicalPatient
from ..db.session import session_scope

SEX = {'M': 'M', 'F': 'F', '男': 'M', '女': 'F', 'MALE': 'M', 'FEMALE': 'F'}
DIABETES = {'yes': 'yes', 'no': 'no', 'unknown': 'unknown', '有': 'yes', '無': 'no', '不明': 'unknown', True: 'yes', False: 'no', 1: 'yes', 0: 'no'}


# ---------- 路徑 ----------
def root() -> Path:
    return get_settings().path('clinical')


def raw_dir(batch_id: str) -> Path:
    return root() / '01_原始' / batch_id


def staging_dir(batch_id: str) -> Path:
    return root() / '05_接收暫存' / batch_id


def image_dir(exam_id: str) -> Path:
    return root() / '02_影像' / exam_id


def image_file(exam_id: str, image_id: str, kind: str) -> Path:
    """kind：model（去識別化）、calc（灰階＋可用像素）、thumb（縮圖）。"""
    return image_dir(exam_id) / f'{image_id}_{kind}.{"jpg" if kind == "thumb" else "png"}'


def analysis_dir(exam_id: str, analysis_id: str) -> Path:
    return root() / '04_分析' / exam_id / analysis_id


def rel(path: Path) -> str:
    return path.relative_to(get_settings().root).as_posix()


def image_suffix(path: Path) -> str:
    """依檔案開頭判斷 PNG 或 JPG（上傳暫存檔的副檔名是 .part，不能拿來用）。"""
    with path.open('rb') as fh:
        head = fh.read(8)
    if head.startswith(bytes((0x89, 0x50, 0x4E, 0x47))):  # PNG 檔頭
        return '.png'
    if head.startswith(bytes((0xFF, 0xD8))):  # JPEG 檔頭
        return '.jpg'
    suffix = path.suffix.lower()
    return suffix if suffix in ('.png', '.jpg', '.jpeg') else '.png'


# ---------- 臨床資料 ----------
def normalize_clinical(age: Any = None, sex: Any = None, diabetes: Any = None) -> dict[str, Any]:
    out: dict[str, Any] = {'age': None, 'sex': None, 'diabetes': 'unknown'}
    if age not in (None, ''):
        try:
            value = float(age)
        except (TypeError, ValueError):
            raise AppError(422, 'BAD_CLINICAL', '年齡必須是數字。') from None
        if not 0 <= value <= 130:
            raise AppError(422, 'BAD_CLINICAL', '年齡必須在 0 到 130 之間。')
        out['age'] = value
    if sex not in (None, ''):
        key = str(sex).strip().upper() if str(sex).strip().upper() in SEX else str(sex).strip()
        if key not in SEX:
            raise AppError(422, 'BAD_CLINICAL', '性別請填男、女（或 M、F）。')
        out['sex'] = SEX[key]
    if diabetes not in (None, ''):
        key = diabetes if diabetes in DIABETES else str(diabetes).strip().lower() if str(diabetes).strip().lower() in DIABETES else str(diabetes).strip()
        if key not in DIABETES:
            raise AppError(422, 'BAD_CLINICAL', '糖尿病請填有、無或不明。')
        out['diabetes'] = DIABETES[key]
    return out


def clinical_for_model(exam: ClinicalExam) -> dict[str, Any]:
    """給 registry.standardize：沒有的值是 None（模型會補值並加缺值標記）；糖尿病不明＝None，不是 False。"""
    return {'age': exam.age, 'sex': exam.sex, 'has_diabetes': {'yes': True, 'no': False}.get(exam.diabetes)}


def missing_clinical(exam: ClinicalExam) -> list[str]:
    return [label for label, value in (('年齡', exam.age), ('性別', exam.sex), ('糖尿病', None if exam.diabetes == 'unknown' else exam.diabetes)) if value is None]


# ---------- 病人與檢查 ----------
def get_or_create_patient(db, case_code: str | None, mode: str = 'demo') -> ClinicalPatient:
    code = (case_code or '').strip()
    if code:
        if len(code) > 40 or any(ch in code for ch in '\\/:*?"<>|'):
            raise AppError(422, 'BAD_CASE_CODE', '病例代碼最多 40 字，不能有 \\ / : * ? " < > |。')
        found = db.query(ClinicalPatient).filter(ClinicalPatient.case_code == code).first()
        if found:
            return found
    else:
        code = next_sequential('C-', [c for (c,) in db.query(ClinicalPatient.case_code).all()])
    patient = ClinicalPatient(id=next_sequential('CP-', [p for (p,) in db.query(ClinicalPatient.id).all()]), case_code=code, mode=mode, created_at=now_iso())
    db.add(patient)
    db.flush()
    return patient


def create_exam(case_code: str | None, clinical: dict[str, Any], *, source: str, batch_id: str | None, title: str = '', operator: str = '', clinical_source: str = 'upload') -> dict[str, str]:
    values = normalize_clinical(**clinical)
    with session_scope('clinical') as db:
        patient = get_or_create_patient(db, case_code)
        exam_id = next_dated('EX-', [e for (e,) in db.query(ClinicalExam.id).all()], width=3)
        db.add(ClinicalExam(id=exam_id, patient_id=patient.id, mode=patient.mode, source=source, upload_batch_id=batch_id, title=(title or '腎臟超音波')[:80],
                            status='receiving', age=values['age'], sex=values['sex'], diabetes=values['diabetes'],
                            clinical_source=clinical_source if any(v not in (None, 'unknown') for v in values.values()) else '',
                            relpath=rel(image_dir(exam_id)), received_at=now_iso(), created_by=operator, created_at=now_iso()))
        return {'exam_id': exam_id, 'case_code': patient.case_code}


def add_image(exam_id: str, batch_id: str, seq: int, raw_path: Path, sha256: str, meta: dict[str, Any]) -> dict[str, Any]:
    """把一張收到的原始檔存進受限區、去識別化、建立影像紀錄。meta：side、pixel_spacing_mm（示範清單）、demo。"""
    from ..data.templates import template_dict
    from ..db.models_research import LayoutTemplate
    from ..services import settings_store  # noqa: F401  醫師端一律做殘留檢查，不看研究端的設定

    image_id = f'CI-{short_uid()}'
    with session_scope('clinical') as db:
        if db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id, ClinicalImage.sha256 == sha256).first():
            raw_path.unlink(missing_ok=True)
            return {'status': 'duplicate'}
    raw = raw_dir(batch_id) / f'{image_id}{image_suffix(raw_path)}'  # 上傳暫存檔是 .part，依內容決定副檔名
    raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(raw_path), raw)
    bgr = deid.read_image(raw)
    h, w = bgr.shape[:2]
    row = ClinicalImage(id=image_id, exam_id=exam_id, seq=seq, sha256=sha256, width=w, height=h, raw_relpath=rel(raw), created_at=now_iso())
    with session_scope('research') as db:
        template = db.query(LayoutTemplate).filter(LayoutTemplate.width == w, LayoutTemplate.height == h).first()
        template = template_dict(template) if template else None
    if template is None:
        row.status, row.deid_json = 'layout_mismatch', json.dumps({'missing': [f'沒有 {w}×{h} 的版面範本']}, ensure_ascii=False)
    else:
        _deidentify(row, bgr, template, meta)
    with session_scope('clinical') as db:
        db.add(row)
    return {'status': row.status, 'image_id': image_id}


def _deidentify(row: ClinicalImage, bgr, template: dict[str, Any], meta: dict[str, Any]) -> None:
    demo = bool(meta.get('demo'))
    # 示範影像已去識別化，標頭、尺與體表示意圖都已遮蓋：不再 OCR，側別與像素間距用示範清單的值
    result = deid.process(bgr, template['regions'], template['readers'], read_text=not demo)
    missing: list[str] = []
    side, side_source = result.side, result.side_source
    if meta.get('side') in ('right', 'left'):
        side, side_source = meta['side'], 'demo_list' if demo else 'upload'
    spacing, spacing_source = result.pixel_spacing_mm, 'ruler' if result.pixel_spacing_mm else 'none'
    if meta.get('pixel_spacing_mm'):
        spacing, spacing_source = float(meta['pixel_spacing_mm']), 'demo_list' if demo else 'upload'
    if not side:
        missing.append('側別')
    if not spacing:
        missing.append('像素間距（量不到尺，腎長不可用）')
    residual = deid.residual_check(result.model_image)
    row.template_id, row.side, row.side_source, row.pixel_spacing_mm, row.spacing_source = template['id'], side, side_source, spacing, spacing_source
    row.status = 'residual' if residual else 'ok'
    row.deid_json = json.dumps({'missing': missing, 'residual': residual, 'sonographer_length_mm': result.dist_a_mm, 'calipers': result.caliper_pixels,
                                'gain': (result.scan_params or {}).get('gain')}, ensure_ascii=False)
    deid.write_png(image_file(row.exam_id, row.id, 'model'), result.model_image)
    deid.write_gray_alpha(image_file(row.exam_id, row.id, 'calc'), result.calc_gray, result.calc_valid)
    deid.write_jpeg(image_file(row.exam_id, row.id, 'thumb'), deid.thumbnail(result.model_image))
    row.relpath = rel(image_file(row.exam_id, row.id, 'model'))


def refresh_status(exam_id: str) -> str:
    """依影像狀態更新檢查狀態（分析中／完成的狀態由分析工作設定）。"""
    with session_scope('clinical') as db:
        exam = db.get(ClinicalExam, exam_id)
        images = db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id).all()
        usable = [i for i in images if i.status == 'ok']
        if not images:
            exam.status = 'receiving'
        elif not usable:
            exam.status = 'layout_mismatch' if any(i.status == 'layout_mismatch' for i in images) else 'failed'
        elif exam.status in ('receiving', 'layout_mismatch', 'failed'):
            exam.status = 'ready'  # 有可分析的影像；接著由收圖工作或版面修正排入分析
        return exam.status


def fix_layout(exam_id: str, operator: str) -> dict[str, Any]:
    """版面不符：從最接近的範本按比例建立新尺寸的範本（之後可以在「版面範本」微調），再重新去識別化這筆檢查的影像。"""
    from ..data.templates import template_dict
    from ..db.models_research import LayoutTemplate

    with session_scope('clinical') as db:
        pending = [(i.id, i.raw_relpath, i.width, i.height) for i in db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id, ClinicalImage.status == 'layout_mismatch').all()]
    if not pending:
        raise AppError(409, 'NOTHING_TO_FIX', '這筆檢查沒有版面不符的影像。')
    created = []
    with session_scope('research') as db:
        templates = db.query(LayoutTemplate).all()
        for _, _, w, h in pending:
            if any(t.width == w and t.height == h for t in templates) or (w, h) in created:
                continue
            nearest = min(templates, key=lambda t: abs(t.width / t.height - w / h) * 10 + abs(t.width - w) / max(w, 1))
            new = LayoutTemplate(id=f'TPL-X{w}x{h}'[:24], machine=nearest.machine, width=w, height=h, version=1, regions_json=nearest.regions_json,
                                 readers_json=nearest.readers_json, updated_at=now_iso(), updated_by=f'{operator}（醫師端：由 {nearest.id} 按比例建立）')
            db.add(new)
            templates.append(new)
            created.append((w, h))
    with session_scope('research') as db:
        by_size = {(t.width, t.height): template_dict(t) for t in db.query(LayoutTemplate).all()}
    fixed = 0
    for image_id, raw_relpath, w, h in pending:
        with session_scope('clinical') as db:
            row = db.get(ClinicalImage, image_id)
            _deidentify(row, deid.read_image(get_settings().root / raw_relpath), by_size[(w, h)], {})
            fixed += 1
        log_edit(exam_id, image_id, 'layout', 'layout_mismatch', 'ok', '由最接近的範本按比例建立版面範本', operator)
    analysis = None
    if refresh_status(exam_id) == 'ready':
        from . import analysis as clinical_analysis

        analysis = clinical_analysis.start(exam_id, operator)['analysis_id']
    return {'templates': [f'{w}×{h}' for w, h in created], 'fixed': fixed, 'analysis_id': analysis}


def log_edit(exam_id: str, image_id: str | None, kind: str, before: Any, after: Any, reason: str, actor: str) -> None:
    with session_scope('clinical') as db:
        db.add(ClinicalEdit(exam_id=exam_id, image_id=image_id, kind=kind, before_json=json.dumps(before, ensure_ascii=False),
                            after_json=json.dumps(after, ensure_ascii=False), reason=reason[:200], actor=actor, created_at=now_iso()))
