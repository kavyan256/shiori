# Signs Shiori.exe so Windows stops warning about an unknown publisher.
# build.ps1 runs this when SHIORI_CERT_THUMBPRINT is set; without it the build stays unsigned.
#
#   $env:SHIORI_CERT_THUMBPRINT = "<the certificate's thumbprint>"
#
# The certificate must already be in your Windows certificate store (or on its hardware token).
# signtool comes with the Windows SDK. See packaging\SIGNING.md for where to get a certificate.
param([Parameter(Mandatory)][string]$File)
$ErrorActionPreference = "Stop"

$signtool = Get-Command signtool -ErrorAction SilentlyContinue
if (-not $signtool) {
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName | Select-Object -Last 1
}
if (-not $signtool) { throw "signtool not found: install the Windows SDK" }

$tool = if ($signtool.Source) { $signtool.Source } else { $signtool.FullName }
# /tr + /td: a timestamp, so the signature stays valid after the certificate expires
& $tool sign /sha1 $env:SHIORI_CERT_THUMBPRINT /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 $File
if ($LASTEXITCODE -ne 0) { throw "Signing failed" }
& $tool verify /pa $File
if ($LASTEXITCODE -ne 0) { throw "The signature didn't verify" }
"Signed: $File"
