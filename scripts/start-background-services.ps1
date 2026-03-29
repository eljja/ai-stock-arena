Set-Location 'D:\Codex'
New-Item -ItemType Directory -Force 'D:\Codex\logs' | Out-Null

$powerShellExe = 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'

$services = @(
    @{ Name = 'API'; Script = 'D:\Codex\scripts\service-api.ps1'; PidFile = 'D:\Codex\logs\api.pid'; Probe = 'http://127.0.0.1:8000/health' },
    @{ Name = 'Dashboard'; Script = 'D:\Codex\scripts\service-dashboard.ps1'; PidFile = 'D:\Codex\logs\dashboard.pid'; Probe = 'http://127.0.0.1:8501' },
    @{ Name = 'Scheduler'; Script = 'D:\Codex\scripts\service-scheduler.ps1'; PidFile = 'D:\Codex\logs\scheduler.pid'; Probe = $null }
)

function Test-AliveProcess {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) {
        return $false
    }
    $pidValue = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pidValue) {
        return $false
    }
    $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
    return $null -ne $process
}

foreach ($service in $services) {
    if (Test-AliveProcess -PidFile $service.PidFile) {
        Write-Host "$($service.Name) already running" -ForegroundColor Yellow
        continue
    }
    Start-Process -FilePath $powerShellExe -WindowStyle Hidden -ArgumentList @(
        '-ExecutionPolicy', 'Bypass',
        '-File', $service.Script
    ) | Out-Null
    Write-Host "Started $($service.Name)" -ForegroundColor Green
}

Start-Sleep -Seconds 6
foreach ($service in $services) {
    if ($service.Probe) {
        try {
            $response = Invoke-WebRequest -Uri $service.Probe -UseBasicParsing -TimeoutSec 5
            Write-Host "$($service.Name) probe: $($response.StatusCode)" -ForegroundColor Cyan
        }
        catch {
            Write-Host "$($service.Name) probe failed: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

Write-Host 'Background services requested.' -ForegroundColor Cyan
Write-Host 'Dashboard: http://127.0.0.1:8501'
Write-Host 'API: http://127.0.0.1:8000/health'
