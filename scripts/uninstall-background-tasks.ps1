$tasks = 'AIStockArena-API', 'AIStockArena-Dashboard', 'AIStockArena-Scheduler'
foreach ($task in $tasks) {
    schtasks /Delete /TN $task /F 2>$null | Out-Host
}
Write-Host 'Removed AI Stock Arena scheduled tasks.' -ForegroundColor Yellow
