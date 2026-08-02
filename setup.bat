@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo ISU AI KUA - Windows 本機安裝
echo ============================================================

set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

if not defined PYTHON_CMD (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -c "import sys; raise SystemExit(0)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.12"
  )
)

if not defined PYTHON_CMD (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.11 -c "import sys; raise SystemExit(0)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
  )
)

if not defined PYTHON_CMD (
  where python >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo [失敗] 找不到 Python 3.11 或 3.12 64-bit。
  echo 請先從 https://www.python.org/downloads/windows/ 安裝，並勾選 Add Python to PATH。
  goto :fail
)

%PYTHON_CMD% -c "import sys,struct; ok=(3,11) ^<= sys.version_info[:2] ^<= (3,12) and struct.calcsize('P')*8 == 64; print('Python',sys.version.split()[0],str(struct.calcsize('P')*8)+'-bit'); raise SystemExit(0 if ok else 1)"
if errorlevel 1 (
  echo [失敗] 僅支援 Python 3.11/3.12 64-bit。
  goto :fail
)

where node >nul 2>&1
if errorlevel 1 (
  echo [失敗] 找不到 Node.js。請安裝 Node.js 20.19 以上版本。
  echo https://nodejs.org/
  goto :fail
)

node -e "const m=process.versions.node.split('.').map(Number); if(m[0]^<20 ^|^| (m[0]===20 ^&^& m[1]^<19)) process.exit(1); console.log('Node.js',process.versions.node)"
if errorlevel 1 (
  echo [失敗] Node.js 版本過舊，需要 20.19 以上版本。
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/7] 建立 Python 虛擬環境...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [1/7] 已存在 Python 虛擬環境，沿用現有環境。
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [2/7] 更新安裝工具...
"%PYTHON_EXE%" -m pip install --upgrade "pip<27" wheel setuptools
if errorlevel 1 goto :fail

if not defined ISU_TORCH_VARIANT set "ISU_TORCH_VARIANT=cpu"
set "TORCH_INDEX=https://download.pytorch.org/whl/cpu"
if /I "%ISU_TORCH_VARIANT%"=="cu124" set "TORCH_INDEX=https://download.pytorch.org/whl/cu124"
if /I "%ISU_TORCH_VARIANT%"=="cu126" set "TORCH_INDEX=https://download.pytorch.org/whl/cu126"

echo [3/7] 安裝 PyTorch 2.6.0 / torchvision 0.21.0 (%ISU_TORCH_VARIANT%)...
"%PYTHON_EXE%" -m pip install torch==2.6.0 torchvision==0.21.0 --index-url "%TORCH_INDEX%"
if errorlevel 1 goto :fail

echo [4/7] 安裝後端相依套件...
"%PYTHON_EXE%" -m pip install -r backend\requirements.txt
if errorlevel 1 goto :fail

echo [5/7] 安裝前端相依套件...
pushd frontend
where pnpm >nul 2>&1
if not errorlevel 1 (
  call pnpm install --frozen-lockfile
) else (
  where corepack >nul 2>&1
  if errorlevel 1 (
    echo [失敗] 找不到 pnpm 或 Corepack，無法依 lockfile 重現前端套件。
    echo 請安裝官方 Node.js 20.19+ 後重試。
    popd
    goto :fail
  )
  call corepack pnpm install --frozen-lockfile
)
if errorlevel 1 (
  popd
  goto :fail
)

echo [6/7] 建置 React production 版本...
where pnpm >nul 2>&1
if not errorlevel 1 (
  call pnpm run build
) else (
  call corepack pnpm run build
)
if errorlevel 1 (
  popd
  goto :fail
)
popd

echo [7/7] 初始化本機資料庫與工作目錄...
"%PYTHON_EXE%" scripts\bootstrap.py
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo 安裝完成。日常使用請雙擊 start.bat。
echo 資料只會保存在本機 data 與 models 目錄。
echo ============================================================
exit /b 0

:fail
echo.
echo ============================================================
echo 安裝失敗。請保留此視窗並查看上方錯誤訊息。
echo ============================================================
pause
exit /b 1
