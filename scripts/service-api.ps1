Set-Location 'D:\Codex'
New-Item -ItemType Directory -Force 'D:\Codex\logs' | Out-Null
Set-Content 'D:\Codex\logs\api.pid' $PID
$env:PYTHONPATH = 'D:\Codex\src'
try {
    & 'D:\Codex\.venv\Scripts\python.exe' -m uvicorn app.api.main:app --app-dir src --host 127.0.0.1 --port 8000 *>> 'D:\Codex\logs\api.log'
}
finally {
    Remove-Item 'D:\Codex\logs\api.pid' -ErrorAction SilentlyContinue
}
