"""M2：遮罩草稿、預訓練權重、訓練、實驗、模型庫、評估、特徵、流程。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from ...annotation import drafts
from ...core import audit
from ...features import service as features
from ...jobs.manager import get_manager
from ...ml import evaluation, experiments, pipeline, pretrained, registry, runs
from ..deps import operator

router = APIRouter()


# ---- 遮罩草稿 ----
class LegacyIn(BaseModel):
    folder: str = Field(min_length=1, max_length=500)


def _submit(kind: str, config: dict[str, Any], target: str, request: Request, action: str) -> dict[str, str]:
    job_id = get_manager().submit(kind, config, target=target, created_by=operator(request))
    audit.record(operator(request), action, 'job', job_id, config)
    return {'job_id': job_id}


@router.post('/annotation/drafts/legacy', status_code=202)
def import_legacy(payload: LegacyIn, request: Request):
    return _submit('legacy_masks', {'folder': payload.folder.strip().strip('"')}, '舊程式遮罩', request, '匯入舊程式遮罩')


@router.post('/annotation/drafts/medsam', status_code=202)
def medsam_redraw(request: Request):
    return _submit('medsam_kidney', {}, '有舊遮罩的影像', request, 'MedSAM 重畫腎臟')


@router.post('/annotation/drafts/organs', status_code=202)
def organ_drafts(request: Request):
    return _submit('organ_drafts', {}, '可用影像', request, '產生肝／脾草稿')


@router.post('/annotation/drafts/regenerate', status_code=202)
def regenerate_drafts(payload: LegacyIn, request: Request):
    config = {'folder': payload.folder.strip().strip('"'), 'max_id': drafts.max_mask_id(), 'operator': operator(request)}
    return _submit('regenerate_drafts', config, '未確認的草稿', request, '用新規則重新產生草稿')


class DeleteDraftsIn(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=10)


@router.post('/annotation/drafts/delete')
def delete_drafts(payload: DeleteDraftsIn, request: Request):
    result = drafts.delete_drafts(payload.sources, operator(request))
    audit.record(operator(request), '刪除草稿（移入回收桶）', 'mask', '、'.join(payload.sources), {'moved': result['moved']})
    return result


@router.get('/annotation/drafts/queue')
def draft_queue(only_needed: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return drafts.review_queue(only_needed, limit, offset)


@router.get('/annotation/drafts/stats')
def draft_stats():
    return drafts.draft_stats()


class DecisionIn(BaseModel):
    decision: str = Field(pattern='^(accept|reject)$')
    reason: str = Field(default='', max_length=200)


@router.post('/annotation/drafts/{mask_id}/decision')
def decide(mask_id: int, payload: DecisionIn, request: Request):
    result = drafts.decide(mask_id, payload.decision, operator(request), payload.reason)
    audit.record(operator(request), '確認草稿' if payload.decision == 'accept' else '退回草稿', 'mask', str(mask_id), {'reason': payload.reason} if payload.reason else {})
    return result


# ---- 預訓練權重 ----
@router.get('/pretrained')
def list_pretrained():
    return {'weights': pretrained.list_weights()}


@router.post('/pretrained/{name}/download', status_code=202)
def download_pretrained(name: str, request: Request):
    import json

    from ...core.errors import AppError
    from ...db.models_system import Job
    from ...db.session import session_scope

    pretrained.spec(name)  # 不認識的名稱直接拒絕
    with session_scope('system') as db:  # 同一份權重同時只下載一次
        for job in db.query(Job).filter(Job.kind == 'download_pretrained', Job.status.in_(('queued', 'running', 'stopping'))).all():
            if json.loads(job.config_json or '{}').get('name') == name:
                raise AppError(409, 'ALREADY_DOWNLOADING', f'{name} 已經在下載中（{job.id}），請等它完成。')
    return _submit('download_pretrained', {'name': name}, name, request, '下載預訓練權重')


# ---- 訓練 ----
class RunIn(BaseModel):
    task: str
    name: str = Field(default='', max_length=120)
    dataset_version_id: str
    split_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    start: bool = True


@router.get('/training/tasks')
def training_tasks():
    from ...ml.data import TASKS
    from ...ml.defaults import COMMON, DEFAULTS

    return {'tasks': [{'id': k, **v, 'defaults': {**COMMON, **DEFAULTS[k]}} for k, v in TASKS.items()]}


@router.get('/training/runs')
def list_runs(task: str | None = None, experiment_id: str | None = None):
    # 三區分開（決策 D28）：清單一定要指定任務（或實驗）
    if not task and not experiment_id:
        from ...core.errors import AppError

        raise AppError(422, 'TASK_REQUIRED', '請指定任務（egfr、segmentation、grade）；三種訓練不混在同一個清單。')
    return {'runs': runs.list_runs(task, experiment_id)}


@router.post('/training/runs', status_code=201)
def create_run(payload: RunIn, request: Request):
    result = runs.create(payload.task, payload.name, payload.dataset_version_id, payload.split_id, payload.config, operator(request), start=payload.start)
    audit.record(operator(request), '建立訓練', 'run', result['id'], {'task': payload.task})
    return result


@router.get('/training/runs/{run_id}')
def run_detail(run_id: str):
    return runs.detail(run_id)


class TrashRunsIn(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=200)
    reason: str = Field(default='', max_length=200)


@router.post('/training/runs/trash', status_code=201)
def trash_runs(payload: TrashRunsIn, request: Request):
    """勾選的訓練（與它們註冊的模型）移入回收桶，同一組；永久刪除時才刪檔案（M2.5 #109）。"""
    from ...services import index
    from ...trash import service as trash

    result = trash.move_runs_to_trash(payload.run_ids, payload.reason, operator(request))
    audit.record(operator(request), '訓練移入回收桶', 'run', '、'.join(payload.run_ids), {'group_id': result['group_id'], 'models': result['models']})
    index.refresh_quietly()
    return result


