<#
.SYNOPSIS
  Removes the FB Automation Windows service. Data, profiles and logs stay.
#>
param(
  [string]$ServiceName = 'FBAutomation'
)

$ErrorActionPreference = 'Stop'

$nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $nssm) {
  $candidate = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter nssm.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like '*win64*' } | Select-Object -First 1
  if (-not $candidate) { throw 'nssm.exe not found.' }
  $nssmPath = $candidate.FullName
} else {
  $nssmPath = $nssm.Source
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  Write-Host 'Administrator rights are needed to remove a service; asking for them...'
  Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-ServiceName', $ServiceName) -Wait
  exit
}

if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
  Write-Host "$ServiceName is not installed."
  exit
}

& $nssmPath stop $ServiceName confirm | Out-Null
& $nssmPath remove $ServiceName confirm
Write-Host "$ServiceName removed. The database, profiles and logs under data\ were left alone."
