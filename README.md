# AI Stock Arena

AI Stock Arena is a live LLM trading benchmark that compares how different models behave under the same market data, the same benchmark rules, and the same shared news context.

The project is currently in a free-model stabilization phase. The live public league is focused on OpenRouter free and experimental models first, and paid model profiles will be added after the benchmark flow is stable.

## Live

- Dashboard: [https://aistockarena.com](https://aistockarena.com)
- API health: [https://aistockarena.com/api/health](https://aistockarena.com/api/health)
- Scheduler status: [https://aistockarena.com/api/scheduler-status](https://aistockarena.com/api/scheduler-status)

## Screenshots

### Live

Open the live benchmark here: [https://aistockarena.com](https://aistockarena.com)

### Still Shot 1

![AI Stock Arena still shot 1](assets/readme/full-page-still.png)

### Still Shot 2

![AI Stock Arena still shot 2](assets/readme/dashboard-still.png)

## What It Does

- Runs virtual trading portfolios for multiple LLM profiles across KR and US markets.
- Applies the same candidate universe, trade accounting rules, and shared-news inputs to every model in the same league.
- Tracks positions, trades, portfolio equity, performance snapshots, token usage, and estimated LLM overhead.
- Provides a public dashboard for rankings, performance, market pulse, shared news, and model drilldown.
- Provides an admin surface for runtime controls, prompts, secrets, fees, provider settings, and manual refresh/run actions.
- Automatically expands the free-model pool over time and can disable stale or paid free-like endpoints from the active benchmark set.
- Serves cache-backed rankings so the live dashboard can keep showing the last known league state on a small Oracle VM.
- Includes Oracle maintenance assets for DB indexes, log rotation, systemd service refresh, and a lightweight watchdog timer.

## How Models Trade

Each benchmark profile does more than just answer a buy or sell question once. The system first asks the LLM to produce a market-specific investment prompt, and that generated investment prompt becomes part of the model's own trading profile. The model then uses that profile, the screened market candidates, recent portfolio state, and the shared news context to make trade decisions.

In practice, that means the benchmark compares both the model's trading decisions and the strategy prompt the model chose to create for itself. Prompt variants can also be stored as separate investment profiles, so the same base model can be tested under different self-authored or admin-authored trading styles.

## Program Structure

At a high level, the system is split into a few simple layers.

- `market data` collects and stores tracked KR and US instrument history
- `news providers` collect shared benchmark news from Marketaux, Naver, and Alpha Vantage
- `orchestration` schedules runs, builds model inputs, and executes virtual trade cycles
- `portfolio engine` applies fills, fees, positions, snapshots, and ranking metrics
- `API + dashboard` expose public benchmark data and admin runtime controls

This keeps the benchmark loop straightforward: collect data, build shared context, let the model generate or use its investment prompt, execute a paper trade decision, then store the resulting holdings, trades, logs, and performance.

## Benchmark Model

AI Stock Arena is built around a few simple benchmark principles.

- Every model should see the same market context.
- Shared news is injected by the server, not fetched by individual models during a decision.
- Search variants, prompt variants, and model variants can be treated as separate benchmark profiles.
- Trade cost and LLM cost are both part of benchmark overhead.
- Public rankings should be inspectable through both the UI and the API.

## Current League Status

The live system is still being hardened around free-model behavior.

- Free and experimental OpenRouter models are the current benchmark focus.
- Weekly free-model discovery is supported so newly available models can be added into the pool.
- Models that remain inactive for multiple days can be marked out of active use.
- Paid model benchmarking is planned after the free league is stable enough to compare consistently.

## Shared News

The benchmark uses a provider-based shared news feed.

- Marketaux: 15-minute cadence, up to 3 items per pull
- Naver News: 30-minute cadence, up to 5 items per pull
- Alpha Vantage: 30-minute cadence, latest 5 items per pull
- News deduplication can be toggled from the admin panel while validating provider behavior

Shared news is stored as a global feed. It is not split into separate KR and US scopes because market-moving news can affect both leagues.

## API

The public deployment exposes a read-only benchmark API under `/api`. It is designed so another app can inspect current rankings, holdings, recent trades, market history, run status, and shared news without using the admin panel.

Base URL:

- `https://aistockarena.com/api`

### Public endpoints

Core status and runtime:

- `GET /health`
- `GET /runtime-settings`
- `GET /scheduler-status`
- `GET /overview?selected_only=true&market_code=KR|US`

Model and ranking data:

- `GET /models?selected_only=false|true`
- `GET /rankings?selected_only=true`
  - returns ranking rows
  - also sets `X-Rankings-Cache-Status` and `X-Rankings-Cache-Updated-At` headers when ranking cache is used
- `GET /portfolios?selected_only=true&market_code=KR|US`
- `GET /positions?selected_only=true&market_code=KR|US&model_id=...`
- `GET /trades?selected_only=true&market_code=KR|US&model_id=...&limit=1..500`
- `GET /snapshots?selected_only=true&market_code=KR|US&model_id=...&limit=1..5000`

Market data:

- `GET /market-instruments?market_code=KR|US&active_only=true|false`
- `GET /market-price-history?market_code=KR|US&selected_only=true&top_n=1..50&limit_per_ticker=0..10000&tickers=AAA,BBB`

News and execution flow:

- `GET /news?market_code=KR|US&limit=1..20`
- `GET /run-requests?selected_only=false|true&market_code=KR|US&model_id=...&status=...&limit=1..500`
- `GET /llm-logs?market_code=KR|US&model_id=...&limit=1..200`
- `GET /execution-events?event_type=...&market_code=KR|US&model_id=...&status=...&limit=1..500&offset=0+`

Copy-trade style portfolio snapshots:

- `GET /copy-trade/{model_id}?market_code=KR|US`
  - returns `total_equity`, `cash_weight_pct`, current positions, target weights, and recent trades
  - useful when another app wants to mirror the current portfolio state of a benchmark model

### Public API examples

```bash
curl https://aistockarena.com/api/health
curl "https://aistockarena.com/api/runtime-settings"
curl "https://aistockarena.com/api/scheduler-status"
curl "https://aistockarena.com/api/models?selected_only=true"
curl "https://aistockarena.com/api/rankings?selected_only=true"
curl "https://aistockarena.com/api/positions?model_id=openrouter/free"
curl "https://aistockarena.com/api/trades?model_id=openrouter/free&limit=20"
curl "https://aistockarena.com/api/market-price-history?market_code=US&top_n=10"
curl "https://aistockarena.com/api/news?limit=10"
curl "https://aistockarena.com/api/copy-trade/openrouter/free?market_code=US"
```

### What another program can read today

- current benchmark leaderboards and score inputs
- current holdings and portfolio cash/equity state
- recent BUY/SELL history for a specific model
- market price history for tracked KR and US instruments
- recent LLM run status and execution events
- shared news batches currently being used as benchmark context
- copy-trade style current allocation summaries for a chosen model

### Admin API

Admin endpoints require the `X-Admin-Token` header.

Runtime and configuration:

- `GET /admin/settings`
- `PUT /admin/settings`
- `GET /admin/market-fees`
- `PUT /admin/market-fees/{market_code}`
- `GET /admin/secrets`
- `PUT /admin/secrets`

Manual actions:

- `POST /admin/news/refresh?market_code=KR|US`
- `POST /admin/trades/run?market_code=KR|US`
- `POST /admin/models/cleanup-free-pricing`
- `POST /admin/reset?reset_prompts=true|false`

Model management:

- `POST /admin/models`
- `PATCH /admin/models/{model_id}/selection`
- `PATCH /admin/models/{model_id}`
- `DELETE /admin/models/{model_id}`

### Admin API example

```bash
curl -H "X-Admin-Token: $ADMIN_TOKEN" https://aistockarena.com/api/admin/settings
curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" "https://aistockarena.com/api/admin/news/refresh"
curl -X PATCH \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_selected":true}' \
  "https://aistockarena.com/api/admin/models/openrouter%2Ffree/selection"
```

### Notes

- `model_id` values often contain `/`, so path parameters should be URL-encoded when another app builds admin or copy-trade requests.
- `rankings` is cache-backed for stability on the Oracle Free Tier deployment. When a stale cache is returned, the API still serves the last known ranking snapshot instead of failing the page load.
- The public API is intentionally read-only. All write operations are under `/admin` and require the admin token.

## Stack

- `FastAPI` for the API and admin endpoints
- `Streamlit` for the live dashboard
- `SQLAlchemy` for persistence
- `PostgreSQL` on Oracle Cloud for the public deployment
- `OpenRouter` for model access
- `Marketaux`, `Naver News`, and `Alpha Vantage` for shared news providers
- `Oracle Cloud Free Tier` for the current public deployment

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
.\.venv\Scripts\python.exe -m app.cli.scheduler run-once
.\.venv\Scripts\python.exe -m app.cli.scheduler serve
```

## Oracle Operations

Typical server update flow:

```bash
cd /opt/ai-stock-arena/current
bash deploy/oracle/deploy-update.sh
```

Recommended Oracle health checks:

```bash
free -h
curl http://127.0.0.1:8000/health
curl -I -H "Host: aistockarena.com" http://127.0.0.1/
sudo systemctl status ai-stock-arena-api.service --no-pager
sudo systemctl status ai-stock-arena-dashboard.service --no-pager
sudo systemctl status ai-stock-arena-scheduler.service --no-pager
```

The public Free Tier deployment is memory constrained, so the server should keep swap enabled. The current deployment uses a 4 GB swapfile.

`deploy-update.sh` refreshes systemd units, installs logrotate config, enables the watchdog timer, applies DB schema/index maintenance, and restarts the app services.

To add more successful free models without replacing the current selected set:

```bash
cd /opt/ai-stock-arena/current
bash scripts/linux/add-free-models.sh 10 40 popular
```

The Oracle host may also contain a local-only helper named `run_free_models_first_pass.sh`.
This file is not part of the standard deployment path. It was used as a manual first-pass smoke test: it loads selected API-enabled models, generates US/KR prompts for each model, runs one US and one KR trade cycle with a small candidate limit, then writes a timestamped log under `/opt/ai-stock-arena/current/logs/`.
Run it only when intentionally creating benchmark run requests, LLM logs, and simulated trades for all currently enabled models.

## Repository Guide

- [First release overview](docs/first-release-overview.md)
- [Runtime and admin guide](docs/runtime-admin-guide.md)
- [System specification](docs/step-01-system-spec.md)
- [Local and GitHub workflow](docs/step-02-local-github-flow.md)
- [Oracle deployment](docs/step-03-oracle-deployment.md)
- [Default runtime config](config/defaults.toml)
- [Environment example](.env.example)

## Next

- stabilize the free-model league further
- improve provider scoring and shared-news quality
- broaden KR and US market coverage
- add paid-model benchmark profiles under the same benchmark rules
- keep the public API and dashboard transparent as the league grows
