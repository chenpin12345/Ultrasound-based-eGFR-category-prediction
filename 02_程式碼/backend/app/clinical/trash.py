"""醫師端檢查的回收桶（M3-8、D41）。

- 移入回收桶：檢查與它的報告一起標記；有「已簽核」的報告時拒絕（已簽核只能作廢）。
- 永久刪除：刪掉資料列與檔案——去識別化影像、分析結果、報告 PDF、受限區的原始檔；沒有其他檢查的病例代碼一併刪除。
  研究端的臨床回饋與已轉入研究的影像不受影響（它們已經屬於研究端）。
"""

from __future__ import annotations

from pathlib import Path

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import now_iso
from ..db.models_clinical import (ClinicalAnalysis, ClinicalEdit, ClinicalExam, ClinicalImage, ClinicalPatient, ClinicalReport,
                                  ClinicalReportVersion, ReceiverBatch)
from ..db.session import session_scope
from . import exams


def move(exam_id: str) -> str:
    with session_scope('clinical') as db:
        e = db.get(ClinicalExam, exam_id)
        if e is None or e.trashed_at:
            raise AppError(404, 'NOT_FOUND', '找不到這筆檢查，或已經在回收桶。')
        reports = db.query(ClinicalReport).filter(ClinicalReport.exam_id == exam_id).all()
        if any(r.status == 'signed' for r in reports):
            raise AppError(409, 'REPORT_SIGNED', '這筆檢查有已簽核的報告，不能刪除；請先在報告頁「作廢」（需要原因）。')
        if db.query(ClinicalAnalysis).filter(ClinicalAnalysis.exam_id == exam_id, ClinicalAnalysis.status.in_(('queued', 'running'))).count():
            raise AppError(409, 'EXAM_BUSY', '這筆檢查還在分析，請等完成後再刪除。')
        stamp = now_iso()
        e.trashed_at = stamp
        for r in reports:
            r.trashed_at = r.trashed_at or stamp
        case = db.get(ClinicalPatient, e.patient_id).case_code
    return f'醫師端檢查 {exam_id}（{case}）'


def restore(exam_ids: list[str]) -> None:
    with session_scope('clinical') as db:
        for exam_id in exam_ids:
            e = db.get(ClinicalExam, exam_id)
            if e is None:
                continue
            for r in db.query(ClinicalReport).filter(ClinicalReport.exam_id == exam_id, ClinicalReport.trashed_at == e.trashed_at).all():
                r.trashed_at = None
            e.trashed_at = None


def purge(exam_ids: list[str], stage=None) -> list:
    """刪除資料列與檔案。stage（回收桶提供）先確認每個檔案都能刪，失敗時資料庫不會被改；回傳已準備刪除的檔案。

    要刪的內容：去識別化影像與縮圖（02_影像/{檢查}）、分析結果（04_分析/{檢查}）、報告 PDF 資料夾、
    受限區的原始檔（整個 01_原始/{上傳批次}，包括處理失敗沒有建立影像紀錄的檔案）、沒傳完的接收暫存（05_接收暫存/{上傳批次}）、
    資料列（報告版本、報告、影像、分析、修改紀錄、檢查；沒有其他檢查的病例代碼），以及研究端關於這筆檢查的臨床回饋。
    """
    from .reports import pdf_path

    root = exams.root()
    settings = get_settings()
    folders: list[tuple[Path, Path]] = []
    staged: list = []
    with session_scope('clinical') as db:
        for exam_id in exam_ids:
            e = db.get(ClinicalExam, exam_id)
            if e is None:
                continue
            reports = db.query(ClinicalReport).filter(ClinicalReport.exam_id == exam_id).all()
            if any(r.status == 'signed' for r in reports):
                raise AppError(409, 'REPORT_SIGNED', f'{exam_id} 有已簽核的報告，不能永久刪除。')
            patient = db.get(ClinicalPatient, e.patient_id)
            folders.append((exams.image_dir(exam_id), root / '02_影像'))
            folders.append((root / '04_分析' / exam_id, root / '04_分析'))
            folders.append((pdf_path(patient.case_code, exam_id).parent, root / '03_報告'))
            folders += [((settings.root / r.pdf_relpath).parent, root / '03_報告') for r in reports if r.pdf_relpath]
            for img in db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id).all():
                if img.raw_relpath:
                    folders.append((settings.root / img.raw_relpath, root / '01_原始'))
            if e.upload_batch_id:
                folders.append((exams.raw_dir(e.upload_batch_id), root / '01_原始'))
                folders.append((exams.staging_dir(e.upload_batch_id), root / '05_接收暫存'))
            # 先刪子項目再刪檢查（直接下 DELETE，順序固定，外鍵才不會擋）
            report_ids = [r.id for r in reports]
            db.query(ClinicalReportVersion).filter(ClinicalReportVersion.report_id.in_(report_ids)).delete()
            for model in (ClinicalReport, ClinicalImage, ClinicalAnalysis, ClinicalEdit):
                db.query(model).filter(model.exam_id == exam_id).delete()
            db.query(ReceiverBatch).filter(ReceiverBatch.exam_id == exam_id).update({ReceiverBatch.exam_id: None})
            db.delete(e)
            db.flush()
            if not db.query(ClinicalExam).filter(ClinicalExam.patient_id == patient.id).count():
                db.delete(patient)
        if stage is not None:
            staged = stage(folders)  # 檔案被開著時在這裡停下，資料庫不會被改
    from ..db.models_research import ClinicalFeedback

    with session_scope('research') as db:
        db.query(ClinicalFeedback).filter(ClinicalFeedback.exam_id.in_(exam_ids)).delete(synchronize_session=False)
    return staged if stage is not None else folders
