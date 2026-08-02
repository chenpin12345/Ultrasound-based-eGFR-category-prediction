"""Validated access to settings persisted in SQLite."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Setting
from ..schemas.settings import SettingsOut, SettingsUpdate


DEFAULT_SETTINGS = SettingsOut().model_dump()


def effective_settings(db: Session) -> dict[str, Any]:
    """Return the complete public settings object with stored overrides."""

    values = dict(DEFAULT_SETTINGS)
    for setting in db.scalars(select(Setting)).all():
        if setting.key in values:
            values[setting.key] = setting.value_json
    return SettingsOut.model_validate(values).model_dump()


def persisted_setting(db: Session, key: str, fallback: Any) -> Any:
    """Return one validated stored setting, or a caller-provided fallback."""

    setting = db.get(Setting, key)
    if setting is None or key not in DEFAULT_SETTINGS:
        return fallback
    try:
        validated = SettingsUpdate.model_validate({key: setting.value_json})
    except (TypeError, ValueError, ValidationError):
        return fallback
    result = getattr(validated, key)
    return fallback if result is None else result
