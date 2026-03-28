Set-Location 'D:\Codex'
$env:PYTHONPATH = 'D:\Codex\src'
& 'D:\Codex\.venv\Scripts\python.exe' -m uvicorn app.api.main:app --app-dir src --host 127.0.0.1 --port 8000
