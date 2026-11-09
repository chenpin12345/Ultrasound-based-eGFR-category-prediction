"""示範影像包（D43、M3-1）：給雙機展示用的去識別化影像與示範清單。

- 只從主要切分的**測試集**病人挑選（訓練、驗證用過的影像不能拿來展示），每位病人每側 1 張。
- 影像是研究端已去識別化、通過殘留檢查的影像；原始檔不會被複製。
- 示範清單.json：檔名、病例代碼（DEMO-01…，不是 P-編號）、側別、像素間距、年齡、性別、糖尿病；不含 eGFR、姓名、病歷號。
- 使用前要先確認醫院同意用去識別化影像展示。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..data import storage
from ..db.models_research import Image, Patient, SplitEntry
from ..db.session import session_scope


def build(max_patients: int = 6) -> dict[str, Any]:
    from ..annotation.circling import primary_split_id

    split_id = primary_split_id()  # 設定的主切分；沒設定時用最新的切分（和其他頁面一致）
    max_patients = max(1, min(int(max_patients), 30))
    with session_scope('research') as db:
        test_ids = sorted(p for (p,) in db.query(SplitEntry.patient_id).filter(SplitEntry.split_id == split_id, SplitEntry.group == 'test').all())
        patients = {p.id: p for p in db.query(Patient).filter(Patient.id.in_(test_ids)).all()}
        images = db.query(Image).filter(Image.patient_id.in_(test_ids), Image.status == 'usable', Image.deid_check != 'residual',
                                        Image.side.in_(('right', 'left')), Image.pixel_spacing_mm.isnot(None)).order_by(Image.id).all()
        chosen: dict[str, dict[str, Image]] = {}
        for img in images:
            per = chosen.setdefault(img.patient_id, {})
            best = per.get(img.side)
            # 偏好長軸切面、超音波師有量腎長的那張
            score = (img.view == 'long', img.sonographer_length_mm is not None)
            if best is None or score > (best.view == 'long', best.sonographer_length_mm is not None):
                per[img.side] = img
        picked = [pid for pid in test_ids if len(chosen.get(pid, {})) == 2][:max_patients]
        if not picked:
            raise AppError(409, 'NO_DEMO_IMAGES', '主要切分的測試集裡沒有左右兩側都有可用影像（含像素間距）的病人。')
        folder = get_settings().path('exports') / f'示範影像包_{datetime.now():%Y%m%d-%H%M%S}'
        folder.mkdir(parents=True, exist_ok=False)
        items = []
        for n, pid in enumerate(picked, start=1):
            p = patients[pid]
            code = f'DEMO-{n:02d}'
            for side in ('right', 'left'):
                img = chosen[pid][side]
                name = f'{code}_{"R" if side == "right" else "L"}.png'
                shutil.copyfile(storage.image_path(img.id, 'model'), folder / name)
                items.append({'file': name, 'case_code': code, 'side': side, 'pixel_spacing_mm': img.pixel_spacing_mm,
                              'age': p.age, 'sex': p.sex, 'diabetes': {True: 'yes', False: 'no'}.get(p.has_diabetes, 'unknown')})
    (folder / '示範清單.json').write_text(json.dumps({'version': 1, 'split_id': split_id, 'note': '去識別化測試集影像；不含 eGFR、姓名、病歷號。', 'items': items},
                                                ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / '說明.txt').write_text('雙機展示用的示範影像包。\n'
                                     '1. 把整個資料夾複製到 A 電腦。\n'
                                     '2. 在 A 電腦打開 B 電腦畫面上的網址，輸入配對碼。\n'
                                     '3. 先匯入「示範清單.json」，再把 PNG 拖進傳送頁，按「傳送」。\n'
                                     '影像都已去識別化，只來自測試集；使用前請先確認醫院同意用去識別化影像展示。\n', encoding='utf-8')
    return {'folder': folder.relative_to(get_settings().root).as_posix(), 'patients': len(picked), 'images': len(items), 'split_id': split_id}
