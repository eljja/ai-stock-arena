$pids = @(
    'D:\Codex\logs\api.pid',
    'D:\Codex\logs\dashboard.pid',
    'D:\Codex\logs\scheduler.pid'
)
foreach ($pidFile in $pids) {
    if (Test-Path $pidFile) {
        $pidValue = Get-Content $pidFile | Select-Object -First 1
        if ($pidValue) {
            Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
}
Write-Host 'Stopped AI Stock Arena background processes referenced by pid files.' -ForegroundColor Yellow
