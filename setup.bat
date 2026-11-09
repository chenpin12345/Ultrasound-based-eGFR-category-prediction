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
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" not found. Install Python 3.12 from python.org first.
  pause
  exit /b 1
)
py -3.12 "%CODE%\scripts\setup_env.py"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
