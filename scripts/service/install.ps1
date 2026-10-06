<#
.SYNOPSIS
  Installs FB Automation as a Windows service that starts with the machine.

.DESCRIPTION
  Uses NSSM (https://nssm.cc) to run the built API server as a service. The
  server also serves the built web app, so once the service is up the whole
  system lives at http://localhost:<PORT> (PORT from .env, 3001 by default).

  Run once after `pnpm build`. Re-run after every build to pick up changes
  (it restarts the service). Needs administrator rights and asks for them.

  The service runs as LocalSystem. Browser profiles, the database and logs
  stay under the repository's data\ directory, and the Playwright browsers
  installed for the current user are pointed at explicitly, because
  LocalSystem has a different %LOCALAPPDATA%.

  Anything that needs a visible browser window — solving a captcha by hand —
  cannot happen inside a service (services have no desktop). Keep headless on
  in Settings while the service runs; to sign accounts in by hand, stop the
  service and run `pnpm dev` for that session.
#>
param(
  [string]$ServiceName = 'FBAutomation',
  [string]$DisplayName = 'FB Automation (MCARSPH)'
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$entry = Join-Path $root 'apps\server\dist\main.js'
$node = (Get-Command node.exe -ErrorAction Stop).Source
$logDir = Join-Path $root 'data\logs'
$browsers = Join-Path $env:LOCALAPPDATA 'ms-playwright'

if (-not (Test-Path $entry)) {
  throw "Nothing to run: $entry is missing. Run 'pnpm build' first."
}
if (-not (Test-Path $browsers)) {
  throw "No Playwright browsers at $browsers. Run 'pnpm exec playwright install chromium' first."
}

$nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $nssm) {
  $candidate = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter nssm.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like '*win64*' } | Select-Object -First 1
  if (-not $candidate) { throw "nssm.exe not found. Install it with: winget install --id NSSM.NSSM -e" }
  $nssmPath = $candidate.FullName
} else {
  $nssmPath = $nssm.Source
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  Write-Host 'Administrator rights are needed to register a service; asking for them...'
  $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-ServiceName', $ServiceName, '-DisplayName', "`"$DisplayName`"")
  Start-Process powershell.exe -Verb RunAs -ArgumentList $args -Wait
  exit
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
  Write-Host "Stopping the existing $ServiceName service..."
  & $nssmPath stop $ServiceName confirm | Out-Null
  & $nssmPath remove $ServiceName confirm | Out-Null
}

Write-Host "Registering $ServiceName..."
# Windows PowerShell strips the quotes around an argument before a native
# program sees it, so nssm would store the entry path bare and node would be
# started with 'C:\...\FB' and 'AUTOMATION\...' as two arguments. Three quotes
# on each side survive as one pair, and nssm keeps them in AppParameters.
& $nssmPath install $ServiceName $node "`"`"`"$entry`"`"`""
& $nssmPath set $ServiceName DisplayName $DisplayName
& $nssmPath set $ServiceName Description 'Facebook automation queue and control panel for MCARSPH.'
& $nssmPath set $ServiceName AppDirectory $root
& $nssmPath set $ServiceName AppEnvironmentExtra "NODE_ENV=production" "PLAYWRIGHT_BROWSERS_PATH=$browsers"
& $nssmPath set $ServiceName AppStdout (Join-Path $logDir 'service.out.log')
& $nssmPath set $ServiceName AppStderr (Join-Path $logDir 'service.err.log')
& $nssmPath set $ServiceName AppRotateFiles 1
& $nssmPath set $ServiceName AppRotateOnline 1
& $nssmPath set $ServiceName AppRotateBytes 10485760
& $nssmPath set $ServiceName AppExit Default Restart
& $nssmPath set $ServiceName AppRestartDelay 5000
& $nssmPath set $ServiceName AppStopMethodConsole 15000
& $nssmPath set $ServiceName Start SERVICE_AUTO_START

Write-Host "Starting $ServiceName..."
& $nssmPath start $ServiceName
Start-Sleep -Seconds 3
& $nssmPath status $ServiceName

$port = 3001
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
  $match = Select-String -Path $envFile -Pattern '^PORT=(\d+)' | Select-Object -First 1
  if ($match) { $port = [int]$match.Matches[0].Groups[1].Value }
}
Write-Host ''
Write-Host "Installed. Open http://localhost:$port"
Write-Host "Logs: $logDir\service.out.log and service.err.log"
Write-Host "Manage: nssm start|stop|restart|status $ServiceName  (or services.msc)"
