"""影像瀏覽的側別篩選：未知＝還沒有側別的影像。"""


def test_side_filter_unknown(imported_client):
    images = imported_client.get('/api/images', params={'limit': 50}).json()['images']
    unknown = imported_client.get('/api/images', params={'limit': 50, 'side': 'unknown'}).json()['images']
    assert {i['id'] for i in unknown} == {i['id'] for i in images if i['side'] is None}
    assert unknown  # 假影像裡的 Canon 沒有側別
