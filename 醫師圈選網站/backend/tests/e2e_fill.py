"""主系統的端對端測試呼叫這個檔：把匯出資料夾匯入網站，圈完每一張，輸出結果，印出輸出資料夾。

圈選內容刻意用不規則、帶小數座標、互相重疊的多邊形，才測得出像素對不對得上。
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def ellipse(cx, cy, rx, ry, angle, n=48, wobble=0.0):
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        r = 1 + wobble * math.sin(5 * t)
        x, y = rx * r * math.cos(t), ry * r * math.sin(t)
        out.append([round(cx + x * math.cos(angle) - y * math.sin(angle), 1), round(cy + x * math.sin(angle) + y * math.cos(angle), 1)])
    return out


def shapes_for(w: int, h: int, n: int) -> list[dict]:
    organ = 'liver' if n % 2 else 'spleen'
    return [
        {'id': 1, 'structure': 'kidney', 'points': ellipse(w * .5, h * .55, w * .22, h * .13, 0.25 + n * 0.03, 60, 0.04)},
        {'id': 2, 'structure': 'sinus', 'points': ellipse(w * .5, h * .55, w * .09, h * .04, 0.3, 30, 0.1)},
        {'id': 3, 'structure': organ, 'points': [[w * .05, h * .1], [w * .8, h * .12], [w * .6, h * .5], [w * .33, h * .38], [w * .1, h * .45]]},  # 凹多邊形，和腎臟重疊
        {'id': 4, 'structure': organ, 'points': ellipse(w * .85, h * .2, w * .05, h * .04, 0, 20)},  # 同一器官的第二塊
        {'id': 5, 'structure': 'cyst', 'points': ellipse(w * .62, h * .58, w * .025, h * .03, 0, 16)},
        {'id': 6, 'structure': 'stone', 'points': [[w * .48 + .3, h * .55 + .7], [w * .5 + .2, h * .55 + .1], [w * .5 + .9, h * .56 + .4]]},
    ]


def main(folder: str, root: str) -> None:
    client = TestClient(create_app(Path(root)))
    client.put('/api/circler', json={'circler': 'E2E'})
    assert client.post('/api/import', json={'folder': folder}).json()['added'] > 0
    for n, row in enumerate(client.get('/api/images').json()):
        detail = client.get(f'/api/images/{row["id"]}').json()
        organ = 'liver' if n % 2 else 'spleen'
        other = 'spleen' if organ == 'liver' else 'liver'
        client.put(f'/api/images/{row["id"]}', json={'shapes': shapes_for(detail['width'], detail['height'], n), 'states': {other: 'absent'},
                                                     'grade': n % 4, 'note': '合成'})
        assert client.post(f'/api/images/{row["id"]}/complete', json={'force': True}).json()['ok']
    print(client.post('/api/export').json()['folder'])


def modify(root: str, image_id: str) -> None:
    """醫師回頭修改一張已完成的影像（腎竇往右移），再輸出一次。"""
    client = TestClient(create_app(Path(root)))
    detail = client.get(f'/api/images/{image_id}').json()
    shapes = [{**s, 'points': [[x + 7.5, y] for x, y in s['points']]} if s['structure'] == 'sinus' else s for s in detail['shapes']]
    client.put(f'/api/images/{image_id}', json={'shapes': shapes, 'grade': 3})
    assert client.post(f'/api/images/{image_id}/complete', json={'force': True}).json()['ok']
    print(client.post('/api/export').json()['folder'])


if __name__ == '__main__':
    if sys.argv[1] == 'modify':
        modify(sys.argv[2], sys.argv[3])
    else:
        main(sys.argv[1], sys.argv[2])
