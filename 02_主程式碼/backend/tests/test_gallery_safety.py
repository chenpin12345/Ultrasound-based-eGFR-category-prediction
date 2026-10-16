import io
import json
import pytest
from PIL import Image


@pytest.mark.parametrize('scenario,expected', [('same',200),('mismatch',409),('missing',404),('foreign',404),('unfinished',404)])
def test_overlay_rejects_unverified_or_missing_sources(client, scenario, expected):
    from backend.app.core.config import get_settings
    from backend.app.db.models import Dataset, Job, uuid_str
    from backend.app.db.session import get_session_factory
    settings=get_settings(); did=uuid_str(); jid=uuid_str(); sid=uuid_str()
    workspace=settings.jobs_dir/jid; workspace.mkdir(parents=True)
    Image.new('RGB',(32,24),(20,40,60)).save(workspace/'image.png')
    Image.new('L',(512,512) if scenario=='mismatch' else (32,24),255).save(workspace/'mask.png')
    entry={'sample_id':sid,'image':f'jobs/{jid}/image.png','mask':f'jobs/{jid}/'+('absent.png' if scenario=='missing' else 'mask.png')}
    (workspace/'handoff.json').write_text(json.dumps({'dataset_id':did,'entries':[entry]}),encoding='utf-8')
    with get_session_factory()() as db:
        db.add(Dataset(id=did,name='test',root_path=f'datasets/{did}')); db.flush()
        db.add(Job(id=jid,dataset_id=did,kind='features',status='failed' if scenario=='unfinished' else 'completed',progress=100,workspace_path=f'jobs/{jid}',config_json={}))
        db.commit()
    original=(workspace/'image.png').read_bytes(); mask=(workspace/'mask.png').read_bytes()
    response=client.get(f'/api/datasets/{uuid_str() if scenario=="foreign" else did}/gallery-overlay-source/{jid}/{sid}')
    assert response.status_code==expected, response.text if expected!=200 else ''
    assert (workspace/'image.png').read_bytes()==original
    assert (workspace/'mask.png').read_bytes()==mask
    if expected==200:
        result=Image.open(io.BytesIO(response.content))
        assert result.size==(32,24) and result.getpixel((0,0))==(20,40,60)


def test_empty_gallery_does_not_invent_assets(client):
    from backend.app.db.models import Dataset, uuid_str
    from backend.app.db.session import get_session_factory
    did=uuid_str()
    with get_session_factory()() as db:
        db.add(Dataset(id=did,name='empty',root_path=f'datasets/{did}'));db.commit()
    response=client.get(f'/api/datasets/{did}/gallery-results?sample_ids=missing')
    assert response.json()=={'job_id':None,'versions':[],'items':{}}
