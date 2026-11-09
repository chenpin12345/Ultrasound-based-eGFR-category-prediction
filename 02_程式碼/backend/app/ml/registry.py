"""模型庫：註冊、合約 v3（仍接受 v2）、模型卡、階段升級、推論。

- 註冊時複製各折最佳模型（推論時平均＝集成）、寫 manifest.json 與 model_card.md，之後檔案不可修改（附 sha256）。
- 推論前檢查合約：版本、任務、檔案雜湊、需要的特徵；不符就拒絕，不會默默用錯模型。
- 階段：research（研究）→ candidate（候選）→ clinical（臨床上線）→ retired（退役）。
  升級為臨床上線要輸入模型名稱確認，並從醫師名單選擇核准醫師；同任務原本的臨床模型改回候選。
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import now_iso
from ..db.models_research import ModelEntry, TrainingRun
from ..db.models_system import Person
from ..db.session import session_scope
from . import data as mldata
from .medsam import sha256_file

CONTRACT_VERSION = 3
ACCEPTED_CONTRACTS = (2, 3)  # v3（M2.5）：eGFR 類別數、輸入方式、臨床欄位、遮罩來源；v2 的模型仍可使用
STAGES = ('research', 'candidate', 'clinical', 'retired')
STAGE_LABELS = {'research': '研究', 'candidate': '候選', 'clinical': '臨床上線', 'retired': '退役'}
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,40}$')


from .paths import model_dir  # noqa: E402,F401  02_模型庫/{eGFR|分割|回音分級}/{名稱}@{版本}


def register(run_id: str, name: str, version: str, note: str, operator: str) -> dict[str, Any]:
    from .defaults import full_config
    from .runs import run_dir

    if not NAME_RE.match(name):
        raise AppError(422, 'BAD_NAME', '模型名稱只能用小寫英文、數字與連字號（例如 hybrid-corn）。')
    if not VERSION_RE.match(version):
        raise AppError(422, 'BAD_VERSION', '版本格式為 主.次.修（例如 1.0.0）。')
    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        if run is None or run.trashed_at or run.status != 'completed':
            raise AppError(409, 'RUN_NOT_COMPLETED', '只能註冊已完成、不在回收桶的訓練。')
        model_id = f'{run.task}/{name}@{version}'
        if db.get(ModelEntry, model_id):
            raise AppError(409, 'MODEL_EXISTS', '這個名稱與版本已經註冊過，請用新的版本號。')
        task, config, summary = run.task, json.loads(run.config_json), json.loads(run.summary_json or '{}')
        if config.get('arch') == 'logreg':
            raise AppError(409, 'BASELINE_NOT_REGISTRABLE', '純臨床或純量測的基準模型只用來比較，不能註冊成模型。')
        dataset_version_id, split_id = run.dataset_version_id, run.split_id
    cfg = full_config(task, config)
    source = run_dir(run_id)
    folds = [f for f in sorted(p.name for p in source.glob('fold-*')) if (source / f / 'best.pth').exists()]
    if not folds:
        raise AppError(409, 'NO_CHECKPOINT', '這個訓練沒有任何一折的最佳模型。')
    target = model_dir(task, name, version)
    target.mkdir(parents=True, exist_ok=False)
    files = {}
    for f in folds:
        dst = target / f'{f}.pth'
        shutil.copy2(source / f / 'best.pth', dst)
        files[dst.name] = sha256_file(dst)
    manifest = {
        'contract_version': CONTRACT_VERSION,
        'id': model_id,
        'task': task,
        'name': name,
        'version': version,
        'classes': mldata.task_classes(task, cfg),
        'input': _with_measures_source(_input_spec(cfg, run_id), cfg),
        'architecture': {'arch': cfg['arch'], 'head': cfg.get('head'), 'init': cfg['init']},
        'features': ({**(cfg.get('features') or {}), **summary['feature_stats']} if summary.get('feature_stats') else None),
        'inputs': cfg.get('inputs'),
        'egfr': {'classes': len(mldata.task_classes(task, cfg)), 'cuts': list(_egfr_cuts(len(mldata.task_classes(task, cfg))))} if task == 'egfr' else None,
        'temperature': summary.get('temperature', 1.0),
        'ensemble': files,
        'training': {'run_id': run_id, 'dataset_version_id': dataset_version_id, 'split_id': split_id, 'config': cfg},
        'metrics': {'oof': summary.get('oof'), 'mean_best_score': summary.get('mean_best_score'), 'folds': [{k: r.get(k) for k in ('fold', 'best_epoch', 'best_score')} for r in summary.get('folds', [])]},
        'intended_use': '研究用途；尚未經臨床驗證',
        'note': note,
        'created_at': now_iso(),
        'created_by': operator,
    }
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (target / 'model_card.md').write_text(model_card(manifest), encoding='utf-8')
    with session_scope('research') as db:
        db.add(
            ModelEntry(
                id=model_id, task=task, name=name, version=version, stage='research', run_id=run_id,
                relpath=target.relative_to(get_settings().root).as_posix(), manifest_json=json.dumps(manifest, ensure_ascii=False),
                stage_history_json=json.dumps([{'stage': 'research', 'by': operator, 'at': now_iso()}], ensure_ascii=False), created_by=operator, created_at=now_iso(),
            )
        )
    return {'id': model_id}


def _with_measures_source(spec: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """⑤ 遮罩量測：記下量測來自哪個特徵集、哪個分割訓練（M3：醫師端分析時檢查分割模型是否相符）。"""
    features = cfg.get('features') or {}
    if 'measures' not in (cfg.get('inputs') or []) or not features.get('feature_set_id'):
        return spec
    from ..db.models_research import FeatureSet, MaskSet

    seg_run_id = None
    with session_scope('research') as db:
        fs = db.get(FeatureSet, features['feature_set_id'])
        fspec = json.loads(fs.spec_json or '{}') if fs else {}
        if fspec.get('source') == 'run':
            seg_run_id = fspec.get('run_id')
        elif fspec.get('source') == 'mask_set' and fspec.get('mask_set_id'):
            ms = db.get(MaskSet, fspec['mask_set_id'])
            seg_run_id = ms.seg_run_id if ms else None
    return {**spec, 'measures_source': {'feature_set_id': features['feature_set_id'], 'source': fspec.get('source'), 'seg_run_id': seg_run_id}}


def _input_spec(cfg: dict[str, Any], run_id: str) -> dict[str, Any]:
    if 'mask_channels' in (cfg.get('inputs') or []):
        from .masksets import get
        from .roi import ROI_MM

        ms = get(cfg['mask_set_id'])
        return {'channels': 4, 'image': 'deid-model', 'img_size': cfg['img_size'], 'letterbox': False, 'init': cfg['init'], 'mode': 'mask_channels',
                'mask_channels': ['parenchyma', 'sinus', 'liver_or_spleen'], 'roi': {'mode': 'fixed_mm', 'mm': float(cfg.get('roi_mm', ROI_MM)), 'fallback': 'bbox_or_whole'},
                'mask_source': {'mask_set_id': ms['id'], 'seg_run_id': ms['seg_run_id'], 'postprocess': 'largest_component'}}
    return {'channels': 1, 'image': 'deid-model', 'img_size': cfg['img_size'], 'letterbox': True, 'init': cfg['init'], 'mode': 'image'}


def _egfr_cuts(k: int) -> tuple[int, ...]:
    from ..data.egfr import SCHEMES

    return SCHEMES[k]['cuts']


INPUT_NAMES = {'image': '影像', 'clinical': '臨床資料（年齡、性別、糖尿病）', 'measures': '遮罩量測（腎長、回音比、P 指數）', 'mask_channels': '遮罩通道（以腎臟為中心 160 mm 裁切）'}
ARCH_NAMES = {'resnet18': 'ResNet-18', 'resnet34': 'ResNet-34', 'unet': 'UNet', 'resnet34-unet': 'UNet＋ResNet-34 編碼器'}
HEAD_NAMES = {'binary': '二元', 'corn': 'CORN（有序）', 'coral': 'CORAL（有序）', 'sord': 'SORD（軟標籤）', 'ce': '一般 CE'}
METRIC_NAMES = {
    'n': '影像數', 'k': '類別數', 'auc_lt60': 'AUC（eGFR<60）', 'auc_lt30': 'AUC（eGFR<30）', 'auc': 'AUC', 'accuracy': '準確率',
    'sensitivity': '敏感度', 'specificity': '特異度', 'brier_lt60': 'Brier 分數（eGFR<60，越小越好）', 'ece_lt60': '校準誤差 ECE（eGFR<60，越小越好）',
    'brier': 'Brier 分數（越小越好）', 'ece': '校準誤差 ECE（越小越好）', 'qwk': 'QWK（有序一致性）', 'mae': '平均差幾類', 'macro_f1': 'Macro F1',
    'ece_before_calibration': '校準前的 ECE（對照用）', 'brier_before_calibration': '校準前的 Brier（對照用）',
    'dice_mean': '平均 Dice', 'dice_parenchyma': 'Dice（腎實質）', 'dice_sinus': 'Dice（腎竇）', 'dice_liver': 'Dice（肝）', 'dice_spleen': 'Dice（脾）',
}


def _feature_lines(features: dict[str, Any] | None) -> list[str]:
    if not features:
        return ['- 表格特徵：沒有（只用影像）']
    lines = []
    clinical = features.get('clinical')
    if clinical:
        sex = {0.0: '男', 1.0: '女'}.get(clinical.get('sex_mode'), '—')
        dm = {0.0: '無', 1.0: '有'}.get(clinical.get('diabetes_mode'), '—')
        lines.append(f'- 臨床資料：年齡（以訓練資料平均 {clinical.get("age_mean", 0):.1f} 歲、標準差 {clinical.get("age_std", 0):.1f} 標準化）、女性、糖尿病，'
                     f'各加一個「缺值」標記，共 6 欄；缺值時年齡補平均、性別補「{sex}」、糖尿病補「{dm}」（都只用訓練資料計算）')
    measures = features.get('measures') or (features if 'mean' in features and not clinical else None)
    if measures:
        lines.append(f'- 遮罩量測：{"、".join(measures.get("columns") or [])}（來自特徵集 {measures.get("feature_set_id", "—")}，以訓練資料標準化）')
    return lines or ['- 表格特徵：沒有（只用影像）']


def model_card(m: dict[str, Any]) -> str:
    """給人看的模型卡（M3 #116：原本直接印出 JSON 與英文代號）。"""
    oof = m['metrics'].get('oof') or {}
    arch = m['architecture']
    classes = m.get('classes') or []
    task = {'segmentation': '分割（腎實質、腎竇、肝、脾）', 'egfr': 'eGFR', 'grade': '回音分級'}.get(m['task'], m['task'])
    if m.get('egfr'):
        task += f'（{len(classes)} 類：{"／".join(classes)}）'
    shown = [(k, v) for k, v in oof.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
             and not (k in ('auc', 'brier', 'ece') and oof.get(f'{k}_lt60') == v)]  # 2 類時 AUC 與 AUC(<60) 相同，只列一次
    lines = [
        f'# 模型卡：{m["id"]}',
        '',
        '## 基本資料',
        '',
        f'- 任務：{task}',
        f'- 輸入：{"＋".join(INPUT_NAMES.get(i, i) for i in (m.get("inputs") or ["image"]))}',
        f'- 架構：{ARCH_NAMES.get(arch["arch"], arch["arch"])}；輸出層：{HEAD_NAMES.get(arch.get("head") or "", "—")}；初始化：{"ImageNet 預訓練" if arch["init"] == "imagenet" else "隨機"}',
        f'- 訓練：{m["training"]["run_id"]}（資料集版本 {m["training"]["dataset_version_id"]}、切分 {m["training"]["split_id"]}）',
        f'- 集成：{len(m["ensemble"])} 個模型（各折最佳 epoch），預測時取平均',
        *_feature_lines(m.get('features')),
        f'- 機率校準：溫度 {m["temperature"]:.3f}（大於 1 表示原始機率太極端，會往中間拉）',
        '',
        '## 交叉驗證成績（out-of-fold，影像層級）',
        '',
        *[f'- {METRIC_NAMES.get(k, k)}：{v:.3f}' if isinstance(v, float) else f'- {METRIC_NAMES.get(k, k)}：{v}' for k, v in shown],
        '',
        '## 使用限制',
        '',
        f'- {m["intended_use"]}。',
        '- 固定測試集的評估只能做一次，結果記在模型詳細頁。',
        '- 訓練資料來自單一院所的 Toshiba 與 Canon Aplio 300；其他機器或院所需重新驗證。',
        '- 所有病人皆無脂肪肝（收案條件）；用在有脂肪肝的病人時，皮質／肝比值可能失真。',
    ]
    return '\n'.join(lines) + '\n'