@router.get('/training/runs/{run_id}/oof.csv')
def run_oof_csv(run_id: str):
    """每位病人的 OOF 機率（只用 P-編號與類別，不含 eGFR 數值）。"""
    import csv
    import io

    from fastapi.responses import Response

    from ...ml import egfr_compare

    header, rows = egfr_compare.oof_table(run_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(('﻿' + buf.getvalue()).encode('utf-8'), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename={run_id}_oof.csv'})


@router.post('/training/runs/{run_id}/start', status_code=202)
def start_run(run_id: str, request: Request):
    job_id = runs.start_run(run_id, operator(request))
    audit.record(operator(request), '開始訓練', 'run', run_id)
    return {'job_id': job_id}


@router.post('/training/runs/{run_id}/evaluate')
def evaluate_run(run_id: str, request: Request):
    result = evaluation.evaluate_oof(run_id, operator(request))
    audit.record(operator(request), '評估交叉驗證', 'run', run_id)
    return result


@router.get('/training/learning-curve')
def learning_curve(split_id: str | None = None):
    return runs.learning_curve(split_id)


@router.get('/training/compare')
def compare_runs(a: str, b: str):
    return evaluation.compare(a, b)


class NnunetIn(BaseModel):
    dataset_version_id: str
    split_id: str
    epochs: str = Field(default='250', pattern='^(100|250|1000)$')


@router.post('/training/nnunet', status_code=202)
def start_nnunet(payload: NnunetIn, request: Request):
    from ...ml import nnunet

    result = nnunet.start(payload.dataset_version_id, payload.split_id, payload.epochs, operator(request))
    audit.record(operator(request), '開始 nnU-Net 基準訓練', 'run', result['id'])
    return result


# ---- 實驗 ----
class ExperimentIn(BaseModel):
    name: str = Field(default='', max_length=120)
    template: str = Field(pattern='^(init|ablation|custom)$')
    task: str
    dataset_version_id: str
    split_id: str
    base_config: dict[str, Any] = Field(default_factory=dict)
    feature_set_id: str | None = None
    note: str = Field(default='', max_length=400)


@router.get('/experiments')
def list_experiments(task: str):
    # eGFR 的比較組在 /api/egfr/comparisons；這裡依任務列出分割與回音分級的實驗（決策 D28）
    return {'experiments': [e for e in experiments.list_experiments() if e['config'].get('task') == task and e['template'] != 'egfr_compare']}


@router.post('/experiments', status_code=201)
def create_experiment(payload: ExperimentIn, request: Request):
    result = experiments.create(payload.name, payload.template, payload.task, payload.dataset_version_id, payload.split_id, payload.base_config, payload.feature_set_id, payload.note, operator(request))
    audit.record(operator(request), '建立實驗', 'experiment', result['id'], {'template': payload.template, 'runs': len(result['runs'])})
    return result


@router.get('/experiments/{exp_id}')
def experiment_detail(exp_id: str):
    return experiments.detail(exp_id)


@router.post('/experiments/{exp_id}/start', status_code=202)
def start_experiment(exp_id: str, request: Request):
    result = experiments.start_all(exp_id, operator(request))
    audit.record(operator(request), '開始實驗', 'experiment', exp_id, {'jobs': len(result['jobs'])})
    return result


# ---- 模型庫 ----
class RegisterIn(BaseModel):
    run_id: str
    name: str
    version: str = '1.0.0'
    note: str = Field(default='', max_length=400)


@router.get('/models')
def list_models(task: str):
    return {'models': registry.list_models(task)}


@router.post('/models', status_code=201)
def register_model(payload: RegisterIn, request: Request):
    result = registry.register(payload.run_id, payload.name, payload.version, payload.note, operator(request))
    audit.record(operator(request), '註冊模型', 'model', result['id'])
    return result


@router.get('/models/{model_id:path}/test-readiness')
def test_readiness(model_id: str):
    return evaluation.test_readiness(model_id)


class TestIn(BaseModel):
    confirm: str


@router.post('/models/{model_id:path}/test', status_code=202)
def evaluate_test(model_id: str, payload: TestIn, request: Request):
    result = evaluation.start_test(model_id, payload.confirm, operator(request))
    audit.record(operator(request), '固定測試集評估', 'model', model_id)
    return result


class StageIn(BaseModel):
    stage: str = Field(pattern='^(research|candidate|clinical|retired)$')
    confirm_name: str = ''
    approver: str = ''


@router.post('/models/{model_id:path}/stage')
def set_stage(model_id: str, payload: StageIn, request: Request):
    result = registry.set_stage(model_id, payload.stage, operator(request), payload.confirm_name, payload.approver)
    audit.record(operator(request), '變更模型階段', 'model', model_id, {'stage': payload.stage, 'approver': payload.approver})
    return result


@router.get('/models/{model_id:path}')
def model_detail(model_id: str):
    return {**registry.detail(model_id), 'evaluations': evaluation.list_evaluations(model_id=model_id)}


@router.get('/evaluations')
def list_evaluations(model_id: str | None = None, run_id: str | None = None):
    return {'evaluations': evaluation.list_evaluations(model_id, run_id)}


# ---- 特徵 ----
class FeatureIn(BaseModel):
    source: str = Field(pattern='^(masks|run|mask_set)$')
    run_id: str | None = None
    mask_set_id: str | None = None
    note: str = Field(default='', max_length=200)


@router.get('/features')
def list_feature_sets():
    return {'feature_sets': features.list_sets()}


@router.post('/features', status_code=201)
def create_feature_set(payload: FeatureIn, request: Request):
    result = features.create(payload.source, payload.run_id, payload.note, operator(request), mask_set_id=payload.mask_set_id)
    audit.record(operator(request), '擷取特徵', 'feature_set', result['id'], {'source': payload.source})
    return result


@router.get('/features/{fs_id}')
def feature_set(fs_id: str, limit: int = Query(200, ge=1, le=2000)):
    rows = features.read_table(fs_id)
    return {'rows': rows[:limit], 'total': len(rows), 'analysis': features.analyze(fs_id)}


@router.post('/features/{fs_id}/export')
def export_feature_set(fs_id: str, request: Request):
    result = features.export(fs_id)
    audit.record(operator(request), '匯出特徵集', 'feature_set', fs_id, result)
    return result


# ---- 一鍵流程／AI 分析 ----
class PipelineIn(BaseModel):
    seg_model_id: str = ''
    classifier_ids: list[str] = Field(default_factory=list)
    image_ids: list[str] | None = None


@router.post('/pipelines', status_code=202)
def start_pipeline(payload: PipelineIn, request: Request):
    result = pipeline.start(payload.seg_model_id, payload.classifier_ids, payload.image_ids, operator(request))
    audit.record(operator(request), '執行一鍵流程', 'job', result['job_id'], {'images': len(payload.image_ids) if payload.image_ids else 'all'})
    return result


@router.get('/pipelines/{job_id}')
def pipeline_results(job_id: str):
    return pipeline.results(job_id)


@router.get('/pipelines/{job_id}/masks/{image_id}')
def pipeline_mask(job_id: str, image_id: str):
    from fastapi.responses import Response

    return Response(pipeline.mask_overlay(job_id, image_id), media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})


# ---- 交叉預測遮罩組（M2.5，決策 D26）----
class MaskSetIn(BaseModel):
    seg_run_id: str
    note: str = Field(default='', max_length=200)


@router.get('/mask-sets')
def list_mask_sets():
    from ...ml import masksets

    return {'mask_sets': masksets.list_sets()}


@router.post('/mask-sets', status_code=202)
def create_mask_set(payload: MaskSetIn, request: Request):
    from ...ml import masksets

    result = masksets.create(payload.seg_run_id, payload.note, operator(request))
    audit.record(operator(request), '產生交叉預測遮罩組', 'mask_set', result['id'], {'seg_run_id': payload.seg_run_id})
    return result


@router.get('/mask-sets/{ms_id}')
def mask_set_detail(ms_id: str):
    from ...ml import masksets

    return masksets.coverage(ms_id)


@router.get('/mask-sets/{ms_id}/overlay/{image_id}')
def mask_set_overlay(ms_id: str, image_id: str):
    from fastapi.responses import Response

    from ...ml import masksets

    return Response(masksets.overlay_png(ms_id, image_id), media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})
