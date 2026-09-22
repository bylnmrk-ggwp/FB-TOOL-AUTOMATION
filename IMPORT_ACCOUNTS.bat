@echo off
cd /d "%~dp0"
if "%~1"=="" (
    python scripts\import_accounts.py --sheet
    goto :done
)
python scripts\import_accounts.py --xlsx %1
:done
pause
