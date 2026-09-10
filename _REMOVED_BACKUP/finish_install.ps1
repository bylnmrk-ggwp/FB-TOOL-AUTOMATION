Write-Host "======================================================================"
Write-Host "  Completing Playwright Browser Installation"
Write-Host "======================================================================"
Write-Host ""
Write-Host "Downloading Chromium browser (114 MB)..."
Write-Host "This may take 3-5 minutes depending on your internet speed..."
Write-Host ""

& python -m playwright install chromium

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "======================================================================"
    Write-Host "  SUCCESS! Installation complete." -ForegroundColor Green
    Write-Host "======================================================================"
    Write-Host ""
    
    # Test the installation
    Write-Host "Testing installation..." -ForegroundColor Cyan
    $testResult = & python check_status.py
    Write-Host $testResult
} else {
    Write-Host ""
    Write-Host "Browser installation failed. You may need to:" -ForegroundColor Red
    Write-Host "  1. Check your internet connection"
    Write-Host "  2. Run manually: python -m playwright install chromium"
}

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
