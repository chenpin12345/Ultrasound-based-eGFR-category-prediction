"""打包發布版：建置網頁後用 PyInstaller 產生 `發布版/醫師圈選/`，整個資料夾複製到要用的電腦即可。

用法（在 `醫師圈選網站/`）：backend\\.venv\\Scripts\\python.exe build.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / 'frontend'
BACKEND = ROOT / 'backend'
RELEASE = ROOT / '發布版'
WORK = ROOT / '.build'
GUIDE = '''醫師圈選網站

1. 雙擊「啟動.exe」，瀏覽器會自動開啟。使用期間不要關閉黑色視窗；關閉就會停止。
2. 第一次使用時，在首頁「匯入影像」填主系統匯出的原始影像資料夾路徑。
3. 圈完後在首頁按「輸出結果」，結果在「輸出」資料夾。把路徑填到主系統「上傳醫師圈選」。

「資料」資料夾有含個資的原始影像與圈選資料庫，只能留在這台電腦，不可上傳或外流。
「輸出」資料夾不含影像內容。
更換版本時，把舊版的「資料」和「輸出」資料夾移到新版旁邊。
'''


def running(exe: Path) -> bool:
    """Windows 上執行中的 exe 不能改名；用改名回原名測試網站是不是還開著。"""
    if not exe.exists():
        return False
    try:
        exe.rename(exe)
        probe = exe.with_name('啟動.exe.check')
        exe.rename(probe)
        probe.rename(exe)
        return False
    except PermissionError:
        return True


def main() -> None:
    if running(RELEASE / '醫師圈選' / '啟動.exe'):
        sys.exit('醫師圈選網站正在執行。請先關閉黑色視窗（圈選資料都已自動儲存），再重新執行。')
    pnpm = shutil.which('pnpm')
    if pnpm is None:
        sys.exit('找不到 pnpm。')
    subprocess.run([pnpm, 'install', '--frozen-lockfile'], cwd=FRONTEND, check=True)
    subprocess.run([pnpm, 'build'], cwd=FRONTEND, check=True)
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--name', '啟動', '--contents-directory', '程式',
        '--distpath', str(WORK / 'out'), '--workpath', str(WORK), '--specpath', str(WORK), '--paths', str(BACKEND),
        '--add-data', f'{FRONTEND / "dist"};dist', '--collect-submodules', 'uvicorn', str(BACKEND / 'run.py'),
    ], cwd=ROOT, check=True)
    # 發布版裡的 資料/、輸出/ 是醫師的圈選成果和原始影像，只替換程式，絕對不能整個資料夾刪掉重建
    target = RELEASE / '醫師圈選'
    target.mkdir(parents=True, exist_ok=True)
    built = WORK / 'out' / '啟動'
    shutil.rmtree(target / '程式', ignore_errors=True)
    shutil.copytree(built / '程式', target / '程式')
    shutil.copy2(built / '啟動.exe', target / '啟動.exe')
    (target / '使用說明.txt').write_text(GUIDE, encoding='utf-8-sig')
    shutil.rmtree(WORK, ignore_errors=True)
    print(f'發布版：{target}')


if __name__ == '__main__':
    main()
