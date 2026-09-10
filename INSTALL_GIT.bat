@echo off
echo ================================================
echo FB Tool Automation - Install Git for Windows
echo ================================================
echo.
echo This enables terminal (bash) commands for the AI
echo assistant and lets it remove dead module files.
echo.
echo Installing Git for Windows...
echo This may take a few minutes on the first run.
echo.

powershell -ExecutionPolicy Bypass -File install_git.ps1

echo.
pause
