# AI Stock Arena

AI Stock Arena is a virtual trading benchmark for comparing how different LLMs behave under the same market constraints.

## Current Scope

- OpenRouter model synchronization and bootstrap flow
- Market settings for unified `KR` and `US` portfolios
- Hourly-style market screening based on recent price action
- Virtual trade execution with market-specific costs
- Portfolio, position, trade, and performance snapshot persistence
- CLI entry points for bootstrap, model catalog inspection, market screening, demo execution, and LLM-driven cycles

## Repository Layout

- [System specification](D:/Codex/docs/step-01-system-spec.md)
- [Local and GitHub workflow](D:/Codex/docs/step-02-local-github-flow.md)
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
.\.venv\Scripts\python.exe -m app.cli.market demo-cycle US --model-id demo/manual-strategy --picks 2
.\.venv\Scripts\python.exe -m app.cli.llm generate-prompt US openai/gpt-4o-mini
.\.venv\Scripts\python.exe -m app.cli.llm run-cycle US openai/gpt-4o-mini --candidate-limit 12
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload
.\.venv\Scripts\python.exe -m streamlit run src\app\dashboard\main.py
```

## Notes

- LLM prompts and model-facing payloads are written in English.
- OpenRouter free variants and zero-token-cost models can be listed through the model catalog CLI.
- `yfinance` is currently used for prototype market data collection.
- The current universe is a curated starter set, not the full exchange universe yet.
- The FastAPI layer is read-only for dashboard and debugging use.
- Streamlit can read data directly from the database or from `API_BASE_URL` if set.
- Oracle deployment and automated scheduler are still pending.



