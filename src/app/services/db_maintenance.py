from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


OPERATIONAL_INDEXES = [
    (
        "ix_trades_model_market_created",
        "trades",
        "model_id, market_code, created_at",
    ),
    (
        "ix_trades_market_created",
        "trades",
        "market_code, created_at",
    ),
    (
        "ix_snapshots_model_market_created",
        "performance_snapshots",
        "model_id, market_code, created_at",
    ),
    (
        "ix_llm_logs_model_market_created",
        "llm_decision_logs",
        "model_id, market_code, created_at",
    ),
    (
        "ix_run_requests_model_market_status_requested",
        "run_requests",
        "model_id, market_code, status, requested_at",
    ),
    (
        "ix_execution_events_type_target_market_code_created",
        "execution_events",
        "event_type, target_type, market_code, code, created_at",
    ),
    (
        "ix_execution_events_model_market_created",
        "execution_events",
        "model_id, market_code, created_at",
    ),
    (
        "ix_hourly_prices_market_ticker_asof",
        "hourly_market_prices",
        "market_code, ticker, as_of",
    ),
    (
        "ix_news_items_published_created",
        "shared_news_items",
        "published_at, created_at",
    ),
    (
        "ix_news_batches_market_created",
        "shared_news_batches",
        "market_code, created_at",
    ),
]

_INDEXES_READY = False


def ensure_operational_indexes(engine: Engine) -> None:
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    with engine.begin() as connection:
        for index_name, table_name, columns in OPERATIONAL_INDEXES:
            connection.execute(
                text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})")
            )
    _INDEXES_READY = True
