# AI Stock Arena

AI Stock Arena is a pure-model virtual trading benchmark for comparing how different LLMs make trading decisions under the same rules, the same hourly market context, and the same shared news feed.

## What This First Version Does

- Compares multiple OpenRouter-backed LLM profiles on the same benchmark rules
- Uses unified `KR` and `US` portfolios instead of exchange-by-exchange league tables
- Runs hourly-style virtual trading with market-specific costs and persistent portfolio state
- Collects hourly market data for tracked instruments and stores historical snapshots
- Stores shared news batches and injects the same recent news context into every model
- Tracks LLM decisions, token usage, estimated LLM cost, trades, positions, and performance snapshots
- Provides a dark-mode Streamlit dashboard and a FastAPI service for operational control
- Supports admin-managed investment profiles, custom prompts, runtime windows, manual refresh actions, and secret management

## Benchmark Principles

- Pure model comparison first: all models receive the same screened candidates and the same shared news context
- Search-enabled variants are treated as separate profiles and should be compared in a different league
- Rankings are based on return and risk metrics, not on combined multi-currency equity
- Trade costs and LLM token costs are both tracked as benchmark overhead

## Current Stack

- `FastAPI` for API and admin endpoints
- `Streamlit` for the dashboard
- `SQLAlchemy` for persistence
- `SQLite` for local development, PostgreSQL recommended for Oracle deployment
- `yfinance` for prototype market data collection
- `OpenRouter` for model access
- `Marketaux` for shared news collection

## Main Features

- OpenRouter model catalog and free-model probing
- `model + prompt` investment profiles with on/off API control
- Admin-managed runtime cadence, UTC windows, and news policy
- Shared news collection policies:
  - `development_fallback`
  - `live_strict`
- Manual admin actions for:
  - shared news refresh
  - full trade-cycle execution
  - simulation reset
- Copy-trade style API for current model allocations
- Background launch scripts for local API, dashboard, and scheduler

## Repository Layout

- [First release overview](D:/Codex/docs/first-release-overview.md)
- [Runtime and admin guide](D:/Codex/docs/runtime-admin-guide.md)
- [System specification](D:/Codex/docs/step-01-system-spec.md)
- [Local and GitHub workflow](D:/Codex/docs/step-02-local-github-flow.md)
- [Oracle deployment](D:/Codex/docs/step-03-oracle-deployment.md)
- [Default runtime config](D:/Codex/config/defaults.toml)
- [Environment example](D:/Codex/.env.example)

## Local Setup

```powershell
D:\python\anaconda3\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

## Useful Commands

```powershell
.\.venv\Scripts\python.exe -m app.cli.bootstrap --skip-openrouter-sync
.\.venv\Scripts\python.exe -m app.cli.models list-models --sort-by price-low --free-mode only --limit 20
.\.venv\Scripts\python.exe -m app.cli.market screen US --limit 5
.\.venv\Scripts\python.exe -m app.cli.market collect-history US
.\.venv\Scripts\python.exe -m app.cli.market collect-history KR
.\.venv\Scripts\python.exe -m app.cli.news collect US
.\.venv\Scripts\python.exe -m app.cli.news collect KR
.\.venv\Scripts\python.exe -m app.cli.scheduler status
.\.venv\Scripts\python.exe -m app.cli.scheduler run-once
.\.venv\Scripts\python.exe -m app.cli.scheduler serve
```

## Local Background Launchers

```powershell
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\start-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\restart-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\status-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\stop-background-tasks.ps1
```

Default local URLs:

- Dashboard: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8000/health`
- Scheduler status: `http://127.0.0.1:8000/scheduler-status`

## Configuration Notes

- LLM-facing prompts and payloads are written in English.
- Local development uses `SQLite` by default.
- Oracle deployment should use PostgreSQL and the `live_strict` news collection policy.
- Runtime secrets can be updated from the admin panel and are persisted separately from `.env` defaults.
- `Marketaux` news is intended as shared benchmark context, not as a model-specific tool.

## First Release Status

This repository now contains the first end-to-end working version of AI Stock Arena:

- benchmark data model
- hourly market snapshot pipeline
- shared-news pipeline
- LLM decision logging
- virtual trading engine
- ranking-first dashboard
- local background launchers
- Oracle deployment assets

## Next Major Work

- PostgreSQL-first local development path
- broader KR/US instrument universe coverage
- stronger KR-specific news source quality
- chart-only benchmark mode
- production deployment on Oracle Cloud Free Tier
