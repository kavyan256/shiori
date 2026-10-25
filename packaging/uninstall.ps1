# Remove Stage: the app, its Start menu and Start-with-Windows shortcuts.
# Your parks stay in %LOCALAPPDATA%\Stage unless you add -RemoveParks.
param([switch]$RemoveParks)
$ErrorActionPreference = "Stop"
$target = $PSScriptRoot

Get-Process Stage -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$target*" } | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item (Join-Path ([Environment]::GetFolderPath("Programs")) "Stage.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Startup")) "Stage.lnk") -ErrorAction SilentlyContinue
if ($RemoveParks) { Remove-Item (Join-Path $env:LOCALAPPDATA "Stage") -Recurse -Force -ErrorAction SilentlyContinue }

# A script can't delete the folder it runs from: hand that to a short-lived helper
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command",
    "Start-Sleep 2; Remove-Item -LiteralPath '$target' -Recurse -Force"
Write-Host "Stage removed." $(if ($RemoveParks) { "Your parks were deleted too." } else { "Your parks are kept in $env:LOCALAPPDATA\Stage." })
