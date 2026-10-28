@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
cd /d "%ROOT%"
node scripts\card020_validation_launcher.cjs
exit /b %errorlevel%
