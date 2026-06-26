@echo off
REM Clean Next.js cache and restart with fresh Tailwind compilation

echo ========================================
echo Cleaning Next.js Cache
echo ========================================
echo.

cd /d %~dp0

echo [1/3] Stopping services...
call stop-signal-board.bat

echo.
echo [2/3] Cleaning cache...
rmdir /s /q frontend\.next 2>nul
if exist frontend\.next (
    echo [WARNING] Could not delete .next folder
) else (
    echo [OK] .next cache cleared
)

echo.
echo [3/3] Restarting services...
call start-signal-board.bat

echo.
echo ========================================
echo Cache cleared and services restarted!
echo ========================================
pause
