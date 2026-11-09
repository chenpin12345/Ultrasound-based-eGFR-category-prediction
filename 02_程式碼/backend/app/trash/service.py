"""單一回收桶（取代腎超新的三區回收桶）。

刪除先移入回收桶（物件標記 trashed_at，清單不再顯示），可以還原；永久刪除才會移除資料列與檔案，
並一併移除變空的資料夾（不只刪畫面上的紀錄）。

訓練（M2.5 #109）：勾選的訓練與它們註冊的模型放在同一組；永久刪除時刪掉訓練資料夾、評估資料夾、
模型資料夾、分割的 OOF 預測遮罩，以及它們的評估紀錄。

醫師端檢查（M3-8）：用醫師端資料庫；已簽核的報告不能刪除，只能作廢（見 app/clinical/trash.py）。

2026-11-09 全面檢查後補強：
- 分割訓練連同它產生的遮罩組、特徵集一起移入與刪除（以前遮罩組會讓分割訓練永遠刪不掉）；
  用到這些遮罩組或特徵集的 eGFR 訓練要一起勾選；比較組的訓練全部移入時，比較組也一起移入；
- 永久刪除模型時，一併刪除用這些模型跑的一鍵流程結果；nnU-Net 的訓練器結果在沒有訓練使用時刪除；
- 切分、資料集版本還被遮罩組使用時不能刪；刪掉主切分時清除設定；刪掉醫師圈選匯入的遮罩時，圈選項目回到「待檢查」；
- 永久刪除前先確認每個檔案都能刪（沒有被其他程式開著），不會只刪掉資料庫或只刪掉一半的檔案；
  只刪物件自己的資料夾，絕不刪工作區或標準資料夾。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from ..core.errors import AppError
from ..core.ids import now_iso, short_uid
from ..core.config import get_settings
from ..data.storage import from_root
from ..services.workspace import remove_empty_dirs
from ..db.models_research import CirclingItem, DatasetVersion, Evaluation, Experiment, FeatureSet, MaskAnnotation, MaskSet, ModelEntry, Split, TrainingRun
from ..db.models_system import TrashGroup
from ..db.session import session_scope

KINDS: dict[str, tuple[Any, str]] = {
    'split': (Split, '資料切分'),
    'dataset_version': (DatasetVersion, '資料集版本'),
    'mask': (MaskAnnotation, '遮罩標註'),
    'run': (TrainingRun, '訓練'),
    'model': (ModelEntry, '模型'),
    'mask_set': (MaskSet, '遮罩組'),  # 跟著分割訓練
    'feature_set': (FeatureSet, '特徵集'),  # 跟著分割訓練或遮罩組
    'experiment': (Experiment, 'eGFR 比較組'),  # 比較組的訓練全部移入時
    'clinical_exam': (None, '醫師端檢查'),  # 醫師端資料庫（M3-8）
}
SINGLE_KINDS = ('split', 'dataset_version', 'mask')  # 訓練與模型用 move_runs_to_trash（要一起處理）


def move_to_trash(kind: str, object_id: str, reason: str, operator: str) -> dict[str, Any]:
    if kind == 'run':
        return move_runs_to_trash([object_id], reason, operator)
    if kind == 'clinical_exam':
        from ..clinical import trash as clinical_trash

        title = clinical_trash.move(object_id)
        return {'group_id': _add_group(kind, title, [{'kind': kind, 'id': object_id}], reason, operator)}
    if kind not in SINGLE_KINDS:
        raise AppError(422, 'BAD_KIND', '這類物件不能移入回收桶。')
    model, label = KINDS[kind]
    key = int(object_id) if kind == 'mask' else object_id
    with session_scope('research') as db:
        obj = db.get(model, key)
        if obj is None or obj.trashed_at:
            raise AppError(404, 'NOT_FOUND', '找不到這個物件，或已經在回收桶。')
        obj.trashed_at = now_iso()
        title = f'{label} {object_id}' if kind != 'mask' else f'遮罩 {obj.image_id} 第 {obj.version} 版'
    return {'group_id': _add_group(kind, title, [{'kind': kind, 'id': object_id}], reason, operator)}


def move_many_to_trash(kind: str, object_ids: list[str], title: str, reason: str, operator: str) -> dict[str, Any]:
    """多個物件放進同一組（例如重新產生草稿時的整批舊草稿），在回收桶一次還原。"""
    if kind not in SINGLE_KINDS:
        raise AppError(422, 'BAD_KIND', '這類物件不能移入回收桶。')
    model, _ = KINDS[kind]
    moved: list[str] = []
    with session_scope('research') as db:
        for object_id in object_ids:
            obj = db.get(model, int(object_id) if kind == 'mask' else object_id)
            if obj is not None and not obj.trashed_at:
                obj.trashed_at = now_iso()
                moved.append(str(object_id))
    if not moved:
        return {'group_id': None, 'moved': 0}
    return {'group_id': _add_group(kind, title, [{'kind': kind, 'id': i} for i in moved], reason, operator), 'moved': len(moved)}


def _dependents(db, run_ids: list[str]) -> tuple[list[MaskSet], list[FeatureSet], list[str]]:
    """分割訓練產生的遮罩組、從這些訓練或遮罩組擷取的特徵集，以及用到它們、但不在 run_ids 裡的訓練。"""
    if not run_ids:
        return [], [], []
    mask_sets = db.query(MaskSet).filter(MaskSet.seg_run_id.in_(run_ids)).all()
    ms_ids = {m.id for m in mask_sets}
    feature_sets = []
    for f in db.query(FeatureSet).all():
        spec = json.loads(f.spec_json or '{}')
        if (spec.get('source') == 'run' and spec.get('run_id') in run_ids) or (spec.get('mask_set_id') and spec['mask_set_id'] in ms_ids):
            feature_sets.append(f)
    fs_ids = {f.id for f in feature_sets}
    users = []
    for r in db.query(TrainingRun).filter(TrainingRun.id.notin_(run_ids)).all():
        cfg = json.loads(r.config_json or '{}')
        if cfg.get('mask_set_id') in ms_ids or (cfg.get('features') or {}).get('feature_set_id') in fs_ids:
            users.append(r)
    return mask_sets, feature_sets, [r.id for r in users]


def _experiment_runs(db, exp: Experiment) -> set[str]:
    """比較組的成員：設定裡的 members（包括沿用的訓練）加上 experiment_id 指向它的訓練。"""
    cfg = json.loads(exp.config_json or '{}')
    members = {m.get('run_id') for m in cfg.get('members') or [] if m.get('run_id')}
    return members | {r for (r,) in db.query(TrainingRun.id).filter(TrainingRun.experiment_id == exp.id).all()}


def _experiments_of(db, run_ids: list[str]) -> list[Experiment]:
    return [e for e in db.query(Experiment).all() if _experiment_runs(db, e) & set(run_ids)]


def move_runs_to_trash(run_ids: list[str], reason: str, operator: str) -> dict[str, Any]:
    """勾選的訓練移入回收桶（同一組）：註冊的模型、分割訓練產生的遮罩組與特徵集一起移入；
    比較組的訓練全部移入時比較組也一起。執行中、有臨床上線模型、被醫師端用到的不能刪；
    其他訓練用到這些遮罩組或特徵集時，要一起勾選。"""
    run_ids = list(dict.fromkeys(run_ids))
    if not run_ids:
        raise AppError(422, 'NOTHING_SELECTED', '請至少勾選一個訓練。')
    with session_scope('research') as db:
        runs = []
        for run_id in run_ids:
            r = db.get(TrainingRun, run_id)
            if r is None or r.trashed_at:
                raise AppError(404, 'RUN_NOT_FOUND', f'找不到 {run_id}，或已經在回收桶。')
            if r.status in ('queued', 'running'):
                raise AppError(409, 'RUN_ACTIVE', f'{run_id} 還在排隊或訓練中，請先到任務紀錄停止。')
            runs.append(r)
        models = db.query(ModelEntry).filter(ModelEntry.run_id.in_(run_ids), ModelEntry.trashed_at.is_(None)).all()
        from ..clinical.plan import ensure_not_referenced

        ensure_not_referenced([m.id for m in models], '移入回收桶')
        clinical = [m.id for m in models if m.stage == 'clinical']
        if clinical:
            raise AppError(409, 'MODEL_CLINICAL', f'{"、".join(clinical)} 是臨床上線的模型，請先在模型頁把階段改成退役或候選。')
        mask_sets, feature_sets, _ = _dependents(db, run_ids)
        live_users = []
        ms_ids, fs_ids = {m.id for m in mask_sets}, {f.id for f in feature_sets}
        for r in db.query(TrainingRun).filter(TrainingRun.id.notin_(run_ids), TrainingRun.trashed_at.is_(None)).all():
            cfg = json.loads(r.config_json or '{}')
            if cfg.get('mask_set_id') in ms_ids or (cfg.get('features') or {}).get('feature_set_id') in fs_ids:
                live_users.append(r.id)
        if live_users:
            raise AppError(409, 'RUN_IN_USE', f'訓練 {"、".join(live_users[:6])}{" 等" if len(live_users) > 6 else ""} 用了這個分割訓練產生的遮罩組或特徵集'
                                              f'（{"、".join(sorted(ms_ids | fs_ids))}），請一起勾選這些訓練再移入回收桶。')
        now = now_iso()
        mask_sets = [m for m in mask_sets if not m.trashed_at]
        feature_sets = [f for f in feature_sets if not f.trashed_at]
        for obj in [*runs, *models, *mask_sets, *feature_sets]:
            obj.trashed_at = now
        db.flush()
        experiments = []
        for exp in _experiments_of(db, run_ids):
            members = _experiment_runs(db, exp)
            left = db.query(TrainingRun).filter(TrainingRun.id.in_(members), TrainingRun.trashed_at.is_(None)).count()
            if not exp.trashed_at and left == 0:
                exp.trashed_at = now
                experiments.append(exp.id)
        model_ids = [m.id for m in models]
        first = runs[0]
    title = f'訓練 {first.id}・{first.name}' if len(runs) == 1 else f'訓練 {len(runs)} 個（{first.id} 等）'
    extras = [f'註冊的模型 {len(model_ids)} 個' if model_ids else '', f'遮罩組 {len(mask_sets)} 個' if mask_sets else '',
              f'特徵集 {len(feature_sets)} 個' if feature_sets else '', f'比較組 {"、".join(experiments)}' if experiments else '']
    if any(extras):
        title += '，含' + '、'.join(x for x in extras if x)
    entries = ([{'kind': 'run', 'id': i} for i in run_ids] + [{'kind': 'model', 'id': i} for i in model_ids]
               + [{'kind': 'mask_set', 'id': m.id} for m in mask_sets] + [{'kind': 'feature_set', 'id': f.id} for f in feature_sets]
               + [{'kind': 'experiment', 'id': i} for i in experiments])
    return {'group_id': _add_group('run', title, entries, reason, operator), 'runs': len(run_ids), 'models': model_ids,
            'mask_sets': [m.id for m in mask_sets], 'feature_sets': [f.id for f in feature_sets], 'experiments': experiments}


def _add_group(kind: str, title: str, entries: list[dict[str, Any]], reason: str, operator: str) -> str:
    group_id = f'TR-{short_uid()}'
    with session_scope('system') as db:
        db.add(TrashGroup(id=group_id, kind=kind, label=title, entries_json=json.dumps(entries), reason=reason, created_by=operator, created_at=now_iso()))
    return group_id


def list_groups(kind: str | None = None) -> list[dict[str, Any]]:
    with session_scope('system') as db:
        q = db.query(TrashGroup).filter(TrashGroup.state == 'trashed')
        if kind:
            q = q.filter(TrashGroup.kind == kind)
        return [
            {'id': g.id, 'kind': g.kind, 'kind_label': KINDS[g.kind][1], 'label': g.label, 'reason': g.reason, 'created_by': g.created_by, 'created_at': g.created_at}
            for g in q.order_by(TrashGroup.created_at.desc()).all()
        ]


def _entries(group_id: str) -> tuple[TrashGroup, list[dict[str, str]]]:
    with session_scope('system') as db:
        g = db.get(TrashGroup, group_id)
        if g is None or g.state != 'trashed':
            raise AppError(404, 'NOT_FOUND', '回收桶裡找不到這個項目。')
        return g, json.loads(g.entries_json)


def restore(group_id: str) -> None:
    _, entries = _entries(group_id)
    clinical = [e['id'] for e in entries if e['kind'] == 'clinical_exam']
    if clinical:
        from ..clinical import trash as clinical_trash

        clinical_trash.restore(clinical)
    with session_scope('research') as db:
        for e in entries:
            if e['kind'] == 'clinical_exam':
                continue
            model, _ = KINDS[e['kind']]
            obj = db.get(model, int(e['id']) if e['kind'] == 'mask' else e['id'])
            if obj is not None:
                obj.trashed_at = None
        db.flush()
        run_ids = [e['id'] for e in entries if e['kind'] == 'run']
        for exp in _experiments_of(db, run_ids):  # 比較組的訓練回來了：比較組也回來（可能在別的回收組被移入）
            exp.trashed_at = None
    _close(group_id, 'restored')


def purge(group_id: str) -> dict[str, Any]:
    """永久刪除資料列與檔案，並移除變空的資料夾。還有其他資料依賴、或有檔案被其他程式開著時拒絕（不會只刪一半）。"""
    _, entries = _entries(group_id)
    settings = get_settings()
    run_ids = [e['id'] for e in entries if e['kind'] == 'run']
    model_ids = [e['id'] for e in entries if e['kind'] == 'model']
    clinical = [e['id'] for e in entries if e['kind'] == 'clinical_exam']
    staged: list[tuple[Path, Path, Path]] = []
    if clinical:
        from ..clinical import trash as clinical_trash

        staged += clinical_trash.purge(clinical, _stage)
    cleared_primary = False
    with session_scope('research') as db:
        _check_references(db, entries, run_ids)
        folders: list[tuple[Path, Path]] = []  # (要刪的檔案或資料夾, 往上清空資料夾到哪裡為止；不刪標準資料夾)
        if run_ids or model_ids:
            folders += _purge_runs(db, run_ids, model_ids)
        for e in entries:
            if e['kind'] in ('run', 'model', 'clinical_exam', 'mask_set', 'feature_set', 'experiment'):
                continue  # 訓練相關的在 _purge_runs 處理
            model, _ = KINDS[e['kind']]
            obj = db.get(model, int(e['id']) if e['kind'] == 'mask' else e['id'])
            if obj is None:
                continue
            if e['kind'] == 'mask':
                if obj.relpath:
                    folders.append((from_root(obj.relpath), settings.path('annotations')))
                for item in db.query(CirclingItem).filter(CirclingItem.mask_id == obj.id).all():
                    # 醫師圈選匯入的遮罩被刪掉：項目回到「已轉換，待檢查」，可以重新匯入
                    parsed = item.parsed_relpath and from_root(item.parsed_relpath).exists()
                    item.mask_id, item.status = None, 'parsed' if parsed else 'exported'
            elif e['kind'] == 'split':
                folders.append((settings.path('splits') / f'{obj.id}.json', settings.path('splits')))
                cleared_primary = True
            elif e['kind'] == 'dataset_version':
                folders.append((settings.path('dataset_versions') / obj.id, settings.path('dataset_versions')))
            db.delete(obj)
        db.flush()
        staged += _stage(folders)  # 檔案被開著時在這裡停下，資料庫不會被改
    for _, tmp, stop in staged:
        _remove(tmp)
        remove_empty_dirs(tmp.parent, stop)  # 不留下空資料夾
    if cleared_primary:
        from ..services import settings_store

        split_ids = {e['id'] for e in entries if e['kind'] == 'split'}
        if settings_store.get_all().get('primary_split_id') in split_ids:
            settings_store.update({'primary_split_id': None})  # 主切分被刪掉：改回「最新的切分」
    _close(group_id, 'purged')
    return {'removed': [p.relative_to(settings.root).as_posix() for p, _, _ in staged if p.is_relative_to(settings.root)]}


def _check_references(db, entries: list[dict[str, str]], run_ids: list[str]) -> None:
    """還有其他資料依賴時不能永久刪除：切分、資料集版本還被訓練或遮罩組使用；
    分割訓練的遮罩組、特徵集還被其他訓練（包括回收桶裡其他組的）使用。"""
    for e in entries:
        if e['kind'] in ('split', 'dataset_version'):
            column = TrainingRun.split_id if e['kind'] == 'split' else TrainingRun.dataset_version_id
            users = [r.id for r in db.query(TrainingRun).filter(column == e['id']).all() if r.id not in run_ids]
            if users:
                raise AppError(409, 'IN_USE', f'{KINDS[e["kind"]][1]} {e["id"]} 還被訓練 {"、".join(users[:5])}{" 等" if len(users) > 5 else ""} 使用；請先永久刪除這些訓練，或還原這個項目。')
            ms_column = MaskSet.split_id if e['kind'] == 'split' else MaskSet.dataset_version_id
            sets = [m.id for m in db.query(MaskSet).filter(ms_column == e['id']).all() if m.seg_run_id not in run_ids]
            if sets:
                raise AppError(409, 'IN_USE', f'{KINDS[e["kind"]][1]} {e["id"]} 還被遮罩組 {"、".join(sets[:5])} 使用；請先刪除產生它們的分割訓練。')
    if run_ids:
        _, _, users = _dependents(db, run_ids)
        if users:
            raise AppError(409, 'RUN_IN_USE', f'訓練 {"、".join(users[:6])} 用了這些分割訓練產生的遮罩組或特徵集；請先永久刪除那些訓練（可能在回收桶的其他組），或還原。')


def _purge_runs(db, run_ids: list[str], model_ids: list[str]) -> list[tuple[Path, Path]]:
    """刪除訓練、模型與它們的評估、遮罩組、特徵集、一鍵流程結果、比較組（先刪子項目，外鍵才不會擋）；回傳要刪的資料夾。
    只刪每個物件自己的資料夾，保留 01_訓練紀錄/eGFR 這類標準資料夾（「開啟資料夾」按鈕會用到）。"""
    from ..db.models_system import Job
    from ..features.service import folder as feature_folder
    from ..ml.defaults import seg_output_dir
    from ..ml.masksets import folder as mask_set_folder
    from ..ml.pipeline import out_dir as pipeline_dir

    settings = get_settings()
    models = db.query(ModelEntry).filter((ModelEntry.id.in_(model_ids)) | (ModelEntry.run_id.in_(run_ids))).all()
    all_model_ids = [m.id for m in models]
    folders: list[tuple[Path, Path]] = []
    for ev in db.query(Evaluation).filter((Evaluation.run_id.in_(run_ids)) | (Evaluation.model_id.in_(all_model_ids))).all():
        if ev.relpath:
            folders.append(_own(settings.root / ev.relpath))
        db.delete(ev)
    db.flush()
    for m in models:
        if m.relpath:
            folders.append(_own(settings.root / m.relpath))
        db.delete(m)
    db.flush()
    if all_model_ids:  # 用這些模型跑的一鍵流程結果
        with session_scope('system') as sdb:
            for job in sdb.query(Job).filter(Job.kind == 'pipeline').all():
                cfg = json.loads(job.config_json or '{}')
                if cfg.get('seg_model_id') in all_model_ids or set(cfg.get('classifier_ids') or []) & set(all_model_ids):
                    folders.append(_own(pipeline_dir(job.id)))
    mask_sets, feature_sets, _ = _dependents(db, run_ids)
    for f in feature_sets:
        folders.append(_own(feature_folder(f.id)))
        db.delete(f)
    for m in mask_sets:
        folders.append(_own(mask_set_folder(m.id)))
        db.delete(m)
    db.flush()
    trainers = set()
    experiments = _experiments_of(db, run_ids)
    for run_id in run_ids:
        r = db.get(TrainingRun, run_id)
        if r is None:
            continue
        if r.relpath:
            folders.append(_own(settings.root / r.relpath))
        if r.task == 'segmentation':
            folders.append(_own(seg_output_dir(run_id)))  # OOF 預測遮罩
        cfg = json.loads(r.config_json or '{}')
        if cfg.get('framework') == 'nnunetv2':
            trainers.add(cfg.get('trainer'))
        db.delete(r)
    db.flush()
    for exp in experiments:  # 比較組的訓練都刪掉了：比較組也刪除
        if not db.query(TrainingRun).filter(TrainingRun.id.in_(_experiment_runs(db, exp))).count():
            db.delete(exp)
    if trainers:
        from ..ml.nnunet import DATASET_NAME, roots

        remaining = [json.loads(r.config_json or '{}') for r in db.query(TrainingRun).all()]
        remaining = [c.get('trainer') for c in remaining if c.get('framework') == 'nnunetv2']
        if not remaining:
            for base in roots().values():  # 最後一個 nnU-Net 訓練：一併刪除 nnU-Net 共用的資料集與結果
                folders.append(_own(base / DATASET_NAME))
        else:
            for trainer in trainers - set(remaining):  # 沒有其他訓練用這個訓練器：刪掉它的結果
                folders.append(_own(roots()['nnUNet_results'] / DATASET_NAME / f'{trainer}__nnUNetPlans__2d'))
    return folders


def _own(path: Path) -> tuple[Path, Path]:
    return path, path.parent  # 只刪這個資料夾本身


def _protected() -> set[Path]:
    """絕不能刪的位置：工作區本身、每個標準資料夾與它們的上層。"""
    settings = get_settings()
    out = {settings.root.resolve()}
    for value in settings.layout.values():
        if isinstance(value, Path):
            p = value.resolve()
            out.add(p)
            out.update(q for q in p.parents if settings.root.resolve() in q.parents or q == settings.root.resolve())
    return out


def _stage(folders: list[tuple[Path, Path]]) -> list[tuple[Path, Path, Path]]:
    """先把要刪的檔案、資料夾改名（確認沒有被其他程式開著），全部成功才回傳；任何一個失敗就全部改回來並停止。"""
    settings = get_settings()
    protected = _protected()
    staged: list[tuple[Path, Path, Path]] = []
    seen: set[Path] = set()
    try:
        for path, stop in folders:
            resolved = path.resolve()
            if resolved in seen or not path.exists():
                continue
            if resolved in protected or settings.root.resolve() not in resolved.parents:
                raise AppError(500, 'UNSAFE_DELETE', f'拒絕刪除 {path}：不是物件自己的資料夾。')
            seen.add(resolved)
            tmp = path.with_name(f'{path.name}.deleting-{short_uid()}')
            path.rename(tmp)
            staged.append((path, tmp, stop))
    except OSError as exc:
        for original, tmp, _ in reversed(staged):
            tmp.rename(original)
        name = getattr(exc, 'filename', '') or ''
        raise AppError(409, 'FILE_IN_USE', f'有檔案正在被其他程式使用（例如檔案總管、Excel、圖片檢視器或正在執行的工作）{"：" + Path(name).name if name else ""}；請關閉後再按「永久刪除」。什麼都沒有刪。') from None
    except AppError:
        for original, tmp, _ in reversed(staged):
            tmp.rename(original)
        raise
    return staged


def _remove(path: Path) -> None:
    if path.is_dir():
        def clear_readonly(func, target, _exc):
            os.chmod(target, stat.S_IWRITE)
            func(target)
        shutil.rmtree(path, onerror=clear_readonly)
    else:
        path.unlink(missing_ok=True)


def _close(group_id: str, state: str) -> None:
    with session_scope('system') as db:
        g = db.get(TrashGroup, group_id)
        g.state, g.closed_at = state, now_iso()
