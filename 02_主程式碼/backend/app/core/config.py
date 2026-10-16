from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from workspace_paths import CODE_ROOT, WORKSPACE_ROOT, ENV_FILE, LAYOUT, default_path


PROJECT_ROOT = CODE_ROOT


class AppSettings(BaseSettings):
    """Environment-backed settings. Filesystem values never leave the API."""

    model_config = SettingsConfigDict(
        env_prefix="ISU_AI_",
        env_file=str(ENV_FILE),
        extra="ignore",
    )

    app_name: str = "義守大學 AI 腎功能影像平台"
    app_version: str = "1.0.0"
    api_prefix: str = "/api"
    debug: bool = False

    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    models_dir: Path = PROJECT_ROOT / "models"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"
    database_url: str | None = None
    clinical_dir: Path | None = None
    reports_dir: Path | None = None
    runtime_dir: Path | None = None
    reference_features_dir: Path | None = None
    require_existing_databases: bool = False

    @model_validator(mode='before')
    @classmethod
    def resolve_workspace_roots(cls, values):
        values = dict(values)
        # Existing DATA_DIR overrides remain isolated, including legacy tests/tools.
        custom_data = 'data_dir' in values
        values.setdefault('data_dir', default_path('research_data', PROJECT_ROOT / 'data'))
        values.setdefault('models_dir', default_path('models', PROJECT_ROOT / 'models'))
        base = Path(values['data_dir'])
        if not base.is_absolute():
            base = WORKSPACE_ROOT / base
        if custom_data:
            values.setdefault('clinical_dir', base / 'clinical')
            values.setdefault('reports_dir', base / 'clinical' / 'reports')
            values.setdefault('runtime_dir', base / 'runtime')
        else:
            values.setdefault('clinical_dir', default_path('clinical', base / 'clinical'))
            values.setdefault('reports_dir', default_path('reports', base / 'clinical' / 'reports'))
            values.setdefault('runtime_dir', default_path('runtime', base / 'run'))
            values.setdefault('require_existing_databases', LAYOUT.get('require_existing_databases', False))
        values.setdefault('reference_features_dir', default_path('reference_features', PROJECT_ROOT / 'features'))
        for key in ('project_root', 'data_dir', 'models_dir', 'frontend_dist', 'clinical_dir',
                    'reports_dir', 'runtime_dir', 'reference_features_dir'):
            if key in values:
                path = Path(values[key])
                values[key] = (path if path.is_absolute() else WORKSPACE_ROOT / path).resolve()
        return values

    max_upload_bytes: int = 512 * 1024 * 1024
    max_metadata_bytes: int = 10 * 1024 * 1024
    max_zip_entries: int = 10_000
    max_zip_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    max_zip_entry_bytes: int = 512 * 1024 * 1024
    max_zip_compression_ratio: float = 100.0
    max_image_pixels: int = 100_000_000
    thumbnail_size: int = Field(default=384, ge=64, le=1024)
    sse_heartbeat_seconds: float = Field(default=10.0, ge=1.0, le=60.0)

    allowed_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def training_dir(self) -> Path:
        return self.data_dir / "training"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "isu_ai.sqlite3"

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.sqlite_path.as_posix()}"

    def ensure_directories(self) -> None:
        if (self.runtime_dir / 'maintenance-operation.json').exists():
            raise RuntimeError('Offline backup/restore is in progress; wait or explicitly recover an abandoned operation')
        if self.require_existing_databases and (WORKSPACE_ROOT / '.maintenance/migration-in-progress.json').exists():
            raise RuntimeError('Workspace migration is not yet validated; keep using the original installation')
        if (self.runtime_dir / 'restore-journal.json').exists():
            raise RuntimeError('Unfinished multi-root restore; run workspace_backup.py recover before startup')
        if (self.runtime_dir / 'schema-upgrade-journal.json').exists():
            raise RuntimeError('Database upgrade is incomplete; keep the service stopped and inspect the upgrade journal before restoring a matched backup')
        if self.require_existing_databases:
            for database in (self.sqlite_path, self.clinical_dir / 'clinical.sqlite3'):
                if not database.is_file():
                    raise RuntimeError('Expected migrated database is missing; refusing empty initialization: ' + str(database))
        for path in (
            self.data_dir,
            self.datasets_dir,
            self.jobs_dir,
            self.outputs_dir,
            self.training_dir,
            self.uploads_dir,
            self.temp_dir,
            self.models_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.ensure_directories()
    return settings
