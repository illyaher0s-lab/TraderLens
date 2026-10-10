@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\traderlens_local_runtime.ps1" -Action Stop -ProjectRoot "%~dp0."
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
