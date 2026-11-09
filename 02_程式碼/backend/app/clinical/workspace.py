"""醫師端的工作清單與檢查工作區（M3-4、B3、B5、B6）。

- 工作清單：日期、狀態、搜尋篩選；每列有候選標示、eGFR P(<60)、待補資料。
- 檢查工作區：影像、去識別化缺項、最新分析、與前次檢查比較、修改紀錄。
- 醫師可以：排除或還原影像（排除要原因）、指定側別、修改腎長、確認或修改分級、補填臨床資料、重新分析。
  每項修改記在醫師端的修改紀錄；腎長、分級、排除、側別另外回饋到研究端的「臨床回饋」（不送年齡、糖尿病這類臨床資料）。
- 姓名、病歷號只有超音波模式才有，也只在醫師端的回應裡出現（D39）。
"""

from __future__ import annotations

import json
from typing import Any

from ..core.errors import AppError
from ..core.ids import now_iso
from ..db.models_clinical import ClinicalAnalysis, ClinicalEdit, ClinicalExam, ClinicalImage, ClinicalPatient, ClinicalReport
from ..db.session import session_scope
from . import analysis as clinical_analysis
from . import exams

STATUS_LABELS = {'receiving': '接收中', 'analyzing': '分析中', 'needs_data': '待補資料', 'layout_mismatch': '版面不符', 'ready': 'AI 完成',
                 'partial': '部分完成', 'failed': '失敗', 'signed': '已簽核'}


def _exam(db, exam_id: str) -> ClinicalExam:
    exam = db.get(ClinicalExam, exam_id)
    if exam is None or exam.trashed_at:
        raise AppError(404, 'EXAM_NOT_FOUND', '找不到這筆檢查。')
    return exam


def _patient_dict(p: ClinicalPatient) -> dict[str, Any]:
    out = {'id': p.id, 'case_code': p.case_code, 'mode': p.mode}
    if p.mode == 'device':  # 受限欄位：只有超音波模式，只在醫師端頁面回傳
        out.update(name=p.name, mrn=p.mrn)
    return out


