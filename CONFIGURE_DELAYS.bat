@echo off
echo ============================================
echo Facebook Automation - Delay Configuration
echo ============================================
echo.

python configure_delays.py
if errorlevel 1 (
    echo.
    echo Error running configuration script
    pause
    exit /b 1
)

pause
