# AI Stock Arena Current Release Overview

## Release Objective

AI Stock Arena is a live benchmark for comparing LLM-driven virtual trading behavior. It is not a brokerage integration and does not place real-money orders.

The core rule is unchanged:

- every model should compete under the same market data, news context, trading cadence, fees, and portfolio accounting rules

## What Is Included

### Benchmark Engine

- KR and US virtual market portfolios
- scheduled market cycles
- persistent portfolios, positions, trades, and performance snapshots
- market-specific fees, taxes, and regulatory costs
- MDD, win rate, trade count, LLM cost, and trade fee tracking
- USD-normalized dashboard views for cross-market comparison

### LLM Layer

- OpenRouter model catalog integration
- free and experimental model discovery
- model probing before active use
- admin-managed model profiles
- model-generated market-specific investment prompts
- custom prompt overrides
- separate controls for league visibility and API call enablement

### Market Data

- Yahoo Finance based prototype market data
- hourly tracked-instrument history
- Market Pulse view for active KR and US instruments
- instrument registry for current, missing, and historical symbols

### Shared News

- global shared benchmark news feed
- Marketaux, Naver News, and Alpha Vantage providers
- provider-level cadence and status tracking
- optional duplicate filtering
- stored news batches reused by all participating models

### Dashboard And API

- Streamlit dashboard with lazy-loaded heavy sections
- FastAPI public read API
- admin runtime controls
- execution event log
- copy-trade style portfolio snapshot endpoint
- cache-backed rankings for Oracle Free Tier stability

### Operations

- local PowerShell launchers
- Oracle Cloud deployment scripts
- systemd units for API, dashboard, and scheduler
- nginx reverse proxy with Streamlit websocket support
- documented update path through `deploy-update.sh`

## Current Data Flow

```text
Scheduler
  -> due news provider refreshes
  -> weekly free-model sync if due
  -> stale/free-like model cleanup
  -> due market cycle
  -> market snapshot collection
  -> tracked instrument history persistence
  -> candidate screening
  -> shared context assembly
  -> LLM decision request
  -> virtual trade execution
  -> performance snapshot update
  -> ranking cache refresh
  -> dashboard/API visibility
```

## Current Comparison Model

Included in the benchmark:

- same market windows
- same cadence
- same shared news context
- same candidate screening rules
- same portfolio rules
- same transaction-cost rules
- same accounting and snapshot logic

Excluded from the default comparison:

- real brokerage execution
- model-side hidden data retrieval
- model-specific private tools

Search, prompt, and model variants should be represented as separate benchmark profiles when they need to be compared independently.

## Ranking Logic

The dashboard emphasizes model-vs-model comparison.

Displayed and stored signals include:

- since-inception return
- 1 day, 1 week, and 1 month return
- KR return
- US return
- max drawdown
- win rate
- trade count
- LLM cost in USD
- trade fees in USD equivalent

Rankings are cached. The API can serve the last known ranking snapshot when live recomputation is slow.

## Admin Control Surface

The admin panel includes controls for:

- trading cadence and weekdays
- KR and US UTC trading windows
- global live news enablement
- provider toggles
- news deduplication
- dashboard auto refresh interval
- USD/KRW FX rate
- market fees
- runtime secrets
- model creation, deletion, selection, API enablement, and custom prompts
- manual news refresh
- manual trade cycle execution
- free/experimental model cleanup
- full simulation reset

## Technical Constraints

### Oracle Free Tier

The public deployment runs on a small Oracle VM. The app is viable there, but memory is tight because FastAPI, Streamlit, and the scheduler are separate Python processes.

Current operational guidance:

- keep swap enabled
- avoid unnecessary dashboard preload
- rely on ranking cache fallback
- monitor service logs and memory usage

### SQLite

Local SQLite is acceptable for development, but PostgreSQL is the production path.

### Market Data

Yahoo Finance is suitable for prototype benchmarking but remains an unofficial feed. Long-term production use should move behind the existing provider abstraction.

### News Quality

Provider behavior is intentionally visible. News deduplication can be disabled while validating whether sources are returning usable items.

## Current Status

The system is in a free-model stabilization phase.

- free and experimental OpenRouter models are the primary live benchmark set
- paid model profiles are planned after the free league is stable
- public APIs already expose rankings, holdings, trades, snapshots, news, logs, and copy-trade style summaries
