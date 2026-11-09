"""測試只用程式產生的假影像，資料放暫存資料夾。"""
import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app

SQUARE = [[50, 50], [250, 50], [250, 200], [50, 200]]
INNER = [[120, 100], [180, 100], [180, 150], [120, 150]]


def shape(code, points=SQUARE):
    return {'id': 1, 'structure': code, 'points': points}


def make_export(folder: Path, sides: list[str], size=(320, 240)) -> list[str]:
    """模擬主系統匯出的受限資料夾：檔名是影像 ID，附 清單.csv。"""
    folder.mkdir(parents=True, exist_ok=True)
    ids = [f'IMG-{n:012X}' for n in range(1, len(sides) + 1)]
    for image_id in ids:
        Image.new('L', size, 60).save(folder / f'{image_id}.jpg')
    with (folder / '清單.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['序號', '影像ID', '側別', '要圈的構造', '備註'])
        for n, (image_id, side) in enumerate(zip(ids, sides), start=1):
            writer.writerow([n, image_id, side, '', ''])
    return ids


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / 'site'))


@pytest.fixture
def loaded(client, tmp_path):
    ids = make_export(tmp_path / 'export', ['右', '左', '未知'])
    assert client.post('/api/import', json={'folder': str(tmp_path / 'export')}).json()['added'] == 3
    return client, ids
