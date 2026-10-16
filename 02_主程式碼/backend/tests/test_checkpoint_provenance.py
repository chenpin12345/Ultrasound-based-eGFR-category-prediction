import json
import random
from types import SimpleNamespace

import pytest

from backend.app.services import checkpoint_provenance as source


def fixture(tmp_path,fold=None):
    folder=tmp_path/'model';folder.mkdir()
    history=[{'epoch':1,'val_loss':.2,'val_accuracy':.7},{'epoch':2,'val_loss':.4,'val_accuracy':.9}]
    if fold is not None:
        history=[{**row,'epoch':fold*2+row['epoch'],'fold_epoch':row['epoch'],'fold':fold} for row in history]
    metrics={'best_epoch':1,'best_validation_loss':.2,'final_validation':{'accuracy':.9},'test':{'accuracy':0}}
    if fold is not None:metrics['cross_validation']={'selected_fold':fold,'aggregate':{'validation_accuracy':{'mean':.8}},'folds':[]}
    metadata={'best_metric':{'epoch':1,'validation_loss':.2,**({'fold':fold} if fold is not None else {})}}
    (folder/'best_model.pth').write_bytes(b'Synthetic evidence only, not loadable model')
    (folder/'model_metadata.json').write_text(json.dumps(metadata))
    (folder/'metrics.json').write_text(json.dumps(metrics))
    (folder/'history.csv').write_text('epoch,val_loss\n1,0.2\n2,0.4\n')
    inputs=[{'sha256':'a'*64,'class_index':0,'split':'train','fold':0,'metadata':{}},
            {'sha256':'b'*64,'class_index':1,'split':'val','fold':1,'metadata':{}}]
    outcome=SimpleNamespace(artifact_dir=folder,metrics=metrics,history=history,best_epoch=1,best_validation_loss=.2)
    model=SimpleNamespace(weights_path='model/best_model.pth',sha256=source.file_sha(folder/'best_model.pth'),source_training_job_id='training')
    return folder,inputs,outcome,model


@pytest.mark.parametrize('fold',[None,1])
def test_best_and_last_epoch_are_not_conflated_and_no_rng_or_artifact_is_changed(tmp_path,fold):
    folder,inputs,outcome,model=fixture(tmp_path,fold)
    before={path.name:source.file_sha(path) for path in folder.iterdir()}
    random_state=random.getstate()
    evidence=source.record(outcome,'training','dataset',inputs,inputs)
    assert random.getstate()==random_state
    assert all(source.file_sha(folder/name)==digest for name,digest in before.items())
    summary=source.summary(model,SimpleNamespace(result_json={'checkpoint_provenance':evidence}),SimpleNamespace(models_dir=tmp_path))
    assert summary['status']=='verified_record'
    assert summary['best_epoch_record']['epoch']==1 and summary['best_epoch_record']['metrics']['val_accuracy']==.7
    assert summary['last_epoch_record']['epoch']==2 and summary['last_epoch_record']['metrics']['val_accuracy']==.9
    assert summary['split_counts'].get('test',0)==0  # no fabricated zero-percent test summary
    assert summary['selection']['selected_fold']==fold


def test_changed_inputs_and_wrong_checkpoint_epoch_are_rejected(tmp_path):
    _,inputs,outcome,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='inputs changed'):source.record(outcome,'training','dataset',inputs,[])
    outcome.best_epoch=2
    with pytest.raises(ValueError,match='epoch'):source.record(outcome,'training','dataset',inputs,inputs)


def test_tampered_weight_or_history_removes_verified_source_status(tmp_path):
    folder,inputs,outcome,model=fixture(tmp_path)
    evidence=source.record(outcome,'training','dataset',inputs,inputs)
    job=SimpleNamespace(result_json={'checkpoint_provenance':evidence})
    settings=SimpleNamespace(models_dir=tmp_path)
    (folder/'history.csv').write_text('different epoch values')
    assert source.summary(model,job,settings)['status']=='unverified'
    assert source.summary(model,None,settings)['status']=='unverified'
