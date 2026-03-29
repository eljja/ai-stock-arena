@echo off
cd /d D:\Codex
start "AI Stock Arena API" powershell -NoExit -ExecutionPolicy Bypass -File "D:\Codex\scripts\run-api.ps1"
start "AI Stock Arena Dashboard" powershell -NoExit -ExecutionPolicy Bypass -File "D:\Codex\scripts\run-dashboard.ps1"
start "AI Stock Arena Scheduler" powershell -NoExit -ExecutionPolicy Bypass -File "D:\Codex\scripts\run-scheduler.ps1"
echo AI Stock Arena local services launched.
echo Dashboard: http://127.0.0.1:8501
echo API: http://127.0.0.1:8000/health
echo Runs: http://127.0.0.1:8000/run-requests?selected_only=true^&limit=20
pause
