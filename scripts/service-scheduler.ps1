Set-Location 'D:\Codex'
New-Item -ItemType Directory -Force 'D:\Codex\logs' | Out-Null
Set-Content 'D:\Codex\logs\scheduler.pid' $PID
$env:PYTHONPATH = 'D:\Codex\src'
try {
    & 'D:\Codex\.venv\Scripts\python.exe' -m app.cli.scheduler serve *>> 'D:\Codex\logs\scheduler.log'
}
finally {
    Remove-Item 'D:\Codex\logs\scheduler.pid' -ErrorAction SilentlyContinue
}
