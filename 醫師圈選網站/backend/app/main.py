"""API 與靜態網頁。只接受本機連線；影像含個資，不能讓其他網頁或電腦讀取。"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import export, images, structures
from .core import AppError, Paths, Store, default_root, frontend_dist

LOCAL_HOSTS = {'127.0.0.1', 'localhost', 'testserver'}
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def create_app(root: Path | None = None) -> FastAPI:
    store = Store(Paths(root or default_root()))
    structures.seed(store)
    store.backup(force=True)
    app = FastAPI(title='醫師圈選網站', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = urlsplit(f'//{request.headers.get("host", "")}').hostname
        origin = request.headers.get('origin')
        if host not in LOCAL_HOSTS or (origin and request.method not in SAFE_METHODS and urlsplit(origin).hostname not in LOCAL_HOSTS):
            return JSONResponse({'error': {'code': 'LOCAL_ONLY', 'message': '只接受本機連線。'}}, status_code=403)
        return await call_next(request)

    @app.exception_handler(AppError)
    async def app_error(_: Request, error: AppError):
        return JSONResponse({'error': {'code': error.code, 'message': error.message}}, status_code=error.status)

    @app.get('/api/summary')
    def get_summary() -> dict[str, Any]:
        return images.summary(store)

    @app.put('/api/circler')
    def put_circler(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
        code = str(data.get('circler') or '').strip()[:40]
        store.set_meta('circler', code)
        return {'circler': code}

    @app.post('/api/import')
    def post_import(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return images.import_folder(store, str(data.get('folder') or ''))

    @app.get('/api/images')
    def get_images(status: str = '') -> list[dict[str, Any]]:
        return images.list_images(store, status)

    @app.get('/api/images/{image_id}')
    def get_image(image_id: str) -> dict[str, Any]:
        return images.image_detail(store, image_id)

    @app.get('/api/images/{image_id}/file')
    def get_image_file(image_id: str) -> FileResponse:
        return FileResponse(images.image_file(store, image_id), headers={'Cache-Control': 'no-store'})

    @app.put('/api/images/{image_id}')
    def put_image(image_id: str, data: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return images.save_image(store, image_id, data)

    @app.post('/api/images/{image_id}/complete')
    def post_complete(image_id: str, data: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return images.complete_image(store, image_id, bool(data.get('force')))

    @app.get('/api/structures')
    def get_structures() -> dict[str, Any]:
        return {'structures': structures.list_structures(store), 'palette': structures.PALETTE}

    @app.post('/api/structures/color-check')
    def post_color_check(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
        others = [s for s in structures.list_structures(store) if s['code'] != data.get('code') and s['active']]
        color = str(data.get('color') or '')
        return {'warnings': structures.color_warnings(color, others) if structures.HEX.match(color) else []}

    @app.post('/api/structures')
    def post_structure(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return structures.create_structure(store, data)

    @app.patch('/api/structures/{code}')
    def patch_structure(code: str, data: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return structures.update_structure(store, code, data)

    @app.delete('/api/structures/{code}')
    def delete_structure(code: str) -> dict[str, Any]:
        structures.delete_structure(store, code)
        return {'ok': True}

    @app.post('/api/export')
    def post_export() -> dict[str, Any]:
        return export.export_results(store)

    @app.get('/api/{rest:path}')
    def unknown_api(rest: str):
        raise AppError(404, 'NOT_FOUND', '找不到這個功能。')

    @app.get('/{path:path}')
    def serve_page(path: str):
        dist = frontend_dist().resolve()
        target = (dist / path).resolve()
        if path and target.is_file() and target.is_relative_to(dist):
            return FileResponse(target)
        index = dist / 'index.html'
        if not index.is_file():
            raise AppError(503, 'FRONTEND_NOT_BUILT', '網頁還沒建置。請先在 frontend 執行 pnpm build。')
        return FileResponse(index, headers={'Cache-Control': 'no-store'})

    return app
