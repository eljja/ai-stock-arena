$ErrorActionPreference = "Stop"

$KeyPath = Join-Path $HOME "ssh-key-2026-03-29.key"
$HostName = "138.2.49.114"
$UserName = "ubuntu"

ssh -i $KeyPath "$UserName@$HostName"
