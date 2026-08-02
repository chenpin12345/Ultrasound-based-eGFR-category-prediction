from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from backend.app.core.config import get_settings
    from backend.app.db.session import init_db

    settings = get_settings()
    for path in (
        settings.data_dir,
        settings.datasets_dir,
        settings.jobs_dir,
        settings.outputs_dir,
        settings.training_dir,
        settings.models_dir,
    ):
        Path(path).mkdir(parents=True, exist_ok=True)
    init_db()
    marker = Path(settings.data_dir) / ".setup-complete"
    marker.write_text("ISU AI KUA setup complete\n", encoding="utf-8")
    print(f"資料庫與工作目錄已就緒：{settings.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
