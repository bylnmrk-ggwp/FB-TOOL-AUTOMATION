@echo off
echo ================================================
echo FB Tool Automation - Setup Script
echo ================================================
echo.

echo Installing required Python packages...
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo ================================================
echo Installing Playwright browsers...
echo ================================================
echo.

python -m playwright install chromium

echo.
echo ================================================
echo Setup Complete!
echo ================================================
echo.
echo You can now run RUN_APP.bat to start the application
echo.

pause
