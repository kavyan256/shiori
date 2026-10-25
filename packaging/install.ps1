# Install Stage for this Windows user: no admin rights, nothing outside your user folder.
#   - copies Stage to %LOCALAPPDATA%\Programs\Stage
#   - adds Stage to the Start menu
#   - starts it (it lives in the tray; press Ctrl+Alt+S)
# Run by "Install Stage.cmd". Options for testing: -Target <folder> -NoShortcuts -NoLaunch
param(
    [string]$Target = (Join-Path $env:LOCALAPPDATA "Programs\Stage"),
    [switch]$NoShortcuts,
    [switch]$NoLaunch
)
$ErrorActionPreference = "Stop"
$source = $PSScriptRoot
Write-Host ""
Write-Host "  Installing Stage" -ForegroundColor Cyan
Write-Host "  -> $Target"

# An older copy running from the target folder would lock its files
Get-Process Stage -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Target*" } | Stop-Process -Force
Start-Sleep -Milliseconds 500

New-Item -ItemType Directory -Force $Target | Out-Null
Copy-Item (Join-Path $source "*") $Target -Recurse -Force
# Files from a downloaded zip are marked "from the internet", which makes Windows warn
# every time Stage starts. You chose to install it, so clear that mark on Stage's own files.
Get-ChildItem $Target -Recurse -File | Unblock-File

if (-not $NoShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    $menu = Join-Path ([Environment]::GetFolderPath("Programs")) "Stage.lnk"
    $link = $shell.CreateShortcut($menu)
    $link.TargetPath = Join-Path $Target "Stage.exe"
    $link.WorkingDirectory = $Target
    $link.Description = "Park your work by voice. Resume where your head was."
    $link.Save()
    Write-Host "  Added to the Start menu"
}

if (-not $NoLaunch) {
    Start-Process (Join-Path $Target "Stage.exe")
    Write-Host "  Started: look for the blue S in the tray (near the clock)" -ForegroundColor Green
}

Write-Host ""
Write-Host "  Try it: press Ctrl+Alt+S and say (or type) 'park'." -ForegroundColor White
Write-Host ""
Write-Host "  Optional, to see each browser tab: right-click the tray S -> 'Set up browser tabs...'"
Write-Host "  Start with Windows: right-click the tray S -> 'Start with Windows'"
Write-Host "  To uninstall later: run uninstall.ps1 in $Target"
Write-Host ""
