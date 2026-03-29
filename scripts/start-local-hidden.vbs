Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell -NoExit -ExecutionPolicy Bypass -File ""D:\Codex\scripts\run-api.ps1""", 0, False
WshShell.Run "powershell -NoExit -ExecutionPolicy Bypass -File ""D:\Codex\scripts\run-dashboard.ps1""", 0, False
WshShell.Run "powershell -NoExit -ExecutionPolicy Bypass -File ""D:\Codex\scripts\run-scheduler.ps1""", 0, False
