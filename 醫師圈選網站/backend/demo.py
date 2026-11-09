"""開發用：在暫存資料夾產生合成影像並啟動網站，不會碰到真實資料。不包進發布版。"""
from __future__ import annotations

import csv
import random
import tempfile
from pathlib import Path

import uvicorn
from PIL import Image, ImageDraw, ImageFilter

from app.main import create_app

PORT = 8130  # 不和正式網站（8100 起）搶連接埠
SIZE = (1000, 760)


def synthetic(seed: int) -> Image.Image:
    rng = random.Random(seed)
    w, h = SIZE
    image = Image.new('L', SIZE, 0)
    draw = ImageDraw.Draw(image)
    draw.polygon([(380, 60), (620, 60), (940, 640), (500, 720), (60, 640)], fill=70)
    draw.polygon([(380, 60), (620, 60), (760, 320), (240, 320)], fill=105)
    cx, cy = 500 + rng.randint(-40, 40), 430 + rng.randint(-20, 20)
    draw.ellipse([cx - 240, cy - 130, cx + 240, cy + 130], fill=55)
    draw.ellipse([cx - 120, cy - 50, cx + 120, cy + 50], fill=170)
    draw.ellipse([cx + 150, cy - 20, cx + 200, cy + 30], fill=8)
    noise = Image.effect_noise(SIZE, 32).filter(ImageFilter.GaussianBlur(1))
    return Image.blend(image.filter(ImageFilter.GaussianBlur(3)), noise, 0.28)


def main() -> None:
    temp = Path(tempfile.mkdtemp(prefix='circling-demo-'))
    export = temp / 'export'
    export.mkdir()
    with (export / '清單.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['序號', '影像ID', '側別', '要圈的構造', '備註'])
        for n in range(1, 7):
            image_id = f'IMG-{n:012X}'
            synthetic(n).save(export / f'{image_id}.jpg', quality=92)
            writer.writerow([n, image_id, '未知' if n == 6 else '右' if n % 2 else '左', '', ''])
    print(f'合成影像資料夾：{export}', flush=True)
    uvicorn.run(create_app(temp / 'site'), host='127.0.0.1', port=PORT, log_level='warning', log_config=None)


if __name__ == '__main__':
    main()
