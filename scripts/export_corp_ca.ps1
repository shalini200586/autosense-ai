# Exports corporate TLS-inspection root CAs (e.g. Zscaler) from the Windows trust store to certs/corp-root.pem
# so Python/Docker can verify HTTPS behind a corporate proxy WITHOUT disabling verification.
param([string]$Pattern = 'Zscaler')
$out = Join-Path (Split-Path $PSScriptRoot -Parent) 'certs'
New-Item -ItemType Directory -Force $out | Out-Null
$found = @{}
foreach ($store in 'Cert:\CurrentUser\Root', 'Cert:\LocalMachine\Root') {
  foreach ($c in (Get-ChildItem $store)) {
    if ($c.Subject -match $Pattern) { $found[$c.Thumbprint] = $c }
  }
}
$pem = ''
foreach ($c in $found.Values) {
  $b64 = [Convert]::ToBase64String($c.RawData, 'InsertLineBreaks') -replace "`r", ''
  $pem += "-----BEGIN CERTIFICATE-----`n$b64`n-----END CERTIFICATE-----`n"
}
[IO.File]::WriteAllText((Join-Path $out 'corp-root.pem'), $pem)
Write-Host "Exported $($found.Count) certificate(s) matching '$Pattern' to certs/corp-root.pem"
