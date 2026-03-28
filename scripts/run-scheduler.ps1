Set-Location 'D:\Codex'
$env:PYTHONPATH = 'D:\Codex\src'
& 'D:\Codex\.venv\Scripts\python.exe' -m app.cli.scheduler serve
