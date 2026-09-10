@echo off
REM Import / refresh the account roster from FB ACCOUNTS.xlsx
echo Importing account roster...
python import_accounts.py
pause