def _dict(m: ModelEntry) -> dict[str, Any]:
    manifest = json.loads(m.manifest_json)
    return {
        'id': m.id, 'task': m.task, 'name': m.name, 'version': m.version, 'stage': m.stage, 'stage_label': STAGE_LABELS[m.stage],
        'run_id': m.run_id, 'metrics': manifest.get('metrics'), 'architecture': manifest.get('architecture'), 'features': manifest.get('features'),
        'classes': manifest.get('classes'), 'egfr_classes': (manifest.get('egfr') or {}).get('classes'), 'inputs': manifest.get('inputs'),
        'created_by': m.created_by, 'created_at': m.created_at, 'stage_history': json.loads(m.stage_history_json),
    }


def list_models(task: str | None = None) -> list[dict[str, Any]]:
    with session_scope('research') as db:
        q = db.query(ModelEntry).filter(ModelEntry.trashed_at.is_(None))
        if task:
            q = q.filter(ModelEntry.task == task)
        return [_dict(m) for m in q.order_by(ModelEntry.created_at.desc()).all()]


def detail(model_id: str) -> dict[str, Any]:
    with session_scope('research') as db:
        m = db.get(ModelEntry, model_id)
        if m is None or m.trashed_at:
            raise AppError(404, 'MODEL_NOT_FOUND', '找不到這個模型（或已在回收桶）。')
        out = _dict(m)
        out['manifest'] = json.loads(m.manifest_json)
        card = get_settings().root / m.relpath / 'model_card.md'
    out['model_card'] = model_card(out['manifest'])  # 由 manifest 重新產生（模型卡不在雜湊檢查內），舊模型也會換成新格式
    try:
        if not card.exists() or card.read_text(encoding='utf-8') != out['model_card']:
            card.write_text(out['model_card'], encoding='utf-8')
    except OSError:
        pass
    return out


