# AI Stock Arena Runtime and Admin Guide

## Runtime Components

AI Stock Arena currently runs as three long-lived processes:

- `FastAPI` for the operational API
- `Streamlit` for the dashboard
- `Scheduler` for recurring market/news/trading work

Local launchers:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\start-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\restart-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\status-background-services.ps1
powershell -ExecutionPolicy Bypass -File D:\Codex\scripts\stop-background-tasks.ps1
```

## Admin Authentication

The admin panel and admin API are protected by `ADMIN_TOKEN`.

Local default behavior:

- enter the token in the dashboard admin tab
- press Enter to unlock controls

API header:

```text
X-Admin-Token: <ADMIN_TOKEN>
```

## Runtime Settings

The admin panel manages these runtime values:

- `decision_interval_minutes`
- `active_weekdays`
- `KR` runtime window in UTC
- `US` runtime window in UTC
- `news_enabled`
- `news_refresh_interval_minutes`
- `news_collection_policy`

### News Collection Policy

`development_fallback`

- intended for local development
- can expand from 15 minutes to longer fallback windows when the short window is empty

`live_strict`

- intended for Oracle/live operation
- only checks the current 15-minute window
- only within the active market runtime window
- uses low-request behavior for the free Marketaux plan

## Shared News Runtime Behavior

Shared news is benchmark context, not a model-specific tool.

The scheduler:

- checks whether the market is inside its active runtime window
- checks whether news refresh is due
- collects shared news if enabled
- stores status even when no new articles are found
- avoids creating empty news batches

## Admin Secrets

The admin panel supports runtime-managed secrets for:

- `OpenRouter API token`
- `Marketaux API token`

Behavior:

- values are masked by default
- `Show secrets` reveals the full values
- saved values override `.env` defaults at runtime

## Manual Admin Actions

The admin panel currently supports two manual actions:

- `Refresh shared news now`
- `Run full trade cycle now`

These should be used carefully because they may consume:

- Marketaux request budget
- OpenRouter token budget

## Model Profile Controls

Each profile can be managed independently.

Available controls:

- add/update profile
- delete profile
- select/unselect for the benchmark league
- enable/disable API calls
- assign a custom prompt template

Disabling API calls is the preferred way to stop token usage without deleting historical benchmark data.

## Operational Data Visible In Admin

The admin panel exposes:

- scheduler trade status
- scheduler news status
- latest trade/news completion times in UTC
- next trade run in UTC
- recent run queue
- current runtime policy values

## Recommended Local Workflow

1. Start local background services.
2. Use the admin tab to verify cadence, UTC windows, and news policy.
3. Refresh shared news manually if needed.
4. Run a manual trade cycle when validating prompt changes.
5. Use reset only when starting a clean benchmark run.

## Recommended Oracle Workflow

When deployed on Oracle:

- use PostgreSQL
- use `live_strict` news policy
- keep market windows in UTC in the admin panel
- avoid manual repeated news refresh on the free Marketaux plan
- treat the admin panel as runtime control, not as a deployment mechanism
