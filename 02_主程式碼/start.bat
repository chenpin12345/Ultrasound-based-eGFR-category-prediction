@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [失敗] 尚未完成安裝，請先雙擊 setup.bat。
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  echo [失敗] 找不到前端 production build，請重新執行 setup.bat。
  pause
  exit /b 1
)

echo 啟動 ISU AI KUA 本機服務...
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\run_server.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [失敗] 服務已停止或無法啟動，請查看上方訊息。
  pause
)
exit /b %EXIT_CODE%
