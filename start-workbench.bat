@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM TraderLens Workbench quick launcher.
REM Default mode starts the product path with real API configuration.
REM Use /demo only for UI smoke checks that do not need real stock identity.

set "ROOT=%~dp0"
set "FRONTEND_PORT=3000"
set "BACKEND_PORT=8010"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%/workbench"
set "BACKEND_URL=http://localhost:%BACKEND_PORT%/docs"
set "MODE=real"
set "AUTO_KILL=1"
set "REUSE_EXISTING=0"

if /i "%~1"=="/check" goto CHECK_ONLY
if /i "%~1"=="/demo" set "MODE=demo"
if /i "%~1"=="/real" set "MODE=real"
if /i "%~1"=="/reuse" set "REUSE_EXISTING=1"
if /i "%~2"=="/reuse" set "REUSE_EXISTING=1"
if not "%~1"=="" if /i not "%~1"=="/demo" if /i not "%~1"=="/real" if /i not "%~1"=="/reuse" if /i not "%~1"=="/check" goto USAGE
if not "%~2"=="" if /i not "%~2"=="/reuse" goto USAGE

cd /d "%ROOT%"

REM Optional local env file. Format: KEY=value, lines starting with # are ignored.
call :load_env_file "%ROOT%.env.local"
call :load_env_file "%ROOT%.env"

REM Tushare private endpoint should bypass proxies.
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="

if /i "%MODE%"=="demo" (
    set "RESEARCH_CONVERSATION_MODE=deterministic"
    set "SERENITY_EXECUTION_MODE=stub"
) else (
    set "RESEARCH_CONVERSATION_MODE=real"
    set "SERENITY_EXECUTION_MODE=two_phase"
    if "%TUSHARE_API_URL%"=="" set "TUSHARE_API_URL=http://8.163.90.143:8686/"
)

set "NEXT_PUBLIC_API_BASE_URL=http://localhost:%BACKEND_PORT%"

echo ========================================
echo TraderLens Workbench Quick Start
echo ========================================
echo.
echo Mode:      %MODE%
echo Backend:   http://localhost:%BACKEND_PORT%
echo Workbench: %FRONTEND_URL%
if "%REUSE_EXISTING%"=="0" (
    echo Startup:   clean restart
) else (
    echo Startup:   reuse existing healthy services
)
echo.

if /i "%MODE%"=="real" (
    call :require_env "RESEARCH_LLM_API_KEY"
    if errorlevel 1 goto FAILED_CONFIG
    call :require_env "TUSHARE_TOKEN"
    if errorlevel 1 goto FAILED_CONFIG
    echo Real API config: LLM key set, Tushare token set, private endpoint ready.
    echo.
) else (
    echo Demo mode: no real LLM/Tushare. Stock-name research may not verify real tickers.
    echo.
)

echo [1/4] Checking backend...
if "%REUSE_EXISTING%"=="0" (
    call :port_in_use %BACKEND_PORT%
    if errorlevel 1 (
        echo Stopping existing process on port %BACKEND_PORT%...
        call :kill_port %BACKEND_PORT%
        timeout /t 1 /nobreak >nul
    )
    goto START_BACKEND
)

call :wait_http_quick "%BACKEND_URL%"
if errorlevel 1 (
    call :port_in_use %BACKEND_PORT%
    if errorlevel 1 (
        echo Port %BACKEND_PORT% is occupied by an unhealthy process. Stopping it...
        call :kill_port %BACKEND_PORT%
        timeout /t 1 /nobreak >nul
    )
    goto START_BACKEND
) else (
    echo Backend already ready.
    goto BACKEND_DONE
)

:START_BACKEND
echo Starting backend API...
start "TraderLens Backend" cmd /k "cd /d ""%ROOT%"" && set RESEARCH_CONVERSATION_MODE=%RESEARCH_CONVERSATION_MODE%&& set SERENITY_EXECUTION_MODE=%SERENITY_EXECUTION_MODE%&& set RESEARCH_LLM_API_KEY=%RESEARCH_LLM_API_KEY%&& set RESEARCH_LLM_BASE_URL=%RESEARCH_LLM_BASE_URL%&& set RESEARCH_LLM_MODEL=%RESEARCH_LLM_MODEL%&& set TUSHARE_TOKEN=%TUSHARE_TOKEN%&& set TUSHARE_API_URL=%TUSHARE_API_URL%&& set HTTP_PROXY=&& set HTTPS_PROXY=&& set http_proxy=&& set https_proxy=&& set ALL_PROXY=&& set all_proxy=&& .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port %BACKEND_PORT%"
call :wait_http "%BACKEND_URL%" "Backend"
if errorlevel 1 goto FAILED

:BACKEND_DONE
echo.
echo [2/4] Checking frontend...
if "%REUSE_EXISTING%"=="0" (
    call :port_in_use %FRONTEND_PORT%
    if errorlevel 1 (
        echo Stopping existing process on port %FRONTEND_PORT%...
        call :kill_port %FRONTEND_PORT%
        timeout /t 1 /nobreak >nul
    )
    goto START_FRONTEND
)

call :wait_http_quick "%FRONTEND_URL%"
if errorlevel 1 (
    call :port_in_use %FRONTEND_PORT%
    if errorlevel 1 (
        echo Port %FRONTEND_PORT% is occupied by an unhealthy process. Stopping it...
        call :kill_port %FRONTEND_PORT%
        timeout /t 1 /nobreak >nul
    )
    goto START_FRONTEND
) else (
    echo Frontend already ready.
    goto FRONTEND_DONE
)

:START_FRONTEND
echo Starting frontend dev server...
start "TraderLens Frontend" cmd /k "cd /d ""%ROOT%"" && set NEXT_PUBLIC_API_BASE_URL=%NEXT_PUBLIC_API_BASE_URL%&& npm run dev -- --port %FRONTEND_PORT%"
call :wait_http "%FRONTEND_URL%" "Frontend"
if errorlevel 1 goto FAILED

:FRONTEND_DONE
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

:load_env_file
set "ENV_FILE=%~1"
if not exist "%ENV_FILE%" exit /b 0
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if not "%%A"=="" if not "%%B"=="" set "%%A=%%B"
)
exit /b 0

:require_env
set "ENV_NAME=%~1"
if "!%ENV_NAME%!"=="" (
    echo [ERROR] %ENV_NAME% is not set.
    echo Set it in Windows environment variables or create %ROOT%.env.local with:
    echo   %ENV_NAME%=your_value
    exit /b 1
)
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

:kill_port
set "PORT=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$pids = @(); $pids += Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; $pids += Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn*--port %PORT%*' -or $_.CommandLine -like '*uvicorn*:%PORT%*' } | Select-Object -ExpandProperty ProcessId; $pids | Where-Object { $_ } | Sort-Object -Unique | ForEach-Object { Write-Host ('Stopping process ' + $_ + ' for port %PORT%...'); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
exit /b 0

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

:USAGE
echo Usage:
echo   start-workbench.bat          Start real API mode and open /workbench
echo   start-workbench.bat /real    Same as default
echo   start-workbench.bat /demo    Start deterministic demo mode
echo   start-workbench.bat /reuse   Reuse existing healthy services
echo   start-workbench.bat /check   Check local prerequisites only
exit /b 1

:FAILED_CONFIG
echo.
echo Missing real API configuration. For quick UI-only checks, run:
echo   start-workbench.bat /demo
echo.
pause
exit /b 1

:FAILED
echo.
echo ========================================
echo Startup failed.
echo ========================================
echo Check the backend/frontend command windows if they opened.
echo.
pause
exit /b 1
