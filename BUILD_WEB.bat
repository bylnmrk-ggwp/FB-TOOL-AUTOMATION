@echo off
REM Build the web app into web\dist, which server.py serves.
REM npm ci installs exactly what package-lock.json pins; run this after every
REM git pull that touched web\.
cd /d "%~dp0web"
call npm ci
if errorlevel 1 (
    echo npm ci failed - is Node installed and on PATH?
    pause
    exit /b 1
)
call npm run build
if errorlevel 1 (
    echo npm run build failed
    pause
    exit /b 1
)
echo Built web\dist - start SERVER.bat to serve it.
pause
