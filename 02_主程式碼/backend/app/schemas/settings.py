from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    language: str | None = Field(default=None, pattern="^(zh-TW|en)$")
    cpu_workers: int | None = Field(default=None, ge=1, le=32)
    gpu_enabled: bool | None = None
    default_seed: int | None = None
    thumbnail_size: int | None = Field(default=None, ge=64, le=1024)

    def values_to_store(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class SettingsOut(BaseModel):
    language: str = "zh-TW"
    cpu_workers: int = 2
    gpu_enabled: bool = True
    default_seed: int = 42
    thumbnail_size: int = 384
