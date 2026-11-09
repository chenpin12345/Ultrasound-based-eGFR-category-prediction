"""多邊形轉像素：和畫面一致（像素中心在多邊形內才算），和另一套獨立算法逐像素相同。"""
import random

import numpy as np
import pytest
from PIL import Image

from app import raster
from app.export import rasterize

SIZES = [(622, 500), (666, 500), (1493, 1200), (1600, 1200)]  # 真實影像的四種尺寸


def reference(points, w, h):
    xs, ys = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    pts = np.array(points, float)
    inside = np.zeros((h, w), bool)
    for (x0, y0), (x1, y1) in zip(pts, np.roll(pts, -1, axis=0)):
        crosses = (y0 <= ys) != (y1 <= ys)
        with np.errstate(divide='ignore', invalid='ignore'):
            x_at = x0 + (ys - y0) * (x1 - x0) / (y1 - y0)
        inside ^= crosses & (xs < x_at)
    return inside


def test_axis_aligned_square_has_exact_area():
    mask = np.array(raster.mask([{'points': [[50, 50], [250, 50], [250, 200], [50, 200]]}], 320, 240)) > 0
    assert mask.sum() == 200 * 150
    assert mask[50, 50] and mask[199, 249] and not mask[49, 50] and not mask[200, 50] and not mask[50, 250]


@pytest.mark.parametrize('size', SIZES)
def test_random_polygons_match_independent_algorithm(size):
    w, h = size
    rng = random.Random(size[0])
    for _ in range(25):
        n = rng.randint(3, 40)
        points = [[round(rng.uniform(-20, w + 20), 1), round(rng.uniform(-20, h + 20), 1)] for _ in range(n)]
        assert np.array_equal(np.array(raster.mask([{'points': points}], w, h)) > 0, reference(points, w, h))


def test_vertices_on_pixel_centers_and_edges():
    points = [[10.5, 10.5], [30.5, 10.5], [30.5, 20.5], [20, 20], [10.5, 30.5]]
    assert np.array_equal(np.array(raster.mask([{'points': points}], 40, 40)) > 0, reference(points, 40, 40))


def test_label_order_and_values_independent_of_drawing_order():
    w, h = 622, 500
    shapes = [{'structure': 'sinus', 'points': [[250, 200], [350, 200], [350, 260], [250, 260]]},
              {'structure': 'kidney', 'points': [[150, 150], [450, 150], [450, 330], [150, 330]]},
              {'structure': 'liver', 'points': [[0, 0], [622, 0], [622, 180], [0, 180]]},
              {'structure': 'cyst', 'points': [[160, 160], [200, 160], [200, 200]]}]
    label = np.array(rasterize(shapes, w, h))
    expected = np.zeros((h, w), np.uint8)
    for code, value in (('liver', 3), ('kidney', 1), ('sinus', 2)):
        expected[reference(next(s for s in shapes if s['structure'] == code)['points'], w, h)] = value
    assert np.array_equal(label, expected)
    assert set(np.unique(label)) == {0, 1, 2, 3}


def test_old_pil_fill_grew_every_outline():
    """改寫前用 PIL：輪廓邊緣的像素會多算進來，遮罩系統性偏大（腎臟約多 0.2%，小的結石、腎竇比例更高）。"""
    from PIL import ImageDraw

    w, h = 622, 500
    points = [[311 + 140 * np.cos(t) + 0.3, 250 + 80 * np.sin(t) + 0.3] for t in np.linspace(0, 2 * np.pi, 60, endpoint=False)]
    old = Image.new('L', (w, h), 0)
    ImageDraw.Draw(old).polygon([tuple(p) for p in points], fill=1)
    exact = reference(points, w, h)
    assert (np.array(old) > 0).sum() > exact.sum()
