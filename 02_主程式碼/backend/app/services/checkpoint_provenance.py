"""Post-training evidence only. No model calls, RNG calls or selection changes."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path


def encoded(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')


def file_sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def capture_inputs(samples):
    # The original order, metadata, labels and stored fold membership are retained.
    return [{'sha256':file_sha(row.image_path),'class_index':row.class_index,'split':row.split,
             'fold':row.fold,'metadata':dict(row.metadata)} for row in samples]


def record(outcome,training_id,dataset_id,before,after):
    if before!=after:raise ValueError('Training inputs changed while the job ran; checkpoint source is unverified')
    folder=Path(outcome.artifact_dir)
    files={name:file_sha(folder/name) for name in ('best_model.pth','model_metadata.json','metrics.json','history.csv')}
    metrics=json.loads((folder/'metrics.json').read_text(encoding='utf-8'))
    metadata=json.loads((folder/'model_metadata.json').read_text(encoding='utf-8'))
    if metrics!=outcome.metrics:raise ValueError('Persisted training metrics differ from the outcome')
    cv=metrics.get('cross_validation') or {}
    fold=cv.get('selected_fold')
    history=[dict(row) for row in outcome.history if fold is None or row.get('fold')==fold]
    def local_epoch(row):return row.get('fold_epoch',row.get('epoch'))
    best_epoch=outcome.best_epoch
    matches=[row for row in history if local_epoch(row)==best_epoch]
    loss=float(outcome.best_validation_loss)
    if len(matches)!=1 or not math.isfinite(loss) or matches[0].get('val_loss')!=loss:
        raise ValueError('Best checkpoint epoch and validation-loss record cannot be matched')
    claimed=metadata.get('best_metric') or {}
    if claimed.get('epoch')!=best_epoch or claimed.get('validation_loss')!=loss or claimed.get('fold')!=fold:
        raise ValueError('Checkpoint metadata does not match the selected epoch/fold')
    last=max(history,key=local_epoch)
    def view(row):
        return {'epoch':local_epoch(row),'metrics':{key:value for key,value in row.items() if key.startswith('val_') or key.startswith('train_')}}
    input_digest=hashlib.sha256(encoded(before)).hexdigest()
    split_counts=Counter()
    for row in before:
        split=row['split']
        if fold is not None and split!='test':split='val' if row['fold']==fold else 'train'
        split_counts[split]+=1
    value={'version':'checkpoint-source-v1','training_job_id':training_id,'dataset_id':dataset_id,
           'weights_sha256':files['best_model.pth'],'artifact_sha256':files,
           'samples':before,'samples_sha256':input_digest,'selected_split_counts':dict(split_counts),
           'selection':{'metric':'validation_loss','direction':'minimize','best_epoch':best_epoch,'value':loss,'selected_fold':fold},
           'best_epoch_record':view(matches[0]),'last_epoch_record':view(last),
           'cross_validation':cv or None,'training_implementation_sha256':file_sha(Path(__file__).parents[1]/'ml/training.py'),
           'not_an_independent_evaluation':True}
    content=encoded(value);digest=hashlib.sha256(content).hexdigest()
    path=folder/f'checkpoint-source-{digest}.json'
    if not path.exists():
        with path.open('xb') as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
    elif path.read_bytes()!=content:raise ValueError('Checkpoint provenance content collision')
    return {'status':'recorded','filename':path.name,'sha256':digest}


def summary(model,job,settings):
    evidence=(job.result_json or {}).get('checkpoint_provenance') if job else None
    unavailable={'status':'unverified','reason':'歷史工作沒有完整的 checkpoint 來源證據；不以最後 epoch 代替。'}
    if not evidence:return unavailable
    if evidence.get('status')!='recorded':return {'status':'unverified','reason':evidence.get('reason') or unavailable['reason']}
    try:
        from ..core.security import safe_resolve
        folder=safe_resolve(settings.models_dir,model.weights_path).parent
        name=evidence['filename']
        if Path(name).name!=name or name!=f'checkpoint-source-{evidence["sha256"]}.json':raise ValueError('identity')
        path=folder/name
        if path.stat().st_size>64*1024*1024 or file_sha(path)!=evidence['sha256']:raise ValueError('digest')
        value=json.loads(path.read_text(encoding='utf-8'))
        if value['weights_sha256']!=model.sha256 or value['training_job_id']!=model.source_training_job_id:raise ValueError('model')
        for filename,digest in value['artifact_sha256'].items():
            if filename not in {'best_model.pth','model_metadata.json','metrics.json','history.csv'} or file_sha(folder/filename)!=digest:raise ValueError('artifact')
        if hashlib.sha256(encoded(value['samples'])).hexdigest()!=value['samples_sha256']:raise ValueError('samples')
        return {'status':'verified_record','reason':'權重、輸入清單與選模紀錄雜湊一致；屬訓練來源證據，不是獨立模型評估。',
                'sha256':evidence['sha256'],'dataset_id':value['dataset_id'],'sample_count':len(value['samples']),
                'samples_sha256':value['samples_sha256'],'split_counts':value['selected_split_counts'],
                'selection':value['selection'],'best_epoch_record':value['best_epoch_record'],'last_epoch_record':value['last_epoch_record'],
                'cross_validation':value['cross_validation']}
    except (OSError,ValueError,KeyError,TypeError):
        return {'status':'unverified','reason':'checkpoint 來源證據或引用產物缺失／不符；不能把訓練數字掛到此權重。'}
