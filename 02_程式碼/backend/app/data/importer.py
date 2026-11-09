"""匯入：預覽 → 執行（背景工作）→ 報表。

- 來源「原始資料集」：IMG_original，登記為批次 B0000，只讀、不複製。
- 來源「匯入區」：06_匯入區/待匯入/{資料夾}。原始檔先複製到 01_原始封存/{批次}，
  成功後把匯入區資料夾移到「已完成」。
- 以 SHA-256 判斷重複，所以同一份資料重複匯入不會產生重複影像；中斷後重跑等於接續。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.ids import image_id as new_image_id
from ..core.ids import next_dated, now_iso
from ..core.security import IMAGE_EXTENSIONS, safe_resolve, sanitize_filename
from ..db.models_research import Batch, Image, LayoutTemplate, SourceMap
from ..db.session import session_scope
from ..jobs.manager import JobContext, register
from . import bodymark, deid, ocr, patients, storage
from .templates import template_dict

ORIGINAL_BATCH = 'B0000'
RULER_CHECKS = 10
TABLE_EXTENSIONS = {'.csv', '.xlsx'}


@dataclass
class SourceFile:
    path: Path
    relpath: str


def source_root(source: str, folder: str | None) -> Path:
    settings = get_settings()
    if source == 'original':
        root = settings.path('source_original')
        if not root.is_dir():
            raise AppError(404, 'SOURCE_NOT_FOUND', '找不到原始資料集資料夾（IMG_original）。')
        return root
    if source == 'inbox':
        if not folder:
            raise AppError(422, 'FOLDER_REQUIRED', '請選擇匯入區裡的資料夾。')
        root = safe_resolve(settings.path('inbox') / '待匯入', sanitize_filename(folder))
        if not root.is_dir():
            raise AppError(404, 'SOURCE_NOT_FOUND', '匯入區找不到這個資料夾。')
        return root
    raise AppError(422, 'UNKNOWN_SOURCE', '來源只能是原始資料集或匯入區。')


def list_files(root: Path) -> tuple[list[SourceFile], list[Path]]:
    images, tables = [], []
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            images.append(SourceFile(path, path.relative_to(root).as_posix()))
        elif suffix in TABLE_EXTENSIONS:
            tables.append(path)
    return images, tables


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _size_of(path: Path) -> tuple[int, int] | None:
    try:
        with PILImage.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


def preview(source: str, folder: str | None = None) -> dict[str, Any]:
    root = source_root(source, folder)
    files, tables = list_files(root)
    with session_scope('research') as db:
        known = {row[0] for row in db.query(Image.sha256).all()}
        templates = {(t.width, t.height): t for t in db.query(LayoutTemplate).all()}
        sizes: Counter = Counter()
        unknown_sizes: Counter = Counter()
        duplicates = unreadable = 0
        for f in files:
            if sha256_of(f.path) in known:
                duplicates += 1
                continue
            size = _size_of(f.path)
            if size is None:
                unreadable += 1
            elif size in templates:
                sizes[templates[size].id] += 1
            else:
                unknown_sizes[f'{size[0]} × {size[1]}'] += 1
        by_template = [
            {'template_id': t.id, 'machine': t.machine, 'size': f'{t.width} × {t.height}', 'count': sizes.get(t.id, 0)}
            for t in templates.values()
        ]
    return {
        'source': source,
        'folder': folder,
        'total': len(files),
        'new': sum(sizes.values()),
        'duplicates': duplicates,
        'unreadable': unreadable,
        'unknown_sizes': [{'size': k, 'count': v} for k, v in unknown_sizes.items()],
        'by_template': by_template,
        'patient_tables': [p.name for p in tables],
    }


def inbox_folders() -> list[dict[str, Any]]:
    root = get_settings().path('inbox') / '待匯入'
    out = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        files, tables = list_files(folder)
        out.append({'name': folder.name, 'images': len(files), 'tables': [t.name for t in tables]})
    return out


def original_status() -> dict[str, Any]:
    root = get_settings().path('source_original')
    with session_scope('research') as db:
        batch = db.get(Batch, ORIGINAL_BATCH)
        return {
            'exists': root.is_dir(),
            'imported': batch is not None and batch.status == 'completed',
            'batch_status': batch.status if batch else None,
        }


def start_import(manager, source: str, folder: str | None, operator: str, residual_check: bool = True) -> dict[str, str]:
    source_root(source, folder)  # 先驗證來源
    with session_scope('research') as db:
        if source == 'original':
            batch_id = ORIGINAL_BATCH
            batch = db.get(Batch, batch_id)
            if batch is None:
                db.add(Batch(id=batch_id, source_kind='original', source_label='IMG_original（初始資料集）', status='running', created_by=operator, created_at=now_iso()))
            else:
                batch.status = 'running'
        else:
            batch_id = next_dated('B', [row[0] for row in db.query(Batch.id).all()])
            db.add(Batch(id=batch_id, source_kind='inbox', source_label=folder or '', status='running', created_by=operator, created_at=now_iso()))
    job_id = manager.submit(
        'import',
        {'source': source, 'folder': folder, 'batch_id': batch_id, 'operator': operator, 'residual_check': residual_check},
        target=batch_id,
        created_by=operator,
    )
    with session_scope('research') as db:
        db.get(Batch, batch_id).job_id = job_id
    return {'batch_id': batch_id, 'job_id': job_id}


@register('import', resumable=True, label='匯入與去識別化')
def run_import(ctx: JobContext) -> dict[str, Any]:
    try:
        return _run_import(ctx)
    except BaseException as exc:
        from ..jobs.manager import StopRequested

        with session_scope('research') as db:
            batch = db.get(Batch, ctx.config['batch_id'])
            if batch is not None:
                batch.status = 'stopped' if isinstance(exc, StopRequested) else 'failed'
        raise


def _run_import(ctx: JobContext) -> dict[str, Any]:
    cfg = ctx.config
    batch_id: str = cfg['batch_id']
    root = source_root(cfg['source'], cfg.get('folder'))
    files, tables = list_files(root)
    archive = storage.batch_archive(batch_id) if cfg['source'] == 'inbox' else None

    with session_scope('research') as db:
        templates = {(t.width, t.height): template_dict(t) for t in db.query(LayoutTemplate).all()}
        known = {row[0] for row in db.query(Image.sha256).all()}

    counts = Counter()
    ruler_checks: dict[str, int] = {}
    review_list: list[dict[str, Any]] = []
    total = max(1, len(files))
    for index, f in enumerate(files, 1):
        ctx.check_stop()
        ctx.progress(index / total * 100, f'{index}／{len(files)}')
        digest = sha256_of(f.path)
        if digest in known:
            counts['duplicates'] += 1
            continue
        try:
            bgr = deid.read_image(f.path)
        except ValueError:
            counts['unreadable'] += 1
            review_list.append({'file_index': index, 'reason': '無法讀取影像'})
            continue
        h, w = bgr.shape[:2]
        template = templates.get((w, h))
        if template is None:
            counts['unknown_size'] += 1
            review_list.append({'file_index': index, 'reason': f'沒有 {w}×{h} 的版面範本'})
            continue

        # 深度尺的 OCR 交叉確認只做每個版面的前 RULER_CHECKS 張：同一台機器同一深度設定的刻度間距相同，
        # 前幾張確認刻度偵測正確後，其餘只用刻度（省下大部分 OCR 時間）
        checked = ruler_checks.get(template['id'], 0)
        result = deid.process(bgr, template['regions'], template['readers'], ruler_cross_check=checked < RULER_CHECKS)
        ruler_checks[template['id']] = checked + 1
        reasons = list(result.review_reasons)
        deid_check = 'unchecked'
        if cfg.get('residual_check', True):
            residual = deid.residual_check(result.model_image)
            deid_check = 'residual' if residual else 'pass'
            if residual:
                reasons.append('去識別化後仍偵測到文字：' + '、'.join(residual))

        new_id = new_image_id()
        deid.write_png(storage.image_path(new_id, 'model'), result.model_image)
        deid.write_gray_alpha(storage.image_path(new_id, 'calc'), result.calc_gray, result.calc_valid)
        deid.write_jpeg(storage.image_path(new_id, 'thumb'), deid.thumbnail(result.model_image))

        if archive is not None:
            target = archive / f.relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f.path, target)
            original_rel = storage.relative_to_root(target)
        else:
            original_rel = storage.relative_to_root(f.path)

        status = 'pending_review' if reasons else 'usable'
        with session_scope('research') as db:
            db.add(
                Image(
                    id=new_id,
                    batch_id=batch_id,
                    sha256=digest,
                    phash=deid.phash(result.model_image),
                    machine=template['machine'],
                    template_id=template['id'],
                    width=w,
                    height=h,
                    side=result.side,
                    side_source=result.side_source,
                    pixel_spacing_mm=result.pixel_spacing_mm,
                    spacing_check=result.spacing_check,
                    sonographer_length_mm=result.dist_a_mm,
                    sonographer_width_mm=result.dist_b_mm,
                    ocr_age=result.age,
                    ocr_sex=result.sex,
                    scan_params_json=deid.scan_params_json(result),
                    caliper_pixels=result.caliper_pixels,
                    status=status,
                    review_reasons_json=json.dumps(reasons, ensure_ascii=False),
                    deid_check=deid_check,
                    created_at=now_iso(),
                )
            )
            db.flush()
            db.add(SourceMap(image_id=new_id, batch_id=batch_id, original_relpath=original_rel))
        known.add(digest)
        counts['imported'] += 1
        counts[status] += 1
        if reasons:
            review_list.append({'image_id': new_id, 'reason': '；'.join(reasons)})

    # 來源資料夾附的病人表：匯入完直接對照這一批的影像（分不出來的會進「病人對照」的人工確認清單）
    table_results: list[dict[str, Any]] = []
    for path in tables:
        if archive is not None:
            target = archive / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        try:
            info = patients.import_table_from_path(path)
            matched = patients.apply(info['table_id'], batch_id=batch_id)
            table_results.append({'name': path.name, 'table_id': info['table_id'], 'rows': info['rows'], **matched})
        except Exception as exc:  # 病人表有問題不能讓整批匯入失敗；寫進報表，之後在「病人對照」重新上傳
            message = exc.message if isinstance(exc, AppError) else '病人表無法讀取，請確認檔案沒有損壞。'
            table_results.append({'name': path.name, 'error': message})

    report = {
        'batch_id': batch_id,
        'source': cfg['source'],
        'folder': cfg.get('folder'),
        'finished_at': now_iso(),
        'total': len(files),
        'imported': counts['imported'],
        'usable': counts['usable'],
        'pending_review': counts['pending_review'],
        'duplicates': counts['duplicates'],
        'unreadable': counts['unreadable'],
        'unknown_size': counts['unknown_size'],
        'review': review_list,
        'patient_tables': table_results,
    }
    record_dir = storage.import_record_dir(batch_id)
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with session_scope('research') as db:
        batch = db.get(Batch, batch_id)
        batch.status, batch.finished_at = 'completed', now_iso()
        batch.counts_json = json.dumps({k: v for k, v in report.items() if isinstance(v, int)}, ensure_ascii=False)
    if cfg['source'] == 'inbox':
        done = get_settings().path('inbox') / '已完成' / f'{batch_id}_{root.name}'
        shutil.move(str(root), str(done))
    return {k: v for k, v in report.items() if k != 'review'}


def header_number(image_id: str) -> str | None:
    """標頭上的長數字（病歷號）：只用來判斷「兩張影像是不是同一位病人」。
    只在記憶體中回傳給呼叫者比較，不寫入資料庫或檔案，也不顯示。"""
    import re

    import cv2

    with session_scope('research') as db:
        template_id = db.query(Image.template_id).filter(Image.id == image_id).scalar()
        tpl = db.get(LayoutTemplate, template_id)
        rect = template_dict(tpl)['readers']['header'] if tpl else None
    if rect is None:
        return None
    region = deid.crop(load_original(image_id), rect)[0]
    if region.shape[1] < 1000:
        region = cv2.resize(region, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    numbers = re.findall(r'(?<!\d)\d{5,10}(?!\d)', ocr.joined(ocr.read_tokens(region)))
    return max(numbers, key=len) if numbers else None


def legacy_mask_pairs(mask_root: Path) -> list[tuple[str, Path]]:
    """舊程式遮罩（IMG_Mask）與影像的對應：遮罩的相對路徑＝原始檔相對於來源資料夾的路徑，副檔名改成 .png。
    原始檔名只在這裡使用，回傳的只有影像 ID 與遮罩檔路徑。"""
    settings = get_settings()
    roots = [settings.path('source_original'), settings.path('raw_archive')]
    pairs: list[tuple[str, Path]] = []
    with session_scope('research') as db:
        rows = db.query(SourceMap.image_id, SourceMap.original_relpath).all()
    for image_id, rel in rows:
        original = storage.from_root(rel)
        for root in roots:
            try:
                inner = original.relative_to(root)
            except ValueError:
                continue
            if root == roots[1]:  # 匯入區批次：去掉批次資料夾那一層
                inner = Path(*inner.parts[1:])
            candidate = mask_root / inner.with_suffix('.png')
            if candidate.is_file():
                pairs.append((image_id, candidate))
            break
    return pairs


def load_original(image_id: str):
    """讀取原圖（只給範本預覽使用；預覽會先強烈模糊，不會顯示可辨識的文字）。"""
    with session_scope('research') as db:
        rel = db.query(SourceMap.original_relpath).filter(SourceMap.image_id == image_id).scalar()
    if rel is None:
        raise AppError(404, 'IMAGE_NOT_FOUND', '找不到這張影像的原始檔。')
    path = storage.from_root(rel)
    if not path.exists():
        raise AppError(404, 'FILE_NOT_FOUND', '原始檔已不在原位置。')
    return deid.read_image(path)


@register('redeid', resumable=True, label='重新去識別化')
def redeid(ctx: JobContext) -> dict[str, Any]:
    """調整版面範本後，用原始檔重做去識別化（不必重新匯入）。
    影像 ID、病人對照、標註都不變；人工排除的影像維持排除；人工設定的側別不覆蓋。"""
    from sqlalchemy import or_

    cfg = ctx.config
    with session_scope('research') as db:
        templates = {t.id: template_dict(t) for t in db.query(LayoutTemplate).all()}
        q = db.query(Image.id, Image.template_id)
        if cfg.get('template_id'):
            q = q.filter(Image.template_id == cfg['template_id'])
        if cfg.get('batch_id'):
            q = q.filter(Image.batch_id == cfg['batch_id'])
        rows = q.order_by(Image.id).all()
    counts: Counter = Counter()
    total = max(1, len(rows))
    for index, (image_id, template_id) in enumerate(rows, 1):
        ctx.check_stop()
        ctx.progress(index / total * 100, f'{index}／{len(rows)}')
        template = templates.get(template_id)
        try:
            bgr = load_original(image_id)
        except AppError:
            counts['missing_original'] += 1
            continue
        result = deid.process(bgr, template['regions'], template['readers'], ruler_cross_check=False)
        residual = deid.residual_check(result.model_image)
        deid.write_png(storage.image_path(image_id, 'model'), result.model_image)
        deid.write_gray_alpha(storage.image_path(image_id, 'calc'), result.calc_gray, result.calc_valid)
        deid.write_jpeg(storage.image_path(image_id, 'thumb'), deid.thumbnail(result.model_image))
        reasons = list(result.review_reasons) + (['去識別化後仍偵測到文字：' + '、'.join(residual)] if residual else [])
        with session_scope('research') as db:
            image = db.get(Image, image_id)
            image.phash = deid.phash(result.model_image)
            image.pixel_spacing_mm, image.spacing_check = result.pixel_spacing_mm, result.spacing_check
            image.caliper_pixels, image.deid_check = result.caliper_pixels, 'residual' if residual else 'pass'
            image.scan_params_json = deid.scan_params_json(result)
            if image.side_source not in ('manual', 'circling') and result.side:  # 人工或醫師圈選的側別不被重新辨識蓋掉
                image.side, image.side_source = result.side, result.side_source
            if residual and image.status != 'excluded':
                image.status = 'pending_review'  # 新的範本仍有文字殘留：需要重新確認
                image.review_reasons_json = json.dumps(reasons, ensure_ascii=False)
                counts['residual'] += 1
        counts['processed'] += 1
    return {'images': len(rows), 'processed': counts['processed'], 'residual': counts['residual'], 'missing_original': counts['missing_original']}


@register('reread_side', resumable=True, label='重新判斷側別')
def reread_side(ctx: JobContext) -> dict[str, Any]:
    """用體表示意圖重新判斷已匯入影像的側別（不必重新匯入）。人工或醫師圈選設定過的側別不會被覆蓋；判斷不出來的保留原值。"""
    from sqlalchemy import or_

    with session_scope('research') as db:
        templates = {t.id: template_dict(t) for t in db.query(LayoutTemplate).all()}
        rows = (
            db.query(Image.id, Image.template_id)
            .filter(or_(Image.side_source.is_(None), Image.side_source.notin_(('manual', 'circling'))))
            .order_by(Image.id)
            .all()
        )
    counts: Counter = Counter()
    total = max(1, len(rows))
    for index, (image_id, template_id) in enumerate(rows, 1):
        ctx.check_stop()
        ctx.progress(index / total * 100, f'{index}／{len(rows)}')
        rect = (templates.get(template_id) or {}).get('readers', {}).get('bodymark')
        if rect is None:
            counts['unknown'] += 1
            continue
        try:
            bgr = load_original(image_id)
        except AppError:
            counts['missing_original'] += 1
            continue
        mark = bodymark.detect(deid.crop(bgr, rect)[0])
        if not mark.side:
            counts['unknown'] += 1
            continue
        with session_scope('research') as db:
            image = db.get(Image, image_id)
            if image is not None and image.side_source not in ('manual', 'circling'):
                image.side, image.side_source = mark.side, 'bodymark'
                counts[mark.side] += 1
    return {'images': len(rows), 'right': counts['right'], 'left': counts['left'], 'unknown': counts['unknown'], 'missing_original': counts['missing_original']}


def batch_report(batch_id: str) -> dict[str, Any]:
    path = storage.import_record_dir(batch_id) / 'report.json'
    with session_scope('research') as db:
        batch = db.get(Batch, batch_id)
        if batch is None:
            raise AppError(404, 'BATCH_NOT_FOUND', '找不到這個匯入批次。')
        info = {
            'id': batch.id,
            'source_kind': batch.source_kind,
            'source_label': batch.source_label,
            'status': batch.status,
            'created_by': batch.created_by,
            'created_at': batch.created_at,
            'finished_at': batch.finished_at,
            'job_id': batch.job_id,
            'counts': json.loads(batch.counts_json or '{}'),
        }
        by_template = (
            db.query(Image.template_id, Image.machine, Image.status)
            .filter(Image.batch_id == batch_id)
            .all()
        )
    per = Counter((t, m, s) for t, m, s in by_template)
    info['per_template'] = [
        {'template_id': t, 'machine': m, 'status': s, 'count': c} for (t, m, s), c in sorted(per.items())
    ]
    info['report'] = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    return info


def list_batches() -> list[dict[str, Any]]:
    with session_scope('research') as db:
        rows = db.query(Batch).order_by(Batch.created_at.desc()).all()
        return [
            {
                'id': b.id,
                'source_kind': b.source_kind,
                'source_label': b.source_label,
                'status': b.status,
                'created_by': b.created_by,
                'created_at': b.created_at,
                'finished_at': b.finished_at,
                'counts': json.loads(b.counts_json or '{}'),
            }
            for b in rows
        ]
