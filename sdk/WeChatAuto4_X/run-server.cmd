@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-server.ps1" %*
set "MYBOT_SERVER_EXIT=%errorlevel%"
echo.
if not "%MYBOT_SERVER_EXIT%"=="0" echo Server failed to start. Exit code: %MYBOT_SERVER_EXIT%
if not "%MYBOT_NO_PAUSE%"=="1" pause
exit /b %MYBOT_SERVER_EXIT%