def set_stage(model_id: str, stage: str, operator: str, confirm_name: str = '', approver: str = '') -> dict[str, Any]:
    if stage not in STAGES:
        raise AppError(422, 'BAD_STAGE', '不支援的階段。')
    with session_scope('system') as db:
        physicians = {p.name for p in db.query(Person).filter(Person.kind == 'physician', Person.active.is_(True)).all()}
    with session_scope('research') as db:
        m = db.get(ModelEntry, model_id)
        if m is None or m.trashed_at:
            raise AppError(404, 'MODEL_NOT_FOUND', '找不到這個模型（或已在回收桶）。')
        if stage in ('research', 'retired'):
            from ..clinical.plan import ensure_not_referenced

            ensure_not_referenced([model_id], '改成「研究」或「退役」')
        if stage == 'clinical':
            if confirm_name.strip() != m.id:
                raise AppError(422, 'CONFIRM_MISMATCH', '確認文字與模型名稱不同，未升級。')
            if approver not in physicians:
                raise AppError(422, 'APPROVER_REQUIRED', '請從醫師名單選擇核准醫師。')
            for other in db.query(ModelEntry).filter(ModelEntry.task == m.task, ModelEntry.stage == 'clinical', ModelEntry.id != m.id).all():
                other.stage = 'candidate'
                hist = json.loads(other.stage_history_json)
                hist.append({'stage': 'candidate', 'by': operator, 'at': now_iso(), 'note': f'{m.id} 升級為臨床上線'})
                other.stage_history_json = json.dumps(hist, ensure_ascii=False)
        hist = json.loads(m.stage_history_json)
        hist.append({'stage': stage, 'by': operator, 'at': now_iso(), **({'approver': approver} if approver else {})})
        m.stage, m.stage_history_json = stage, json.dumps(hist, ensure_ascii=False)
        return {'id': m.id, 'stage': stage}


