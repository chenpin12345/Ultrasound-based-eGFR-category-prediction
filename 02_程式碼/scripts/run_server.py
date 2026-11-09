"""啟動後端（只綁 127.0.0.1），並在服務就緒後開啟瀏覽器。

改寫自腎超新 scripts/run_server.py：
- 已經在執行時不重複啟動，只開啟網頁。
- 連接埠被占用時自動往後找。
- 把 PID 與啟動時間寫到 08_系統/run/server.json，stop_server.py 用來安全停止。

在 Windows 上，連到「沒有程式在聽」的本機連接埠，每次要等約 2 秒才失敗（系統會重試）。
所以這裡不用連線去試：檢查連接埠用 bind、檢查舊的系統用 server.json 的程序、就緒用 uvicorn 的 started 旗標，
啟動時不會白等。
"""

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

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
ROOT = Path(os.environ.get("KIDNEY_WORKSPACE_ROOT", BACKEND.parents[1])).resolve()
RUN_FILE = ROOT / '08_系統' / 'run' / 'server.json'
HOST = '127.0.0.1'


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f'http://{HOST}:{port}/api/health', timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def port_free(port: int) -> bool:
    """能 bind 就是沒被占用（不用 connect：連到沒人聽的埠在 Windows 要等約 2 秒）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):  # Windows：避免和別的程式共用同一個埠時誤判為空
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def running_server() -> int | None:
    """server.json 記錄的系統若還在執行，回傳它的連接埠。先看程序與連接埠，確定在執行才發 HTTP 確認。"""
    if not RUN_FILE.exists():
        return None
    try:
        info = json.loads(RUN_FILE.read_text(encoding='utf-8'))
        import psutil

        if not psutil.pid_exists(int(info['pid'])) or port_free(int(info['port'])):
            return None  # 上次沒有正常結束留下的紀錄
    except Exception:  # noqa: BLE001
        return None
    return int(info['port']) if healthy(int(info['port'])) else None


def main() -> int:
    if sys.platform == 'win32':
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW('腎超工作台（關閉這個視窗會停止系統）')
    existing = running_server()
    if existing:
        print(f'系統已經在執行：http://{HOST}:{existing}')
        if os.environ.get('KIDNEY_NO_BROWSER') != '1':
            webbrowser.open(f'http://{HOST}:{existing}')
        return 0
    port = int(os.environ.get('KIDNEY_PORT', '8000'))
    for candidate in range(port, port + 20):
        if port_free(candidate):
            port = candidate
            break
    else:
        print('找不到可用的連接埠（8000–8019 都被占用）。')
        return 1

    print('啟動中…（電腦剛開機後第一次啟動，載入套件可能要多等幾秒）', flush=True)
    RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUN_FILE.write_text(json.dumps({'pid': os.getpid(), 'port': port, 'started': time.time()}), encoding='utf-8')
    os.environ['KIDNEY_PORT'] = str(port)
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    import uvicorn

    server = uvicorn.Server(uvicorn.Config('app.main:app', host=HOST, port=port, log_level='warning'))

    def open_when_ready() -> None:
        while not server.started:  # uvicorn 完成啟動（資料庫遷移、快照、索引）並開始接受連線後設為 True
            if server.should_exit:
                return
            time.sleep(0.05)
        print(f'系統已啟動：http://{HOST}:{port}（關閉這個視窗或執行 stop.bat 即可停止）', flush=True)
        if os.environ.get('KIDNEY_NO_BROWSER') != '1':
            webbrowser.open(f'http://{HOST}:{port}')

    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.run()
    finally:
        try:
            info = json.loads(RUN_FILE.read_text(encoding='utf-8'))
            if info.get('pid') == os.getpid():
                RUN_FILE.unlink()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
