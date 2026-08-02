@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 找不到本專案的虛擬環境，沒有可停止的服務。
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\stop_server.py
if errorlevel 1 (
  echo 無法安全停止服務，請查看上方訊息。
  pause
  exit /b 1
)

echo 已停止本專案服務。
exit /b 0
