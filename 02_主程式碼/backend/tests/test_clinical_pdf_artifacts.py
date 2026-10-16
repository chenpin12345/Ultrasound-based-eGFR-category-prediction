import hashlib
import io
import sqlite3
from pathlib import Path

import pytest
from pypdf import PdfReader


def report_fixture(client,make_image,with_image=True):
    from backend.app.clinical import service
    exam=client.post('/api/clinical/exams',json={'kind':'demo','title':'隔離 PDF 生命週期測試'}).json()['id']
    frames=[service.save_frame(make_image(),exam,'network_demo',saved=True)] if with_image else []
    report=client.post('/api/clinical/reports',json={'exam_id':exam,'frame_ids':frames,'fields':{'findings':'測試所見\n'*100,'physician':'測試醫師'}}).json()['id']
    return exam,report


def test_get_is_read_only_delete_is_tombstone_and_rebuild_is_new_artifact(client,make_image):
    from backend.app.clinical import store
    _,report=report_fixture(client,make_image)
    url=f'/api/clinical/reports/{report}/versions/1/pdf'
    assert client.get(url).status_code==404
    created=client.post(url);assert created.status_code==200,created.text
    row=created.json();assert row['template_version']==2
    content=client.get(row['url']).content
    assert hashlib.sha256(content).hexdigest()==row['sha256']
    pdf=PdfReader(io.BytesIO(content));text='\n'.join(page.extract_text() for page in pdf.pages)
    assert text.index('1. 超音波影像')<text.index('2. 量測')<text.index('3. AI 預測')<text.index('4. 檢查所見')
    assert '尚無實體長度量測' in text
    assert all('非正式診斷書' in page.extract_text() for page in pdf.pages)
    assert client.post(url).json()['id']==row['id']  # explicit generate is idempotent while ready
    removed=client.request('DELETE',row['url'],json={'expected_sha256':row['sha256'],'reason':'隔離測試刪除產物'})
    assert removed.status_code==200,removed.text
    for _ in range(2):
        assert client.get(row['url']).status_code==410
        assert client.get(url).status_code==410
    assert client.get(f'/api/clinical/reports/{report}').json()['current_version']==1
    rebuilt=client.post(url).json();assert rebuilt['id']!=row['id']
    assert client.get(row['url']).status_code==410 and client.get(rebuilt['url']).status_code==200
    with store.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE pdf_artifacts SET status='ready' WHERE id=?",(row['id'],))


def test_read_lease_blocks_deletion_void_and_parent_lifecycle(client,make_image):
    from backend.app.clinical import pdf_artifacts
    exam,report=report_fixture(client,make_image)
    row=client.post(f'/api/clinical/reports/{report}/versions/1/pdf').json()
    response=pdf_artifacts.read(row['id'])
    try:
        assert client.request('DELETE',row['url'],json={'expected_sha256':row['sha256'],'reason':'test'}).status_code==409
        assert client.post(f'/api/clinical/reports/{report}/versions',json={'exam_id':exam,'expected_version':1,'action':'void'}).status_code==409
        pre=client.get(f'/api/clinical/lifecycle/exams/{exam}').json()
        assert not pre['allowed']
        assert client.post(f'/api/clinical/lifecycle/exams/{exam}',json={'action':'trash','expected_revision':pre['revision'],'reason':'test'}).status_code==409
    finally:pdf_artifacts.end(response.report_id)
    assert client.get(row['url']).status_code==200


def test_delete_failure_is_recoverable_and_does_not_claim_success(client,make_image,monkeypatch):
    _,report=report_fixture(client,make_image)
    row=client.post(f'/api/clinical/reports/{report}/versions/1/pdf').json()
    original=Path.unlink
    def locked(path,*args,**kwargs):
        if path.name==row['id']+'.pdf':raise PermissionError('isolated locked-file fixture')
        return original(path,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'unlink',locked)
        assert client.request('DELETE',row['url'],json={'expected_sha256':row['sha256'],'reason':'test'}).status_code==409
    items=client.get(f'/api/clinical/reports/{report}/versions/1/pdf-artifacts').json()['items']
    assert items[0]['status']=='deletion_failed'
    assert client.get(row['url']).status_code==409
    assert client.request('DELETE',row['url'],json={'expected_sha256':row['sha256'],'reason':'retry'}).status_code==200


