from __future__ import annotations

import hashlib
import os
import time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ..core.errors import AppError
from ..core.config import get_settings
from . import pdf_fonts,store
from .service import required


_render_lock = threading.RLock()


def missing_items(payload):
    missing=[]
    images=payload.get('images',[])
    if not images:missing.append('尚未加入影像')
    for index,item in enumerate(images,1):
        result=item.get('analysis') or {}
        if item.get('analysis_evidence')!='verified' or not result.get('probabilities'):
            missing.append(f'影像 {index} 缺少已核實的 AI 分析')
        if not result.get('has_mask') or not result.get('features'):
            missing.append(f'影像 {index} 未包含分割特徵（OnlyIMG 亦不提供）')
    return missing


def artifact_path(kind: str, exam_id: str, report_id: str, version_number: int, void=False) -> Path:
    """Only DB-derived opaque identifiers may select a report artifact."""
    import re
    if kind not in {'patient', 'demo'} or any(
        not re.fullmatch(r'[A-Za-z0-9-]{1,64}', value) for value in (exam_id, report_id)
    ) or type(version_number) is not int or version_number < 1:
        raise AppError(422, 'REPORT_PATH_INVALID', '報告識別碼或版本不正確。')
    base = get_settings().reports_dir.resolve()
    path = (base / kind / exam_id / report_id / (f'v{version_number}' + ('-void' if void else '') + '.pdf')).resolve()
    if not path.is_relative_to(base):
        raise AppError(422, 'REPORT_PATH_INVALID', '報告位置超出受管理範圍。')
    return path


def version(db, report_id, payload, state, actor, expected):
    report=required(db,'reports',report_id)
    from .lifecycle import guard
    guard(db,'reports',report_id,write=True)
    if report['current_version'] != expected:
        raise AppError(409,'REVISION_CONFLICT','報告已變更，請重新載入後比較內容。')
    if report['state']=='void':
        raise AppError(409,'REPORT_VOID','作廢報告不可修改。')
    next_version=expected+1
    db.execute('INSERT INTO report_versions VALUES(?,?,?,?,?,?)',
        (report_id,next_version,store.dumps(payload),state,actor,time.time()))
    db.execute('UPDATE reports SET current_version=?,state=? WHERE id=?',(next_version,state,report_id))
    store.audit(db,actor,'report_'+state,report_id)
    return next_version


def validate_payload(db, exam_id, fields, frame_ids, include_ai, analysis_run_ids=None, previous=None):
    if set(fields)-{'findings','diagnosis','advice','notes','physician','institution'} or any(len(v)>10000 for v in fields.values()):
        raise AppError(422,'REPORT_FIELDS','報告欄位不正確或內容超過限制。')
    exam=required(db,'exams',exam_id)
    from .lifecycle import guard
    guard(db,'exams',exam_id,write=True)
    from . import analysis_runs
    selected=analysis_run_ids or {}
    if set(selected)-set(frame_ids):raise AppError(422,'ANALYSIS_FRAME_MISMATCH','分析選擇包含未加入報告的影像。')
    prior={item['id']:item for item in (previous or {}).get('images',[])}
    images=[]
    for fid in dict.fromkeys(frame_ids):
        frame=required(db,'frames',fid)
        if frame['exam_id']!=exam_id or not frame['saved']:
            raise AppError(422,'REPORT_FRAME_MISMATCH','報告只能引用本次檢查中已保存的影像。')
        item={'id':fid,'sha256':frame['sha256'],'path':frame['path'],'analysis':None,'analysis_run_id':None}
        if include_ai:
            old=prior.get(fid,{})
            run_id=selected.get(fid) or old.get('analysis_run_id')
            if fid in selected and not selected[fid]:run=None
            elif run_id:run=analysis_runs.get(db,run_id,fid)
            elif old.get('analysis'):
                # Never upgrade unverified historical content using today's output.
                item.update(analysis=old['analysis'],analysis_evidence='legacy_unverified',analysis_reason='沿用舊報告數值；歷史產物關聯未核實。')
                run=None
            else:run=analysis_runs.latest(db,fid)
            if run:
                item.update(analysis_run_id=run['id'],analysis=run['snapshot']['result'],analysis_snapshot=run['snapshot'],analysis_evidence=run['evidence'])
            elif item['analysis'] is None:item['analysis_reason']='此影像尚無可保存的分析版本。'
        images.append(item)
    return {'exam':exam,'fields':fields,'images':images,'include_ai':include_ai,'template_version':(previous or {}).get('template_version',2)}


def render_pdf(report_id, version_number):
    # One local application process owns the PDF cache and ReportLab font registry.
    # Concurrent preview/download requests must receive the same immutable artifact.
    with _render_lock:
        return _render_pdf(report_id, version_number)


