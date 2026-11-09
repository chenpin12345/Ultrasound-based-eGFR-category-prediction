"""M2.5 eGFR 比較組：勾選輸入方式與類別數建立、比較格、兩兩比較、匯出（決策 D22–D24）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ...core import audit
from ...ml import egfr_compare
from ...services import index
from ..deps import operator

router = APIRouter(tags=['eGFR'])


@router.get('/egfr/options')
def options():
    return egfr_compare.options()


@router.get('/egfr/comparisons')
def list_comparisons():
    return {'comparisons': egfr_compare.list_groups()}


class ComparisonIn(BaseModel):
    name: str = Field(default='', max_length=120)
    dataset_version_id: str
    split_id: str
    inputs: list[str] = Field(min_length=1, max_length=6)
    classes: list[int] = Field(min_length=1, max_length=3)
    base_config: dict[str, Any] = Field(default_factory=dict)
    mask_set_id: str | None = None
    reuse: bool = True
    start: bool = True


@router.post('/egfr/comparisons', status_code=201)
def create_comparison(payload: ComparisonIn, request: Request):
    result = egfr_compare.create(payload.name, payload.dataset_version_id, payload.split_id, payload.inputs, payload.classes, payload.base_config,
                                 payload.mask_set_id, payload.reuse, payload.start, operator(request))
    audit.record(operator(request), '建立 eGFR 比較組', 'experiment', result['id'], {'inputs': payload.inputs, 'classes': payload.classes, 'reused': result['reused']})
    index.refresh_quietly()
    return result


@router.get('/egfr/comparisons/{exp_id}')
def comparison(exp_id: str):
    return egfr_compare.detail(exp_id)


@router.post('/egfr/comparisons/{exp_id}/start', status_code=202)
def start_comparison(exp_id: str, request: Request):
    result = egfr_compare.start_group(exp_id, operator(request))
    audit.record(operator(request), '開始 eGFR 比較組', 'experiment', exp_id, {'jobs': len(result['jobs'])})
    return result


@router.post('/egfr/comparisons/{exp_id}/export')
def export_comparison(exp_id: str, request: Request):
    result = egfr_compare.export(exp_id)
    audit.record(operator(request), '匯出 eGFR 比較', 'experiment', exp_id, result)
    return result


@router.get('/egfr/pairwise')
def pairwise(a: str, b: str, metric: str = 'auc_lt60'):
    return egfr_compare.pairwise(a, b, metric)


@router.get('/egfr/test-readiness')
def test_readiness(experiment_ids: str):
    return egfr_compare.test_readiness([e for e in experiment_ids.split(',') if e])


class TestIn(BaseModel):
    experiment_ids: list[str] = Field(min_length=1, max_length=20)
    confirm: str


@router.post('/egfr/test', status_code=202)
def start_test(payload: TestIn, request: Request):
    result = egfr_compare.start_test(payload.experiment_ids, payload.confirm, operator(request))
    audit.record(operator(request), 'eGFR 比較組一起評估固定測試集', 'experiment', '、'.join(payload.experiment_ids), {'job_id': result['job_id']})
    return result
