# Remove Shiori: the app, its Start menu and Start-with-Windows shortcuts.
# Your parks stay in %LOCALAPPDATA%\Shiori unless you add -RemoveParks.
param([switch]$RemoveParks)
$ErrorActionPreference = "Stop"
$target = $PSScriptRoot

Get-Process Shiori -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$target*" } | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item (Join-Path ([Environment]::GetFolderPath("Programs")) "Shiori.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Startup")) "Shiori.lnk") -ErrorAction SilentlyContinue
# Take out the block "Remember PowerShell folders" may have added to your profiles (see psprofile.py)
$documents = [Environment]::GetFolderPath("MyDocuments")
foreach ($folder in "WindowsPowerShell", "PowerShell") {
    $profilePath = Join-Path $documents "$folder\Microsoft.PowerShell_profile.ps1"
    if (Test-Path -LiteralPath $profilePath) {
        $text = Get-Content -LiteralPath $profilePath -Raw
        $cleaned = $text -replace '(?s)# >>> Shiori:.*?# <<< Shiori <<<\r?\n?', ''
        if ($cleaned -cne $text) { Set-Content -LiteralPath $profilePath -Value $cleaned -NoNewline }
    }
}
if ($RemoveParks) { Remove-Item (Join-Path $env:LOCALAPPDATA "Shiori") -Recurse -Force -ErrorAction SilentlyContinue }

# A script can't delete the folder it runs from: hand that to a short-lived helper
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command",
    "Start-Sleep 2; Remove-Item -LiteralPath '$target' -Recurse -Force"
Write-Host "Shiori removed." $(if ($RemoveParks) { "Your parks were deleted too." } else { "Your parks are kept in $env:LOCALAPPDATA\Shiori." })
