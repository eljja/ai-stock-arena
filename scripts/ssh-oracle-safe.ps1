$ErrorActionPreference = "Stop"

$KeyPath = Join-Path $HOME "ssh-key-2026-03-29.key"
$HostName = "138.2.49.114"
$UserName = "ubuntu"
$CurrentUser = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME

if (-not (Test-Path $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

Write-Host "Fixing private key permissions..." -ForegroundColor Cyan
& icacls $KeyPath /inheritance:r | Out-Null
& icacls $KeyPath /remove "ELJJA-2024\CodexSandboxUsers" | Out-Null
& icacls $KeyPath /remove "NT AUTHORITY\Authenticated Users" | Out-Null
& icacls $KeyPath /remove "BUILTIN\Users" | Out-Null
& icacls $KeyPath /grant:r "${CurrentUser}:(R)" | Out-Null

Write-Host "Opening SSH session..." -ForegroundColor Green
ssh -i $KeyPath "$UserName@$HostName"
