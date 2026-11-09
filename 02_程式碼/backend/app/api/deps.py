"""路由共用：目前操作者（前端以 X-Operator 標頭傳送名單裡選的人）。"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import Request


def operator(request: Request) -> str:
    value = unquote(request.headers.get('x-operator', '')).strip()
    return value[:80] or '本機'
