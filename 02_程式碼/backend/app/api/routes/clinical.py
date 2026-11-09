"""醫師端 API（M3）。分析方案的設定值存在系統設定 `clinical_plan`（PUT /api/settings）。

雙機接收的「上傳小程式」是另一個程式（app/clinical/receiver.py 的 upload_app），只在開始接收時於區網 IP 上啟動；
這裡的 API 只給本機的醫師端頁面使用。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ...core import audit
from ..deps import operator

router = APIRouter()


@router.get('/clinical/plan')
def analysis_plan():
    """每一區可選的模型、目前的方案（含候選標示與問題）、已預先載入的模型。"""
    from ...clinical import models_cache, plan

    return {'options': plan.options(), 'current': plan.current(), 'loaded': models_cache.loaded()}


@router.post('/clinical/warmup', status_code=202)
def warmup(request: Request):
    """把分析方案的模型先載入（醫師端佇列，不排在訓練後面）。"""
    from ...jobs.manager import get_manager

    job_id = get_manager().submit('clinical_warmup', {}, target='醫師端分析方案', created_by=operator(request))
    audit.record(operator(request), '醫師端預先載入模型', 'job', job_id)
    return {'job_id': job_id}


# ---- 首頁 ----
@router.get('/clinical/overview')
def overview():
    """醫師端首頁（B1）：開始前檢查、今日待辦。"""
    from ...clinical import home

    return home.overview()


# ---- 雙機接收（D38） ----
class ReceiverStartIn(BaseModel):
    address: str | None = None


@router.get('/clinical/receiver')
def receiver_status():
    from ...clinical import receiver

    return receiver.status()


@router.post('/clinical/receiver/start')
def receiver_start(body: ReceiverStartIn, request: Request):
    from ...clinical import receiver

    result = receiver.start(body.address, operator(request))
    audit.record(operator(request), '開始雙機接收', 'receiver', result['id'], {'address': result['address'], 'port': result['port']})
    return result


@router.post('/clinical/receiver/stop')
def receiver_stop(request: Request):
    from ...clinical import receiver

    receiver.stop()
    audit.record(operator(request), '停止雙機接收', 'receiver', '')
    return {'ok': True}


@router.post('/clinical/receiver/code')
def receiver_code():
    from ...clinical import receiver

    return receiver.new_code()


@router.get('/clinical/receiver/batches/{batch_id}/summary')
def receiver_summary(batch_id: str):
    """傳送摘要（B10）：下載成 JSON 檔；不含檔名與個資。"""
    import json

    from ...clinical import receiver

    data = receiver.summary(batch_id)
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="transfer_{batch_id}.json"'})


class DemoPackIn(BaseModel):
    patients: int = Field(6, ge=1, le=30)


@router.post('/clinical/demo-pack')
def demo_pack(body: DemoPackIn, request: Request):
    """匯出示範影像包（D43）：測試集病人的去識別化影像＋示範清單，放在 08_匯出。"""
    from ...clinical import demo_pack as pack

    result = pack.build(body.patients)
    audit.record(operator(request), '匯出示範影像包', 'export', result['folder'], {'patients': result['patients'], 'images': result['images']})
    return result


# ---- 工作清單與檢查工作區 ----
@router.get('/clinical/exams')
def exams_list(status: str | None = None, q: str | None = None, date_from: str | None = None, date_to: str | None = None):
    from ...clinical import workspace

    return {'items': workspace.list_exams(status, q, date_from, date_to), 'status_labels': workspace.STATUS_LABELS}


@router.get('/clinical/exams/{exam_id}')
def exam_detail(exam_id: str):
    from ...clinical import workspace

    return workspace.detail(exam_id)


@router.get('/clinical/images/{image_id}/{kind}')
def exam_image(image_id: str, kind: str):
    from ...clinical import workspace

    path = workspace.image_path(image_id, kind)
    return FileResponse(path, media_type='image/jpeg' if kind == 'thumb' else 'image/png', headers={'Cache-Control': 'private, max-age=3600'})


@router.get('/clinical/analyses/{analysis_id}/overlay/{image_id}')
def exam_overlay(analysis_id: str, image_id: str):
    from ...clinical import analysis

    return Response(analysis.overlay_png(analysis_id, image_id), media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})


class ImagePatch(BaseModel):
    excluded: bool | None = None
    reason: str = ''
    side: str | None = None


@router.patch('/clinical/exams/{exam_id}/images/{image_id}')
def exam_image_patch(exam_id: str, image_id: str, body: ImagePatch, request: Request):
    from ...clinical import workspace

    changes: dict[str, Any] = body.model_dump(exclude_unset=True)
    return workspace.set_image(exam_id, image_id, changes, operator(request))


class SidePatch(BaseModel):
    length_mm: float | None = None
    grade: str | None = None


@router.patch('/clinical/exams/{exam_id}/sides/{side}')
def exam_side_patch(exam_id: str, side: str, body: SidePatch, request: Request):
    from ...clinical import workspace

    return workspace.set_side_values(exam_id, side, body.model_dump(exclude_unset=True), operator(request))


class ClinicalIn(BaseModel):
    age: float | None = None
    sex: str | None = None
    diabetes: str | None = None


@router.patch('/clinical/exams/{exam_id}/clinical')
def exam_clinical_patch(exam_id: str, body: ClinicalIn, request: Request):
    from ...clinical import workspace

    return workspace.set_clinical(exam_id, body.model_dump(), operator(request))


@router.post('/clinical/exams/{exam_id}/reanalyze', status_code=202)
def exam_reanalyze(exam_id: str, request: Request):
    from ...clinical import workspace

    result = workspace.reanalyze(exam_id, operator(request))
    audit.record(operator(request), '醫師端重新分析', 'exam', exam_id, {'analysis_id': result['analysis_id']})
    return result


@router.post('/clinical/exams/{exam_id}/layout')
def exam_fix_layout(exam_id: str, request: Request):
    """版面不符：從最接近的範本按比例建立新範本，再重新去識別化。"""
    from ...clinical import exams

    result = exams.fix_layout(exam_id, operator(request))
    audit.record(operator(request), '醫師端建立版面範本', 'exam', exam_id, result)
    return result


@router.get('/clinical/patients')
def patients_list():
    from ...clinical import workspace

    return {'items': workspace.list_patients()}


@router.get('/clinical/patients/{patient_id}')
def patient_detail(patient_id: str):
    from ...clinical import workspace

    return workspace.patient_detail(patient_id)


# ---- 報告（M3-5） ----
@router.get('/clinical/reports')
def reports_list(status: str | None = None):
    from ...clinical import reports

    return {'items': reports.list_reports(status), 'status_labels': reports.STATUS_LABELS}


@router.post('/clinical/exams/{exam_id}/report')
def report_create(exam_id: str, request: Request):
    from ...clinical import reports

    result = reports.create(exam_id, operator(request))
    if result['created']:
        audit.record(operator(request), '建立報告草稿', 'report', result['id'], {'exam_id': exam_id})
    return reports.detail(result['id'])


@router.get('/clinical/reports/{report_id}')
def report_detail(report_id: str):
    from ...clinical import reports

    return reports.detail(report_id)


@router.get('/clinical/reports/{report_id}/versions/{version}')
def report_version(report_id: str, version: int):
    from ...clinical import reports

    return reports.version_payload(report_id, version)


class ReportSave(BaseModel):
    payload: dict[str, Any]
    submit: bool = False


@router.put('/clinical/reports/{report_id}')
def report_save(report_id: str, body: ReportSave, request: Request):
    from ...clinical import reports

    result = reports.save(report_id, body.payload, operator(request), body.submit)
    if body.submit:
        audit.record(operator(request), '報告送簽核', 'report', report_id, {'version': result['version']})
    return result


class SignIn(BaseModel):
    physician: str
    confirm_name: str
    acknowledged: list[str] = []


@router.post('/clinical/reports/{report_id}/sign')
def report_sign(report_id: str, body: SignIn, request: Request):
    from ...clinical import reports

    result = reports.sign(report_id, body.physician, body.confirm_name, body.acknowledged, operator(request))
    audit.record(operator(request), '簽核報告', 'report', report_id, {'version': result['version'], 'physician': body.physician, 'acknowledged': body.acknowledged})
    return result


@router.post('/clinical/reports/{report_id}/revise')
def report_revise(report_id: str, request: Request):
    from ...clinical import reports

    result = reports.revise(report_id, operator(request))
    audit.record(operator(request), '修訂已簽核報告', 'report', report_id, {'version': result['version']})
    return result


class VoidIn(BaseModel):
    reason: str


@router.post('/clinical/reports/{report_id}/void')
def report_void(report_id: str, body: VoidIn, request: Request):
    from ...clinical import reports

    result = reports.void(report_id, body.reason, operator(request))
    audit.record(operator(request), '作廢報告', 'report', report_id, {'reason': body.reason})
    return result


@router.post('/clinical/reports/{report_id}/pdf')
def report_pdf_make(report_id: str, request: Request):
    """產生 PDF：同一份報告只保留一個檔案，新版覆蓋舊版（D42）。"""
    from ...clinical import reports

    result = reports.render_pdf(report_id)
    audit.record(operator(request), '產生報告 PDF', 'report', report_id, result)
    return result


@router.get('/clinical/reports/{report_id}/pdf')
def report_pdf(report_id: str, download: bool = False):
    from ...clinical import reports

    path = reports.pdf_file(report_id)
    return FileResponse(path, media_type='application/pdf', filename=f'{report_id}.pdf', content_disposition_type='attachment' if download else 'inline',
                        headers={'Cache-Control': 'no-store'})


# ---- 轉入研究（M3-7） ----
class TransferIn(BaseModel):
    patient_id: str
    image_ids: list[str] = []


@router.post('/clinical/exams/{exam_id}/transfer')
def exam_transfer(exam_id: str, body: TransferIn, request: Request):
    from ...clinical import transfer

    result = transfer.to_research(exam_id, body.patient_id, body.image_ids, operator(request))
    audit.record(operator(request), '醫師端轉入研究', 'exam', exam_id, {'patient_id': body.patient_id, 'batch_id': result['batch_id'], 'images': result['images']})
    return result

