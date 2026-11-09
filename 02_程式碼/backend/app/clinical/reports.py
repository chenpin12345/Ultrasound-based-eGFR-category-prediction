"""醫師端報告（M3-5、B7、B8、B9、D42）。

- AI 只預填有模型支撐的項目：腎長、eGFR（P(<60) 與類別），有分級模型時再加分級；皮髓質分界、積水、結石、囊腫由醫師手填（不預設「無」）。
- 草稿 → 待簽核 → 已簽核；已簽核只能修訂（新版本）或作廢（需原因）。每次儲存都是新的、不能修改的版本。
- 簽核前檢查清單：未確認的 AI 建議、失敗或略過的步驟、候選模型、待補資料、版面不符、缺像素間距；簽核時要勾選「已知悉」並記錄。
- PDF 只保留最新一份：同一份報告固定一個檔案，新版直接覆蓋；作廢時覆蓋成作廢版。記錄雜湊，被外部修改時下載會發現。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_dated, now_iso
from ..db.models_clinical import ClinicalAnalysis, ClinicalExam, ClinicalImage, ClinicalPatient, ClinicalReport, ClinicalReportVersion
from ..db.models_system import Person
from ..db.session import session_scope
from . import exams, plan
from .workspace import _exam

MANUAL_FIELDS = ('corticomedullary', 'hydronephrosis', 'stones', 'cysts')
SIDE_FIELDS = ('length_mm', 'grade', *MANUAL_FIELDS)
TEXT_FIELDS = ('findings', 'impression', 'advice', 'notes')
FIELD_LABELS = {'length_mm': '腎長（mm）', 'grade': '回音分級', 'corticomedullary': '皮髓質分界', 'hydronephrosis': '積水', 'stones': '結石', 'cysts': '囊腫'}
STATUS_LABELS = {'draft': '草稿', 'pending': '待簽核', 'signed': '已簽核', 'void': '已作廢'}


# ---------- 草稿與版本 ----------
def _ai_payload(db, exam: ClinicalExam) -> tuple[dict[str, Any], str | None]:
    a = db.get(ClinicalAnalysis, exam.latest_analysis_id) if exam.latest_analysis_id else None
    if a is None or a.status in ('queued', 'running'):
        raise AppError(409, 'ANALYSIS_NOT_READY', '這筆檢查還沒有完成的分析；請等分析完成再建立報告。')
    res = json.loads(a.results_json or '{}')
    overrides = json.loads(exam.overrides_json or '{}')
    sides = {}
    for side in ('right', 'left'):
        ai = (res.get('sides') or {}).get(side) or {}
        o = overrides.get(side) or {}
        ai_grade = (ai.get('grade') or {}).get('predicted')
        sides[side] = {'length_mm': o.get('length_mm', ai.get('length_mm')), 'length_ai': ai.get('length_mm'), 'grade': o.get('grade', ai_grade), 'grade_ai': ai_grade,
                       'ratio_mean': ai.get('ratio_mean'), 'images': ai.get('images', 0), **{f: '' for f in MANUAL_FIELDS}}
    return {'sides': sides, 'egfr': res.get('egfr'), 'ai_confirmed': False, **{f: '' for f in TEXT_FIELDS}}, a.id


def create(exam_id: str, actor: str) -> dict[str, Any]:
    with session_scope('clinical') as db:
        exam = _exam(db, exam_id)
        existing = db.query(ClinicalReport).filter(ClinicalReport.exam_id == exam_id, ClinicalReport.trashed_at.is_(None), ClinicalReport.status != 'void').first()
        if existing:
            return {'id': existing.id, 'created': False}
        payload, analysis_id = _ai_payload(db, exam)
        report_id = next_dated('RP-', [r for (r,) in db.query(ClinicalReport.id).all()], width=3)
        db.add(ClinicalReport(id=report_id, exam_id=exam_id, status='draft', analysis_id=analysis_id, created_at=now_iso(), updated_at=now_iso()))
        db.flush()
        _add_version(db, report_id, 'draft', payload, actor)
    return {'id': report_id, 'created': True}


def _add_version(db, report_id: str, status: str, payload: dict[str, Any], actor: str, acknowledged: list[str] | None = None) -> int:
    r = db.get(ClinicalReport, report_id)
    version = r.current_version + 1
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    db.add(ClinicalReportVersion(report_id=report_id, version=version, status=status, payload_json=text, payload_sha256=hashlib.sha256(text.encode()).hexdigest(),
                                 acknowledged_json=json.dumps(acknowledged or [], ensure_ascii=False), actor=actor, created_at=now_iso()))
    r.current_version, r.status, r.updated_at = version, status, now_iso()
    return version


def _report(db, report_id: str) -> ClinicalReport:
    r = db.get(ClinicalReport, report_id)
    if r is None or r.trashed_at:
        raise AppError(404, 'REPORT_NOT_FOUND', '找不到這份報告。')
    return r


def _payload(db, report_id: str, version: int | None = None) -> dict[str, Any]:
    r = _report(db, report_id)
    v = db.query(ClinicalReportVersion).filter(ClinicalReportVersion.report_id == report_id, ClinicalReportVersion.version == (version or r.current_version)).first()
    return json.loads(v.payload_json) if v else {}


def _clean(old: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(old))
    for f in TEXT_FIELDS:
        if f in incoming:
            out[f] = str(incoming[f] or '')[:5000]
    if 'ai_confirmed' in incoming:
        out['ai_confirmed'] = bool(incoming['ai_confirmed'])
    for side, values in (incoming.get('sides') or {}).items():
        if side not in ('right', 'left') or not isinstance(values, dict):
            continue
        target = out['sides'].setdefault(side, {})
        for f in SIDE_FIELDS:
            if f not in values:
                continue
            v = values[f]
            if f == 'length_mm' and v not in (None, ''):
                v = float(v)
                if not 20 <= v <= 250:
                    raise AppError(422, 'BAD_LENGTH', '腎長請填 20 到 250 mm。')
            if f == 'grade' and v not in (None, '', 'G0', 'G1', 'G2', 'G3'):
                raise AppError(422, 'BAD_GRADE', '分級只能是 G0–G3。')
            target[f] = v if not isinstance(v, str) else v[:500]
    return out


def save(report_id: str, incoming: dict[str, Any], actor: str, submit: bool = False) -> dict[str, Any]:
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        if r.status not in ('draft', 'pending'):
            raise AppError(409, 'REPORT_LOCKED', '已簽核或已作廢的報告不能直接修改；已簽核的請按「修訂」。')
        payload = _clean(_payload(db, report_id), incoming)
        _add_version(db, report_id, 'pending' if submit else 'draft', payload, actor)
    return detail(report_id)


def checklist(report_id: str) -> list[dict[str, str]]:
    """簽核前要知悉的事（B9）。"""
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        payload = _payload(db, report_id)
        exam = db.get(ClinicalExam, r.exam_id)
        a = db.get(ClinicalAnalysis, r.analysis_id) if r.analysis_id else None
        images = db.query(ClinicalImage).filter(ClinicalImage.exam_id == r.exam_id).all()
    items: list[dict[str, str]] = []
    if not payload.get('ai_confirmed'):
        items.append({'key': 'ai_unconfirmed', 'text': 'AI 預填的腎長、eGFR（與分級）還沒有確認'})
    for zone, step in (json.loads(a.steps_json or '{}') if a else {}).items():
        if step.get('status') in ('failed', 'skipped'):
            items.append({'key': f'step_{zone}', 'text': f'{plan.ZONE_LABELS.get(zone, zone)}步驟{"失敗" if step["status"] == "failed" else "略過"}：{step.get("message", "")}'})
    if a and a.candidate:
        items.append({'key': 'candidate', 'text': f'使用候選模型：{plan.CANDIDATE_LABEL}'})
    missing = exams.missing_clinical(exam)
    if missing:
        items.append({'key': 'needs_data', 'text': f'缺臨床資料：{"、".join(missing)}'})
    if any(i.status == 'layout_mismatch' for i in images):
        items.append({'key': 'layout', 'text': '有影像版面不符，沒有納入分析'})
    if any(i.status == 'ok' and not i.pixel_spacing_mm for i in images):
        items.append({'key': 'spacing', 'text': '有影像缺像素間距（量不到尺），腎長不可用'})
    return items


def _physicians() -> set[str]:
    with session_scope('system') as db:
        return {p.name for p in db.query(Person).filter(Person.kind == 'physician', Person.active.is_(True)).all()}


def sign(report_id: str, physician: str, confirm_name: str, acknowledged: list[str], actor: str) -> dict[str, Any]:
    if physician not in _physicians():
        raise AppError(422, 'PHYSICIAN_REQUIRED', '請從醫師名單選擇判讀醫師（設定 › 醫師與操作者名單）。')
    if confirm_name.strip() != physician:
        raise AppError(422, 'CONFIRM_MISMATCH', '請輸入判讀醫師的姓名確認簽核。')
    needed = {i['key'] for i in checklist(report_id)}
    if not needed <= set(acknowledged or []):
        raise AppError(422, 'CHECKLIST_REQUIRED', '請先勾選簽核前檢查清單的每一項「已知悉」。')
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        if r.status not in ('draft', 'pending'):
            raise AppError(409, 'REPORT_LOCKED', '這份報告已簽核或已作廢。')
        payload = _payload(db, report_id)
        _add_version(db, report_id, 'signed', payload, actor, sorted(needed))
        r.signed_by, r.signed_at = physician, now_iso()
        db.get(ClinicalExam, r.exam_id).status = 'signed'
    render_pdf(report_id)
    return detail(report_id)


def revise(report_id: str, actor: str) -> dict[str, Any]:
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        if r.status != 'signed':
            raise AppError(409, 'NOT_SIGNED', '只有已簽核的報告可以修訂。')
        payload = _payload(db, report_id)
        _add_version(db, report_id, 'draft', payload, actor)
        r.signed_by, r.signed_at = None, None
        exam = db.get(ClinicalExam, r.exam_id)
        exam.status = 'ready'
    return detail(report_id)


def void(report_id: str, reason: str, actor: str) -> dict[str, Any]:
    if not (reason or '').strip():
        raise AppError(422, 'REASON_REQUIRED', '作廢需要填原因。')
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        if r.status == 'void':
            raise AppError(409, 'ALREADY_VOID', '這份報告已經作廢。')
        payload = _payload(db, report_id)
        _add_version(db, report_id, 'void', payload, actor)
        r.void_reason = reason.strip()[:200]
        exam = db.get(ClinicalExam, r.exam_id)
        if exam.status == 'signed':
            exam.status = 'ready'
        had_pdf = bool(r.pdf_relpath)
    if had_pdf:
        render_pdf(report_id)  # 覆蓋成作廢版（D42）
    return detail(report_id)


# ---------- 查詢 ----------
def detail(report_id: str) -> dict[str, Any]:
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        exam = db.get(ClinicalExam, r.exam_id)
        patient = db.get(ClinicalPatient, exam.patient_id)
        a = db.get(ClinicalAnalysis, r.analysis_id) if r.analysis_id else None
        versions = [{'version': v.version, 'status': v.status, 'actor': v.actor, 'created_at': v.created_at, 'acknowledged': json.loads(v.acknowledged_json or '[]')}
                    for v in db.query(ClinicalReportVersion).filter(ClinicalReportVersion.report_id == report_id).order_by(ClinicalReportVersion.version.desc()).all()]
        out = {'id': r.id, 'exam_id': r.exam_id, 'status': r.status, 'status_label': STATUS_LABELS[r.status], 'version': r.current_version, 'payload': _payload(db, report_id),
               'signed_by': r.signed_by, 'signed_at': r.signed_at, 'void_reason': r.void_reason, 'analysis_id': r.analysis_id,
               'candidate': bool(a and a.candidate), 'candidate_label': plan.CANDIDATE_LABEL if a and a.candidate else '',
               'models': json.loads(a.models_json or '{}') if a else {}, 'pdf': {'version': r.pdf_version, 'exists': bool(r.pdf_relpath)},
               'case_code': patient.case_code, 'patient_mode': patient.mode, 'exam_title': exam.title, 'received_at': exam.received_at, 'versions': versions}
    out['checklist'] = checklist(report_id) if out['status'] in ('draft', 'pending') else []
    return out


def version_payload(report_id: str, version: int) -> dict[str, Any]:
    with session_scope('clinical') as db:
        payload = _payload(db, report_id, version)
    if not payload:
        raise AppError(404, 'VERSION_NOT_FOUND', '找不到這個版本。')
    return payload


def list_reports(status: str | None = None) -> list[dict[str, Any]]:
    with session_scope('clinical') as db:
        q = db.query(ClinicalReport, ClinicalExam, ClinicalPatient).join(ClinicalExam, ClinicalExam.id == ClinicalReport.exam_id).join(
            ClinicalPatient, ClinicalPatient.id == ClinicalExam.patient_id).filter(ClinicalReport.trashed_at.is_(None))
        if status:
            q = q.filter(ClinicalReport.status == status)
        return [{'id': r.id, 'exam_id': r.exam_id, 'case_code': p.case_code, 'status': r.status, 'status_label': STATUS_LABELS[r.status], 'version': r.current_version,
                 'signed_by': r.signed_by, 'signed_at': r.signed_at, 'updated_at': r.updated_at, 'void_reason': r.void_reason, 'pdf': bool(r.pdf_relpath)}
                for r, e, p in q.order_by(ClinicalReport.updated_at.desc()).all()]


# ---------- PDF ----------
def pdf_path(case_code: str, exam_id: str) -> Path:
    from .exams import root

    safe = ''.join(ch for ch in case_code if ch not in '\\/:*?"<>|')
    return root() / '03_報告' / f'{safe}_{exam_id}' / '報告.pdf'


def _font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if 'MSJH' in pdfmetrics.getRegisteredFontNames():
        return 'MSJH'
    import os

    candidates = [os.environ.get('KIDNEY_PDF_FONT', ''), str(Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'msjh.ttc')]
    for path in candidates:
        if path and Path(path).exists():
            pdfmetrics.registerFont(TTFont('MSJH', path, subfontIndex=0) if path.lower().endswith('.ttc') else TTFont('MSJH', path))
            return 'MSJH'
    raise AppError(503, 'FONT_REQUIRED', '找不到微軟正黑體（msjh.ttc），無法產生中文 PDF。')


def _composite(exam_id: str, analysis_id: str | None, image_id: str) -> bytes | None:
    """去識別化影像＋遮罩疊圖，給 PDF 用。"""
    import cv2
    import numpy as np

    from ..ml.pipeline import OVERLAY

    model = exams.image_file(exam_id, image_id, 'model')
    if not model.exists():
        return None
    gray = cv2.imdecode(np.fromfile(str(model), np.uint8), cv2.IMREAD_GRAYSCALE)
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32)
    mask_path = exams.analysis_dir(exam_id, analysis_id) / f'{image_id}_mask.png' if analysis_id else None
    if mask_path and mask_path.exists():
        label = cv2.imdecode(np.fromfile(str(mask_path), np.uint8), cv2.IMREAD_GRAYSCALE)
        for value, (b, g, r, a) in OVERLAY.items():
            sel = label == value
            bgr[sel] = bgr[sel] * (1 - a / 255) + np.array([b, g, r], np.float32) * (a / 255)
    h, w = gray.shape
    scale = min(1.0, 900 / max(h, w))
    out = cv2.resize(bgr.clip(0, 255).astype(np.uint8), (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.imencode('.png', out)[1].tobytes()


def render_pdf(report_id: str) -> dict[str, Any]:
    """產生（覆蓋）這份報告唯一的 PDF。"""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    info = detail(report_id)
    font = _font()
    p = info['payload']
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        exam = db.get(ClinicalExam, r.exam_id)
        patient = db.get(ClinicalPatient, exam.patient_id)
        a = db.get(ClinicalAnalysis, r.analysis_id) if r.analysis_id else None
        res = json.loads(a.results_json or '{}') if a else {}
        name, mrn = (patient.name, patient.mrn) if patient.mode == 'device' else (None, None)

    def esc(text: Any) -> str:
        s = '—' if text in (None, '') else str(text)
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('≥', '≧').replace('≤', '≦').replace('\n', '<br/>')

    base = ParagraphStyle('base', fontName=font, fontSize=10, leading=15)
    small = ParagraphStyle('small', parent=base, fontSize=8, leading=11, textColor=colors.HexColor('#4A5A68'))
    h1 = ParagraphStyle('h1', parent=base, fontSize=17, leading=23)
    h2 = ParagraphStyle('h2', parent=base, fontSize=12, leading=18, spaceBefore=8, spaceAfter=4)
    warn = ParagraphStyle('warn', parent=base, textColor=colors.HexColor('#A8661A'))
    story: list[Any] = [Paragraph('腎臟超音波報告', h1)]
    if info['status'] == 'void':
        story.append(Paragraph(f'【已作廢】原因：{esc(info["void_reason"])}', ParagraphStyle('void', parent=base, fontSize=14, textColor=colors.HexColor('#B03A2E'))))
    if info['candidate']:
        story.append(Paragraph(f'【{plan.CANDIDATE_LABEL}】AI 結果來自尚未臨床核准的候選模型。', warn))
    ident = [['病例代碼', esc(patient.case_code), '檢查編號', esc(exam.id)]]
    if name or mrn:
        ident.append(['姓名', esc(name), '病歷號', esc(mrn)])
    ident += [['檢查日期', esc(exam.received_at[:10]), '報告版本', f'第 {info["version"]} 版（{info["status_label"]}）'],
              ['年齡／性別', f'{esc(exam.age if exam.age is None else int(exam.age))}／{ {"M": "男", "F": "女"}.get(exam.sex or "", "—") }', '糖尿病', {'yes': '有', 'no': '無'}.get(exam.diabetes, '不明')]]
    table_style = TableStyle([('FONTNAME', (0, 0), (-1, -1), font), ('FONTSIZE', (0, 0), (-1, -1), 9.5), ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D3DCDB')),
                              ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#EEF2F1')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')])
    t = Table(ident, colWidths=[24 * mm, 56 * mm, 24 * mm, 56 * mm])
    t.setStyle(TableStyle([*table_style.getCommands(), ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#EEF2F1'))]))
    story += [Spacer(0, 4 * mm), t, Paragraph('左右腎結果', h2)]
    sides = p.get('sides') or {}
    rows = [['項目', '右腎', '左腎']]
    for f in SIDE_FIELDS:
        rows.append([FIELD_LABELS[f], *[Paragraph(esc((sides.get(s) or {}).get(f)), base) for s in ('right', 'left')]])
    rows.append(['回音比（皮質／肝或脾）', *[esc((sides.get(s) or {}).get('ratio_mean')) for s in ('right', 'left')]])
    t = Table(rows, colWidths=[44 * mm, 58 * mm, 58 * mm])
    t.setStyle(TableStyle([*table_style.getCommands(), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEF2F1'))]))
    story.append(t)
    egfr = p.get('egfr')
    story.append(Paragraph('eGFR（AI 預測，整次檢查）', h2))
    if egfr:
        probs = '、'.join(f'{esc(c)}：{v * 100:.0f}%' for c, v in zip(egfr.get('classes') or [], egfr.get('probs') or []))
        story.append(Paragraph(f'P(eGFR&lt;60)：{egfr["p_lt60"] * 100:.0f}%　預測類別：{esc(egfr.get("predicted"))}<br/>各類機率：{probs}', base))
        story.append(Paragraph('機率是模型輸出，不等於準確率；不是 CKD 診斷。', small))
    else:
        story.append(Paragraph('沒有 eGFR 結果（分析方案沒有選 eGFR 模型，或缺臨床資料而略過）。', base))
    images = []
    for side in ('right', 'left'):
        image_id = ((res.get('sides') or {}).get(side) or {}).get('longest_image_id')
        if image_id:
            png = _composite(exam.id, r.analysis_id, image_id)
            if png:
                img = RLImage(io.BytesIO(png))
                ratio = img.imageHeight / img.imageWidth
                img.drawWidth, img.drawHeight = 78 * mm, 78 * mm * ratio
                images.append([img, Paragraph(f'{"右腎" if side == "right" else "左腎"}（最長的一張，遮罩疊圖）', small)])
    if images:
        story.append(Paragraph('影像（去識別化）', h2))
        grid = Table([[i[0] for i in images], [i[1] for i in images]], colWidths=[80 * mm] * len(images))
        grid.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story.append(grid)
    for f, label in (('findings', '檢查所見'), ('impression', '醫師判讀'), ('advice', '建議'), ('notes', '備註')):
        story += [Paragraph(label, h2), Paragraph(esc(p.get(f)) if p.get(f) else '尚未填寫', base)]
    models = info['models'] or {}
    if models:
        story.append(Paragraph('使用的模型', h2))
        story.append(Paragraph('<br/>'.join(f'{plan.ZONE_LABELS.get(z, z)}：{esc(m.get("model_id"))}（{plan.STAGE_LABELS.get(m.get("stage"), m.get("stage"))}）' for z, m in models.items()), base))
    signer = f'判讀醫師：{esc(info["signed_by"])}　簽核時間：{esc(info["signed_at"])}' if info['signed_by'] else '尚未簽核'
    story += [Spacer(0, 6 * mm), Paragraph(signer, base), Spacer(0, 3 * mm),
              Paragraph('研究用途，非醫療診斷。AI 結果僅供參考，需由醫師判讀。本系統的簽核是本機操作紀錄，不是電子簽章。', small)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#7A8894'))
        canvas.drawString(18 * mm, 10 * mm, f'{info["id"]}・第 {info["version"]} 版・{info["status_label"]}・第 {doc.page} 頁')
        if info['status'] == 'void':
            canvas.setFont(font, 60)
            canvas.setFillColor(colors.Color(0.69, 0.23, 0.18, alpha=0.18))
            canvas.translate(105 * mm, 150 * mm)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, '已作廢')
        canvas.restoreState()

    target = pdf_path(patient.case_code, exam.id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.part')
    SimpleDocTemplate(str(tmp), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                      title=f'腎臟超音波報告 {patient.case_code}').build(story, onFirstPage=footer, onLaterPages=footer)
    tmp.replace(target)  # 覆蓋舊版：資料夾只留最新一份（D42）
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        r.pdf_relpath, r.pdf_sha256, r.pdf_version = target.relative_to(get_settings().root).as_posix(), digest, r.current_version
    return {'path': target.relative_to(get_settings().root).as_posix(), 'version': info['version']}


def pdf_file(report_id: str) -> Path:
    with session_scope('clinical') as db:
        r = _report(db, report_id)
        rel, digest = r.pdf_relpath, r.pdf_sha256
    if not rel:
        raise AppError(404, 'PDF_NOT_FOUND', '這份報告還沒有產生 PDF。')
    path = get_settings().root / rel
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise AppError(409, 'PDF_CHANGED', 'PDF 檔案被移動或修改過，請按「產生 PDF」重新產生。')
    return path
