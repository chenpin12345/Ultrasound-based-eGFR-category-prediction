"""安全停止後端：只停止 server.json 記錄、而且命令列確實是 run_server.py 的程序。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import psutil

ROOT = Path(os.environ.get("KIDNEY_WORKSPACE_ROOT", Path(__file__).resolve().parents[2])).resolve()
RUN_FILE = ROOT / '08_系統' / 'run' / 'server.json'


def main() -> int:
    if not RUN_FILE.exists():
        print('系統沒有在執行。')
        return 0
    info = json.loads(RUN_FILE.read_text(encoding='utf-8'))
    try:
        proc = psutil.Process(info['pid'])
        cmdline = ' '.join(proc.cmdline())
        if 'run_server.py' not in cmdline or abs(proc.create_time() - info['started']) > 120:
            print('紀錄中的程序不是本系統（可能已重新開機），只清除紀錄。')
            RUN_FILE.unlink(missing_ok=True)
            return 0
        for child in proc.children(recursive=True):
            child.terminate()
        proc.terminate()
        proc.wait(timeout=15)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        proc.kill()
    RUN_FILE.unlink(missing_ok=True)
    print('系統已停止。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