# ---------- 推論 ----------
class LoadedModel:
    def __init__(self, manifest: dict[str, Any], nets: list, device):
        self.manifest, self.nets, self.device = manifest, nets, device

    @property
    def task(self) -> str:
        return self.manifest['task']


def load(model_id: str, expect_task: str | None = None, *, device: str = 'auto') -> LoadedModel:
    import torch

    from .models import build_classifier, build_segmentation

    with session_scope('research') as db:
        m = db.get(ModelEntry, model_id)
        if m is None or m.trashed_at:
            raise AppError(404, 'MODEL_NOT_FOUND', '找不到這個模型（或已在回收桶）。')
        folder = get_settings().root / m.relpath
        registered = json.loads(m.manifest_json)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('contract_version') not in ACCEPTED_CONTRACTS:
        raise AppError(409, 'CONTRACT_MISMATCH', f'模型合約版本 {manifest.get("contract_version")} 和系統（{ACCEPTED_CONTRACTS}）不符，拒絕使用。')
    if expect_task and manifest['task'] != expect_task:
        raise AppError(409, 'CONTRACT_MISMATCH', f'這個步驟需要 {expect_task} 模型，但選的是 {manifest["task"]}。')
    if manifest.get('ensemble') != registered.get('ensemble'):  # 雜湊以註冊時存進資料庫的為準，只改硬碟上的 manifest 也會被發現（M3 #114）
        raise AppError(409, 'MODEL_TAMPERED', '模型資料夾的 manifest 和註冊時的紀錄不同，拒絕使用。')
    for file, digest in registered['ensemble'].items():
        if sha256_file(folder / file) != digest:
            raise AppError(409, 'MODEL_TAMPERED', f'模型檔 {file} 的雜湊和註冊時不同，拒絕使用。')
    dev = torch.device('cuda' if device == 'auto' and torch.cuda.is_available() else 'cpu' if device == 'auto' else device)
    arch = manifest['architecture']
    n_feat = len(manifest['features']['columns']) if manifest.get('features') else 0
    nets = []
    for file in manifest['ensemble']:
        if manifest['task'] == 'segmentation':
            net = build_segmentation(arch['arch'], 'random', mldata.NUM_SEG_CLASSES)  # 權重從檔案載入，不需要再下載 ImageNet
        else:
            net = build_classifier(arch['arch'], 'random', arch['head'], len(manifest['classes']), n_feat, int(manifest['input'].get('channels', 1)))
        net.load_state_dict(torch.load(folder / file, map_location=dev, weights_only=True)['model'])
        nets.append(net.to(dev).eval())
    return LoadedModel(manifest, nets, dev)


