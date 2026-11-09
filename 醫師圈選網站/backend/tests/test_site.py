import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app

from .conftest import INNER, SQUARE, make_export, shape


def finish(client, image_id, shapes=None, **extra):
    data = {'shapes': shapes if shapes is not None else [shape('kidney'), shape('sinus', INNER)], 'grade': 1, 'states': {'liver': 'unlabeled', 'spleen': 'absent'}, **extra}
    assert client.put(f'/api/images/{image_id}', json=data).status_code == 200
    return client.post(f'/api/images/{image_id}/complete', json={}).json()


def test_import_keeps_order_side_and_does_not_overwrite(loaded, tmp_path):
    client, ids = loaded
    rows = client.get('/api/images').json()
    assert [r['id'] for r in rows] == ids
    assert [r['side'] for r in rows] == ['right', 'left', None]
    assert client.get(f'/api/images/{ids[0]}').json()['states'] == {'spleen': 'absent'}
    assert client.get(f'/api/images/{ids[1]}').json()['states'] == {'liver': 'absent'}
    client.put(f'/api/images/{ids[0]}', json={'shapes': [shape('kidney')]})
    again = client.post('/api/import', json={'folder': str(tmp_path / 'export')}).json()
    assert again['added'] == 0 and again['existing'] == 3
    assert len(client.get(f'/api/images/{ids[0]}').json()['shapes']) == 1


def test_import_rejects_folder_without_image_ids(client, tmp_path):
    folder = tmp_path / 'raw'
    folder.mkdir()
    Image.new('L', (10, 10)).save(folder / 'someone.jpg')
    response = client.post('/api/import', json={'folder': str(folder)})
    assert response.status_code == 422 and response.json()['error']['code'] == 'NO_IMAGES'


def test_autosave_survives_restart(tmp_path):
    root = tmp_path / 'site'
    client = TestClient(create_app(root))
    make_export(tmp_path / 'export', ['右'])
    client.post('/api/import', json={'folder': str(tmp_path / 'export')})
    image_id = client.get('/api/images').json()[0]['id']
    client.put(f'/api/images/{image_id}', json={'shapes': [shape('kidney')], 'note': '備註', 'seconds': 12})
    reopened = TestClient(create_app(root))
    detail = reopened.get(f'/api/images/{image_id}').json()
    assert detail['shapes'][0]['points'] == SQUARE and detail['note'] == '備註' and detail['status'] == 'in_progress'
    assert list((root / '資料' / '備份').glob('*.sqlite3'))


def test_points_are_clamped_to_image(loaded):
    client, ids = loaded
    client.put(f'/api/images/{ids[0]}', json={'shapes': [shape('kidney', [[-5, -5], [999, 0], [999, 999]])]})
    points = client.get(f'/api/images/{ids[0]}').json()['shapes'][0]['points']
    assert points == [[0, 0], [320, 0], [320, 240]]


def test_complete_requires_core_states_and_grade(loaded):
    client, ids = loaded
    client.put(f'/api/images/{ids[0]}', json={'shapes': [shape('kidney')]})
    result = client.post(f'/api/images/{ids[0]}/complete', json={}).json()
    assert not result['ok']
    assert any('腎竇' in e for e in result['errors']) and any('肝' in e for e in result['errors']) and any('回音分級' in e for e in result['errors'])
    assert not any('脾' in e for e in result['errors'])  # 右腎的脾預設不在影像中


def test_unsure_grade_needs_reason(loaded):
    client, ids = loaded
    result = finish(client, ids[0], grade=None, grade_unsure=True)
    assert any('原因' in e for e in result['errors'])
    client.put(f'/api/images/{ids[0]}', json={'grade_reason': '看不到肝'})
    assert client.post(f'/api/images/{ids[0]}/complete', json={}).json()['ok']


def test_warnings_can_be_forced(loaded):
    client, ids = loaded
    outside = [[240, 180], [319, 180], [319, 239], [240, 239]]
    result = finish(client, ids[0], [shape('kidney'), shape('sinus', outside)])
    assert not result['ok'] and result['warnings'] and not result['errors']
    assert client.post(f'/api/images/{ids[0]}/complete', json={'force': True}).json()['ok']


def test_sinus_with_absent_kidney_is_an_error(loaded):
    client, ids = loaded
    result = finish(client, ids[0], [shape('sinus', INNER)], states={'kidney': 'absent', 'liver': 'unlabeled'})
    assert any('不在影像中' in e for e in result['errors'])
    assert not client.post(f'/api/images/{ids[0]}/complete', json={'force': True}).json()['ok']
    client.put(f'/api/images/{ids[0]}', json={'states': {'kidney': 'unlabeled', 'liver': 'unlabeled', 'spleen': 'absent'}})
    assert client.post(f'/api/images/{ids[0]}/complete', json={'force': True}).json()['ok']


def test_crossed_contour_warns(loaded):
    client, ids = loaded
    crossed = [[50, 50], [250, 200], [250, 50], [50, 200]]
    result = finish(client, ids[0], [shape('kidney', crossed), shape('sinus', INNER)])
    assert any('交叉' in w for w in result['warnings'])


def test_completion_marks_optional_items_not_seen_and_edit_reopens(loaded):
    client, ids = loaded
    assert finish(client, ids[0], [shape('kidney'), shape('sinus', INNER), shape('stone', [[130, 110], [140, 110], [140, 120]])])['ok']
    detail = client.get(f'/api/images/{ids[0]}').json()
    assert detail['states']['stone'] == 'drawn' and detail['states']['cyst'] == 'not_seen' and detail['states']['kidney'] == 'drawn'
    client.put(f'/api/images/{ids[0]}', json={'grade': 2})
    assert client.get(f'/api/images/{ids[0]}').json()['status'] == 'in_progress'


