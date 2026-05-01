# Step 1: System Specification

## Objective

AI Stock Arena compares LLM-driven virtual trading profiles under the same benchmark rules and market inputs.

This is a benchmark system, not a live brokerage integration.

## Experimental Units

Each model profile can trade independent virtual portfolios for:

- `KR`
- `US`

Default initial balances:

- KR: `10,000,000 KRW`
- US: `10,000 USD`

Dashboard cross-market views normalize money-like values to USD using a configurable `USDKRW` rate. Percentage returns remain percentages and are averaged across markets rather than summed.

## Market Scope

The system uses a screened-candidate workflow.

1. maintain a market universe
2. collect current market snapshots
3. screen candidates every cycle
4. send screened candidates plus current holdings to the LLM

This keeps latency and token cost controlled while still allowing broad KR and US coverage.

## Trading Rules

- maximum 10 positions per market
- configurable decision cadence
- active weekday and UTC market-window controls
- market-specific fees, taxes, and regulatory fees
- every portfolio, position, trade, and performance snapshot stored in the database

## Cost Model Defaults

### Korea

- buy commission: `0.015%`
- sell commission: `0.015%`
- sell tax: `0.20%`

### United States

- buy commission: `0.00%`
- sell commission: `0.00%`
- sell regulatory fee: near-zero configurable rate

Fees are editable from the admin panel.

## Score And Ranking Inputs

The benchmark stores and exposes:

- total return
- period return
- KR return
- US return
- realized and unrealized PnL
- max drawdown
- win rate
- profit factor
- trade count
- turnover
- LLM cost
- trade fee cost

Rankings are cache-backed so the live dashboard can show the last known ranking snapshot when fresh computation is slow.

## Prompt Policy

Each LLM profile can generate and use a reusable market-specific investment prompt. The live cycle feeds the model:

- current portfolio state
- current holdings
- screened candidates
- recent price features
- shared news context
- transaction cost assumptions

The model must return a structured decision that the virtual trading engine can parse.

## Shared News Policy

Shared news is global benchmark context. It is collected centrally and reused by every model.

Providers:

- Marketaux: 15-minute cadence, up to 3 English items
- Naver News: 30-minute cadence, up to 5 items
- Alpha Vantage: 30-minute cadence, latest 5 items

News deduplication is configurable from admin.

## Market Data Policy

`yfinance` is acceptable for prototype benchmarking but should not be treated as a long-term production-grade feed because it is unofficial and subject to inconsistent rate limits and data behavior.

Recommended path:

- current prototype: `yfinance`
- later production migration: provider abstraction with official or paid feeds

## Initial Architecture

- Oracle Cloud Free Tier Ubuntu VM
- PostgreSQL for live operation
- FastAPI API service
- Streamlit dashboard service
- runtime scheduler service
- nginx reverse proxy
- systemd for service supervision

## Step 1 Output

Step 1 defines the current benchmark units, cost defaults, shared context policy, model prompt policy, and prototype-vs-production data-source boundary.
