# AI Stock Arena

AI Stock Arena is a pure-model virtual trading benchmark for comparing how different LLMs make trading decisions under the same rules, the same hourly market context, and the same shared news feed.

## Live Deployment

- Dashboard: [https://aistockarena.com](https://aistockarena.com)
- API health: [https://aistockarena.com/api/health](https://aistockarena.com/api/health)
- Scheduler status: [https://aistockarena.com/api/scheduler-status](https://aistockarena.com/api/scheduler-status)

## Live Screenshot

The image below is a live snapshot of the deployed site.

![AI Stock Arena live dashboard](https://image.thum.io/get/width/1600/crop/900/https://aistockarena.com)

## Current Status

AI Stock Arena is currently running in a free-model stabilization phase.

- The live benchmark is currently focused on OpenRouter free models.
- The system records performance, portfolio state, trades, run status, token usage, and estimated LLM overhead.
- After the free-model league is stable, paid model profiles will be added and benchmarked under the same rules.

## Benchmark Principles

- Pure model comparison first: all models receive the same screened candidates and the same shared news context.
- Search-enabled variants are treated as separate profiles and should be compared in a different league.
- Rankings are based on fee-adjusted return and risk metrics, not on combined multi-currency equity.
- Trade costs and LLM token costs are both tracked as benchmark overhead.
- News is shared benchmark context, not model-side browsing.

## What This Version Does

- Compares multiple OpenRouter-backed LLM profiles on the same benchmark rules.
- Uses unified `KR` and `US` portfolios instead of exchange-by-exchange league tables.
- Runs hourly-style virtual trading with market-specific costs and persistent portfolio state.
- Collects hourly market data for tracked instruments and stores historical snapshots.
- Collects shared news batches and injects the same recent news context into every model.
- Tracks LLM decisions, token usage, estimated LLM cost, trades, positions, and performance snapshots.
- Provides a dark-mode Streamlit dashboard and a FastAPI service for operational control.
- Supports admin-managed investment profiles, custom prompts, runtime windows, manual refresh actions, and secret management.

## Public API

The deployment intentionally exposes read-only benchmark data so anyone can inspect rankings, holdings, and trade activity.

### Public Endpoints

- `GET /api/health`
- `GET /api/models?selected_only=true`
- `GET /api/rankings?selected_only=true`
- `GET /api/portfolios?selected_only=true`
- `GET /api/positions?selected_only=true&market_code=US`
- `GET /api/trades?selected_only=true&market_code=KR&limit=20`
- `GET /api/snapshots?selected_only=true&limit=200`
- `GET /api/news?market_code=US&limit=5`
- `GET /api/run-requests?selected_only=true&limit=50`
- `GET /api/copy-trade/{model_id}?market_code=US`

### Example Requests

```bash
curl https://aistockarena.com/api/health
curl "https://aistockarena.com/api/rankings?selected_only=true"
curl "https://aistockarena.com/api/positions?selected_only=true&market_code=US"
curl "https://aistockarena.com/api/trades?selected_only=true&market_code=KR&limit=20"
curl "https://aistockarena.com/api/copy-trade/openrouter/free?market_code=US"
```

### Copy-Trade Style Response

`/api/copy-trade/{model_id}` returns:

- current total equity
- current cash weight
- current positions
- target weight by position
- last action per ticker
- recent trades

This makes the live benchmark transparent and allows external consumers to follow what each model currently holds and has recently traded.

## Stack

- `FastAPI` for API and admin endpoints
- `Streamlit` for the dashboard
- `SQLAlchemy` for persistence
- `SQLite` for local development, PostgreSQL for the Oracle deployment
- `yfinance` for prototype market data collection
- `OpenRouter` for model access
- `Marketaux` for shared news collection
- `Oracle Cloud Free Tier` for the current public deployment

## Repository Layout

- [First release overview](docs/first-release-overview.md)
- [Runtime and admin guide](docs/runtime-admin-guide.md)
- [System specification](docs/step-01-system-spec.md)
- [Local and GitHub workflow](docs/step-02-local-github-flow.md)
- [Oracle deployment](docs/step-03-oracle-deployment.md)
- [Default runtime config](config/defaults.toml)
- [Environment example](.env.example)

## Local Setup

```powershell
.\.venv\Scripts\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

## Useful Commands

```powershell
.\.venv\Scripts\python.exe -m app.cli.bootstrap --skip-openrouter-sync
.\.venv\Scripts\python.exe -m app.cli.models list-models --sort-by price-low --free-mode only --limit 20
.\.venv\Scripts\python.exe -m app.cli.models probe-free-models --target-count 10 --candidate-limit 20 --sort-by popular
.\.venv\Scripts\python.exe -m app.cli.models add-free-models --additional-count 10 --candidate-limit 40 --sort-by popular
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
powershell -ExecutionPolicy Bypass -File .\scripts\start-background-services.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restart-background-services.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\status-background-services.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop-background-tasks.ps1
```

Default local URLs:

- Dashboard: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8000/health`
- Scheduler status: `http://127.0.0.1:8000/scheduler-status`

## Oracle Operations

Initial Oracle deployment and updates are documented in [docs/step-03-oracle-deployment.md](docs/step-03-oracle-deployment.md).

Typical update flow:

```bash
cd /opt/ai-stock-arena/current
bash deploy/oracle/deploy-update.sh
```

To add more successful free models without replacing the current selected set:

```bash
cd /opt/ai-stock-arena/current
bash scripts/linux/add-free-models.sh 10 40 popular
```

## Configuration Notes

- LLM-facing prompts and payloads are written in English.
- The live Oracle deployment uses PostgreSQL.
- Oracle should run with the `live_strict` news collection policy.
- Runtime secrets can be updated from the admin panel and are persisted separately from `.env` defaults.
- Shared news currently runs on a 30-minute cadence.
- `Marketaux` news is benchmark context, not model-specific web search.

## First Release Scope

This repository now contains the first end-to-end working version of AI Stock Arena:

- benchmark data model
- hourly market snapshot pipeline
- shared-news pipeline
- LLM decision logging
- virtual trading engine
- ranking-first dashboard
- local background launchers
- Oracle deployment assets
- public benchmark API

## Next Major Work

- stabilize the free-model league further
- add paid-model benchmark profiles after the free league is stable
- broaden KR and US instrument universe coverage
- improve KR-specific news source quality
- refine production monitoring and operations on Oracle Cloud
