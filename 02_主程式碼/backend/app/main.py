from __future__ import annotations

import re
import uuid
import asyncio
import secrets
from contextlib import suppress
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import datasets_router, jobs_router, models_router, system_router, training_router
from .core.config import get_settings
from .core.errors import install_error_handlers
from .db.session import get_session_factory, init_db

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    init_db()
    from .clinical import store, transfer
    store.migrate()
    from .clinical import monitor,analysis_runs,pdf_artifacts
    pdf_artifacts.recover_and_import()
    analysis_runs.recover()
    monitor.recover()
    transfer.recover()
    async def maintain_clinical():
        from starlette.concurrency import run_in_threadpool
        while True:
            await asyncio.sleep(60)
            await run_in_threadpool(transfer.expire)
    maintenance=asyncio.create_task(maintain_clinical())
    try:
        from .workers.manager import configure_worker_manager
        from .services.settings_service import persisted_setting

        session_factory = get_session_factory()
        with session_factory() as db:
            cpu_workers = int(persisted_setting(db, "cpu_workers", 2))

        configure_worker_manager(
            session_factory=session_factory,
            data_root=settings.data_dir,
            models_root=settings.models_dir,
            features_root=settings.reference_features_dir,
            cpu_workers=cpu_workers,
        )
    except ImportError:
        # Read-only/listing endpoints remain usable when optional workers are not installed.
        pass
    try:
        yield
    finally:
        maintenance.cancel()
        with suppress(asyncio.CancelledError): await maintenance
        transfer.shutdown()
    try:
        from .workers.manager import worker_shutdown

        worker_shutdown()
    except ImportError:
        pass


def create_app(*, testing: bool = False) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.local_testing = testing
    app.state.local_boot_id = secrets.token_urlsafe(32)
    app.state.local_challenges = {}
    app.state.model_mutation_lock = asyncio.Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID", "X-Request-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        from .clinical.auth import check_origin, current
        from .core.errors import AppError, error_payload
        from fastapi.responses import JSONResponse
        try:
            check_origin(request)
            path = request.url.path
            if path.startswith('/api/'):
                public = path == '/api/health' or path.startswith('/api/auth/') or (
                    path == '/api/local-session/challenge' and request.method == 'GET'
                ) or (path == '/api/local-session' and request.method == 'POST')
                if not public and request.method != 'OPTIONS':
                    readonly = request.method in {'GET', 'HEAD'}
                    if path.startswith('/api/clinical/reports') and not readonly:
                        capability = 'reports.manage'
                    elif path.startswith('/api/clinical/'):
                        capability = 'clinical.read' if readonly else 'clinical.operate'
                    elif path.startswith('/api/models'):
                        capability = 'research.read' if readonly else 'models.manage'
                    elif path.startswith('/api/settings'):
                        capability = 'research.read' if readonly else 'system.manage'
                    else:
                        capability = 'research.read' if readonly else 'research.execute'
                    current(request, capability)
        except AppError as exc:
            return JSONResponse(error_payload(request,exc.code,exc.message),status_code=exc.status_code)
        from .core.model_coordination import coordinates
        if coordinates(request.method,request.url.path):
            # Cover reference validation through DB commit/file publication;
            # a plan/job cannot race between a deletion's check and rename.
            async with app.state.model_mutation_lock:
                response = await call_next(request)
        else:
            response = await call_next(request)
        if request.url.path.startswith(('/api/clinical/','/api/auth/','/api/local-session')):
            response.headers['Cache-Control']='no-store'
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_error_handlers(app)
    from .api.routes.workflow import router as workflow_router
    from .api.routes.evaluations import router as evaluations_router
    from .clinical.auth import router as auth_router
    from .clinical.routes import router as clinical_router
    from .clinical.transfer import router as transfer_router
    from .clinical.monitor import router as monitor_router
    from .clinical.lifecycle import router as lifecycle_router
    from .clinical.defaults import router as defaults_router
    for router in (auth_router, clinical_router, transfer_router, defaults_router, monitor_router, lifecycle_router, system_router, workflow_router, datasets_router, jobs_router, training_router, models_router, evaluations_router):
        app.include_router(router, prefix=settings.api_prefix)

    if settings.frontend_dist.is_dir() and (settings.frontend_dist / "index.html").is_file():
        assets = settings.frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend_fallback(path: str):
            if path == "api" or path.startswith("api/"):
                from .core.errors import AppError
                raise AppError(404, "API_NOT_FOUND", "找不到指定 API。")
            requested = (settings.frontend_dist / path).resolve()
            try:
                requested.relative_to(settings.frontend_dist.resolve())
            except ValueError:
                requested = settings.frontend_dist / "index.html"
            if requested.is_file() and requested.name != "index.html":
                return FileResponse(requested)
            return FileResponse(settings.frontend_dist / "index.html", media_type="text/html")
    else:
        @app.get("/", include_in_schema=False)
        async def api_root() -> dict:
            return {"name": settings.app_name, "version": settings.app_version, "api": "/api/docs"}
    return app


app = create_app()
