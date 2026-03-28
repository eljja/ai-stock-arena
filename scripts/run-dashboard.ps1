Set-Location 'D:\Codex'
$env:PYTHONPATH = 'D:\Codex\src'
& 'D:\Codex\.venv\Scripts\python.exe' -m streamlit run src\app\dashboard\main.py --server.address 127.0.0.1 --server.port 8501
