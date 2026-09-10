# ======================================================================
#  install_git.ps1 — Install Git for Windows
# ======================================================================
#  Enables terminal (bash) commands for the AI assistant and lets it
#  remove dead module files from disk / run the test suite.
#
#  Strategy:
#    1. Reuse an existing Git bash if one is already installed
#    2. Try winget (Windows Package Manager) — cleanest route
#    3. Fall back to a silent download of the latest official installer
#    4. Set CODEBUFF_GIT_BASH_PATH (the env var the AI assistant reads)
#    5. Verify bash.exe actually runs
# ======================================================================

Write-Host "======================================================================"
Write-Host "  Installing Git for Windows"
Write-Host "======================================================================"
Write-Host ""
Write-Host "This enables terminal (bash) commands for the AI assistant"
Write-Host "and lets it remove the dead module files from disk."
Write-Host ""

# ── Common install locations for bash.exe ──────────────────────────
$bashCandidates = @(
    "$env:ProgramFiles\Git\bin\bash.exe",
    "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
    "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
)
$bashPath = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

# ── 0. Reuse an existing install ───────────────────────────────────
if ($bashPath) {
    Write-Host "[✓] Git bash already installed at:" -ForegroundColor Green
    Write-Host "    $bashPath"
} else {
    # ── 1. Try winget first ────────────────────────────────────────
    Write-Host "[1/3] Checking for winget (Windows Package Manager)..." -ForegroundColor Cyan
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "      winget found — installing Git.Git (this may take a moment)..." -ForegroundColor Cyan
        & winget install --id Git.Git -e --source winget `
            --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
            Write-Host "      ✓ Git installed via winget" -ForegroundColor Green
        } else {
            Write-Host "      ⚠ winget returned code $LASTEXITCODE — trying direct download" -ForegroundColor Yellow
        }
    } else {
        Write-Host "      winget not available — using direct download" -ForegroundColor Yellow
    }

    $bashPath = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    # ── 2. Silent download of the latest official installer ────────
    if (-not $bashPath) {
        Write-Host "[2/3] Downloading latest Git for Windows..." -ForegroundColor Cyan
        $installer = Join-Path $env:TEMP "git-for-windows-installer.exe"
        try {
            $release = Invoke-RestMethod -Uri `
                "https://api.github.com/repos/git-for-windows/git/releases/latest" `
                -Headers @{ "User-Agent" = "FB-Tool-Installer" }
            $asset = $release.assets | Where-Object {
                $_.name -match '^Git-[\d.]+-64-bit\.exe$'
            } | Select-Object -First 1
            if (-not $asset) { throw "No 64-bit installer asset found in latest release" }

            Write-Host "      Downloading $($asset.name) ..."
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installer -UseBasicParsing
        } catch {
            Write-Host "      ⚠ Auto-download failed: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "      Please install Git for Windows manually from:" -ForegroundColor Yellow
            Write-Host "          https://git-scm.com/download/win"
            Write-Host "      Then re-run this script, or set the"
            Write-Host "      CODEBUFF_GIT_BASH_PATH environment variable yourself."
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 1
        }

        Write-Host "[3/3] Installing (silent, default options)..." -ForegroundColor Cyan
        $proc = Start-Process -FilePath $installer -ArgumentList `
            "/VERYSILENT", "/NORESTART", "/SP-", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS" `
            -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            Write-Host "      ⚠ Installer exited with code $($proc.ExitCode)" -ForegroundColor Red
            Write-Host "      You may need to run this script as Administrator."
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 1
        }

        $bashPath = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $bashPath) {
            Write-Host "      ⚠ Installed, but bash.exe wasn't found at the expected paths." -ForegroundColor Red
            Write-Host "      Locate bash.exe and set CODEBUFF_GIT_BASH_PATH manually."
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
}

# ── 3. Point the AI assistant at this bash ─────────────────────────
Write-Host ""
Write-Host "Setting CODEBUFF_GIT_BASH_PATH..." -ForegroundColor Cyan
[Environment]::SetEnvironmentVariable("CODEBUFF_GIT_BASH_PATH", $bashPath, "User")
Write-Host "    $bashPath" -ForegroundColor Green

# ── 4. Verify bash actually runs ───────────────────────────────────
Write-Host ""
Write-Host "Verifying bash works..." -ForegroundColor Cyan
& $bashPath --version
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "======================================================================"
    Write-Host "  SUCCESS! Git for Windows is ready." -ForegroundColor Green
    Write-Host "======================================================================"
    Write-Host ""
    Write-Host "IMPORTANT: Restart the AI assistant app so it picks up the"
    Write-Host "new environment variable. Then ask it to:"
    Write-Host "    1. Delete the dead module files (quick_share_tab.py,"
    Write-Host "       credentials_tab.py)"
    Write-Host "    2. Run the unit test suite"
    Write-Host ""
} else {
    Write-Host "⚠ bash.exe exists but failed to run (exit $LASTEXITCODE)" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"
