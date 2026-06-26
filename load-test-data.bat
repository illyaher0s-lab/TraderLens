@echo off
REM Load test data into Signal Board

echo ========================================
echo Loading Test Data
echo ========================================
echo.

cd /d %~dp0

echo Creating 15 test signals...
.venv\Scripts\python.exe backend/scripts/load_test_signals.py

echo.
echo ========================================
echo Test data loaded!
echo ========================================
echo.
echo You can now view signals at:
echo http://localhost:3000/signals
echo.
pause
