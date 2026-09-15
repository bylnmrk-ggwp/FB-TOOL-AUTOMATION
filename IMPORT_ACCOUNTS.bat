@echo off
cd /d "%~dp0"
if "%~1"=="" (
    echo Usage: IMPORT_ACCOUNTS.bat "path\to\FB ACCOUNTS.xlsx"
    echo The roster is imported from a local workbook into the database.
    pause
    exit /b 1
)
python scripts\import_accounts.py --xlsx %1
pause
