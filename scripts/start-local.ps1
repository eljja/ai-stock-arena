Set-Location 'D:\Codex'

$host.ui.RawUI.WindowTitle = 'AI Stock Arena Launcher'

Write-Host 'Starting AI Stock Arena local services in separate PowerShell windows...' -ForegroundColor Cyan

$powerShellExe = 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'

$services = @(
    @{
        Name = 'AI Stock Arena API'
        Script = 'D:\Codex\scripts\run-api.ps1'
    },
    @{
        Name = 'AI Stock Arena Dashboard'
        Script = 'D:\Codex\scripts\run-dashboard.ps1'
    },
    @{
        Name = 'AI Stock Arena Scheduler'
        Script = 'D:\Codex\scripts\run-scheduler.ps1'
    }
)

foreach ($service in $services) {
    Start-Process -FilePath $powerShellExe -WorkingDirectory 'D:\Codex' -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-File', $service.Script
    ) | Out-Null
    Write-Host "Launched: $($service.Name)" -ForegroundColor Green
}

Write-Host ''
Write-Host 'Endpoints:' -ForegroundColor Yellow
Write-Host '  Dashboard  http://127.0.0.1:8501'
Write-Host '  API        http://127.0.0.1:8000/health'
Write-Host '  Runs       http://127.0.0.1:8000/run-requests?selected_only=true&limit=20'
Write-Host ''
Write-Host 'You can close this launcher window. The three service windows stay open.' -ForegroundColor Cyan
