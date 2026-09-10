@echo off
echo Installing packages...
python -m pip install playwright Pillow groq --quiet --no-warn-script-location
if %errorlevel% neq 0 (
    echo Package installation failed
    exit /b 1
)
echo Packages installed successfully
echo.
echo Installing Playwright browser...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo Browser installation failed
    exit /b 1
)
echo Browser installed successfully
echo.
echo Installation complete!
