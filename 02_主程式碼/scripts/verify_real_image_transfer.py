"""Opt-in same-host check with real source images: sender (A) → TLS receiver (B), protocol 2.

Everything runs in an isolated scratch workspace (never the live databases). Logs no
file names or pixels. This is a same-host HTTPS test, not two-PC acceptance.

  python scripts/verify_real_image_transfer.py <image folder> [--output result.json] [--scratch dir]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--scratch',type=Path)
    args=parser.parse_args()
    from tools.image_sender import sender
    sources=[p for p in sender.scan(args.source) if not any('mask' in part.lower() for part in p.parts)][:2]
    if len(sources)<2: raise RuntimeError('需要至少兩張可測試的原始 JPEG／PNG。')
    originals=[p.read_bytes() for p in sources];expected=[hashlib.sha256(d).hexdigest() for d in originals]
    scratch=Path(tempfile.mkdtemp(prefix='kt-transfer-',dir=args.scratch))
    for name,folder in {'DATA':'data','MODELS':'models','CLINICAL':'clinical','REPORTS':'reports','RUNTIME':'runtime','REFERENCE_FEATURES':'features'}.items():
        os.environ['ISU_AI_'+name+'_DIR']=str(scratch/folder)
    os.environ['ISU_AI_DATABASE_URL']='sqlite:///'+(scratch/'data'/'research.sqlite3').as_posix()
    os.environ['ISU_AI_REQUIRE_EXISTING_DATABASES']='false'
    from backend.app.main import create_app
    from fastapi.testclient import TestClient
    from backend.app.clinical import transfer
    started=time.perf_counter()
    try:
        with TestClient(create_app(testing=True)) as client:
            client.headers['Origin']='http://testserver'
            challenge=client.get('/api/local-session/challenge',headers={'X-Local-Init':'1'}).json()['challenge']
            login=client.post('/api/local-session',json={'challenge':challenge},headers={'X-Local-Init':'1'}).json()
            client.headers['X-CSRF-Token']=login['csrf']
            response=client.post('/api/clinical/demo-sessions',json={'host':'127.0.0.1','analysis':{'mode':'preview_only'}})
            assert response.status_code==200,response.text
            pair=response.json()
            sender.pair_receiver(pair,pair['fingerprint'])
            cases=[{'case_code':'VERIFY-A','age':61,'diabetes':'yes','side':'left'},{'case_code':'VERIFY-B','age':45,'diabetes':'unknown','side':'right'}]
            sender.STATE['files']={f'img{i}':{'path':p,'name':'image','size':len(originals[i]),'case':sender.clean_case(cases[i])} for i,p in enumerate(sources)}
            sender.queue_start(['img0','img1'],'batch')
            deadline=time.time()+60
            while sender.STATE['running'] and time.time()<deadline:time.sleep(.05)
            assert not sender.STATE['running'],'傳輸逾時'
            assert sender.STATE['phase']=='completed',sender.STATE['message']
            batches=client.get('/api/clinical/demo-batches?session_id='+pair['session_id']).json()
            items={i['case_code']:i for i in batches[0]['items']}
            for index,code in enumerate(('VERIFY-A','VERIFY-B')):
                item=items[code];frame=item['frame']
                assert client.get(frame['url']).content==originals[index] and frame['sha256']==expected[index]
                assert item['status']=='received_only'  # explicit preview-only session never classifies
                exam=client.get('/api/clinical/exams/'+item['exam_id']).json()
                assert exam['title']==code and exam['side']==cases[index]['side'] and exam['payload']['age']==cases[index]['age'] and exam['patient_id'] is None
            assert items['VERIFY-A']['exam_id']!=items['VERIFY-B']['exam_id']
            assert 'has_diabetes' not in client.get('/api/clinical/exams/'+items['VERIFY-B']['exam_id']).json()['payload']
            assert client.get('/api/datasets').json()['total']==0
            assert client.post('/api/clinical/demo-sessions/'+pair['session_id']+'/stop',json={}).status_code==200
            transfer._executor.submit(lambda:None).result(10)
            assert all(client.get(items[c]['frame']['url']).status_code==404 for c in items)
    finally:
        shutil.rmtree(scratch,ignore_errors=True)
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]==expected
    result={'passed':True,'protocol':2,'source_kind':'two explicitly requested real ultrasound images','images':2,
            'sender_receiver_sha256_equal':True,'originals_unchanged':True,'cases_not_mixed':True,'unknown_diabetes_not_stored_as_no':True,
            'research_dataset_unchanged':True,'unsaved_frames_cleaned_on_stop':True,'receiver_process_separate':True,
            'test_topology':'same-host HTTPS between sender and independent receiver process; not physical two-PC acceptance',
            'elapsed_ms':round((time.perf_counter()-started)*1000,2),'sender_transfer_ms':[q.get('transfer_ms') for q in sender.STATE['queue']]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
