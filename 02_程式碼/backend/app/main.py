"""FastAPI 應用程式。

啟動時：建立資料夾 → 資料庫遷移 → 預設版面範本 → 恢復背景工作 → 每日資料庫快照。
每個 /api 請求：檢查路由已登記 → 檢查本機工作階段（寫入另外檢查 CSRF）。
"""

from __future__ import annotations

import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from .core import routes_table, session
from .core.config import ensure_directories, get_settings
from .core.errors import AppError, error_payload, install_error_handlers
from .db.session import migrate_all, session_scope
from .jobs.manager import get_manager

logger = logging.getLogger(__name__)


def _register_job_handlers() -> None:
    from .data import importer  # noqa: F401  註冊 import 工作
    from .annotation import circling, drafts  # noqa: F401  醫師圈選匯出與讀取；舊遮罩、MedSAM、肝脾草稿
    from .features import service  # noqa: F401  擷取回音特徵
    from .ml import baseline, egfr_compare, evaluation, masksets, nnunet, pipeline, pretrained, runs  # noqa: F401
    from .clinical import analysis, models_cache, receiver  # noqa: F401  醫師端：預先載入模型、收圖與去識別化、自動分析（M3）


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_directories(settings)
    migrate_all()
    from .data.templates import seed_defaults

    with session_scope('research') as db:
        seed_defaults(db)
    _register_job_handlers()
    from .jobs.manager import FINISH_HOOKS
    from .services import index, workspace

    workspace.ensure_readmes()
    workspace.cleanup_empty_mask_dirs()  # 只刪空資料夾（例如永久刪除草稿後留下的）
    workspace.cleanup_legacy_clinical_dirs()  # M3 改用新的醫師端資料夾；舊的空資料夾（只刪空的）
    if index.after_job not in FINISH_HOOKS:
        FINISH_HOOKS.append(index.after_job)
    from .clinical import receiver

    receiver.recover()  # 上次沒停止的雙機接收標成「中斷」
    get_manager().recover()
    if not settings.testing:
        try:
            from .services.backups import daily_snapshot

            daily_snapshot()
        except Exception:  # noqa: BLE001
            logger.exception('每日資料庫快照失敗')
        index.refresh_quietly()
    yield
    receiver.stop()
    get_manager().shutdown()


def create_app(testing: bool = False) -> FastAPI:
    app = FastAPI(title='腎超工作台 API', version='0.2.0', lifespan=lifespan, docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)
    app.state.testing = testing or get_settings().testing
    app.state.boot_id = secrets.token_hex(8)
    app.state.challenges = {}
    install_error_handlers(app)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        path = request.url.path
        if path.startswith('/api'):
            try:
                if not routes_table.is_public(request.method, path):
                    if not routes_table.is_registered(path):
                        raise AppError(403, 'API_NOT_REGISTERED', '這個 API 沒有登記在路由表。')
                    session.require(request)
            except AppError as exc:
                return JSONResponse(status_code=exc.status_code, content=error_payload(request, exc.code, exc.message, exc.details))
        response = await call_next(request)
        if path.startswith('/api') and 'cache-control' not in response.headers:
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    from .api.routes import circling, clinical, data, egfr, jobs, ml, research, system

    for module in (system, jobs, data, research, ml, circling, egfr, clinical):
        app.include_router(module.router, prefix='/api')
    app.include_router(session.router, prefix='/api')

    dist = get_settings().frontend_dist

    @app.get('/{full_path:path}', include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith('api/'):
            return JSONResponse(status_code=404, content={'error': {'code': 'NOT_FOUND', 'message': '找不到這個 API。'}})
        candidate = (dist / full_path).resolve()
        if full_path and dist in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index = dist / 'index.html'
        if index.exists():
            return FileResponse(index, headers={'Cache-Control': 'no-store'})
        return JSONResponse(status_code=503, content={'error': {'code': 'FRONTEND_NOT_BUILT', 'message': '前端尚未建置，請執行 setup.bat。'}})

    return app


def _dist_ok(path: Path) -> bool:
    return (path / 'index.html').exists()


app = create_app()
