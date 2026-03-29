$tasks = 'AIStockArena-API', 'AIStockArena-Dashboard', 'AIStockArena-Scheduler'
foreach ($task in $tasks) {
    schtasks /Run /TN $task | Out-Host
}
Write-Host 'Started AI Stock Arena background tasks.' -ForegroundColor Green
