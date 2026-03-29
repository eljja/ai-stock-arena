$tasks = 'AIStockArena-API', 'AIStockArena-Dashboard', 'AIStockArena-Scheduler'
foreach ($task in $tasks) {
    Write-Host "=== $task ===" -ForegroundColor Cyan
    schtasks /Query /TN $task /FO LIST 2>$null | Out-Host
    Write-Host ''
}
Write-Host 'PID files:' -ForegroundColor Cyan
Get-ChildItem 'D:\Codex\logs\*.pid' -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_.FullName }
