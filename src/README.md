# Source Layout

- `src/app/config/` runtime settings and configuration models
- `src/app/db/` SQLAlchemy models, schema creation, and sessions
- `src/app/market_data/` price providers, universes, and candidate screening
- `src/app/news/` Marketaux, Naver, and Alpha Vantage clients
- `src/app/llm/` OpenRouter client and decision schemas
- `src/app/trading/` virtual portfolio accounting and trade execution
- `src/app/orchestration/` model decision and trade-cycle coordination
- `src/app/services/` runtime admin, scheduler support, news, setup, and event services
- `src/app/api/` FastAPI public and admin endpoints
- `src/app/dashboard/` Streamlit dashboard
- `src/app/cli/` bootstrap, scheduler, model, market, news, and LLM commands
