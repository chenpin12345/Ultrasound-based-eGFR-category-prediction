"""安裝：建立 Python 虛擬環境、安裝後端套件、安裝並建置前端（setup.bat 呼叫）。

批次檔本身只用英文字元：cmd 讀含中文的批次檔時，會因主控台字碼頁不同而把行切錯；
中文訊息都由這個腳本輸出。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
BACKEND = CODE / 'backend'
FRONTEND = CODE / 'frontend'
VENV_PYTHON = BACKEND / '.venv' / 'Scripts' / 'python.exe'


def run(args: list[str], cwd: Path | None = None) -> bool:
    return subprocess.run(args, cwd=cwd).returncode == 0


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        print(f'需要 Python 3.12，目前是 {sys.version.split()[0]}。')
        return 1
    print('[1/3] 建立 Python 虛擬環境')
    if not VENV_PYTHON.exists() and not run([sys.executable, '-m', 'venv', str(BACKEND / '.venv')]):
        return fail()
    print('[2/3] 安裝後端套件')
    run([str(VENV_PYTHON), '-m', 'pip', 'install', '--upgrade', 'pip', '-q'])
    if not run([str(VENV_PYTHON), '-m', 'pip', 'install', '-r', str(BACKEND / 'requirements.txt')]):
        return fail()
    print('      安裝訓練套件（CUDA 版 PyTorch、MedSAM、nnU-Net，約 3 GB，第一次較久）')
    if not run([str(VENV_PYTHON), '-m', 'pip', 'install', '-r', str(BACKEND / 'requirements-gpu.txt')]):
        return fail()
    print('[3/3] 安裝並建置前端（需要 Node.js 20 以上與 pnpm）')
    pnpm = shutil.which('pnpm')
    if pnpm is None:
        print('找不到 pnpm。請先安裝 Node.js 20 以上，再執行：npm install -g pnpm')
        return fail()
    if not run([pnpm, 'install'], cwd=FRONTEND) or not run([pnpm, 'build'], cwd=FRONTEND):
        return fail()
    print()
    print('安裝完成。之後雙擊 start.bat 啟動系統。')
    return 0


def fail() -> int:
    print()
    print('安裝失敗，請把上面的錯誤訊息截圖。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
