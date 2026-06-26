@echo off
setlocal EnableDelayedExpansion

REM Signal Board Development Server Launcher
REM Cleans stale ports/cache, starts Backend + Frontend, then waits for real HTTP readiness.

set "ROOT=%~dp0"
set "FRONTEND_PORT=3000"
set "BACKEND_PORT=8000"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%/signals"
set "BACKEND_URL=http://localhost:%BACKEND_PORT%/health"

echo ========================================
echo Signal Board Development Server
echo ========================================
echo.

echo [0/5] Cleaning old dev servers...
call :kill_port %FRONTEND_PORT% "Frontend"
if errorlevel 1 goto PORT_BLOCKED
call :kill_port %BACKEND_PORT% "Backend"
if errorlevel 1 goto PORT_BLOCKED
echo.

echo [1/5] Cleaning stale Next.js cache...
if exist "%ROOT%frontend\.next" (
    rmdir /s /q "%ROOT%frontend\.next"
    if errorlevel 1 (
        echo [ERROR] Could not remove frontend\.next.
        echo Close old frontend windows and run this script again.
        goto FAILED
    )
    echo Removed frontend\.next
) else (
    echo No frontend\.next cache found.
)
echo.

echo [2/5] Starting Backend API (port %BACKEND_PORT%)...
start "Signal Board Backend" cmd /k "cd /d ""%ROOT%"" && .venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port %BACKEND_PORT%"

echo [3/5] Starting Frontend Dev Server (port %FRONTEND_PORT%)...
start "Signal Board Frontend" cmd /k "cd /d ""%ROOT%"" && npm run dev -- --port %FRONTEND_PORT%"
echo.

echo [4/5] Waiting for Backend readiness...
call :wait_http "%BACKEND_URL%" "Backend"
if errorlevel 1 goto FAILED

echo [5/5] Waiting for Frontend readiness...
call :wait_http "%FRONTEND_URL%" "Frontend"
if errorlevel 1 goto FAILED

echo.
echo ========================================
echo Services Ready
echo ========================================
echo Backend:  http://localhost:%BACKEND_PORT%
echo Frontend: %FRONTEND_URL%
echo API Docs: http://localhost:%BACKEND_PORT%/docs
echo.

echo Opening browser...
start "" "%FRONTEND_URL%"

echo.
echo To stop servers: Run stop-signal-board.bat or close the command windows.
echo.
pause
exit /b 0

:kill_port
set "PORT=%~1"
set "LABEL=%~2"
set "FOUND=0"
set "KILL_FAILED=0"

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "FOUND=1"
    echo Stopping %LABEL% process on port %PORT% ^(PID %%P^)...
    taskkill /F /PID %%P >nul 2>nul
    if errorlevel 1 (
        echo [WARNING] Could not stop PID %%P on port %PORT%.
        set "KILL_FAILED=1"
    )
)

if "%FOUND%"=="0" (
    echo No %LABEL% process found on port %PORT%.
    exit /b 0
)

timeout /t 1 /nobreak >nul
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo [ERROR] Port %PORT% is still occupied after cleanup.
    echo Close the old %LABEL% window, run stop-signal-board.bat, or run this launcher as Administrator.
    exit /b 1
)

if "%KILL_FAILED%"=="1" (
    echo [WARNING] Some stale %LABEL% processes could not be killed, but port %PORT% is now free.
)
exit /b 0

:wait_http
set "URL=%~1"
set "LABEL=%~2"

for /l %%I in (1,1,40) do (
    curl.exe -fsS --max-time 3 -o NUL "%URL%" >nul 2>nul
    if not errorlevel 1 (
        echo %LABEL% ready: %URL%
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)

echo [ERROR] %LABEL% did not become ready: %URL%
exit /b 1

:PORT_BLOCKED
echo.
echo ========================================
echo Startup stopped: a required port is blocked.
echo ========================================
echo Frontend port: %FRONTEND_PORT%
echo Backend port:  %BACKEND_PORT%
echo.
pause
exit /b 1

:FAILED
echo.
echo ========================================
echo Startup failed.
echo ========================================
echo Check the Backend and Frontend command windows for the exact error.
echo.
pause
exit /b 1
