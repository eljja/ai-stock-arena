# AI Stock Arena Runtime and Admin Guide

## Runtime Components

AI Stock Arena runs as three long-lived services:

- `FastAPI` for public and admin API endpoints
- `Streamlit` for the dashboard
- `Scheduler` for news refreshes, model discovery, market cycles, and ranking cache refreshes
- `Watchdog timer` for lightweight local health checks and targeted service restarts on Oracle

Local launchers:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\start-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\restart-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\status-background-services.ps1
```

Oracle services:

```bash
sudo systemctl status ai-stock-arena-api.service --no-pager
sudo systemctl status ai-stock-arena-dashboard.service --no-pager
sudo systemctl status ai-stock-arena-scheduler.service --no-pager
sudo systemctl status ai-stock-arena-watchdog.timer --no-pager
```

## Admin Authentication

The admin panel and admin API are protected by `ADMIN_TOKEN`.

Dashboard flow:

- open the `Admin` section
- enter the admin token
- press Enter to unlock runtime controls

API header:

```text
X-Admin-Token: <ADMIN_TOKEN>
```

## Runtime Settings

The admin panel manages operational values stored in the database:

- decision cadence in minutes
- active weekdays
- KR and US trading windows in UTC
- provider-based live news enablement
- provider toggles for Marketaux, Naver, and Alpha Vantage
- news deduplication toggle
- dashboard auto refresh enablement and interval
- USD/KRW FX rate used for cross-market dashboard normalization

`Selected for league` controls whether a model appears in league views and selected-only API responses. `Enable API calls` controls whether the scheduler is allowed to call the model going forward.

## Shared News Runtime Behavior

Shared news is global benchmark context. It is not split by KR and US market scope anymore.

Provider cadence:

- Marketaux: every 15 minutes, up to 3 English items
- Naver News: every 30 minutes, up to 5 items
- Alpha Vantage: every 30 minutes, latest 5 items

Behavior:

- all enabled providers run 24/7 when live news is on
- provider results are stored as `GLOBAL` shared news batches
- deduplication can be toggled while validating provider behavior
- empty refreshes are recorded as execution events without creating empty batches

## Admin Secrets

The admin panel supports runtime-managed secrets for:

- OpenRouter API token
- Marketaux API token
- Naver client id
- Naver client secret
- Alpha Vantage API key

Saved runtime secrets override `.env` defaults without requiring a deployment.

## Manual Admin Actions

Manual actions:

- refresh shared news now
- run full trade cycle now
- clean up paid free/experimental OpenRouter models
- update market fee settings
- reset simulation data

Use manual trade/news actions carefully because they can consume provider and model quotas.

## Model Maintenance

The scheduler can maintain the free-model league over time.

- Weekly free/experimental OpenRouter discovery runs on Sunday.
- Newly probed successful models can be added as benchmark profiles.
- Free-like models that have not been successfully used for multiple days can be disabled.
- Admin can manually disable free/experimental models with non-zero token pricing.

Historical results remain visible when API calls are disabled.

## Execution Log

The admin section exposes concise execution events for:

- provider news refreshes
- model trade cycles
- manual admin runs
- scheduler-driven work
- success, empty, partial, and error states

The log is paged with a visible limit so it remains usable as it grows.

## Public API Notes

Most benchmark data is exposed through read-only public API endpoints under `/api`.

Useful external-app endpoints:

- `GET /api/rankings?selected_only=true`
- `GET /api/positions?model_id=...`
- `GET /api/trades?model_id=...&limit=20`
- `GET /api/copy-trade/{model_id}?market_code=KR|US`

`/api/rankings` is cache-backed. If the live ranking calculation is slow, the API can return the last known ranking snapshot and expose cache status through response headers.

The scheduler also refreshes the ranking cache as an isolated maintenance task. A failure in news refresh, model sync, stale-model cleanup, or ranking-cache refresh is logged as an execution event without stopping the whole scheduler loop.

## Recommended Local Workflow

1. Start local background services.
2. Verify API and dashboard health.
3. Configure provider secrets in the admin panel.
4. Add or probe free models.
5. Run a manual trade cycle only when validating behavior.
6. Use reset only when starting a clean benchmark run.

## Recommended Oracle Workflow

When deployed on Oracle:

- use PostgreSQL
- keep 4 GB swap enabled on the Free Tier VM
- update through `deploy/oracle/deploy-update.sh`
- control runtime behavior from the admin panel
- monitor `/var/log/ai-stock-arena/*.log`
- let logrotate manage app logs through `/etc/logrotate.d/ai-stock-arena`
- let the watchdog timer check API, rankings, dashboard, and low-memory signals every 5 minutes
- keep API, dashboard, scheduler as systemd services
