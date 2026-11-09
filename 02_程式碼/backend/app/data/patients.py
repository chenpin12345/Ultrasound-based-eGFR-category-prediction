"""病人對照（改寫自腎超新 services/patients.py）。

病人表（CSV／XLSX）提供病人資料與 eGFR。影像對到病人的方式：
1. 病人表有「影像檔名」欄 → 直接對應（未來收案建議用這種格式）。
2. 沒有檔名欄 → 用原始檔名前綴（就是 eGFR 數值）比對病人表的 eGFR；
   同一個 eGFR 有多位病人時，再用 OCR 讀到的年齡、性別區分；還是分不出來就列入人工確認。
這個模組與匯入模組是唯二可以讀原始檔名（source_map）的地方。對照完成後，原始檔名不再被使用。
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import next_sequential, now_iso, short_uid
from ..core.security import sanitize_filename
from ..db.models_research import Image, Patient, SourceMap
from ..db.models_system import Setting
from ..db.session import session_scope

ALIASES = {
    'source_ref': {'patient_id', 'patientid', '病人編號', '病患編號', 'id'},
    'sex': {'性別', 'sex', 'gender'},
    'age': {'年齡', '年紀', 'age'},
    'diabetes': {'是否有糖尿病', '是否糖尿病', '糖尿病', 'has_diabetes', 'diabetes', 'dm'},
    'fatty_liver': {'是否有脂肪肝', '脂肪肝', 'fatty_liver', 'has_fatty_liver'},
    'egfr': {'matched_egfr', 'egfr'},
    'date': {'matched_date', '日期', 'date', 'exam_date'},
    'filename': {'影像檔名', '檔名', 'image_name', 'filename', 'file'},
}
STATE_KEY = 'patient_match_state'


def tables_dir() -> Path:
    return get_settings().path('raw_archive') / '病人表'


def _norm_header(h: str) -> str:
    return re.sub(r'\s+', '', str(h or '')).lower()


def _map_headers(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, header in enumerate(headers):
        key = _norm_header(header)
        for field, names in ALIASES.items():
            if key in {_norm_header(n) for n in names} and field not in mapping:
                mapping[field] = index
    return mapping


def read_table(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    rows: list[list[Any]]
    if suffix == '.xlsx':
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    elif suffix == '.csv':
        raw = path.read_bytes()
        for encoding in ('utf-8-sig', 'utf-8', 'cp950'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise AppError(422, 'TABLE_ENCODING', '無法辨識病人表的文字編碼。')
        rows = list(csv.reader(io.StringIO(text)))
    else:
        raise AppError(422, 'TABLE_FORMAT', '病人表只支援 CSV 或 XLSX。')
    if not rows:
        raise AppError(422, 'TABLE_EMPTY', '病人表是空的。')
    mapping = _map_headers([str(h) if h is not None else '' for h in rows[0]])
    if 'egfr' not in mapping and 'filename' not in mapping:
        raise AppError(422, 'TABLE_COLUMNS', '病人表至少要有 eGFR 欄或影像檔名欄。')
    if 'egfr' not in mapping and 'source_ref' not in mapping:
        # 只有檔名、沒有病人編號也沒有 eGFR（例如舊訓練程式的 metadata.csv）：分不出哪些影像屬於同一位病人，
        # 若用年齡等欄位湊病人，會把同年齡的不同病人併成一人，造成切分洩漏
        raise AppError(422, 'TABLE_NO_PATIENT_KEY', '病人表需要「病人編號」欄或 eGFR 欄，才能分辨哪些影像屬於同一位病人。')
    out = []
    for raw_row in rows[1:]:
        if not any(v not in (None, '') for v in raw_row):
            continue
        rec = {field: (raw_row[i] if i < len(raw_row) else None) for field, i in mapping.items()}
        out.append(_clean(rec))
    return out


def _clean(rec: dict[str, Any]) -> dict[str, Any]:
    def num(v):
        try:
            return float(str(v).strip())
        except (TypeError, ValueError):
            return None

    def text(v) -> str:
        # 不能寫成 `v or ''`：Excel 的數字 0（例如「否」編成 0）會被當成空白
        out = '' if v is None else str(v).strip()
        return out[:-2] if out in ('0.0', '1.0') else out  # Excel 有時把 0／1 存成小數

    sex_raw = text(rec.get('sex')).upper()
    sex = {'男': 'M', 'M': 'M', '1': 'M', 'MALE': 'M', '女': 'F', 'F': 'F', '0': 'F', '2': 'F', 'FEMALE': 'F'}.get(sex_raw)
    yes_no = {'1': True, '是': True, 'Y': True, 'YES': True, 'TRUE': True, '有': True, '0': False, '否': False, 'N': False, 'NO': False, 'FALSE': False, '無': False}
    dm = yes_no.get(text(rec.get('diabetes')).upper())
    fatty = yes_no.get(text(rec.get('fatty_liver')).upper())
    age = num(rec.get('age'))
    date = rec.get('date')
    return {
        'source_ref': str(rec.get('source_ref') or '').strip(),
        'sex': sex,
        'age': int(age) if age is not None else None,
        'diabetes': dm,
        'fatty_liver': fatty,
        'egfr': num(rec.get('egfr')),
        'date': str(date)[:10] if date not in (None, '') else None,
        'filename': str(rec.get('filename') or '').strip() or None,
    }


def save_table(filename: str, content: bytes) -> dict[str, Any]:
    safe = sanitize_filename(filename)
    if Path(safe).suffix.lower() not in {'.csv', '.xlsx'}:
        raise AppError(422, 'TABLE_FORMAT', '病人表只支援 CSV 或 XLSX。')
    table_id = f'T-{short_uid()}'
    target = tables_dir() / f'{table_id}{Path(safe).suffix.lower()}'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    rows = read_table(target)
    return {'table_id': table_id, 'rows': len(rows), 'has_filename_column': any(r['filename'] for r in rows)}


def import_table_from_path(path: Path) -> dict[str, Any]:
    table_id = f'T-{short_uid()}'
    target = tables_dir() / f'{table_id}{path.suffix.lower()}'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    rows = read_table(target)
    return {'table_id': table_id, 'rows': len(rows), 'has_filename_column': any(r['filename'] for r in rows)}


def _table_path(table_id: str) -> Path:
    for suffix in ('.xlsx', '.csv'):
        p = tables_dir() / f'{table_id}{suffix}'
        if p.exists():
            return p
    raise AppError(404, 'TABLE_NOT_FOUND', '找不到這份病人表，請重新上傳。')


def _prefix(relpath: str) -> float | None:
    stem = Path(relpath).stem
    head = stem.rsplit('_', 1)[0]
    try:
        return float(head)
    except ValueError:
        return None


def _row_key(row: dict[str, Any]) -> str:
    return row['source_ref'] or f"egfr={row['egfr']}|age={row['age']}|sex={row['sex']}"


def compute_matches(table_id: str, batch_id: str | None = None) -> dict[str, Any]:
    """計算對照結果（不寫入）。回傳 assigned：影像→病人表列鍵；ambiguous：需人工確認的群組。

    batch_id：只對照這個批次的影像（匯入區資料夾附的病人表只用在自己那一批）。
    """
    rows = read_table(_table_path(table_id))
    by_key = {_row_key(r): r for r in rows}
    by_filename = {Path(r['filename']).name: _row_key(r) for r in rows if r['filename']}
    by_egfr: dict[float, list[str]] = defaultdict(list)
    for r in rows:
        if r['egfr'] is not None:
            by_egfr[round(r['egfr'], 2)].append(_row_key(r))

    assigned: dict[str, str] = {}
    ambiguous: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    with session_scope('research') as db:
        q = (
            db.query(Image.id, Image.ocr_age, Image.ocr_sex, SourceMap.original_relpath)
            .join(SourceMap, SourceMap.image_id == Image.id)
            .filter(Image.patient_id.is_(None), Image.status != 'excluded')
        )
        if batch_id:
            q = q.filter(Image.batch_id == batch_id)
        for image_id, ocr_age, ocr_sex, relpath in q.all():
            name = Path(relpath).name
            if name in by_filename:
                assigned[image_id] = by_filename[name]
                continue
            prefix = _prefix(relpath)
            candidates = by_egfr.get(round(prefix, 2), []) if prefix is not None else []
            if len(candidates) > 1 and ocr_age is not None:
                narrowed = [
                    k for k in candidates
                    if by_key[k]['age'] is not None and abs(by_key[k]['age'] - ocr_age) <= 1 and (by_key[k]['sex'] in (None, ocr_sex))
                ]
                if narrowed:
                    candidates = narrowed
            if len(candidates) == 1:
                assigned[image_id] = candidates[0]
            elif len(candidates) > 1:
                group = ambiguous.setdefault('|'.join(sorted(candidates)), {'candidates': sorted(candidates), 'image_ids': []})
                group['image_ids'].append(image_id)
            else:
                unmatched.append(image_id)
    candidates_view = {
        k: {'source_ref': r['source_ref'], 'sex': r['sex'], 'age': r['age'], 'diabetes': r['diabetes']}
        for k, r in by_key.items()
    }
    groups = [
        {
            'key': f'G{i + 1}',
            'image_ids': g['image_ids'],
            'candidates': [{'row_key': c, **candidates_view[c]} for c in g['candidates']],
        }
        for i, g in enumerate(ambiguous.values())
    ]
    return {'table_id': table_id, 'assigned': assigned, 'ambiguous': groups, 'unmatched': unmatched, 'rows': by_key}


def preview(table_id: str) -> dict[str, Any]:
    result = compute_matches(table_id)
    return {
        'table_id': table_id,
        'matched_images': len(result['assigned']),
        'matched_patients': len(set(result['assigned'].values())),
        'ambiguous_groups': len(result['ambiguous']),
        'ambiguous_images': sum(len(g['image_ids']) for g in result['ambiguous']),
        'unmatched_images': len(result['unmatched']),
    }


# 病人表欄位 → Patient 欄位：重新套用病人表時，只補空白，不覆蓋已有的值
BACKFILL = (('age', 'age'), ('diabetes', 'has_diabetes'), ('fatty_liver', 'has_fatty_liver'), ('date', 'egfr_date'))


def _backfill(patient: Patient, row: dict[str, Any]) -> bool:
    changed = False
    for col, attr in BACKFILL:
        if row.get(col) is not None and getattr(patient, attr) is None:
            setattr(patient, attr, row[col])
            changed = True
    return changed


def _ensure_patient(db, row: dict[str, Any]) -> str:
    ref = row['source_ref']
    existing = db.query(Patient).filter(Patient.source_ref == ref).one_or_none() if ref else None
    if existing is None and not ref:
        existing = (
            db.query(Patient)
            .filter(Patient.egfr == row['egfr'], Patient.age == row['age'], Patient.sex == row['sex'])
            .one_or_none()
        )
    if existing:
        _backfill(existing, row)
        return existing.id
    new_id = next_sequential('P-', [r[0] for r in db.query(Patient.id).all()])
    db.add(
        Patient(
            id=new_id,
            source_ref=ref,
            sex=row['sex'],
            age=row['age'],
            has_diabetes=row['diabetes'],
            has_fatty_liver=row.get('fatty_liver'),
            egfr=row['egfr'],
            egfr_date=row['date'],
            created_at=now_iso(),
        )
    )
    db.flush()
    return new_id


def apply(table_id: str, batch_id: str | None = None) -> dict[str, Any]:
    result = compute_matches(table_id, batch_id)
    rows = result['rows']
    with session_scope('research') as db:
        for image_id, key in result['assigned'].items():
            pid = _ensure_patient(db, rows[key])
            db.query(Image).filter(Image.id == image_id).update({'patient_id': pid})
        # 已對照過的病人：補上空白的欄位（之後才加入的「是否有脂肪肝」，或舊版讀不到的「年紀」、糖尿病 0）
        by_ref = {r['source_ref']: r for r in rows.values() if r['source_ref']}
        updated = sum(_backfill(p, by_ref[p.source_ref]) for p in db.query(Patient).filter(Patient.source_ref.in_(list(by_ref))).all())
    # 待確認清單會累積多份病人表的結果（例如 B0000 的病人表還沒確認完，又匯入一批新收案）；
    # 每組記住自己來自哪份表，人工確認時用那份表的資料建立病人
    groups = [{**g, 'key': f"{table_id}:{g['key']}", 'table_id': table_id} for g in result['ambiguous']]
    settled = set(result['assigned']) | {i for g in groups for i in g['image_ids']}
    with session_scope('system') as db:
        setting = db.get(Setting, STATE_KEY)
        old = json.loads(setting.value_json) if setting else {}
        kept = [
            {**g, 'table_id': g.get('table_id') or old.get('table_id'), 'image_ids': [i for i in g['image_ids'] if i not in settled]}
            for g in old.get('ambiguous', [])
        ]
        kept = [g for g in kept if g['image_ids']]
        in_kept = {i for g in kept for i in g['image_ids']}
        state = {
            'table_id': table_id,
            'ambiguous': kept + groups,
            'unmatched': sorted((set(old.get('unmatched', [])) | set(result['unmatched'])) - settled - in_kept),
            'updated_at': now_iso(),
        }
        setting = setting or Setting(key=STATE_KEY, value_json='{}', updated_at=now_iso())
        setting.value_json, setting.updated_at = json.dumps(state, ensure_ascii=False), now_iso()
        db.merge(setting)
    return {
        'matched_images': len(result['assigned']),
        'ambiguous_groups': len(result['ambiguous']),
        'unmatched_images': len(result['unmatched']),
        'updated_patients': updated,
    }


def review_state() -> dict[str, Any]:
    with session_scope('system') as db:
        setting = db.get(Setting, STATE_KEY)
        state = json.loads(setting.value_json) if setting else {'ambiguous': [], 'unmatched': []}
    with session_scope('research') as db:
        still = {row[0] for row in db.query(Image.id).filter(Image.patient_id.is_(None)).all()}
    state['ambiguous'] = [
        {**g, 'image_ids': [i for i in g['image_ids'] if i in still]} for g in state.get('ambiguous', [])
    ]
    state['ambiguous'] = [g for g in state['ambiguous'] if g['image_ids']]
    state['unmatched'] = [i for i in state.get('unmatched', []) if i in still]
    return state


def resolve(table_id: str, image_ids: list[str], row_key: str) -> str:
    rows = read_table(_table_path(table_id))
    by_key = {_row_key(r): r for r in rows}
    if row_key not in by_key:
        raise AppError(404, 'ROW_NOT_FOUND', '病人表裡找不到這位病人。')
    with session_scope('research') as db:
        pid = _ensure_patient(db, by_key[row_key])
        db.query(Image).filter(Image.id.in_(image_ids)).update({'patient_id': pid}, synchronize_session=False)
    return pid


# 切點來自 data/egfr.py（5 類 KDIGO）；標籤文字一字不改：切分用它當分層鍵與亂數種子，改字會讓切分結果不同
from .egfr import groups_upper_bounds  # noqa: E402

EGFR_GROUPS = list(zip(groups_upper_bounds(), ['eGFR <15', 'eGFR 15–29', 'eGFR 30–59', 'eGFR 60–89', 'eGFR ≥90']))


def egfr_group(egfr: float | None) -> str:
    if egfr is None:
        return '未知'
    for upper, label in EGFR_GROUPS:
        if egfr < upper:
            return label
    return '未知'


def list_patients() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        counts: dict[str, dict[str, int]] = defaultdict(lambda: {'images': 0, 'right': 0, 'left': 0})
        for pid, side in db.query(Image.patient_id, Image.side).filter(Image.patient_id.isnot(None), Image.status != 'excluded').all():
            counts[pid]['images'] += 1
            if side in ('right', 'left'):
                counts[pid][side] += 1
        return [
            {
                'id': p.id,
                'sex': p.sex,
                'age': p.age,
                'has_diabetes': p.has_diabetes,
                'has_fatty_liver': p.has_fatty_liver,
                'egfr_group': egfr_group(p.egfr),
                **counts[p.id],
            }
            for p in db.query(Patient).order_by(Patient.id).all()
        ]


# ---------- 重新比對待確認的組 ----------
from ..jobs.manager import JobContext, register  # noqa: E402


def _candidate_view(row: dict[str, Any]) -> dict[str, Any]:
    return {'source_ref': row['source_ref'], 'sex': row['sex'], 'age': row['age'], 'diabetes': row['diabetes']}


@register('rematch_patients', label='重新比對待確認的病人')
def rematch_job(ctx: JobContext) -> dict[str, Any]:
    """待確認的組重新比對：
    1. 用目前的讀取方式重新讀病人表（認得「年紀」、糖尿病 0 不會變成空白）。
    2. 標頭上的病歷號相同＝同一位病人：把組內影像分成「同一人」的小組（號碼只在記憶體中比較，不保存、不顯示）。
    3. 每個小組用 OCR 年齡與性別找唯一符合的候選病人；兩位候選、兩個小組時，一組確定後另一組用刪去法。
    分不出來的小組留給人工確認，每組只要決定一次。"""
    from .importer import header_number

    with session_scope('system') as db:
        setting = db.get(Setting, STATE_KEY)
        state = json.loads(setting.value_json) if setting else {'ambiguous': [], 'unmatched': []}
    groups = state.get('ambiguous', [])
    with session_scope('research') as db:
        unmatched = {r[0] for r in db.query(Image.id).filter(Image.patient_id.is_(None)).all()}
        info = {i.id: (i.ocr_age, i.ocr_sex) for i in db.query(Image).filter(Image.id.in_([x for g in groups for x in g['image_ids']])).all()}
    total = max(1, sum(len(g['image_ids']) for g in groups))
    done, counts, new_groups = 0, {'groups': len(groups), 'by_age': 0, 'by_elimination': 0, 'still_ambiguous_images': 0, 'still_ambiguous_groups': 0}, []
    for g in groups:
        table_id = g.get('table_id') or state.get('table_id')
        rows = {_row_key(r): r for r in read_table(_table_path(table_id))}
        cands = [c['row_key'] for c in g['candidates'] if c['row_key'] in rows]
        clusters: dict[str, list[str]] = defaultdict(list)
        for image_id in g['image_ids']:
            ctx.check_stop()
            done += 1
            ctx.progress(done / total * 100, f'{done}／{total}')
            if image_id not in unmatched:
                continue
            key = header_number(image_id)
            clusters[f'n:{key}' if key else f'single:{image_id}'].append(image_id)
        if not clusters:
            continue

        def fits(ids: list[str]) -> list[str]:
            ages = {info[i][0] for i in ids if info[i][0] is not None}
            sexes = {info[i][1] for i in ids if info[i][1]}
            if len(ages) != 1:
                return []
            age = next(iter(ages))
            return [k for k in cands if rows[k]['age'] is not None and abs(rows[k]['age'] - age) <= 1 and (not sexes or rows[k]['sex'] in sexes)]

        assigned: dict[str, tuple[str, str]] = {}
        for key, ids in clusters.items():
            fit = fits(ids)
            if len(fit) == 1:
                assigned[key] = (fit[0], 'age')
        used = [k for k, _ in assigned.values()]
        if len(used) != len(set(used)):  # 兩組對到同一人：不自動分配
            assigned = {}
        real = [k for k in clusters if k.startswith('n:')]
        left = [k for k in real if k not in assigned]
        free = [c for c in cands if c not in {v[0] for v in assigned.values()}]
        if len(real) == len(clusters) == len(cands) and len(left) == 1 and len(free) == 1:
            # 不同號碼＝不同人：其他人都確定了，剩下的一組就是最後一位（年齡不能矛盾）
            ids = clusters[left[0]]
            has_age = any(info[i][0] is not None for i in ids)
            if free[0] in fits(ids) or not has_age:
                assigned[left[0]] = (free[0], 'elimination')
        with session_scope('research') as db:
            for key, (row_key, how) in assigned.items():
                pid = _ensure_patient(db, rows[row_key])
                db.query(Image).filter(Image.id.in_(clusters[key])).update({'patient_id': pid}, synchronize_session=False)
                counts['by_age' if how == 'age' else 'by_elimination'] += len(clusters[key])
        for n, (key, ids) in enumerate((k, v) for k, v in clusters.items() if k not in assigned):
            note = f'這 {len(ids)} 張影像標頭的病歷號相同，是同一位病人' if key.startswith('n:') else '讀不到標頭的病歷號'
            new_groups.append({'key': f'{table_id}:{g["key"]}:{n}', 'table_id': table_id, 'image_ids': ids, 'note': note,
                               'candidates': [{'row_key': c, **_candidate_view(rows[c])} for c in cands]})
            counts['still_ambiguous_images'] += len(ids)
    counts['still_ambiguous_groups'] = len(new_groups)
    with session_scope('system') as db:
        setting = db.get(Setting, STATE_KEY)
        state['ambiguous'], state['updated_at'] = new_groups, now_iso()
        setting.value_json, setting.updated_at = json.dumps(state, ensure_ascii=False), now_iso()
    return counts
