# ======================================================================
#  cleanup.ps1 - Delete outdated docs & debug artifacts
# ======================================================================
#  Deletes the files confirmed by the user:
#    - Debug artifacts (4): dump_*.json x3, debug_profile_page.png
#    - Redundant anti-spam delay docs (8)
#    - COMMENT_FEATURE_UPDATE.txt (content merged into the docs file)
#    - Install notices (3) (content merged into the docs file)
#
#  Keeps: INSTALL + TROUBLESHOOTING.md (the one doc), README.md (pointer
#         stub for GitHub), all .py/.bat/.ps1 utilities, installers,
#         facebook_profiles.db (live data!)
#
#  This script works regardless of the working directory it is launched
#  from: it anchors itself to its own folder first.
# ======================================================================

# Work relative to THIS script's folder, no matter where it is launched from.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "======================================================================"
Write-Host "  FB TOOL AUTOMATION - Cleanup"
Write-Host "======================================================================"
Write-Host "  Working in: $scriptDir"
Write-Host ""

# ASCII-safe patterns only. The last one is a wildcard so the special
# checkmark character in the real filename never has to match file encodings.
$targets = @(
    # Debug artifacts
    "dump_group.json",
    "dump_reaction_error.json",
    "dump_reaction_no_button.json",
    "debug_profile_page.png",
    # Redundant anti-spam delay docs
    "ANTI_SPAM_DELAYS_UPDATE.txt",
    "BEFORE_AFTER_COMPARISON.txt",
    "COMMENT_DELAYS_UPDATE.txt",
    "COMPLETE_DELAYS_SUMMARY.txt",
    "IMPLEMENTATION_SUMMARY.txt",
    "QUICK_START_DELAYS.txt",
    "START_HERE.txt",
    "DELAY_SETTINGS_README.md",
    # Feature doc merged into the docs file
    "COMMENT_FEATURE_UPDATE.txt",
    # Install notices merged into the docs file
    "HOW_TO_FIX.txt",
    "INSTALLATION_COMPLETE.txt",
    "*ALL FIXED - READ THIS.txt",
    # Dead-code stubs in src/ui
    "src/ui/quick_share_tab.py",
    "src/ui/credentials_tab.py"
)

$deleted = 0
$missing = 0

foreach ($file in $targets) {
    try {
        if (Test-Path -Path $file -PathType Leaf) {
            # -ErrorAction Stop turns failures into terminating errors so the
            # catch below reports [FAILED] and the count stays honest.
            Remove-Item -Path $file -Force -ErrorAction Stop
            Write-Host "  [DELETED] $file" -ForegroundColor Green
            $deleted++
        } else {
            Write-Host "  [already gone] $file" -ForegroundColor DarkGray
            $missing++
        }
    } catch {
        Write-Host "  [FAILED ] $file  ($_)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "======================================================================"
if ($deleted -gt 0) {
    Write-Host "  Done! $deleted file(s) deleted, $missing already absent." -ForegroundColor Green
} else {
    Write-Host "  Nothing to delete - all targets already gone." -ForegroundColor Yellow
}
Write-Host "======================================================================"
Write-Host ""

Write-Host "Remaining project files that are KEPT:" -ForegroundColor Cyan
Get-ChildItem -File | Where-Object { $_.Name -notmatch '^\.git' } |
    Select-Object -ExpandProperty Name | Sort-Object

Write-Host ""
Write-Host "Press Enter to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
