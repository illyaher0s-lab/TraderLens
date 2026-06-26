@echo off
REM Stop all Signal Board services

echo Stopping Signal Board services...

REM Kill uvicorn processes (Backend)
taskkill /F /FI "WINDOWTITLE eq Signal Board Backend*" 2>nul
if %ERRORLEVEL% == 0 (
    echo [OK] Backend stopped
) else (
    echo [INFO] No backend process found
)

REM Kill npm/node processes (Frontend)
taskkill /F /FI "WINDOWTITLE eq Signal Board Frontend*" 2>nul
if %ERRORLEVEL% == 0 (
    echo [OK] Frontend stopped
) else (
    echo [INFO] No frontend process found
)

echo.
echo All services stopped.
pause