def test_legacy_registration_preserves_bytes_and_never_revives_deleted_file(client,make_image):
    from backend.app.clinical import store,reports,pdf_artifacts,service
    exam=client.post('/api/clinical/exams',json={'kind':'demo','title':'Legacy PDF fixture'}).json()['id']
    actor=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        rid=store.uid();db.execute('INSERT INTO reports VALUES(?,?,0,?,0)',(rid,exam,'draft'))
        payload=reports.validate_payload(db,exam,{'findings':'保留舊模板'},[],False);payload['template_version']=1
        reports.version(db,rid,payload,'draft',actor,0)
    path=reports.render_pdf(rid,1);before=path.read_bytes();stamp=path.stat().st_mtime_ns
    pdf_artifacts.recover_and_import();pdf_artifacts.recover_and_import()
    listed=client.get(f'/api/clinical/reports/{rid}/versions/1/pdf-artifacts').json()['items']
    assert len(listed)==1 and listed[0]['template_version']==1
    assert path.read_bytes()==before and path.stat().st_mtime_ns==stamp
    row=listed[0]
    assert client.request('DELETE',row['url'],json={'expected_sha256':row['sha256'],'reason':'test'}).status_code==200
    pdf_artifacts.recover_and_import()
    assert not path.exists() and client.get(row['url']).status_code==410
    rebuilt=client.post(f'/api/clinical/reports/{rid}/versions/1/pdf').json()
    assert rebuilt['id']!=row['id'] and rebuilt['template_version']==1


def pdf_base_fonts(pdf):
    return {str(font.get_object()['/BaseFont']).split('+')[-1] for page in pdf.pages for font in page['/Resources']['/Font'].values()}


def test_class_label_math_symbols_render_with_real_glyphs_in_v1_and_v2(client,make_image,monkeypatch):
    from reportlab.pdfbase import pdfmetrics
    from backend.app.clinical import pdf_fonts,reports,service,store
    label='eGFR ≥ 90'
    actor=client.get('/api/local-session').json()['id']
    with store.transaction() as db:
        exam=service.new_exam(db,'demo',None,'Glyph fallback fixture','left',{})
        db.execute('INSERT INTO plans VALUES(?,?,?,?,?)',('glyph-plan','Isolated fake plan','{"mode":"prepared"}','{}',0))
    frame=service.save_frame(make_image(),exam,'network_demo',saved=True)
    probabilities=[{'label':label,'probability':.7},{'label':'eGFR 60–89','probability':.2},{'label':'eGFR < 60','probability':.1}]
    monkeypatch.setattr(service,'infer',lambda *args:({'predicted_class':label,'probabilities':probabilities,'features':{},'has_mask':False},{}))
    service.analyze_frame(frame,'glyph-plan',actor=actor)
    report=client.post('/api/clinical/reports',json={'exam_id':exam,'frame_ids':[frame],'include_ai':True,'fields':{'findings':'所見'}}).json()['id']
    v2=client.post(f'/api/clinical/reports/{report}/versions/1/pdf');assert v2.status_code==200,v2.text
    assert v2.json()['template_version']==2
    with store.transaction() as db:
        legacy=store.uid();db.execute('INSERT INTO reports VALUES(?,?,0,?,0)',(legacy,exam,'draft'))
        payload=reports.validate_payload(db,exam,{'findings':'所見'},[frame],True);payload['template_version']=1
        reports.version(db,legacy,payload,'draft',actor,0)
    # The renderer's own cmap check: every character of each class name has a real glyph somewhere.
    for value in probabilities:
        assert all(pdf_fonts.font_for(char) for char in value['label']),value['label']
    assert pdf_fonts.markup('eGFR < 60')=='eGFR &lt; 60'
    # Microsoft JhengHei lacks U+2265; a configured CJK font that has it needs no fallback run.
    fallback=ord('≥') not in pdf_fonts.cmap(pdf_fonts.PRIMARY)
    if fallback:assert pdf_fonts.markup(label)==f'eGFR <font name="{pdf_fonts.SYMBOL}">≥</font> 90'
    for content in [client.get(v2.json()['url']).content,reports.render_pdf(legacy,1).read_bytes()]:
        pdf=PdfReader(io.BytesIO(content));text='\n'.join(page.extract_text() for page in pdf.pages)
        assert '≥' in text and '60–89' in text and '< 60' in text
        if fallback:assert pdfmetrics.getFont(pdf_fonts.SYMBOL).face.name.decode() in pdf_base_fonts(pdf)


def test_missing_frozen_source_blocks_rebuild_and_wrong_hash_cannot_delete(client,make_image):
    from backend.app.clinical import store
    exam,report=report_fixture(client,make_image)
    url=f'/api/clinical/reports/{report}/versions/1/pdf'
    row=client.post(url).json()
    assert client.request('DELETE',row['url'],json={'expected_sha256':'0'*64,'reason':'test'}).status_code==409
    assert client.request('DELETE',row['url'],json={'expected_sha256':row['sha256'],'reason':'test'}).status_code==200
    with store.read_transaction() as db:frame=db.execute('SELECT * FROM frames WHERE exam_id=?',(exam,)).fetchone()
    store.managed(frame['path']).unlink()  # isolated test fixture only
    assert client.post(url).status_code==409
    assert client.get(row['url']).status_code==410
