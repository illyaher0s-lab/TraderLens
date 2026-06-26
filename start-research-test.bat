@echo off
REM TraderLens Research Module - Test Mode
REM Starts with deterministic fake agents (no API keys required)

echo ========================================
echo TraderLens Research Module - TEST MODE
echo ========================================
echo.
echo Running with FAKE agents (no real LLM/Tushare)
echo For production use, run start-research-module.bat instead
echo.

REM Force deterministic mode
set RESEARCH_CONVERSATION_MODE=deterministic

REM Start backend API
echo Starting TraderLens API...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000 (start separately)
echo.

cd /d "%~dp0"
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
