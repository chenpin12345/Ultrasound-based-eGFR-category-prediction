from __future__ import annotations

import re
import uuid
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
            features_root=settings.project_root / "features",
            cpu_workers=cpu_workers,
        )
    except ImportError:
        # Read-only/listing endpoints remain usable when optional workers are not installed.
        pass
    yield
    try:
        from .workers.manager import worker_shutdown

        worker_shutdown()
    except ImportError:
        pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_error_handlers(app)
    from .api.routes.workflow import router as workflow_router
    for router in (system_router, workflow_router, datasets_router, jobs_router, training_router, models_router):
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
