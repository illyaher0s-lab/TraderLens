@echo off
setlocal EnableDelayedExpansion

REM TraderLens Workbench quick launcher.
REM Starts backend + frontend in local deterministic mode, then opens /workbench.

set "ROOT=%~dp0"
set "FRONTEND_PORT=3000"
set "BACKEND_PORT=8000"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%/workbench"
set "BACKEND_URL=http://localhost:%BACKEND_PORT%/health"

if /i "%~1"=="/check" goto CHECK_ONLY

REM Force local deterministic mode for all child windows launched by this script.
set "RESEARCH_CONVERSATION_MODE=deterministic"
set "SERENITY_EXECUTION_MODE=stub"

echo ========================================
echo TraderLens Workbench Quick Start
echo ========================================
echo.
echo Backend:  http://localhost:%BACKEND_PORT%
echo Workbench: %FRONTEND_URL%
echo Mode: deterministic local mode (no real API keys required)
echo.

echo [1/4] Checking backend...
call :wait_http_quick "%BACKEND_URL%"
if errorlevel 1 (
    call :port_in_use %BACKEND_PORT%
    if errorlevel 1 (
        echo [ERROR] Port %BACKEND_PORT% is occupied, but backend health is not ready.
        echo Close the process using port %BACKEND_PORT% and run this script again.
        goto FAILED
    )

    echo Starting backend API...
    start "TraderLens Backend" cmd /k "cd /d ""%ROOT%"" && echo Mode: %RESEARCH_CONVERSATION_MODE% / %SERENITY_EXECUTION_MODE% && .venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port %BACKEND_PORT%"
    call :wait_http "%BACKEND_URL%" "Backend"
    if errorlevel 1 goto FAILED
) else (
    echo Backend already ready.
)

echo.
echo [2/4] Checking frontend...
call :wait_http_quick "%FRONTEND_URL%"
if errorlevel 1 (
    call :port_in_use %FRONTEND_PORT%
    if errorlevel 1 (
        echo [ERROR] Port %FRONTEND_PORT% is occupied, but Workbench is not ready.
        echo Close the process using port %FRONTEND_PORT% and run this script again.
        goto FAILED
    )

    echo Starting frontend dev server...
    start "TraderLens Frontend" cmd /k "cd /d ""%ROOT%"" && npm run dev -- --port %FRONTEND_PORT%"
    call :wait_http "%FRONTEND_URL%" "Frontend"
    if errorlevel 1 goto FAILED
) else (
    echo Frontend already ready.
)

echo.
echo [3/4] Opening Workbench...
start "" "%FRONTEND_URL%"

echo.
echo [4/4] Ready.
echo.
echo Workbench opened: %FRONTEND_URL%
echo API docs:         http://localhost:%BACKEND_PORT%/docs
echo.
echo To stop the app, close the "TraderLens Backend" and "TraderLens Frontend" windows.
echo.
pause
exit /b 0

:wait_http_quick
set "URL=%~1"
curl.exe -fsS --max-time 2 -o NUL "%URL%" >nul 2>nul
exit /b %errorlevel%

:wait_http
set "URL=%~1"
set "LABEL=%~2"

for /l %%I in (1,1,60) do (
    curl.exe -fsS --max-time 3 -o NUL "%URL%" >nul 2>nul
    if not errorlevel 1 (
        echo %LABEL% ready: %URL%
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)

echo [ERROR] %LABEL% did not become ready: %URL%
exit /b 1

:port_in_use
set "PORT=%~1"
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>nul
if errorlevel 1 exit /b 0
exit /b 1

:CHECK_ONLY
echo Checking TraderLens Workbench launcher prerequisites...
if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [ERROR] Missing Python virtual environment: %ROOT%.venv\Scripts\python.exe
    exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm is not available on PATH.
    exit /b 1
)
where curl.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] curl.exe is not available on PATH.
    exit /b 1
)
cd /d "%ROOT%"
.venv\Scripts\python.exe -c "import uvicorn, fastapi; print('backend dependencies ready')"
if errorlevel 1 exit /b 1
echo Launcher prerequisites ready.
exit /b 0

:FAILED
echo.
echo ========================================
echo Startup failed.
echo ========================================
echo Check the backend/frontend command windows if they opened.
echo.
pause
exit /b 1
