# Signing Shiori

Unsigned, Windows shows "Windows protected your PC" on first run. Signing needs a certificate that
proves who published the app. Check current prices and rules before paying: they change.

Options to look at, cheapest first:

1. **SignPath Foundation.** Free code signing for open source projects, by application. Shiori is MIT
   licensed on GitHub, which is the kind of project it's for. The signing runs in their service, from a
   GitHub Actions build, not with a certificate on your PC.
2. **Microsoft's cloud signing (Azure Trusted/Artifact Signing).** A low monthly fee, but it has limits
   on who can verify as an individual, and by country. Check that it's open to you first.
3. **A certificate from a certificate authority.** Usually a yearly cost and a hardware token. It works
   anywhere, and it's the most expensive route.

A signature alone doesn't remove the warning straight away: SmartScreen also goes by reputation, which a
new publisher builds up as people download the app.

## Using a certificate

Once it's in your Windows certificate store:

    $env:SHIORI_CERT_THUMBPRINT = "<thumbprint>"
    packaging\build.ps1

`build.ps1` then runs `sign.ps1` on `Shiori.exe` before zipping. Without that variable it builds unsigned,
as it always has.
