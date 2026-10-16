from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from backend.app.core.config import AppSettings
SERVER_RECORD = AppSettings().runtime_dir / "run" / "server.json"


def main() -> int:
    if not SERVER_RECORD.exists():
        print("本專案目前沒有執行中的服務。")
        return 0

    try:
        record = json.loads(SERVER_RECORD.read_text(encoding="utf-8"))
        pid = int(record["pid"])
        expected_created = float(record.get("create_time", 0))
    except (OSError, ValueError, KeyError, TypeError):
        print("服務紀錄損壞；為避免誤關其他程序，不會執行停止。", file=sys.stderr)
        return 1

    import psutil

    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        SERVER_RECORD.unlink(missing_ok=True)
        print("服務已不在執行，已清除過期紀錄。")
        return 0

    command = " ".join(process.cmdline()).lower()
    same_process = not expected_created or abs(process.create_time() - expected_created) <= 1
    belongs_to_project = str(PROJECT_ROOT).lower() in command and "run_server.py" in command
    if not same_process or not belongs_to_project:
        print("PID 已被其他程序使用；為避免誤關，不會停止該程序。", file=sys.stderr)
        return 1

    # Capture only descendants of the verified project process. Never enumerate
    # unrelated Python processes by name, and guard against PID reuse below.
    descendants = [(child, child.create_time()) for child in process.children(recursive=True)]
    process.terminate()
    try:
        process.wait(timeout=15)
    except psutil.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    for child, created in descendants:
        try:
            if child.is_running() and abs(child.create_time() - created) <= 1:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except psutil.TimeoutExpired:
                    child.kill()
        except psutil.NoSuchProcess:
            pass
    SERVER_RECORD.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
