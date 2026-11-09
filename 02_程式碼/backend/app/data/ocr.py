"""OCR（RapidOCR，模型內建、離線執行）。

只回傳解析後的欄位（年齡、性別、量測值、側別、掃描參數），標頭的原始文字含有姓名與病歷號，
讀完就丟棄，不寫入資料庫或日誌。
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

import numpy as np

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


@dataclass
class Token:
    text: str
    confidence: float
    cx: float
    cy: float


def read_tokens(image: np.ndarray, min_confidence: float = 0.5) -> list[Token]:
    """影像（BGR 或灰階）→ 文字片段與位置（位置以傳入影像的像素為準）。"""
    if image.size == 0:
        return []
    h, w = image.shape[:2]
    scale = 1.0
    if max(h, w) < 64:  # 太小的區域放大，提高辨識率
        scale = 64 / max(h, w)
    if scale != 1.0:
        import cv2

        image = cv2.resize(image, (int(w * scale) + 1, int(h * scale) + 1), interpolation=cv2.INTER_CUBIC)
    with _lock:
        # 文字都是水平的，不需要方向分類（use_cls=False 可省下約三成時間）
        result, _ = _get_engine()(image, use_cls=False)
    tokens: list[Token] = []
    for box, text, conf in result or []:
        if float(conf) < min_confidence:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        tokens.append(Token(str(text), float(conf), sum(xs) / 4 / scale, sum(ys) / 4 / scale))
    return tokens


def joined(tokens: list[Token]) -> str:
    return ' '.join(t.text for t in sorted(tokens, key=lambda t: (round(t.cy / 8), t.cx)))


@dataclass
class HeaderFields:
    age: int | None = None
    sex: str | None = None


def parse_header(text: str) -> HeaderFields:
    """Toshiba：「病歷號:姓名:78:F」；Canon：「F 67」。只取年齡與性別。"""
    m = re.search(r':\s*(\d{1,3})\s*:\s*([MF])\b', text)
    if m:
        return HeaderFields(age=int(m.group(1)), sex=m.group(2))
    # OCR 有時會把「F 67」讀成「F67」，所以空白可有可無；前後不能接英數字，避免誤抓病歷號或姓名
    m = re.search(r'(?<![A-Za-z0-9:])([MF])\s*(\d{1,3})(?![\d.A-Za-z])', text)
    if m and 0 < int(m.group(2)) < 120:
        return HeaderFields(age=int(m.group(2)), sex=m.group(1))
    return HeaderFields()


@dataclass
class MeasureFields:
    dist_a_mm: float | None = None
    dist_b_mm: float | None = None


def parse_measure(text: str) -> MeasureFields:
    norm = text.replace(' ', '')
    a = re.search(r'DistA([\d.]+)mm', norm, re.I)
    b = re.search(r'DistB([\d.]+)mm', norm, re.I)
    return MeasureFields(float(a.group(1)) if a else None, float(b.group(1)) if b else None)


def parse_side(text: str) -> str | None:
    norm = text.upper().replace(' ', '')
    if re.search(r'(^|[^A-Z])(L|LT|LEFT)[-_]?KIDNEY', norm):
        return 'left'
    if re.search(r'(^|[^A-Z])(R|RT|RIGHT)[-_]?KIDNEY', norm):
        return 'right'
    return None


@dataclass
class ParamFields:
    gain: int | None = None
    tokens: list[str] = field(default_factory=list)


def parse_params(tokens: list[Token]) -> ParamFields:
    texts = [t.text for t in sorted(tokens, key=lambda t: t.cy)]
    gain = None
    for text in texts:
        m = re.search(r'G\s*[:：]\s*(\d{2,3})', text)
        if m:
            gain = int(m.group(1))
    return ParamFields(gain=gain, tokens=[t for t in texts if len(t) <= 16][:20])


PHI_PATTERNS = (
    re.compile(r'\d{6,}'),  # 病歷號
    re.compile(r'[A-Z]{2,}\s+[A-Z]{2,}'),  # 拼音姓名
    re.compile(r':\s*\d{1,3}\s*:\s*[MF]'),
    re.compile(r'HOSPITAL', re.I),
)


def looks_like_phi(tokens: list[Token]) -> list[str]:
    """去識別化後的檢查：回傳可疑片段的「類型」，不回傳文字本身。"""
    kinds = []
    text = ' '.join(t.text for t in tokens)
    names = ['病歷號格式', '姓名格式', '年齡性別格式', '醫院名稱']
    for name, pattern in zip(names, PHI_PATTERNS):
        if pattern.search(text):
            kinds.append(name)
    return kinds
