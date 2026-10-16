"""Image-first A4 report, rendered strictly from a frozen report version."""
from __future__ import annotations
import hashlib
import math
import os
from pathlib import Path
from datetime import datetime,timezone,timedelta
from ..core.errors import AppError
from . import pdf_fonts,store


def render(record,path,report_id,number,void=False):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,KeepTogether,Table,TableStyle
    payload=record['payload'];exam=payload['exam']
    if payload.get('template_version')!=2:raise AppError(422,'TEMPLATE_UNSUPPORTED','本模板只處理 v2 快照。')
    font=Path(os.getenv('ISU_CLINICAL_FONT',str(Path(os.getenv('WINDIR','C:/Windows'))/'Fonts/msjh.ttc')))
    if not font.is_file():raise AppError(503,'FONT_REQUIRED','缺少繁體中文字型，無法產生 PDF。')
    pdf_fonts.register(font)
    body=ParagraphStyle('body',fontName='ClinicalCJK',fontSize=10,leading=17,wordWrap='CJK',textColor=colors.HexColor('#173348'))
    heading=ParagraphStyle('heading',parent=body,fontSize=12,leading=19,spaceBefore=12,spaceAfter=7,keepWithNext=True)
    small=ParagraphStyle('small',parent=body,fontSize=8,leading=12)
    title=ParagraphStyle('title',parent=heading,fontSize=20,leading=28)
    def p(text,style=body):return Paragraph(pdf_fonts.markup(text).replace('\n','<br/>'),style)
    def table(rows,widths):
        value=Table([[p(cell) for cell in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        value.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF4F4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#86AAA8')),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7)]))
        return value
    state='已作廢' if void else {'draft':'草稿','pending':'待確認','confirmed':'已確認','void':'已作廢'}.get(record['state'],record['state'])
    patient=exam['payload'].get('patient',{})
    side={'left':'左側','right':'右側','both':'雙側','unspecified':'尚未確認'}.get(exam['side'],'尚未確認')
    when=datetime.fromtimestamp(exam['created'],timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M UTC+08:00')
    story=[p('超音波檢查報告',title),p(f"檢查：{exam['title']} | {side}"),p(f"病人：{patient.get('name','示範案例')} | 識別：{patient.get('code',exam['id'])}"),p(f'{when} | {state} | 報告 v{number} / 模板 v2'),p('本機操作身分不是判讀醫師驗證，也不代表電子簽章。',small)]
    images=payload.get('images',[])
    story.append(p('1. 超音波影像',heading))
    if not images:story.append(p('尚未加入已保存影像。'))
    for index,item in enumerate(images,1):
        original=store.managed(item['path'])
        if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest()!=item['sha256']:
            raise AppError(409,'REPORT_SOURCE_MISSING','引用原圖遺失或不符，不能以其他影像替代。')
        image=Image(str(original));ratio=min(160*mm/image.imageWidth,85*mm/image.imageHeight)
        image.drawWidth=image.imageWidth*ratio;image.drawHeight=image.imageHeight*ratio
        story.append(KeepTogether([p(f'影像 {index} | {item["id"][:12]}'),Spacer(1,2*mm),image]))
        story.append(Spacer(1,4*mm))
    story.append(p('2. 量測與相關特徵',heading))
    story.append(p('尚無實體長度量測。本報告不提供 mm／cm 換算；像素特徵不是實體腎長。'))
    for index,item in enumerate(images,1):
        result=item.get('analysis') or {};features=result.get('features') or {}
        snapshot=item.get('analysis_snapshot') or {}
        story.append(p(f'影像 {index}',heading))
        if item.get('analysis_evidence')!='verified':
            story.append(p(item.get('analysis_reason') or '尚無已核實的分析快照，特徵不作為有效量測呈現。'));continue
        if not result.get('has_mask'):
            story.append(p('本次分析未包含分割遮罩；不提供長軸或其他分割特徵。'));continue
        rows=[['特徵','數值／性質']]
        for key,label,unit in [('Length_px','分割區域長軸特徵','px'),('Contrast_Ratio','Contrast_Ratio','無單位比值'),('Entropy','Entropy','影像熵特徵')]:
            value=features.get(key)
            valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
            rows.append([label,f'{value:.6g} {unit}' if valid else '缺失或無效，未補零'])
        story.append(table(rows,[75*mm,99*mm]))
        story.append(p('分析版本：'+str(item.get('analysis_run_id','未核實')),small))
        story.append(p('處理尺寸：'+str(snapshot.get('coordinates',{}).get('processed_size','未記錄'))+'；方法：既有分割／特徵實作，版本雜湊保存在分析快照。',small))
    story.append(p('3. AI 預測 eGFR 類別',heading))
    story.append(p('以下是逐張影像的模型輸出，不自動合成病例期別，不構成 CKD 診斷。模型預測機率不等於準確率或確診機率。'))
    if not images:story.append(p('尚無影像與分析附件。'))
    for index,item in enumerate(images,1):
        result=item.get('analysis') or {}
        story.append(p(f'影像 {index} | '+str(result.get('predicted_class','尚無 AI 結果')),heading))
        if item.get('analysis_evidence')!='verified':story.append(p('分析來源未核實或缺失；以下舊數值如有列出，僅供歷史追溯。',small))
        probabilities=result.get('probabilities',[])
        if probabilities:
            rows=[['原模型類別（原順序）','模型預測機率']]
            for value in probabilities:
                probability=value.get('probability')
                valid=isinstance(probability,(int,float)) and math.isfinite(probability) and 0<=probability<=1
                rows.append([value.get('label','未核實'),f'{probability*100:.2f}%' if valid else '缺失或無效'])
            story.append(table(rows,[100*mm,74*mm]))
        else:story.append(p(item.get('analysis_reason') or '尚無分類機率；未補造結果。'))
        if result.get('model_sha256'):story.append(p('模型 SHA-256：'+str(result['model_sha256']),small))
        if item.get('analysis_run_id'):story.append(p('分析版本：'+item['analysis_run_id'],small))
    for index,(key,label) in enumerate([('findings','檢查所見'),('diagnosis','醫師判讀'),('advice','建議'),('notes','備註'),('physician','判讀醫師'),('institution','院所')],4):
        story.append(p(f'{index}. {label}',heading))
        # Let explicit lines break independently. A heading must not drag a
        # whole long multi-line field to a new page, leaving a half-empty page.
        for line in (payload.get('fields',{}).get(key) or '尚未填寫').split('\n'):
            story.append(p(line) if line else Spacer(1,3*mm))
    story.extend([Spacer(1,8*mm),p('簽署欄：________________　日期：________________'),p('簽署欄為人工簽署用途，不代表已驗證電子簽章。',small)])
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('ClinicalCJK',8)
        mark='真實影像示範／非正式診斷書' if exam['kind']=='demo' else '研究用途檢查報告／非正式診斷證明'
        canvas.drawString(18*mm,15*mm,mark+' | '+state)
        canvas.drawString(18*mm,10*mm,f'{report_id} / v{number} / template 2 / {doc.page}')
        canvas.restoreState()
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp')
    try:
        SimpleDocTemplate(str(temporary),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=24*mm).build(story,onFirstPage=footer,onLaterPages=footer)
        with temporary.open('r+b') as saved:os.fsync(saved.fileno())
        os.replace(temporary,path)
        path.with_suffix('.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest(),encoding='ascii')
    finally:temporary.unlink(missing_ok=True)
