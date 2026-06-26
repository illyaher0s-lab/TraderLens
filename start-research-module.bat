@echo off
REM TraderLens Research Module Startup Script
REM Starts the backend API with real LLM and Tushare integration

echo ========================================
echo TraderLens Research Module
echo ========================================
echo.

REM Check if environment variables are set
if "%RESEARCH_LLM_API_KEY%"=="" (
    echo ERROR: RESEARCH_LLM_API_KEY is not set
    echo.
    echo Please set the environment variable:
    echo   set RESEARCH_LLM_API_KEY=your-api-key
    echo.
    echo Or run in test mode:
    echo   set RESEARCH_CONVERSATION_MODE=deterministic
    echo.
    pause
    exit /b 1
)

if "%TUSHARE_TOKEN%"=="" (
    echo ERROR: TUSHARE_TOKEN is not set
    echo.
    echo Please set the environment variable:
    echo   set TUSHARE_TOKEN=your-token
    echo.
    echo Or run in test mode:
    echo   set RESEARCH_CONVERSATION_MODE=deterministic
    echo.
    pause
    exit /b 1
)

REM Set mode to real (default)
if "%RESEARCH_CONVERSATION_MODE%"=="" (
    set RESEARCH_CONVERSATION_MODE=real
)

echo Mode: %RESEARCH_CONVERSATION_MODE%
echo.

REM Start backend API
echo Starting TraderLens API...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000 (start separately)
echo.

cd /d "%~dp0"
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
