Set-Location 'D:\Codex'
New-Item -ItemType Directory -Force 'D:\Codex\logs' | Out-Null
Set-Content 'D:\Codex\logs\dashboard.pid' $PID
$env:PYTHONPATH = 'D:\Codex\src'
try {
    & 'D:\Codex\.venv\Scripts\python.exe' -m streamlit run src\app\dashboard\main.py --server.headless true --server.address 127.0.0.1 --server.port 8501 *>> 'D:\Codex\logs\dashboard.log'
}
finally {
    Remove-Item 'D:\Codex\logs\dashboard.pid' -ErrorAction SilentlyContinue
}
