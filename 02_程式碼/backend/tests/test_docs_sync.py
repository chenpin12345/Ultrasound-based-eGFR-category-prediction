"""文件檢查（決策 D32）：程式裡有的，01_計畫與文件 的對應文件就一定要寫。

只檢查「程式 → 文件」這個方向：文件中標示【M2.5 規劃】【M3 規劃】的項目不會造成失敗。
只確認名稱有寫進文件，說明是否正確仍要人工確認。
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIRoute

ROOT = Path(__file__).resolve().parents[3]
DOCS = next(ROOT.glob('01_*'))
APP_TSX = Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'App.tsx'
PARAM = re.compile(r'\{[^}]*\}')


def _doc(name: str) -> str:
    return (DOCS / name).read_text(encoding='utf-8')


def _report(missing: list[str], doc: str, how: str) -> str:
    return f'下列項目沒有寫在 01_計畫與文件/{doc}，請補上（{how}）：\n  ' + '\n  '.join(missing)


def test_every_api_route_is_documented(workspace):
    from app.main import create_app

    text = PARAM.sub('{}', _doc('API規格.md'))
    missing = []
    for r in create_app(testing=True).routes:
        if not isinstance(r, APIRoute) or not r.path.startswith('/api'):
            continue
        for method in sorted(r.methods - {'HEAD', 'OPTIONS'}):
            entry = f'{method} {PARAM.sub("{}", r.path)}'
            if f'`{entry}`' not in text:
                missing.append(entry)
    assert not missing, _report(missing, 'API規格.md', '在對應的表格加一列，格式 `方法 /api/路徑`')


def test_every_table_is_documented():
    from app.db import models_research, models_system  # noqa: F401
    from app.db.base import ResearchBase, SystemBase

    text = _doc('資料庫與檔案設計.md')
    tables = sorted(set(SystemBase.metadata.tables) | set(ResearchBase.metadata.tables))
    missing = [t for t in tables if f'`{t}`' not in text]
    assert not missing, _report(missing, '資料庫與檔案設計.md', '在第 1 節加上資料表，表名寫成 `表名`')


def _frontend_paths() -> list[str]:
    """依 <Route> 的巢狀結構組出完整路徑（index 路由沒有 path，略過）。"""
    stack: list[str] = []
    paths: list[str] = []
    for line in APP_TSX.read_text(encoding='utf-8').splitlines():
        m = re.search(r'<Route\s+path="([^"]+)"', line)
        if m:
            path = m.group(1)
            full = '/' + '/'.join([*stack, path]) if path != '*' else '*'
            paths.append(full)
            if not line.rstrip().endswith('/>'):
                stack.append(path)
        elif re.search(r'<Route\b', line) and 'path=' not in line and not line.rstrip().endswith('/>'):
            stack.append('')  # 沒有路徑的版面路由（例如 AppShell）
        if '</Route>' in line and stack:
            stack.pop()
    return [p.replace('//', '/') for p in paths]


def test_every_frontend_route_is_documented():
    text = _doc('網頁規格.md')
    missing = [p for p in _frontend_paths() if f'`{p}`' not in text]
    assert not missing, _report(missing, '網頁規格.md', '在 §1 的表格加一列，路徑寫成 `/完整/路徑`')


def test_every_job_kind_is_documented(workspace):
    import app.main as main
    from app.jobs.manager import HANDLERS

    main._register_job_handlers()
    text = _doc('系統架構.md')
    missing = sorted(k for k in HANDLERS if f'`{k}`' not in text)
    assert not missing, _report(missing, '系統架構.md', '在 §4.2 的表格加一列，種類寫成 `種類`')
