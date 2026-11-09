"""遮罩草稿：舊遮罩座標換算、多邊形轉換、腎竇分割、肝脾規則、MedSAM 流程（用替身）、人工確認。"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from tests import synthetic
from tests.conftest import wait_job


def _to_legacy(mask: np.ndarray) -> np.ndarray:
    """舊程式的作法：縮放成 1600×1200，再裁 (235, 90) 起的 1024×1024。"""
    big = cv2.resize(mask.astype(np.uint8) * 255, (1600, 1200), interpolation=cv2.INTER_NEAREST)
    return big[90:1114, 235:1259]


@pytest.mark.parametrize('size', [(622, 500), (1493, 1200), (1600, 1200), (666, 500)])
def test_legacy_mapping_roundtrip(size):
    from app.annotation.drafts import iou, legacy_to_original

    w, h = size
    truth = synthetic.kidney_mask(w, h, (w // 2, h // 2))
    back = legacy_to_original(_to_legacy(truth), w, h)
    assert iou(back, truth) > 0.95


def test_raster_to_shapes_roundtrip():
    from app.annotation.drafts import iou, raster_to_shapes
    from app.annotation.service import STRUCTURES, rasterize

    w, h = 622, 500
    label = np.zeros((h, w), np.uint8)
    cv2.rectangle(label, (20, 20), (200, 120), STRUCTURES['liver'], -1)
    kidney = synthetic.kidney_mask(w, h, (320, 260))
    label[kidney] = STRUCTURES['parenchyma']
    label[synthetic.kidney_mask(w, h, (320, 260), sinus=True)] = STRUCTURES['sinus']
    back = rasterize(raster_to_shapes(label), w, h)
    for value in (1, 2, 3):
        assert iou(back == value, label == value) > 0.93


def test_split_sinus_and_organ_rule():
    from app.annotation.drafts import iou, organ_draft, split_sinus

    img, truth = synthetic.toshiba(622, 500, 3)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    valid = np.ones(gray.shape, bool)
    kidney = synthetic.kidney_mask(622, 500, truth.kidney_center)
    sinus, _ = split_sinus(gray, valid, kidney)
    assert sinus is not None and iou(sinus, synthetic.kidney_mask(622, 500, truth.kidney_center, sinus=True)) > 0.4
    organ, info = organ_draft(gray, valid & (gray > 0), kidney, 0.38)
    assert organ is not None and not (organ & kidney).any()  # 肝脾區域不會和腎臟重疊
    assert 'reasons' in info and 'depth_overlap' in info


# ---- 依文獻改寫的腎內分層與肝脾規則（合成影像）----
W, H, C = 622, 500, (311, 250)


def _ellipse(center, axes, angle=0):
    m = np.zeros((H, W), np.uint8)
    cv2.ellipse(m, center, axes, angle, 0, 360, 1, -1)
    return m > 0


KIDNEY = _ellipse(C, (110, 60))
SINUS = _ellipse(C, (60, 22))
PELVIS = _ellipse((C[0] + 30, C[1]), (44, 16))  # 往右延伸到腎竇外緣：亮的腎竇不再是封閉的一圈
PYRAMIDS = np.zeros((H, W), bool)
for dx in (-35, 35):
    for dy in (-33, 33):
        PYRAMIDS |= _ellipse((C[0] + dx, C[1] + dy), (14, 7))


def _kidney_image(cortex=50, sinus=170, pelvis=False, pyramids=False, seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((H, W), 80.0)
    img[KIDNEY] = cortex
    if pyramids:
        img[PYRAMIDS] = 18
    img[SINUS] = sinus
    if pelvis:
        img[PELVIS] = 3  # 接近無回音
    img += rng.normal(0, 12, img.shape)
    return cv2.GaussianBlur(img.clip(0, 255).astype(np.uint8), (5, 5), 0)


def test_sinus_normal_and_pyramids_stay_in_parenchyma():
    from app.annotation.drafts import iou, split_sinus

    valid = np.ones((H, W), bool)
    sinus, info = split_sinus(_kidney_image(), valid, KIDNEY)
    assert sinus is not None and iou(sinus, SINUS) > 0.6 and not info['hydronephrosis']
    # 明顯的暗錐體：只用 Otsu 時閾值會落在「錐體 vs 皮質＋腎竇」，把皮質切進腎竇
    sinus, info = split_sinus(_kidney_image(pyramids=True), valid, KIDNEY)
    assert sinus is not None and iou(sinus, SINUS) > 0.6
    assert (sinus & PYRAMIDS).sum() < 0.1 * PYRAMIDS.sum()  # 錐體留在腎實質
    assert not info['hydronephrosis']


def test_sinus_includes_dilated_pelvis():
    from app.annotation.drafts import sinus_reasons, split_sinus

    sinus, info = split_sinus(_kidney_image(pelvis=True), np.ones((H, W), bool), KIDNEY)
    assert sinus is not None and info['hydronephrosis']
    assert (sinus & PELVIS).sum() > 0.8 * PELVIS.sum()  # 擴張的腎盂屬於腎竇
    assert '腎盂擴張' in sinus_reasons(sinus, info)[0]


def test_sinus_not_split_when_cortex_as_bright_as_sinus():
    from app.annotation.drafts import sinus_reasons, split_sinus

    sinus, info = split_sinus(_kidney_image(cortex=160, sinus=170), np.ones((H, W), bool), KIDNEY)
    assert sinus is None and info.get('cmd_lost')
    assert '無法自動分出腎竇' in sinus_reasons(sinus, info)[0]


def test_shadow_mask_needs_bright_reflector_above():
    from app.annotation.drafts import shadow_mask

    img = np.full((H, W), 80, np.uint8)
    img[60:70, 40:100] = 245  # 肋骨
    img[70:260, 40:100] = 8  # 正下方的聲影
    img[300:480, 450:520] = 8  # 一樣暗，但上方沒有強反射：不是聲影
    shadow = shadow_mask(img, np.ones((H, W), bool))
    assert shadow[100:250, 50:90].mean() > 0.9
    assert not shadow[300:480, 450:520].any()


def test_organ_rule_excludes_shadow_and_deep_side(monkeypatch):
    from app.annotation import drafts
    from app.annotation.drafts import organ_draft

    monkeypatch.setattr(drafts, 'DEEP_SIDE_RULE', True)  # 預設關閉，待人工確認後決定

    img = _kidney_image()
    img[C[1] + 60:, :] = 80  # 腎臟下方（深側）同樣均勻，也會被當成候選
    img[100:112, 60:130] = 245
    img[112:300, 60:130] = 8  # 肋骨聲影緊鄰腎臟頭側
    organ, info = organ_draft(img, np.ones((H, W), bool), KIDNEY, 0.3)
    assert organ is not None
    assert not organ[112:300, 70:120].any()  # 聲影不算器官
    deepest = np.nonzero(KIDNEY.any(axis=1))[0].max()
    assert not organ[int(deepest + 0.03 * H) + 2:].any()  # 不在腎臟深側
    monkeypatch.setattr(drafts, 'DEEP_SIDE_RULE', False)
    organ, _ = organ_draft(img, np.ones((H, W), bool), KIDNEY, 0.3)
    assert organ is not None and not organ[112:300, 70:120].any()  # 關閉位置規則時，聲影仍然排除


def test_kidney_checks_flags_shape_and_length():
    from app.annotation.drafts import kidney_checks

    gray = _kidney_image()
    ok, metrics = kidney_checks(gray, KIDNEY, 0.5)  # 長軸 220 px × 0.5 mm ≈ 11 cm
    assert ok == [] and 100 < metrics['length_mm'] < 120
    odd = KIDNEY.copy()
    odd[C[1] - 140:C[1] - 50, C[0] - 10:C[0] + 10] = True  # 突出去一大塊
    reasons, _ = kidney_checks(gray, odd, 1.0)
    assert any('形狀不規則' in r for r in reasons) and any('腎長' in r for r in reasons)


def test_draft_flow(imported_client, imported_template, workspace, monkeypatch):
    from app.ml import medsam

    template_root, names = imported_template
    legacy = workspace / 'legacy_masks'
    for name, truth in names:
        img = cv2.imdecode(np.fromfile(str(template_root / 'IMG_original' / name), np.uint8), cv2.IMREAD_GRAYSCALE)
        h, w = img.shape
        loose = cv2.dilate(synthetic.kidney_mask(w, h, truth.kidney_center).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0  # 舊遮罩偏鬆
        (legacy / name).with_suffix('.png').parent.mkdir(parents=True, exist_ok=True)
        cv2.imencode('.png', _to_legacy(loose))[1].tofile(str((legacy / name).with_suffix('.png')))

    job = imported_client.post('/api/annotation/drafts/legacy', json={'folder': str(legacy)}).json()['job_id']
    wait_job(job)
    result = imported_client.get(f'/api/jobs/{job}').json()
    assert result['status'] == 'completed' and result['result']['imported'] == len(names)
    legacy_items = imported_client.get('/api/annotation/drafts/queue').json()['items']
    assert any('sinus' in i['labeled'] for i in legacy_items)  # 舊遮罩匯入時已分出腎竇

    # MedSAM 替身：圈出框內的內切橢圓（不用載入真的權重）
    def fake(gray, boxes):
        prob = np.zeros(gray.shape, np.float32)
        x0, y0, x1, y1 = boxes[0]
        cv2.ellipse(prob, ((x0 + x1) // 2, (y0 + y1) // 2), (int((x1 - x0) * 0.42), int((y1 - y0) * 0.42)), 0, 0, 360, 1.0, -1)
        return prob

    monkeypatch.setattr(medsam, 'get_segmenter', lambda: fake)
    job = imported_client.post('/api/annotation/drafts/medsam').json()['job_id']
    wait_job(job)
    result = imported_client.get(f'/api/jobs/{job}').json()
    assert result['status'] == 'completed' and result['result']['drafted'] == len(names), result

    job = imported_client.post('/api/annotation/drafts/organs').json()['job_id']
    wait_job(job)
    assert imported_client.get(f'/api/jobs/{job}').json()['status'] == 'completed'

    queue = imported_client.get('/api/annotation/drafts/queue').json()
    assert queue['total'] == len(names)
    first, second = queue['items'][0], queue['items'][1]
    assert first['source'] in {'medsam', 'rule'} and 'iou_vs_legacy' in first
    assert imported_client.post(f'/api/annotation/drafts/{first["mask_id"]}/decision', json={'decision': 'accept'}).json()['status'] == 'reviewed'
    assert imported_client.post(f'/api/annotation/drafts/{second["mask_id"]}/decision', json={'decision': 'reject', 'reason': '邊界錯'}).json()['status'] == 'rejected'
    assert imported_client.get('/api/annotation/drafts/queue').json()['total'] == len(names) - 2

    stats = imported_client.get('/api/annotation/drafts/stats').json()['by_source']
    assert sum(s['accepted'] for s in stats.values()) == 1 and sum(s['rejected'] for s in stats.values()) == 1

    # 已經有人工確認的影像，重跑舊遮罩匯入不會再產生草稿
    job = imported_client.post('/api/annotation/drafts/legacy', json={'folder': str(legacy)}).json()['job_id']
    wait_job(job)
    assert imported_client.get(f'/api/jobs/{job}').json()['result']['imported'] == 0

    # 規則更新後重新產生：未確認的舊程式／肝脾草稿整批移入回收桶，再重做；人工確認過的影像不動
    regenerable = imported_client.get('/api/annotation/drafts/stats').json()['regenerable']
    assert regenerable > 0
    job = imported_client.post('/api/annotation/drafts/regenerate', json={'folder': str(legacy)}).json()['job_id']
    wait_job(job)
    result = imported_client.get(f'/api/jobs/{job}').json()
    assert result['status'] == 'completed', result
    assert result['result']['trashed'] == regenerable
    assert result['result']['legacy']['imported'] == len(names) - 1  # 接受過的那張不重做
    assert imported_client.get('/api/annotation/drafts/stats').json()['regenerable'] > 0  # 新草稿之後也能再重新產生
    stats = imported_client.get('/api/annotation/drafts/stats').json()['by_source']
    assert sum(s['accepted'] for s in stats.values()) == 1 and sum(s['rejected'] for s in stats.values()) == 1
    group = next(g for g in imported_client.get('/api/trash').json()['groups'] if g['id'] == result['result']['trash_group'])
    assert '舊規則' in group['label']
    assert imported_client.post(f"/api/trash/{group['id']}/restore").status_code == 200  # 一次還原整批

    # 被退回的草稿不算「標註完成」
    mask_task = next(t for t in imported_client.get('/api/annotation/tasks').json()['tasks'] if t['id'] == 'mask')
    assert mask_task['done'] == 1  # 只有接受的那一張

    # 依來源刪除草稿：待確認與退回的移入回收桶（每個來源一組），接受的保留
    before = imported_client.get('/api/annotation/drafts/stats').json()['by_source']
    r = imported_client.post('/api/annotation/drafts/delete', json={'sources': ['legacy', 'rule']}).json()
    assert r['moved'] > 0 and len(r['groups']) == 2
    after = imported_client.get('/api/annotation/drafts/stats').json()['by_source']
    assert sum(s['accepted'] for s in after.values()) == sum(s['accepted'] for s in before.values())
    empty = {'pending': 0, 'rejected': 0}
    assert all(after.get(k, empty)['pending'] == 0 and after.get(k, empty)['rejected'] == 0 for k in ('legacy', 'rule'))
    assert after['medsam']['pending'] == before['medsam']['pending']  # 沒勾選的來源不動
    assert imported_client.post('/api/annotation/drafts/delete', json={'sources': ['bogus']}).status_code == 422
