# Step 2: Local Development And GitHub Flow

## Recommended Flow

1. Make changes locally.
2. Run a focused compile or smoke check.
3. Commit to `main`.
4. Push to GitHub.
5. Update Oracle with `deploy/oracle/deploy-update.sh`.

## Local Repository

- workspace: `D:\Codex`
- repository: `https://github.com/eljja/ai-stock-arena`
- default branch: `main`

## Local Setup

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Typical local checks:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m py_compile src\app\api\main.py src\app\dashboard\main.py
```

## Local Services

Start or restart local background services:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\start-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\restart-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\status-background-services.ps1
```

## Git Commands

```powershell
git status
git add <files>
git commit -m "Describe the change"
git push origin main
```

## Oracle Update Flow

```bash
cd /opt/ai-stock-arena/current
bash deploy/oracle/deploy-update.sh
```

The Oracle server should not be treated as the source of truth for code. Server-local edits should either be moved back into Git or backed up before aligning to `origin/main`.
