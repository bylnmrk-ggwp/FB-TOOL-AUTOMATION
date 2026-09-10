Write-Host "======================================================================"
Write-Host "  FB TOOL AUTOMATION - Installing Dependencies"
Write-Host "======================================================================"
Write-Host ""

Write-Host "[1/3] Installing Python packages..." -ForegroundColor Cyan
$packages = "playwright", "Pillow", "groq"

foreach ($package in $packages) {
    Write-Host "  Installing $package..." -NoNewline
    $result = & python -m pip install $package --quiet 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "  Error: $result"
        exit 1
    }
}

Write-Host ""
Write-Host "[2/3] Installing Playwright browser (may take 2-3 minutes)..." -ForegroundColor Cyan
$result = & python -m playwright install chromium 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Chromium installed successfully" -ForegroundColor Green
} else {
    Write-Host "  Browser installation failed" -ForegroundColor Red
    Write-Host "  Error: $result"
    exit 1
}

Write-Host ""
Write-Host "[3/3] Testing imports..." -ForegroundColor Cyan
$testScript = @"
import sys
try:
    from playwright.async_api import async_playwright
    from PIL import Image
    import groq
    import tkinter
    print('OK')
except ImportError as e:
    print(f'FAILED: {e}', file=sys.stderr)
    sys.exit(1)
"@

$result = & python -c $testScript 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  All imports successful" -ForegroundColor Green
} else {
    Write-Host "  Import test failed" -ForegroundColor Red
    Write-Host "  Error: $result"
    exit 1
}

Write-Host ""
Write-Host "======================================================================"
Write-Host "  SUCCESS! All dependencies installed." -ForegroundColor Green
Write-Host "======================================================================"
Write-Host ""
Write-Host "You can now run: RUN_APP.bat"
Write-Host ""
