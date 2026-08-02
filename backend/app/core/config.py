from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class AppSettings(BaseSettings):
    """Environment-backed settings. Filesystem values never leave the API."""

    model_config = SettingsConfigDict(
        env_prefix="ISU_AI_",
        env_file=str(PROJECT_ROOT / ".env"),
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
