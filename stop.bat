@echo off
setlocal EnableExtensions
chcp 65001 >nul
call "%~dp002_主程式碼\stop.bat" %*
exit /b %ERRORLEVEL%
