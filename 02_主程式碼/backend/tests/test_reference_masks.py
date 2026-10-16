import hashlib
import json

import pytest

from test_evaluations import setup_evaluation, submit, wait_done


def reference_fixture(client,make_image,monkeypatch):
    payload=setup_evaluation(client,make_image,monkeypatch)
    from backend.app.core.config import get_settings
    from backend.app.db.models import DatasetMask,DatasetSample,ModelRecord
    from backend.app.db.session import get_session_factory
    from PIL import Image,ImageDraw
    settings=get_settings()
    root=settings.data_dir/'datasets/cohort'
    with get_session_factory()() as db:
        for index in range(5):
            path=root/f'{index}.png';Image.new('RGB',(512,512),(index,0,0)).save(path)
            mask=root/f'{index}-mask.png';image=Image.new('L',(512,512))
            ImageDraw.Draw(image).rectangle((10,10,30,30),fill=255);image.save(mask)
            sample=db.get(DatasetSample,f'sample-{index}')
            sample.width=512;sample.height=512;sample.sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            db.add(DatasetMask(id=f'mask-{index}',sample_id=sample.id,relative_path=mask.name,display_name=mask.name,
                               sha256=hashlib.sha256(mask.read_bytes()).hexdigest(),mime_type='image/png',size_bytes=mask.stat().st_size,width=512,height=512))
        model=db.get(ModelRecord,'binary');model.task='segmentation';model.architecture='unet';model.class_names=['background','foreground'];db.commit()
    manifest=settings.models_dir/'binary/model_metadata.json'
    content=json.loads(manifest.read_text());content.update(task='segmentation',architecture='unet',class_names=['background','foreground'])
    manifest.write_text(json.dumps(content),encoding='utf-8')
    registration={'dataset_id':'cohort','sample_id':'sample-0','source':'人工繪製測試矩形，僅用於軟體流程驗證，不是臨床標註。',
                  'reviewer':'Isolated fixture reviewer','annotation_method':'manual_annotation','independent_of_evaluated_model':True,'coordinate_mapping':'identity'}
    return payload,registration


def register(client,payload):
    checked=client.post('/api/evaluations/reference-masks/preflight',json=payload)
    assert checked.status_code==200,checked.text
    result=client.post('/api/evaluations/reference-masks',json={**payload,'expected_preflight_sha256':checked.json()['preflight_sha256']})
    assert result.status_code==201,result.text
    return result.json()


def test_reference_attestation_immutable_and_segmentation_adapter(client,make_image,monkeypatch):
    payload,registration=reference_fixture(client,make_image,monkeypatch)
    assert client.post('/api/evaluations/reference-masks',json=registration).status_code==409
    for index in range(5):
        record=register(client,{**registration,'sample_id':f'sample-{index}'})
        assert 'independence_human_attested' in record['evidence']['verification']
        assert record['evidence']['local_actor_id']
    assert client.post('/api/evaluations/reference-masks/preflight',json=registration).status_code==409
    # Exercise the actual mask evaluation adapter, stubbing only neural model
    # generation with a known binary pattern; not a model-accuracy claim.
    import importlib
    from backend.app.workers import evaluation_runner
    from backend.app.ml import segmentation
    importlib.reload(evaluation_runner)
    def known_mask(images,*,output_root,**_kwargs):
        from PIL import Image,ImageDraw
        output=output_root/'predicted.png'
        image=Image.new('L',(512,512));ImageDraw.Draw(image).rectangle((10,10,30,30),fill=255);image.save(output)
        return [output]
    monkeypatch.setattr(segmentation,'generate_masks',known_mask)
    result=wait_done(client,submit(client,payload))
    assert result['status']=='completed',result
    assert result['result']['metrics']['macro_per_image']=={'dice':1.0,'iou':1.0}
    assert result['result']['metrics']['micro_pixel_counts']=={'dice':1.0,'iou':1.0}
    summary=client.get('/api/models/binary').json()['evaluation_summary']
    assert summary['metrics']=={'dice':1.0,'iou':1.0} and 'accuracy' not in summary['metrics']
    from backend.app.db.session import get_session_factory
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with get_session_factory()() as db:
        with pytest.raises(IntegrityError):db.execute(text("UPDATE mask_provenance SET kind='unknown'"))
        db.rollback()


def test_reference_preflight_refuses_changed_grid_and_model_generated(client,make_image,monkeypatch):
    _,registration=reference_fixture(client,make_image,monkeypatch)
    checked=client.post('/api/evaluations/reference-masks/preflight',json=registration).json()
    from backend.app.core.config import get_settings
    from PIL import Image
    Image.new('L',(20,20)).save(get_settings().data_dir/'datasets/cohort/0-mask.png')
    result=client.post('/api/evaluations/reference-masks',json={**registration,'expected_preflight_sha256':checked['preflight_sha256']})
    assert result.status_code==409 and result.json()['error']['code']=='REFERENCE_HASH_CHANGED'
    from backend.app.db.models import MaskProvenance
    from backend.app.db.session import get_session_factory
    with get_session_factory()() as db:
        db.add(MaskProvenance(mask_id='mask-1',kind='model_generated',evidence_json={'model_id':'binary'}));db.commit()
    assert client.post('/api/evaluations/reference-masks/preflight',json={**registration,'sample_id':'sample-1'}).status_code==409
    assert client.post('/api/evaluations/reference-masks/preflight',json={**registration,'independent_of_evaluated_model':False}).status_code==422
    assert client.post('/api/evaluations/reference-masks/preflight',json={**registration,'coordinate_mapping':'resized'}).status_code==422


def test_reference_nonbinary_and_wrong_dataset_are_not_silently_accepted(client,make_image,monkeypatch):
    _,registration=reference_fixture(client,make_image,monkeypatch)
    from backend.app.core.config import get_settings
    from backend.app.db.models import DatasetMask
    from backend.app.db.session import get_session_factory
    from PIL import Image
    path=get_settings().data_dir/'datasets/cohort/0-mask.png';Image.new('L',(512,512),127).save(path)
    with get_session_factory()() as db:
        db.get(DatasetMask,'mask-0').sha256=hashlib.sha256(path.read_bytes()).hexdigest();db.commit()
    response=client.post('/api/evaluations/reference-masks/preflight',json=registration)
    assert response.status_code==422 and response.json()['error']['code']=='REFERENCE_MASK_BINARY'
    assert client.post('/api/evaluations/reference-masks/preflight',json={**registration,'dataset_id':'other'}).status_code==404
