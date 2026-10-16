"""Fonts shared by the clinical PDF templates.

ReportLab has no per-glyph fallback: a character missing from the paragraph font
is drawn as the .notdef box. Microsoft JhengHei lacks e.g. U+2265 (≥) used in
eGFR class names, so such characters are wrapped in a symbol-font run instead.
The candidate order is fixed, so the same machine always renders the same bytes.
"""
from __future__ import annotations
import itertools
import os
from pathlib import Path
from xml.sax.saxutils import escape

PRIMARY='ClinicalCJK'
SYMBOL='ClinicalSymbol'


def symbol_candidates():
    fonts=Path(os.getenv('WINDIR','C:/Windows'))/'Fonts'
    configured=os.getenv('ISU_CLINICAL_SYMBOL_FONT')
    # Segoe UI is the Latin design JhengHei itself is based on; the rest are wider-coverage fallbacks.
    return ([Path(configured)] if configured else [])+[fonts/'segoeui.ttf',fonts/'arial.ttf',fonts/'seguisym.ttf']


def register(font):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    registered=pdfmetrics.getRegisteredFontNames()
    if PRIMARY not in registered:pdfmetrics.registerFont(TTFont(PRIMARY,str(font),subfontIndex=0))
    if SYMBOL not in registered:
        symbol=next((path for path in symbol_candidates() if path.is_file()),None)
        if symbol:pdfmetrics.registerFont(TTFont(SYMBOL,str(symbol),subfontIndex=0))


def cmap(name):
    from reportlab.pdfbase import pdfmetrics
    return pdfmetrics.getFont(name).face.charToGlyph if name in pdfmetrics.getRegisteredFontNames() else {}


def font_for(char,primary=None,symbol=None):
    """Registered font name that will draw ``char``, or None if no font has the glyph."""
    primary=cmap(PRIMARY) if primary is None else primary
    symbol=cmap(SYMBOL) if symbol is None else symbol
    if char.isspace() or ord(char) in primary:return PRIMARY
    return SYMBOL if ord(char) in symbol else None


def markup(text):
    """Escape ``text`` for a Paragraph, routing glyphs the CJK font lacks to the symbol font."""
    primary,symbol=cmap(PRIMARY),cmap(SYMBOL)
    parts=[]
    for fallback,run in itertools.groupby(str(text),key=lambda char:font_for(char,primary,symbol)==SYMBOL):
        run=escape(''.join(run))
        parts.append(f'<font name="{SYMBOL}">{run}</font>' if fallback else run)
    return ''.join(parts)