def list_exams(status: str | None = None, q: str | None = None, date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
    with session_scope('clinical') as db:
        query = db.query(ClinicalExam, ClinicalPatient).join(ClinicalPatient, ClinicalPatient.id == ClinicalExam.patient_id).filter(ClinicalExam.trashed_at.is_(None))
        if status:
            query = query.filter(ClinicalExam.status.in_(status.split(',')))
        if date_from:
            query = query.filter(ClinicalExam.received_at >= date_from)
        if date_to:
            query = query.filter(ClinicalExam.received_at <= date_to + 'T23:59:59')
        rows = query.order_by(ClinicalExam.received_at.desc()).limit(500).all()
        ids = [e.id for e, _ in rows]
        analyses = {a.id: a for a in db.query(ClinicalAnalysis).filter(ClinicalAnalysis.id.in_([e.latest_analysis_id for e, _ in rows if e.latest_analysis_id])).all()}
        counts: dict[str, int] = {}
        for (exam_id,) in db.query(ClinicalImage.exam_id).filter(ClinicalImage.exam_id.in_(ids)).all():
            counts[exam_id] = counts.get(exam_id, 0) + 1
        reports: dict[str, ClinicalReport] = {}
        for r in db.query(ClinicalReport).filter(ClinicalReport.exam_id.in_(ids), ClinicalReport.trashed_at.is_(None)).order_by(ClinicalReport.created_at).all():
            if r.exam_id not in reports or reports[r.exam_id].status == 'void':  # 同一筆檢查作廢後重開的報告：顯示目前有效的那份
                reports[r.exam_id] = r
        out = []
        for e, p in rows:
            if q and q.strip().upper() not in f'{e.id} {p.case_code}'.upper():
                continue
            a = analyses.get(e.latest_analysis_id or '')
            res = json.loads(a.results_json or '{}') if a else {}
            sides = res.get('sides') or {}
            r = reports.get(e.id)
            out.append({'id': e.id, 'case_code': p.case_code, 'title': e.title, 'received_at': e.received_at, 'status': e.status, 'status_label': STATUS_LABELS.get(e.status, e.status),
                        'images': counts.get(e.id, 0), 'candidate': bool(a and a.candidate), 'p_lt60': (res.get('egfr') or {}).get('p_lt60'),
                        'right_length_mm': (sides.get('right') or {}).get('length_mm'), 'left_length_mm': (sides.get('left') or {}).get('length_mm'),
                        'missing_clinical': exams.missing_clinical(e), 'report_status': r.status if r else None, 'report_id': r.id if r else None})
        return out


def detail(exam_id: str) -> dict[str, Any]:
    with session_scope('clinical') as db:
        e = _exam(db, exam_id)
        p = db.get(ClinicalPatient, e.patient_id)
        images = [{'id': i.id, 'seq': i.seq, 'side': i.side, 'side_source': i.side_source, 'pixel_spacing_mm': i.pixel_spacing_mm, 'spacing_source': i.spacing_source,
                   'status': i.status, 'exclude_reason': i.exclude_reason, 'width': i.width, 'height': i.height, 'deid': json.loads(i.deid_json or '{}')}
                  for i in db.query(ClinicalImage).filter(ClinicalImage.exam_id == exam_id).order_by(ClinicalImage.seq).all()]
        latest = db.get(ClinicalAnalysis, e.latest_analysis_id) if e.latest_analysis_id else None
        history = [{'id': a.id, 'status': a.status, 'created_at': a.created_at, 'candidate': a.candidate} for a in
                   db.query(ClinicalAnalysis).filter(ClinicalAnalysis.exam_id == exam_id).order_by(ClinicalAnalysis.created_at.desc()).all()]
        running = any(h['status'] in ('queued', 'running') for h in history)
        edits = [{'id': x.id, 'image_id': x.image_id, 'kind': x.kind, 'before': json.loads(x.before_json), 'after': json.loads(x.after_json), 'reason': x.reason,
                  'actor': x.actor, 'created_at': x.created_at} for x in db.query(ClinicalEdit).filter(ClinicalEdit.exam_id == exam_id).order_by(ClinicalEdit.id.desc()).all()]
        report = current_report(db, exam_id)
        out = {'id': e.id, 'patient': _patient_dict(p), 'title': e.title, 'mode': e.mode, 'source': e.source, 'status': e.status, 'status_label': STATUS_LABELS.get(e.status, e.status),
               'received_at': e.received_at, 'clinical': {'age': e.age, 'sex': e.sex, 'diabetes': e.diabetes, 'source': e.clinical_source},
               'missing_clinical': exams.missing_clinical(e), 'overrides': json.loads(e.overrides_json or '{}'), 'images': images,
               'analysis': clinical_analysis.analysis_dict(latest) if latest else None, 'analyses': history, 'analysis_running': running, 'edits': edits,
               'report': {'id': report.id, 'status': report.status, 'version': report.current_version} if report else None}
        out['previous'] = _previous(db, e)
    return out


def current_report(db, exam_id: str) -> ClinicalReport | None:
    """目前有效的報告；全部作廢時回傳最新那份（作廢的）。"""
    rows = db.query(ClinicalReport).filter(ClinicalReport.exam_id == exam_id, ClinicalReport.trashed_at.is_(None)).order_by(ClinicalReport.created_at.desc()).all()
    return next((r for r in rows if r.status != 'void'), rows[0] if rows else None)


def _previous(db, e: ClinicalExam) -> dict[str, Any] | None:
    """與前次檢查比較（B3）：同一病人上一次有分析結果的檢查。"""
    prev = (db.query(ClinicalExam).filter(ClinicalExam.patient_id == e.patient_id, ClinicalExam.id != e.id, ClinicalExam.received_at < e.received_at,
                                          ClinicalExam.trashed_at.is_(None), ClinicalExam.latest_analysis_id.isnot(None))
            .order_by(ClinicalExam.received_at.desc()).first())
    if prev is None:
        return None
    a = db.get(ClinicalAnalysis, prev.latest_analysis_id)
    res = json.loads(a.results_json or '{}') if a else {}
    overrides = json.loads(prev.overrides_json or '{}')
    sides = {s: {'length_mm': (overrides.get(s) or {}).get('length_mm') or (v or {}).get('length_mm'),
                 'grade': (overrides.get(s) or {}).get('grade') or ((v or {}).get('grade') or {}).get('predicted')} for s, v in (res.get('sides') or {}).items()}
    return {'exam_id': prev.id, 'received_at': prev.received_at, 'sides': sides, 'p_lt60': (res.get('egfr') or {}).get('p_lt60'), 'age': prev.age}


# ---------- 醫師的修改 ----------
def _feedback(exam_id: str, kind: str, item: str, ai: Any, doctor: Any, actor: str, side: str | None = None, image_id: str | None = None, reason: str = '', model_id: str | None = None) -> None:
    """回饋到研究端的「臨床回饋」（只送項目、AI 值、醫師值、模型；不送臨床資料）。"""
    from ..db.models_research import ClinicalFeedback

    with session_scope('research') as db:
        db.add(ClinicalFeedback(exam_id=exam_id, item=item[:80], ai_value=str('—' if ai is None else ai)[:120], doctor_value=str('—' if doctor is None else doctor)[:120],
                                by=actor, created_at=now_iso(), kind=kind, side=side, image_id=image_id, reason=reason[:200], model_id=model_id))


def _latest_results(db, e: ClinicalExam) -> tuple[dict[str, Any], dict[str, Any]]:
    a = db.get(ClinicalAnalysis, e.latest_analysis_id) if e.latest_analysis_id else None
    return (json.loads(a.results_json or '{}'), json.loads(a.models_json or '{}')) if a else ({}, {})


def _not_signed(e: ClinicalExam) -> None:
    if e.status == 'signed':
        raise AppError(409, 'EXAM_SIGNED', '這筆檢查的報告已簽核；要修改請先在報告「修訂」。')


def set_image(exam_id: str, image_id: str, changes: dict[str, Any], actor: str) -> dict[str, Any]:
    """排除／還原（排除要原因）或指定側別。"""
    with session_scope('clinical') as db:
        e = _exam(db, exam_id)
        _not_signed(e)
        img = db.get(ClinicalImage, image_id)
        if img is None or img.exam_id != exam_id:
            raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
        if 'excluded' in changes:
            if changes['excluded']:
                reason = (changes.get('reason') or '').strip()
                if not reason:
                    raise AppError(422, 'REASON_REQUIRED', '排除影像需要填原因。')
                if img.status != 'ok':
                    raise AppError(409, 'IMAGE_NOT_USABLE', '這張影像目前不能分析，不需要排除。')
                img.status, img.exclude_reason = 'excluded', reason[:120]
                kind, before, after = 'exclude', '採用', '排除'
            else:
                if img.status != 'excluded':
                    raise AppError(409, 'NOT_EXCLUDED', '這張影像沒有被排除。')
                img.status, img.exclude_reason, reason = 'ok', '', ''
                kind, before, after = 'include', '排除', '採用'
            side = img.side
        elif 'side' in changes:
            if changes['side'] not in ('right', 'left'):
                raise AppError(422, 'BAD_SIDE', '側別只能是右腎或左腎。')
            kind, before, after, reason = 'side', img.side, changes['side'], ''
            img.side, img.side_source, side = changes['side'], 'manual', changes['side']
        else:
            raise AppError(422, 'NOTHING_TO_CHANGE', '沒有要修改的項目。')
    exams.log_edit(exam_id, image_id, kind, before, after, reason, actor)
    _feedback(exam_id, kind, {'exclude': '排除影像', 'include': '還原影像', 'side': '側別'}[kind], before, after, actor, side=side, image_id=image_id, reason=reason)
    return detail(exam_id)


def set_side_values(exam_id: str, side: str, changes: dict[str, Any], actor: str) -> dict[str, Any]:
    """修改腎長（mm）或確認／修改分級；None 表示改回 AI 的值。"""
    if side not in ('right', 'left'):
        raise AppError(422, 'BAD_SIDE', '側別只能是右腎或左腎。')
    with session_scope('clinical') as db:
        e = _exam(db, exam_id)
        _not_signed(e)
        results, models = _latest_results(db, e)
        ai_side = (results.get('sides') or {}).get(side) or {}
        overrides = json.loads(e.overrides_json or '{}')
        current = overrides.setdefault(side, {})
        logs = []
        if 'length_mm' in changes:
            value = changes['length_mm']
            if value is not None and not (20 <= float(value) <= 250):
                raise AppError(422, 'BAD_LENGTH', '腎長請填 20 到 250 mm。')
            logs.append(('length', '腎長（mm）', ai_side.get('length_mm'), current.get('length_mm'), value, (models.get('segmentation') or {}).get('model_id')))
            if value is None:  # 改回 AI 的值
                current.pop('length_mm', None)
            else:
                current['length_mm'] = round(float(value), 1)
        if 'grade' in changes:
            value = changes['grade']
            if value is not None and value not in ('G0', 'G1', 'G2', 'G3'):
                raise AppError(422, 'BAD_GRADE', '分級只能是 G0–G3。')
            logs.append(('grade', '回音分級', (ai_side.get('grade') or {}).get('predicted'), current.get('grade'), value, (models.get('grade') or {}).get('model_id')))
            if value is None:
                current.pop('grade', None)
            else:
                current['grade'] = value
        e.overrides_json = json.dumps(overrides, ensure_ascii=False)
    for kind, item, ai, before, after, model_id in logs:
        exams.log_edit(exam_id, None, kind, {'side': side, 'value': before}, {'side': side, 'value': after}, '', actor)
        _feedback(exam_id, kind, item, ai, after, actor, side=side, model_id=model_id)
    return detail(exam_id)


def set_clinical(exam_id: str, values: dict[str, Any], actor: str) -> dict[str, Any]:
    """補填年齡、性別、糖尿病（只記在醫師端，不回饋到研究端）。補填後可以重新分析。"""
    clean = exams.normalize_clinical(values.get('age'), values.get('sex'), values.get('diabetes'))
    with session_scope('clinical') as db:
        e = _exam(db, exam_id)
        _not_signed(e)
        before = {'age': e.age, 'sex': e.sex, 'diabetes': e.diabetes}
        e.age, e.sex, e.diabetes, e.clinical_source = clean['age'], clean['sex'], clean['diabetes'], 'manual'
    exams.log_edit(exam_id, None, 'clinical', before, clean, '', actor)
    return detail(exam_id)


def reanalyze(exam_id: str, actor: str) -> dict[str, Any]:
    with session_scope('clinical') as db:
        e = _exam(db, exam_id)
        _not_signed(e)
        latest = e.latest_analysis_id
    result = clinical_analysis.start(exam_id, actor, retry_of=latest)
    exams.log_edit(exam_id, None, 'reanalyze', latest, result['analysis_id'], '', actor)
    return result


def image_path(image_id: str, kind: str):
    """去識別化影像或縮圖；版面不符、去識別化有殘留的影像不提供（原始檔永遠不提供）。"""
    from ..core.config import get_settings

    if kind not in ('model', 'thumb'):
        raise AppError(422, 'BAD_KIND', '只提供去識別化影像與縮圖。')
    with session_scope('clinical') as db:
        img = db.get(ClinicalImage, image_id)
        if img is None:
            raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
        if img.status in ('layout_mismatch', 'residual') or not img.relpath:
            raise AppError(403, 'IMAGE_NOT_SHOWN', '這張影像沒有通過去識別化檢查，不顯示。')
        path = exams.image_file(img.exam_id, img.id, kind)
    if not path.exists() or get_settings().root not in path.resolve().parents:
        raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像。')
    return path


# ---------- 病人與趨勢 ----------
def list_patients() -> list[dict[str, Any]]:
    with session_scope('clinical') as db:
        patients = db.query(ClinicalPatient).filter(ClinicalPatient.trashed_at.is_(None)).order_by(ClinicalPatient.id.desc()).all()
        exams_by: dict[str, list[ClinicalExam]] = {}
        for e in db.query(ClinicalExam).filter(ClinicalExam.trashed_at.is_(None)).order_by(ClinicalExam.received_at).all():
            exams_by.setdefault(e.patient_id, []).append(e)
        return [{**_patient_dict(p), 'exams': len(exams_by.get(p.id, [])), 'last_exam_at': exams_by[p.id][-1].received_at if exams_by.get(p.id) else None,
                 'last_exam_id': exams_by[p.id][-1].id if exams_by.get(p.id) else None} for p in patients if exams_by.get(p.id)]


def patient_detail(patient_id: str) -> dict[str, Any]:
    """病人的每次檢查與趨勢：腎長（醫師修改後的值優先）、分級、eGFR P(<60)。"""
    with session_scope('clinical') as db:
        p = db.get(ClinicalPatient, patient_id)
        if p is None or p.trashed_at:
            raise AppError(404, 'PATIENT_NOT_FOUND', '找不到這位病人。')
        rows = []
        for e in db.query(ClinicalExam).filter(ClinicalExam.patient_id == patient_id, ClinicalExam.trashed_at.is_(None)).order_by(ClinicalExam.received_at).all():
            a = db.get(ClinicalAnalysis, e.latest_analysis_id) if e.latest_analysis_id else None
            res = json.loads(a.results_json or '{}') if a else {}
            overrides = json.loads(e.overrides_json or '{}')
            sides = {}
            for side in ('right', 'left'):
                ai = (res.get('sides') or {}).get(side) or {}
                o = overrides.get(side) or {}
                sides[side] = {'length_mm': o.get('length_mm', ai.get('length_mm')), 'grade': o.get('grade', (ai.get('grade') or {}).get('predicted'))}
            r = current_report(db, e.id)
            rows.append({'id': e.id, 'received_at': e.received_at, 'status': e.status, 'status_label': STATUS_LABELS.get(e.status, e.status), 'age': e.age,
                         'p_lt60': (res.get('egfr') or {}).get('p_lt60'), 'sides': sides, 'candidate': bool(a and a.candidate),
                         'report': {'id': r.id, 'status': r.status} if r else None})
        return {'patient': _patient_dict(p), 'exams': rows}
