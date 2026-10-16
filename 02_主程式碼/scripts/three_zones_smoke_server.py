"""Disposable UI fixture. All data roots must be supplied by the test harness."""
import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
assert 'ISU_AI_DATA_DIR' in os.environ and 'three-zone-ui' in os.environ['ISU_AI_DATA_DIR']
from backend.app.db.session import init_db,get_session_factory
from backend.app.db.models import ModelRecord
from backend.app.clinical import store

init_db();store.migrate()
with store.transaction() as db:
    db.execute("INSERT INTO users VALUES('cleanup-fixture-owner','cleanup-fixture','!disabled','[]',0,'human')")
    db.execute("INSERT INTO demo_sessions(id,owner,plan_id,state,created,expires) VALUES('cleanup-fixture-session','cleanup-fixture-owner',NULL,'ended',1,2)")
    db.execute("INSERT INTO exams(id,kind,title,side,payload,revision,created,demo_session_id) VALUES('cleanup-fixture-exam','demo','隔離清理測試','left','{}',1,1,'cleanup-fixture-session')")
    fixture_frame='a'*32
    db.execute('INSERT INTO frames VALUES(?,?,?,?,?,NULL,?,0,1)',(fixture_frame,'cleanup-fixture-exam','0'*64,f'frames/{fixture_frame}/original.png','network_demo','received'))
    db.execute("INSERT INTO temporary_cleanup VALUES('cleanup-fixture','cleanup-fixture-session',?,'cleanup-fixture-exam',?,'interrupted',0,1,NULL,'隔離中斷 fixture')",(fixture_frame,f'frames/{fixture_frame}/original.png'))
    db.execute('INSERT INTO plans VALUES(?,?,?,?,1)',('preview-fixture-plan','隔離預覽方案','{"mode":"unknown"}','{"models":{}}'))
    db.execute('''INSERT INTO preview_operations
        (id,operation_key,exam_id,plan_id,actor,basic_input,status,created,completed,error_code,error_message)
        VALUES('preview-fixture','fixture-key','cleanup-fixture-exam','preview-fixture-plan','cleanup-fixture-owner','{}',
        'cancelled',1,2,'CAPTURE_ENDED','隔離預覽已停止；未保存影像不自動重試')''')
    for index in range(537):
        db.execute('INSERT INTO patients VALUES(?,?,?,?)',
                   (f'ui-patient-{index:04}',f'UI{index:04}',f'隔離介面測試病人 {index:04}',1000+index))
with get_session_factory()() as db:
    for index in range(237):
        identifier=f'fixture-{index:04}'
        db.add(ModelRecord(id=identifier,name=f'隔離介面測試模型 {index:04}',version='fixture',task='classification',architecture='resnet18',
                           class_count=2,class_names=['eGFR < 60','eGFR ≥ 60'],metadata_columns=[],preprocessing={},
                           weights_path=f'{identifier}/weights.pth',metadata_path=f'{identifier}/model_metadata.json',
                           sha256=hashlib.sha256(identifier.encode()).hexdigest(),size_bytes=0,status='ready'))
    db.commit()
import uvicorn
uvicorn.run('backend.app.main:app',host='127.0.0.1',port=int(os.environ['ISU_UI_TEST_PORT']),proxy_headers=False,log_level='warning')