def _render_pdf(report_id, version_number, *, destination=None, void_override=None):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, KeepTogether
    from reportlab.lib.units import mm
    with store.transaction() as db:
        report=required(db,'reports',report_id)
        row=db.execute('SELECT * FROM report_versions WHERE report_id=? AND version=?',(report_id,version_number)).fetchone()
        if not row:
            raise AppError(404,'VERSION_NOT_FOUND','找不到報告版本。')
        record=store.rowdict(row)
    payload=record['payload']; exam=payload['exam']
    font=Path(os.getenv('ISU_CLINICAL_FONT',str(Path(os.getenv('WINDIR','C:/Windows'))/'Fonts'/'msjh.ttc')))
    if not font.is_file():
        raise AppError(503,'FONT_REQUIRED','缺少繁體中文字型；請設定 ISU_CLINICAL_FONT。')
    pdf_fonts.register(font)
    void=report['state']=='void' if void_override is None else void_override
    path=destination or artifact_path(exam['kind'], exam['id'], report_id, version_number, void)
    folder=path.parent; folder.mkdir(parents=True,exist_ok=True)
    if path.exists():
        return path
    temp=folder/(store.uid()+'.tmp')
    style=ParagraphStyle('body',fontName='ClinicalCJK',fontSize=10,leading=17,wordWrap='CJK')
    title=ParagraphStyle('title',parent=style,fontSize=18,leading=26,spaceAfter=10)
    story=[Paragraph('超音波檢查報告',title)]
    def paragraph(text):
        return Paragraph(pdf_fonts.markup(text).replace('\n','<br/>'),style)
    demo=exam['kind']=='demo'
    state={'draft':'草稿','pending':'待確認','confirmed':'已確認','void':'已作廢'}.get(record['state'],record['state'])
    if void: state='已作廢'
    patient=exam['payload'].get('patient',{})
    side={'left':'左側','right':'右側','both':'雙側','unspecified':'尚未確認'}[exam['side']]
    exam_time=datetime.fromtimestamp(exam['created'],timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC+08:00')
    for text in [f"檢查：{exam['title']}　側別：{side}",
                 f"病人：{patient.get('name','示範案例')}　識別碼：{patient.get('code',exam['id'])}",
                 f"檢查時間：{exam_time}",
                 f"狀態：{state}　報告版本：{version_number}"]:
        story.append(paragraph(text))
    labels={'findings':'檢查所見','diagnosis':'醫師判讀','advice':'建議','notes':'備註','physician':'醫師','institution':'院所'}
    for key,label in labels.items():
        story.extend([Spacer(1,4*mm),paragraph(label+'：'),paragraph(payload['fields'].get(key,''))])
    for index,item in enumerate(payload['images'],1):
        im=Image(str(store.managed(item['path'])))
        ratio=min(160*mm/im.imageWidth,100*mm/im.imageHeight)
        im.drawWidth=im.imageWidth*ratio; im.drawHeight=im.imageHeight*ratio
        story.extend([Spacer(1,5*mm),KeepTogether([paragraph(f'代表影像 {index} · {item["id"][:12]}'),im])])
        if item.get('analysis'):
            analysis=item['analysis']
            story.append(paragraph('AI 輔助資料（模型機率不是準確率）：'+str(analysis.get('predicted_class',analysis.get('message','')))))
            story.append(paragraph('模型 SHA-256：'+str(analysis.get('model_sha256',''))))
            for probability in analysis.get('probabilities',[]):
                story.append(paragraph(f"{probability['label']}：{probability['probability']*100:.2f}%"))
            if analysis.get('plan_id'): story.append(paragraph('方案：'+analysis['plan_id']+'；前處理：'+str(analysis.get('profile',{}).get('mode',''))))
    story.extend([Spacer(1,10*mm),paragraph('醫師簽署：________________　日期：________________')])
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont('ClinicalCJK',8)
        mark='真實影像示範／非正式診斷書' if demo else '研究用途檢查報告／非正式診斷證明'
        canvas.drawString(18*mm,15*mm,mark+' · '+state)
        canvas.drawString(18*mm,10*mm,f'{report_id} / v{version_number} / {doc.page}')
        canvas.restoreState()
    try:
        SimpleDocTemplate(str(temp),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,
                          topMargin=18*mm,bottomMargin=24*mm).build(story,onFirstPage=footer,onLaterPages=footer)
        os.replace(temp,path)
        path.with_suffix('.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest(),encoding='ascii')
    finally:
        temp.unlink(missing_ok=True)
    return path
