@echo off
rem ============================================================
rem  FB Tool Automation - Cleanup Old Files
rem ============================================================
rem  Deletes outdated delay docs and debug files using plain
rem  cmd.exe commands - NO PowerShell, NO Python, NO Git needed.
rem
rem  Does NOT touch code, installers, INSTALL + TROUBLESHOOTING.md,
rem  README.md (pointer stub), or your profile database
rem  (facebook_profiles.db).
rem ============================================================

rem Work in this file's folder no matter where it is launched from.
cd /d "%~dp0"

echo.
echo  Cleaning up outdated docs and debug files...
echo.

set /a DELETED=0

for %%F in (
    "dump_group.json"
    "dump_reaction_error.json"
    "dump_reaction_no_button.json"
    "debug_profile_page.png"
    "ANTI_SPAM_DELAYS_UPDATE.txt"
    "BEFORE_AFTER_COMPARISON.txt"
    "COMMENT_DELAYS_UPDATE.txt"
    "COMPLETE_DELAYS_SUMMARY.txt"
    "IMPLEMENTATION_SUMMARY.txt"
    "QUICK_START_DELAYS.txt"
    "START_HERE.txt"
    "DELAY_SETTINGS_README.md"
    "COMMENT_FEATURE_UPDATE.txt"
    "HOW_TO_FIX.txt"
    "INSTALLATION_COMPLETE.txt"
    "*ALL FIXED - READ THIS.txt"
    "src/ui/quick_share_tab.py"
    "src/ui/credentials_tab.py"
) do (
    if exist "%%~F" (
        del /f /q "%%~F" >nul 2>&1
        if exist "%%~F" (
            echo   [FAILED ] %%~F  (file is locked or in use?)
        ) else (
            echo   [DELETED] %%~F
            set /a DELETED+=1
        )
    ) else (
        echo   [already gone] %%~F
    )
)

echo.
if %DELETED% GTR 0 (
    echo   Done! %DELETED% file(s) deleted.
) else (
    echo   Nothing to delete - all targets already gone.
)
echo.
echo Remaining files in this folder:
echo.
dir /b
echo.
pause
