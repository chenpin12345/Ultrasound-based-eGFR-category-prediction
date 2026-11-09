"""索引（決策 D29）：在 03_資料/09_索引/ 產生 Excel 可直接開啟的 CSV，方便在檔案總管查找。

不含個資：病人只用 P-編號、eGFR 只寫分組；不寫原始檔名。
寫入失敗（例如檔案正在 Excel 中開啟）時略過該檔，下次再更新。
"""

from __future__ import annotations

import csv
import json
import logging
import threading
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.ids import now_iso
from ..data import storage
from ..db.models_research import (
    Evaluation,
    Image,
    MaskAnnotation,
    ModelEntry,
    Patient,
    Split,
    SplitEntry,
    TrainingRun,
)
from ..db.session import session_scope

logger = logging.getLogger(__name__)
_lock = threading.Lock()

TASK_NAMES = {'egfr': 'eGFR', 'segmentation': '分割', 'grade': '回音分級'}
SOURCE_NAMES = {
    'manual': '系統內人工', 'physician_upload': '醫師圈選上傳', 'edited_upload': '修改自醫師圈選',
    'legacy': '舊程式草稿', 'rule': '規則草稿', 'medsam': 'MedSAM 草稿', 'model': '模型草稿',
}


def _write(folder: Path, name: str, header: list[str], rows: list[list[Any]]) -> bool:
    tmp = folder / f'.{name}.tmp'
    try:
        with tmp.open('w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
        tmp.replace(folder / name)
        return True
    except OSError:
        tmp.unlink(missing_ok=True)
        return False


def _primary_split(db) -> str | None:
    from ..services.settings_store import get_all

    wanted = get_all().get('primary_split_id')
    q = db.query(Split).filter(Split.trashed_at.is_(None))
    if wanted and q.filter(Split.id == wanted).first():
        return wanted
    latest = q.order_by(Split.created_at.desc()).first()
    return latest.id if latest else None


def _score(summary: dict[str, Any]) -> str:
    oof = summary.get('oof') or {}
    for key in ('patient_auc_lt60', 'auc_lt60', 'auc', 'qwk', 'dice_mean', 'dice'):
        if isinstance(oof.get(key), (int, float)):
            return f'{key}={oof[key]:.3f}'
    mean = summary.get('mean_best_score')
    return f'mean_best={mean:.3f}' if isinstance(mean, (int, float)) else ''


def refresh() -> dict[str, Any]:
    """重新產生全部索引；回傳寫入與略過的檔名。"""
    from ..data.patients import egfr_group

    folder = get_settings().path('index')
    folder.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []

    def save(name: str, header: list[str], rows: list[list[Any]]) -> None:
        (written if _write(folder, name, header, rows) else skipped).append(name)

    with _lock, session_scope('research') as db:
        split_id = _primary_split(db)
        groups = dict(db.query(SplitEntry.patient_id, SplitEntry.group).filter(SplitEntry.split_id == split_id).all()) if split_id else {}
        patients = {p.id: p for p in db.query(Patient).all()}
        masks: dict[str, list[MaskAnnotation]] = {}
        for m in db.query(MaskAnnotation).filter(MaskAnnotation.trashed_at.is_(None)).order_by(MaskAnnotation.image_id, MaskAnnotation.version).all():
            masks.setdefault(m.image_id, []).append(m)
        circling = _circling_lookup(db)

        rows = []
        for i in db.query(Image).order_by(Image.id).all():
            p = patients.get(i.patient_id)
            physician = any(m.source in ('physician_upload', 'edited_upload') and m.status != 'rejected' for m in masks.get(i.id, []))
            rows.append([
                i.id, i.patient_id or '', egfr_group(p.egfr) if p else '', i.side or '', i.view or '', i.machine or '', i.batch_id or '',
                groups.get(i.patient_id, ''), circling.get(i.id, ''), '是' if physician else '', i.status,
                storage.image_path(i.id, 'model').relative_to(get_settings().root).as_posix(),
            ])
        save('影像索引.csv', ['影像ID', '病人', 'eGFR分組', '側別', '切面', '機型', '匯入批次', f'切分組別（{split_id or "無"}）', '醫師圈選批次', '有醫師遮罩', '狀態', '檔案位置'], rows)

        rows = []
        for image_id, items in sorted(masks.items()):
            for m in items:
                flags = json.loads(m.flags_json or '{}')
                verified = m.verified_by or (m.source in ('manual', 'physician_upload', 'edited_upload') and m.status in ('done', 'reviewed'))
                rows.append([image_id, m.version, SOURCE_NAMES.get(m.source, m.source), flags.get('circler', ''), m.status, '是' if verified else '', m.created_at, m.relpath])
        save('遮罩索引.csv', ['影像ID', '版本', '來源', '圈選者代號', '狀態', '已確認', '建立時間', '檔案位置'], rows)

        runs = db.query(TrainingRun).filter(TrainingRun.trashed_at.is_(None)).order_by(TrainingRun.created_at).all()
        for task, label in TASK_NAMES.items():
            rows = []
            for r in runs:
                if r.task != task:
                    continue
                cfg = json.loads(r.config_json or '{}')
                inputs = cfg.get('inputs') or (['image', 'measures'] if cfg.get('features') else ['image'])
                rows.append([r.id, r.name, cfg.get('egfr_classes', 2) if task == 'egfr' else '', '＋'.join(inputs) if task == 'egfr' else '',
                             cfg.get('arch', cfg.get('framework', '')), r.status, _score(json.loads(r.summary_json or '{}')), r.experiment_id or '', r.split_id, r.created_at, r.relpath])
            save(f'{label}訓練索引.csv', ['訓練ID', '名稱', '類別數', '輸入方式', '架構', '狀態', '主要成績（OOF）', '比較組／實驗', '切分', '建立時間', '資料夾'], rows)

        models = db.query(ModelEntry).filter(ModelEntry.trashed_at.is_(None)).order_by(ModelEntry.created_at).all()
        for task, label in TASK_NAMES.items():
            rows = [[m.id, m.stage, m.run_id, m.created_at, m.relpath] for m in models if m.task == task]
            save(f'{label}模型索引.csv', ['模型ID', '階段', '來源訓練', '註冊時間', '資料夾'], rows)

        run_tasks = {r.id: r.task for r in runs}
        rows = []
        hidden_models = {m.id for m in db.query(ModelEntry).filter(ModelEntry.trashed_at.isnot(None)).all()}
        for e in db.query(Evaluation).order_by(Evaluation.created_at).all():
            if (e.run_id and e.run_id not in run_tasks) or e.model_id in hidden_models:
                continue  # 訓練或模型在回收桶
            metrics = json.loads(e.metrics_json or '{}')
            task = metrics.get('task') or run_tasks.get(e.run_id, '')
            rows.append([e.id, TASK_NAMES.get(task, task), e.model_id or e.run_id or '', '固定測試集' if e.target == 'test' else '交叉驗證', _headline(metrics), e.created_at, e.relpath])
        save('評估索引.csv', ['評估ID', '任務', '對象', '目標', '主要成績', '建立時間', '資料夾'], rows)

        save('遮罩組索引.csv', ['遮罩組ID', '分割訓練', '切分', '張數', '找不到腎臟', '狀態', '資料夾'], _mask_set_rows(db))
        save('醫師圈選批次.csv', ['批次ID', '種類', '張數', '已匯出', '已傳回', '已匯入', '需重圈', '醫師判定不能用', '匯出日期', '含原始影像'], _circling_rows(db))

    save('病人表上傳.csv', ['病人表', '上傳時間', '大小（KB）'], _patient_tables())
    _write(folder, '更新時間.txt', ['索引更新時間'], [[now_iso()]])
    return {'written': written, 'skipped': skipped}


def _headline(metrics: dict[str, Any]) -> str:
    for level in ('patient', 'image'):
        block = metrics.get(level) or {}
        for key in ('auc_lt60', 'auc', 'qwk'):
            value = block.get(key)
            if isinstance(value, (int, float)):
                return f'{level} {key}={value:.3f}'
    dice = metrics.get('dice') or {}
    if isinstance(dice.get('mean'), (int, float)):
        return f'Dice={dice["mean"]:.3f}'
    return ''


def _circling_lookup(db) -> dict[str, str]:
    try:
        from ..db.models_research import CirclingItem
    except ImportError:
        return {}
    return {i.image_id: i.batch_id for i in db.query(CirclingItem).all()}


def _circling_rows(db) -> list[list[Any]]:
    try:
        from ..db.models_research import CirclingBatch, CirclingItem
    except ImportError:
        return []
    rows = []
    for b in db.query(CirclingBatch).order_by(CirclingBatch.created_at).all():
        items = db.query(CirclingItem).filter(CirclingItem.batch_id == b.id).all()
        count = lambda *s: sum(1 for i in items if i.status in s)  # noqa: E731
        rows.append([b.id, {'test': '測試集', 'train': '訓練', 'all': '全部影像'}.get(b.kind, b.kind), len(items),
                     count('exported', 'returned', 'parsed', 'imported', 'needs_redraw', 'unusable'), count('returned', 'parsed', 'imported', 'unusable'),
                     count('imported'), count('needs_redraw'), count('unusable'), (b.exported_at or '')[:10], '是' if b.include_original else ''])
    return rows


def _mask_set_rows(db) -> list[list[Any]]:
    try:
        from ..db.models_research import MaskSet
    except ImportError:
        return []
    rows = []
    for m in db.query(MaskSet).filter(MaskSet.trashed_at.is_(None)).order_by(MaskSet.created_at).all():
        spec = json.loads(m.spec_json or '{}')
        rows.append([m.id, m.seg_run_id, m.split_id, m.rows or 0, spec.get('no_kidney', ''), m.status, m.relpath])
    return rows


def _patient_tables() -> list[list[Any]]:
    from datetime import datetime

    folder = get_settings().path('raw_archive') / '病人表'
    if not folder.exists():
        return []
    rows = []
    for f in sorted(folder.glob('T-*')):
        stat = f.stat()
        rows.append([f.name, datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'), round(stat.st_size / 1024, 1)])
    return rows


def refresh_quietly(*_args: Any) -> None:
    """背景工作結束、匯入等之後呼叫；失敗只記錄，不影響主流程。"""
    try:
        refresh()
    except Exception:  # noqa: BLE001
        logger.warning('更新索引失敗', exc_info=True)


def after_job(job_id: str) -> None:
    """背景工作結束後：醫師端的工作只更新醫師端索引，不重建全部研究索引（M3-8）。"""
    from ..db.models_system import Job

    with session_scope('system') as db:
        job = db.get(Job, job_id)
        kind = job.kind if job else ''
    if kind.startswith('clinical_'):
        try:
            refresh_clinical()
        except Exception:  # noqa: BLE001
            logger.warning('更新醫師端索引失敗', exc_info=True)
    else:
        refresh_quietly()


def refresh_clinical_quietly() -> None:
    try:
        refresh_clinical()
    except Exception:  # noqa: BLE001
        logger.warning('更新醫師端索引失敗', exc_info=True)


def refresh_clinical() -> bool:
    """醫師端檢查.csv：病例代碼、檢查、狀態、腎長、eGFR P(<60)、報告；不寫姓名與病歷號。"""
    from ..clinical import workspace

    folder = get_settings().path('index')
    folder.mkdir(parents=True, exist_ok=True)
    rows = [[e['id'], e['case_code'], e['received_at'][:16].replace('T', ' '), e['status_label'], e['images'],
             '' if e['right_length_mm'] is None else e['right_length_mm'], '' if e['left_length_mm'] is None else e['left_length_mm'],
             '' if e['p_lt60'] is None else f"{e['p_lt60'] * 100:.0f}%", '是' if e['candidate'] else '', e['report_status'] or '']
            for e in workspace.list_exams()]
    with _lock:
        return _write(folder, '醫師端檢查.csv', ['檢查', '病例代碼', '收到時間', '狀態', '影像數', '右腎長(mm)', '左腎長(mm)', 'eGFR<60 機率', '候選模型', '報告'], rows)
