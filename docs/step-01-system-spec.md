# Step 1: System Specification

## Objective

AI Stock Arena compares multiple LLMs under the same portfolio rules and market inputs to evaluate which models produce stronger virtual trading outcomes.

This is a benchmark system, not a live brokerage integration.

## Experimental Units

Each model owns three independent portfolios:

- `KOSPI`
- `KOSDAQ`
- `US`

Initial balances:

- KOSPI: `10,000,000 KRW`
- KOSDAQ: `10,000,000 KRW`
- US: `10,000 USD`

## Market Scope

The user requirement for the United States is the broad market rather than a single ETF or sector subset. The implementation therefore uses this pattern:

1. maintain a market universe
2. screen that universe every cycle
3. send only screened candidates plus current holdings to the LLM

This keeps cost and latency under control while still targeting the wider market.

## Trading Rules

- maximum 10 positions per market
- hourly decision cadence
- market-specific fees and taxes applied to virtual trades
- every portfolio, position, trade, and performance snapshot stored in the database

## Cost Model Defaults

### Korea

- buy commission: `0.015%`
- sell commission: `0.015%`
- sell tax:
  - KOSPI: `0.20%`
  - KOSDAQ: `0.20%`

### United States

- buy commission: `0.00%`
- sell commission: `0.00%`
- sell regulatory fee: configurable, defaulted to a near-zero rate

All of these values are configuration-driven and can later be exposed in the dashboard.

## Score Components

The benchmark stores more than raw return.

Metrics to persist:

- total return
- daily return
- realized PnL
- unrealized PnL
- volatility
- Sharpe ratio
- max drawdown
- win rate
- profit factor
- trade count
- turnover
- average holding period

Initial weighted score:

- total return: `35%`
- Sharpe ratio: `20%`
- max drawdown inverse: `15%`
- win rate: `10%`
- profit factor: `10%`
- volatility inverse: `5%`
- turnover penalty: `5%`

## Prompt Policy

Each LLM first generates its own reusable market-specific trading prompt in English. The live cycle then feeds the model:

- current portfolio state
- current holdings
- screened candidates
- recent price features
- transaction cost assumptions

The model must return a structured JSON decision.

## Market Data Policy

`yfinance` is acceptable for early prototyping but should not be treated as a long-term production-grade feed because it is unofficial and subject to inconsistent rate limits and data behavior.

Recommended path:

- early prototype: `yfinance`
- later production migration: provider abstraction with official or paid feeds

## Initial Architecture

- Oracle Cloud Free Tier Ubuntu VM
- PostgreSQL
- FastAPI
- APScheduler
- Streamlit
- systemd

## Step 1 Output

Step 1 fixed the market units, cost defaults, score model, and the prototype-vs-production data-source policy.
