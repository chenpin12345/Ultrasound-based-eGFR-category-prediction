@echo off
rem Keep this file ASCII-only: cmd mis-reads non-ASCII batch lines when the console code page differs.
cd /d "%~dp0"
set "CODE="
for /d %%D in ("02_*") do set "CODE=%%~fD"
if not defined CODE (
  echo Cannot find the 02_ code folder next to this file.
  pause
  exit /b 1
)
if not exist "%CODE%\backend\.venv\Scripts\python.exe" (
  echo Not installed yet. Please run setup.bat first.
  pause
  exit /b 1
)
"%CODE%\backend\.venv\Scripts\python.exe" "%CODE%\scripts\run_server.py"
