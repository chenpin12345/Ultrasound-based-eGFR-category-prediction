from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import AppSettings
from workspace_paths import ENV_FILE

RUN_DIR = AppSettings().runtime_dir / "run"
SERVER_RECORD = RUN_DIR / "server.json"


def _load_env_file() -> None:
    path = ENV_FILE
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _is_record_process_alive(record: dict[str, object]) -> bool:
    try:
        import psutil

        process = psutil.Process(int(record["pid"]))
        expected = float(record.get("create_time", 0))
        if expected and abs(process.create_time() - expected) > 1:
            return False
        command = " ".join(process.cmdline()).lower()
        return str(PROJECT_ROOT).lower() in command and "run_server.py" in command
    except Exception:
        return False


def _existing_server() -> dict[str, object] | None:
    if not SERVER_RECORD.exists():
        return None
    try:
        record = json.loads(SERVER_RECORD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        SERVER_RECORD.unlink(missing_ok=True)
        return None
    if _is_record_process_alive(record):
        return record
    SERVER_RECORD.unlink(missing_ok=True)
    return None


def _find_port(host: str, preferred: int) -> int:
    for port in range(preferred, min(preferred + 100, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("找不到可用的本機連接埠（已檢查 100 個連續連接埠）。")


def _open_when_ready(url: str) -> None:
    health = f"{url}/api/health"
    for _ in range(120):
        try:
            with urllib.request.urlopen(health, timeout=1) as response:
                if response.status == 200:
                    print(f"服務已就緒：{url}", flush=True)
                    if os.getenv("ISU_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}:
                        webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.25)
    print(f"服務正在 {url} 執行，但健康檢查尚未回應。", flush=True)


def main() -> int:
    _load_env_file()
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    existing = _existing_server()
    if existing:
        url = str(existing["url"])
        print(f"本專案已在執行：{url}")
        if os.getenv("ISU_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}:
            webbrowser.open(url)
        return 0

    host = os.getenv("ISU_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("為保護醫療資料，start.bat 僅允許本機 loopback 位址。")
    if host == "localhost":
        host = "127.0.0.1"
    preferred = int(os.getenv("ISU_PORT", "8000"))
    port = _find_port(host, preferred)
    url_host = "[::1]" if host == "::1" else "127.0.0.1"
    url = f"http://{url_host}:{port}"

    import psutil
    import uvicorn

    record = {
        "pid": os.getpid(),
        "create_time": psutil.Process().create_time(),
        "url": url,
        "port": port,
        "project_root": str(PROJECT_ROOT),
    }
    SERVER_RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"啟動本機服務：{url}")
    print("按 Ctrl+C 可停止；也可另外雙擊 stop.bat。")
    threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    try:
        uvicorn.run("backend.app.main:app", host=host, port=port, reload=False, access_log=True, proxy_headers=False)
    finally:
        try:
            current = json.loads(SERVER_RECORD.read_text(encoding="utf-8"))
            if int(current.get("pid", -1)) == os.getpid():
                SERVER_RECORD.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:
        print(f"[啟動失敗] {exc}", file=sys.stderr)
        raise SystemExit(1)
