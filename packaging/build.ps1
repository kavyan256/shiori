# Build Stage.exe and the zip a student downloads.
#
#   .\packaging\build.ps1
#
# Output: build\Stage-setup.zip, containing
#   Install Stage.cmd      double-click this
#   README.txt             the 3 steps
#   Stage\                 the app (Stage.exe + everything it needs, no Python required)

# "Continue", not "Stop": pip and PyInstaller print progress to stderr, which Windows
# PowerShell would treat as a failure. Real failures are caught by exit codes below.
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root ".venv\Scripts\python.exe"
$build = Join-Path $root "build"

& $py -m pip install -q --disable-pip-version-check pyinstaller==6.16.0
if ($LASTEXITCODE -ne 0) { throw "Couldn't install PyInstaller" }
& $py (Join-Path $PSScriptRoot "make_icon.py")
if ($LASTEXITCODE -ne 0) { throw "Couldn't draw the icon" }

# --windowed: no console window. --add-data: the bar's page goes inside the app.
& $py -m PyInstaller --noconfirm --clean --windowed --name Stage `
    --icon (Join-Path $PSScriptRoot "stage.ico") `
    --add-data "$(Join-Path $root 'web');web" `
    --distpath (Join-Path $build "dist") --workpath (Join-Path $build "work") --specpath $build `
    (Join-Path $root "main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$app = Join-Path $build "dist\Stage"
# The extension sits next to Stage.exe (not inside it): Chrome's "Load unpacked" needs a real folder
Copy-Item (Join-Path $root "extension") (Join-Path $app "extension") -Recurse -Force
Copy-Item (Join-Path $PSScriptRoot "install.ps1"), (Join-Path $PSScriptRoot "uninstall.ps1") $app -Force

$setup = Join-Path $build "Stage-setup"
Remove-Item $setup -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $setup | Out-Null
Copy-Item $app (Join-Path $setup "Stage") -Recurse
Copy-Item (Join-Path $PSScriptRoot "Install Stage.cmd"), (Join-Path $PSScriptRoot "README.txt") $setup

$zip = Join-Path $build "Stage-setup.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $setup "*") -DestinationPath $zip
"Built: $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
