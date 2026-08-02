from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.config import AppSettings, get_settings
from ...db.models import Setting
from ...db.session import db_healthcheck, get_db
from ...schemas.settings import SettingsOut, SettingsUpdate
from ...services.settings_service import effective_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    db_healthcheck()
    return {"status": "ok", "database": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/system/info")
def system_info(settings: AppSettings = Depends(get_settings)) -> dict:
    memory = None
    cpu_percent = None
    try:
        import psutil

        vm = psutil.virtual_memory()
        memory = {"total": vm.total, "available": vm.available, "percent": vm.percent}
        cpu_percent = psutil.cpu_percent(interval=None)
    except ImportError:
        pass

    cuda = {"available": False, "device_count": 0, "devices": []}
    try:
        import torch

        available = bool(torch.cuda.is_available())
        cuda = {
            "available": available,
            "device_count": torch.cuda.device_count() if available else 0,
            "devices": [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())] if available else [],
        }
    except ImportError:
        pass

    return {
        "application": {"name": settings.app_name, "version": settings.app_version},
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "machine": platform.machine(),
            "process_id": os.getpid(),
        },
        "resources": {"cpu_count": os.cpu_count(), "cpu_percent": cpu_percent, "memory": memory, "cuda": cuda},
        "capabilities": {
            "dataset_import": True,
            "zip_import": True,
            "training": True,
            "inference": True,
            "sse": True,
        },
    }


@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)) -> dict:
    return effective_settings(db)


@router.put("/settings", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> dict:
    for key, value in payload.values_to_store().items():
        setting = db.get(Setting, key)
        if setting:
            setting.value_json = value
        else:
            db.add(Setting(key=key, value_json=value))
    db.commit()
    return effective_settings(db)