def predict_segmentation(model: LoadedModel, gray: np.ndarray) -> np.ndarray:
    import torch

    from . import augment

    size, init = model.manifest['input']['img_size'], model.manifest['input']['init']
    boxed, box = augment.letterbox(gray, size)
    x = torch.from_numpy(augment.to_tensor_array(boxed, init))[None].to(model.device)
    with torch.no_grad():
        prob = sum(torch.softmax(net(x).float(), 1) for net in model.nets) / len(model.nets)
    return augment.unletterbox(prob.argmax(1)[0].cpu().numpy().astype(np.uint8), box)


def standardize(model: LoadedModel, raw: dict[str, float | None], clinical: dict[str, Any] | None = None) -> list[float]:
    """用訓練時的統計值把表格特徵轉成模型的輸入：臨床資料（年齡標準化、女性、糖尿病與缺值標記）在前，遮罩量測在後。"""
    spec = model.manifest['features']
    out: list[float] = []
    if 'clinical' in spec:
        c, cs = clinical or {}, spec['clinical']
        sex = {'F': 1.0, 'M': 0.0}.get(str(c.get('sex') or '').upper())
        dm = None if c.get('has_diabetes') is None else float(bool(c.get('has_diabetes')))
        age = None if c.get('age') is None else float(c['age'])
        out += [((age if age is not None else cs['age_mean']) - cs['age_mean']) / (cs['age_std'] or 1.0), sex if sex is not None else cs['sex_mode'],
                dm if dm is not None else cs['diabetes_mode'], float(age is None), float(sex is None), float(dm is None)]
    measures = spec.get('measures') if ('clinical' in spec or 'measures' in spec) else spec  # v2 只有量測
    if measures:
        for col, mean, std in zip(measures['columns'], measures['mean'], measures['std']):
            v = raw.get(col)
            out.append(0.0 if v is None else (float(v) - mean) / (std or 1.0))
    return out


