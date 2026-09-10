@echo off
cls
echo ======================================================================
echo   FB TOOL AUTOMATION - Complete Installation
echo ======================================================================
echo.
echo This will install all required dependencies.
echo Please wait, this process may take 5-10 minutes.
echo.
echo Step 1: Installing Python packages (playwright, Pillow, groq)
echo Step 2: Installing Chromium browser (114 MB download)
echo Step 3: Testing installation
echo.
pause
echo.

echo [1/3] Installing Python packages...
python -m pip install playwright Pillow groq --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Python packages
    echo Try running: python -m pip install playwright Pillow groq
    pause
    exit /b 1
)
echo OK - Python packages installed
echo.

echo [2/3] Installing Chromium browser (this will take a few minutes)...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Chromium browser
    echo Try running: python -m playwright install chromium
    pause
    exit /b 1
)
echo OK - Chromium browser installed
echo.

echo [3/3] Testing installation...
python check_status.py
if %errorlevel% neq 0 (
    echo WARNING: Some tests failed
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   SUCCESS! Installation complete.
echo ======================================================================
echo.
echo You can now run the application:
echo   Double-click: RUN_APP.bat
echo.
pause
