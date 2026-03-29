$taskRoot = 'AIStockArena'
$powerShellExe = 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'
$tasks = @(
    @{ Name = "$taskRoot-API"; Script = 'D:\Codex\scripts\service-api.ps1' },
    @{ Name = "$taskRoot-Dashboard"; Script = 'D:\Codex\scripts\service-dashboard.ps1' },
    @{ Name = "$taskRoot-Scheduler"; Script = 'D:\Codex\scripts\service-scheduler.ps1' }
)
foreach ($task in $tasks) {
    $taskCommand = '"' + $powerShellExe + '" -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $task.Script + '"'
    schtasks /Create /TN $task.Name /SC ONLOGON /TR $taskCommand /RL LIMITED /F | Out-Host
}
Write-Host 'Installed AI Stock Arena scheduled tasks.' -ForegroundColor Green