def predict_classification(model: LoadedModel, gray: np.ndarray, features: list[float] | None = None, label: np.ndarray | None = None, spacing: float | None = None) -> list[float]:
    import torch

    from . import augment, losses

    if model.manifest.get('features') and features is None:
        raise AppError(409, 'CONTRACT_MISMATCH', '這個模型需要表格特徵（臨床資料或腎長、灰階比等），但沒有提供。')
    spec = model.manifest['input']
    size, init = spec['img_size'], spec['init']
    if spec.get('mode') == 'mask_channels':
        from . import roi

        if label is None:
            raise AppError(409, 'CONTRACT_MISMATCH', '這個模型需要分割遮罩（影像＋遮罩通道），請同時選它使用的分割模型。')
        img, channels, _ = roi.prepare(gray, label, spacing, size, float(spec.get('roi', {}).get('mm', roi.ROI_MM)))
        arr = np.concatenate([augment.to_tensor_array(img, init), channels.astype(np.float32)], 0)
    else:
        boxed, _ = augment.letterbox(gray, size)
        arr = augment.to_tensor_array(boxed, init)
    x = torch.from_numpy(arr)[None].to(model.device)
    f = torch.tensor([features], dtype=torch.float32, device=model.device) if features is not None else None
    with torch.no_grad():
        probs = sum(losses.class_probs(model.manifest['architecture']['head'], net(x, f), model.manifest['temperature']) for net in model.nets) / len(model.nets)
    return [round(float(v), 5) for v in probs[0].cpu()]


def load_run(run_id: str, *, device: str = 'auto') -> LoadedModel:
    """直接用訓練資料夾的各折最佳模型（不必先註冊），給 eGFR 比較組一起評估固定測試集使用。"""
    import torch

    from .defaults import full_config
    from .models import build_classifier
    from .paths import run_dir

    with session_scope('research') as db:
        run = db.get(TrainingRun, run_id)
        if run is None or run.status != 'completed':
            raise AppError(409, 'RUN_NOT_COMPLETED', f'{run_id} 還沒有完成。')
        task, config, summary = run.task, json.loads(run.config_json), json.loads(run.summary_json or '{}')
    cfg = full_config(task, config)
    folder = run_dir(run_id)
    folds = [f for f in sorted(p.name for p in folder.glob('fold-*')) if (folder / f / 'best.pth').exists()]
    if not folds:
        raise AppError(409, 'NO_CHECKPOINT', f'{run_id} 沒有任何一折的最佳模型。')
    manifest = {'task': task, 'classes': mldata.task_classes(task, cfg), 'input': _input_spec(cfg, run_id), 'architecture': {'arch': cfg['arch'], 'head': cfg.get('head'), 'init': cfg['init']},
                'features': ({**(cfg.get('features') or {}), **summary['feature_stats']} if summary.get('feature_stats') else None), 'temperature': summary.get('temperature', 1.0),
                'inputs': cfg.get('inputs'), 'training': {'run_id': run_id, 'config': cfg}}
    dev = torch.device('cuda' if device == 'auto' and torch.cuda.is_available() else 'cpu' if device == 'auto' else device)
    n_feat = len(manifest['features']['columns']) if manifest.get('features') else 0
    nets = []
    for f in folds:
        net = build_classifier(cfg['arch'], 'random', cfg['head'], len(manifest['classes']), n_feat, int(manifest['input']['channels']))
        net.load_state_dict(torch.load(folder / f / 'best.pth', map_location=dev, weights_only=True)['model'])
        nets.append(net.to(dev).eval())
    return LoadedModel(manifest, nets, dev)
