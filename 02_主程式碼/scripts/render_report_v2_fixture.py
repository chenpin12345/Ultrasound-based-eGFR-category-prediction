"""One explicitly synthetic PDF for visual QA; no production DB or weights."""
import argparse
import hashlib
import os
from pathlib import Path
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
args.output=args.output.resolve()
args.output.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(ISU_AI_CLINICAL_DIR=str(args.output/'clinical'),ISU_AI_DATA_DIR=str(args.output/'data'),
    ISU_AI_MODELS_DIR=str(args.output/'models'),ISU_AI_REPORTS_DIR=str(args.output/'reports'),
    ISU_AI_RUNTIME_DIR=str(args.output/'runtime'),ISU_AI_REFERENCE_FEATURES_DIR=str(args.output/'features'),
    ISU_AI_DATABASE_URL='sqlite:///'+(args.output/'data/fixture.sqlite3').as_posix(),ISU_AI_REQUIRE_EXISTING_DATABASES='false')
from PIL import Image,ImageDraw
from backend.app.clinical.report_v2 import render
from backend.app.core.config import get_settings
get_settings.cache_clear()
originals=args.output/'clinical/frames';originals.mkdir(parents=True)
images=[]
for index,classes in enumerate([2,3,5],1):
    path=originals/f'fixture-{index}.png'
    picture=Image.new('RGB',(640,480),(24,35,42))
    draw=ImageDraw.Draw(picture);draw.ellipse((100,100,540,380),outline=(170,190,190),width=8)
    draw.text((25,25),'SYNTHETIC QA FIXTURE - NOT A PATIENT',fill='white')
    picture.save(path)
    labels={2:['<60','>=60'],3:['<30','30-59','>=60'],5:['<15','15-29','30-59','60-89','>=90']}[classes]
    result={'predicted_class':labels[0],'has_mask':index!=1,'features':{'Length_px':0 if index==2 else 321.123456,'Contrast_Ratio':1.23456789,'Entropy':4.678901},'model_sha256':'a'*64,'probabilities':[{'label':label,'probability':1/classes} for label in labels]}
    images.append({'id':f'fixture-{index}','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'path':path.relative_to(args.output/'clinical').as_posix(),'analysis':result,'analysis_run_id':f'SYNTHETIC-RUN-{index}','analysis_evidence':'verified','analysis_snapshot':{'coordinates':{'processed_size':[640,480]}}})
payload={'template_version':2,'exam':{'id':'synthetic-exam','title':'隔離模板驗證（非病人、非模型成績）','kind':'demo','side':'left','created':1791504000,'payload':{}},'images':images,'include_ai':True,
         'fields':{'findings':'本頁只檢查中文字型、段落換頁及版面。\n'*35,'diagnosis':'人工測試文字，不是醫療判讀。','advice':'此檔案不可用於醫療決策。','notes':'包含 OnlyIMG、二／三／五分類示意與有效零值；不是實際模型輸出。','physician':'測試填寫者（非身分驗證）','institution':'隔離驗證環境'}}
render({'payload':payload,'state':'draft'},args.output/'sample-v2.pdf','synthetic-report',1)
print(args.output/'sample-v2.pdf')
