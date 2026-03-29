# AI Stock Arena First Release Overview

## Release Objective

The first release of AI Stock Arena establishes a working benchmark system for comparing LLM-driven investment behavior, not for running real-money trading.

The release is designed around one core rule:

- every model should see the same benchmark context before making a decision

That means the benchmark engine, not the model, controls:

- market snapshot timing
- candidate screening
- shared news ingestion
- transaction-cost rules
- portfolio accounting
- performance scoring

## What Is Included

### Benchmark Engine

- Unified `KR` and `US` benchmark portfolios
- Hourly virtual trading cycles
- Persistent portfolios, positions, trades, and snapshots
- Trade costs recorded by market
- LLM token usage and estimated LLM cost recorded as overhead

### LLM Layer

- OpenRouter model catalog integration
- Free-model probing and selection tools
- Admin-managed investment profiles
- Support for `model + custom prompt` profiles
- Per-profile API enable/disable switch

### Market Data

- Prototype price data through Yahoo Finance
- Hourly market history persistence
- Tracked-instrument market pulse view
- Instrument registry for active and missing symbols

### Shared News

- Shared Marketaux-based benchmark news feed
- Common news context for all models
- News collection policies:
  - `development_fallback`
  - `live_strict`
- Duplicate filtering by normalized title and URL
- Empty refreshes recorded as status without creating empty news batches

### Operations

- FastAPI service
- Streamlit dashboard
- Runtime scheduler
- Local hidden background launchers
- Oracle deployment assets and systemd units

## Current Data Flow

```text
Hourly scheduler
  -> market price collection
  -> tracked instrument history persistence
  -> shared news refresh (policy-based)
  -> market screening
  -> common prompt context assembly
  -> LLM decision request
  -> virtual trade execution
  -> performance snapshot update
  -> dashboard/API visibility
```

## Current Comparison Model

The benchmark is intentionally built as a pure-model comparison league.

Included in the comparison:

- same market windows
- same cadence
- same shared news
- same candidate list
- same portfolio rules
- same transaction-cost rules

Excluded from the comparison by default:

- model-side web search
- model-specific proprietary tools
- hidden news retrieval capabilities

Search-enabled variants may still exist, but they should be treated as separate profiles or separate leagues.

## Ranking Logic

The current dashboard emphasizes model-vs-model comparison rather than combined portfolio totals.

Primary comparison dimensions include:

- since-inception return
- 1 day return
- 1 week return
- 1 month return
- KR return
- US return
- composite score
- max drawdown
- win rate
- trade count
- LLM cost in USD

## Admin Control Surface

The first release already includes a working admin panel for:

- runtime cadence
- UTC runtime windows for KR and US
- shared news enable/disable
- news collection policy
- news refresh interval
- manual shared-news refresh
- manual trade-cycle execution
- profile creation and deletion
- per-profile API pause control
- runtime secret management
- full simulation reset

## Technical Constraints In This Release

### SQLite

Local SQLite works for development, but it is still a bottleneck for concurrent writes.

Mitigations already included:

- WAL mode
- busy timeout
- sequential run preference for heavier tasks

Production recommendation:

- use PostgreSQL on Oracle

### Price Data

`yfinance` is sufficient for the benchmark prototype but should not be treated as a production-grade market-data provider.

Known limitations:

- occasional ticker gaps
- inconsistent KR coverage
- possible rate limiting
- unofficial dependency path

### News Quality

`Marketaux` works well enough for shared benchmark context, but KR coverage still needs improvement for production quality.

## Definition Of Done For This Release

This first version should be treated as complete when the following are true:

- local dashboard and API can be launched reliably
- shared news can be collected and injected into model prompts
- benchmark profiles can be added, paused, and compared
- hourly market history and performance snapshots are visible
- the current repository state is committed as the first baseline release

## What Comes Next After This Release

- Oracle Cloud Free Tier deployment
- PostgreSQL-first operation
- stronger KR news source coverage
- richer full-universe screening
- chart-only benchmark mode
- clearer production monitoring and backup procedures
