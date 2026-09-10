@echo off
REM Facebook Automation Tool Launcher
REM Uses the correct Python installation (not LibreOffice Python)

REM Clear Python cache files
echo Clearing Python cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc >nul 2>&1

REM Wait a moment
timeout /t 1 /nobreak >nul

REM Run the application
echo Starting FB Tool Automation...
python main.py

pause