def test_unusable_skips_checks_and_export_has_no_label(loaded):
    client, ids = loaded
    client.put(f'/api/images/{ids[0]}', json={'unusable_reason': '影像模糊'})
    assert client.post(f'/api/images/{ids[0]}/complete', json={}).json()['status'] == 'unusable'
    result = client.post('/api/export').json()
    assert result['images'] == 1 and result['labels'] == 0
    assert not list((Path(result['folder']) / '標籤').iterdir())


def test_side_change_moves_default_absent(loaded):
    client, ids = loaded
    client.put(f'/api/images/{ids[0]}', json={'side': 'left'})
    assert client.get(f'/api/images/{ids[0]}').json()['states'] == {'liver': 'absent'}


def test_list_hides_grades(loaded):
    client, ids = loaded
    finish(client, ids[0])
    assert 'grade' not in client.get('/api/images').json()[0]


def test_export_label_values_order_and_no_image_content(loaded):
    client, ids = loaded
    liver = [[0, 0], [319, 0], [319, 120], [0, 120]]
    shapes = [shape('sinus', INNER), shape('kidney'), shape('liver', liver), shape('cyst', [[60, 60], [90, 60], [90, 90]])]
    finish(client, ids[0], shapes)
    result = client.post('/api/export').json()
    folder = Path(result['folder'])
    label = Image.open(folder / '標籤' / f'{ids[0]}.png')
    assert label.mode == 'L' and label.size == (320, 240)
    assert {v for _, v in label.getcolors()} == {0, 1, 2, 3}
    assert label.getpixel((150, 125)) == 2 and label.getpixel((10, 10)) == 3 and label.getpixel((70, 70)) == 1 and label.getpixel((10, 230)) == 0
    assert sorted(p.name for p in folder.rglob('*') if p.suffix.lower() in {'.png', '.jpg'}) == [f'{ids[0]}.png']
    data = json.loads((folder / '圈選結果.json').read_text(encoding='utf-8'))
    item = data['images'][0]
    assert item['grade'] == 1 and item['states']['cyst'] == 'drawn' and any(s['structure'] == 'cyst' for s in item['shapes'])
    assert (folder / '圈選結果.csv').read_text(encoding='utf-8-sig').startswith('影像ID')


def test_export_folders_do_not_collide(loaded):
    client, ids = loaded
    finish(client, ids[0])
    assert client.post('/api/export').json()['folder'] != client.post('/api/export').json()['folder']


def test_custom_structure_rename_keeps_data(loaded):
    client, ids = loaded
    code = client.post('/api/structures', json={'name': '腎周積液', 'meaning': '腎臟周圍的液體', 'color': '#f97316'}).json()['code']
    client.put(f'/api/images/{ids[0]}', json={'shapes': [shape(code)]})
    client.patch(f'/api/structures/{code}', json={'name': '積液', 'color': '#14B8A6'})
    assert client.get(f'/api/images/{ids[0]}').json()['shapes'][0]['structure'] == code
    saved = next(s for s in client.get('/api/structures').json()['structures'] if s['code'] == code)
    assert saved['name'] == '積液' and saved['color'] == '#14B8A6' and saved['used'] == 1


def test_structure_rules(loaded):
    client, ids = loaded
    assert client.post('/api/structures', json={'name': '', 'meaning': 'x', 'color': '#123456'}).status_code == 422
    assert client.post('/api/structures', json={'name': '腎竇', 'meaning': 'x', 'color': '#123456'}).status_code == 409
    assert client.patch('/api/structures/kidney', json={'name': '腎'}).status_code == 409
    assert client.patch('/api/structures/kidney', json={'color': '#00FFAA'}).status_code == 200
    assert client.delete('/api/structures/sinus').status_code == 409
    client.put(f'/api/images/{ids[0]}', json={'shapes': [shape('stone')]})
    assert client.delete('/api/structures/stone').status_code == 409
    assert client.patch('/api/structures/stone', json={'active': False}).json()['active'] is False
    assert client.delete('/api/structures/cyst').status_code == 200


def test_color_check_warns_close_and_gray(client):
    assert any('太接近' in w for w in client.post('/api/structures/color-check', json={'color': '#00E0FA'}).json()['warnings'])
    assert any('太灰' in w for w in client.post('/api/structures/color-check', json={'color': '#808080'}).json()['warnings'])
    assert client.post('/api/structures/color-check', json={'color': '#F97316'}).json()['warnings'] == []


def test_rejects_other_hosts_and_origins(client):
    assert client.get('/api/summary', headers={'host': 'evil.example'}).status_code == 403
    assert client.put('/api/circler', json={'circler': 'A'}, headers={'origin': 'http://evil.example'}).status_code == 403
    assert client.put('/api/circler', json={'circler': 'A'}, headers={'origin': 'http://127.0.0.1:8100'}).status_code == 200


def test_estimate_after_twenty(client, tmp_path):
    make_export(tmp_path / 'export', ['右'] * 25)
    client.post('/api/import', json={'folder': str(tmp_path / 'export')})
    ids = [r['id'] for r in client.get('/api/images').json()]
    for image_id in ids[:19]:
        finish(client, image_id, seconds=60)
    assert client.get('/api/summary').json()['estimate'] is None
    finish(client, ids[19], seconds=60)
    estimate = client.get('/api/summary').json()['estimate']
    assert estimate['seconds_per_image'] == 60 and estimate['remaining_hours'] == 0.1
