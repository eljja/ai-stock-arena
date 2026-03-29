from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class LLMModel(Base):
    __tablename__ = "llm_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), default="openrouter")
    model_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    context_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_price_per_million: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_price_per_million: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class MarketSetting(Base):
    __tablename__ = "market_settings"
    __table_args__ = (UniqueConstraint("market_code", name="uq_market_settings_market_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    market_name: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(10))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    initial_cash: Mapped[float] = mapped_column(Float)
    buy_commission_rate: Mapped[float] = mapped_column(Float, default=0.0)
    sell_commission_rate: Mapped[float] = mapped_column(Float, default=0.0)
    sell_tax_rate: Mapped[float] = mapped_column(Float, default=0.0)
    sell_regulatory_fee_rate: Mapped[float] = mapped_column(Float, default=0.0)
    max_positions: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ModelMarketPrompt(Base):
    __tablename__ = "model_market_prompts"
    __table_args__ = (
        UniqueConstraint("model_id", "market_code", "version", name="uq_model_market_prompt_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(255), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    prompt_content: Mapped[str] = mapped_column(Text)
    source_meta_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("model_id", "market_code", name="uq_portfolios_model_market"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(255), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    currency: Mapped[str] = mapped_column(String(10))
    initial_cash: Mapped[float] = mapped_column(Float)
    available_cash: Mapped[float] = mapped_column(Float)
    invested_value: Mapped[float] = mapped_column(Float, default=0.0)
    total_equity: Mapped[float] = mapped_column(Float)
    total_realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("model_id", "market_code", "ticker", name="uq_positions_model_market_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(255), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    ticker: Mapped[str] = mapped_column(String(50), index=True)
    instrument_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_entry_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_value: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(255), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    ticker: Mapped[str] = mapped_column(String(50), index=True)
    instrument_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    gross_amount: Mapped[float] = mapped_column(Float)
    commission_amount: Mapped[float] = mapped_column(Float, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    regulatory_fee_amount: Mapped[float] = mapped_column(Float, default=0.0)
    net_amount: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(255), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    available_cash: Mapped[float] = mapped_column(Float)
    invested_value: Mapped[float] = mapped_column(Float)
    total_equity: Mapped[float] = mapped_column(Float)
    total_return_pct: Mapped[float] = mapped_column(Float)
    daily_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    volatility: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    turnover: Mapped[float] = mapped_column(Float, default=0.0)
    avg_holding_hours: Mapped[float] = mapped_column(Float, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class AdminSetting(Base):
    __tablename__ = "admin_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_admin_settings_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    value_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SharedNewsBatch(Base):
    __tablename__ = "shared_news_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    source: Mapped[str] = mapped_column(String(100), default="manual")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class SharedNewsItem(Base):
    __tablename__ = "shared_news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_key: Mapped[str] = mapped_column(String(120), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tickers_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class MarketInstrument(Base):
    __tablename__ = "market_instruments"
    __table_args__ = (UniqueConstraint("market_code", "ticker", name="uq_market_instruments_market_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    ticker: Mapped[str] = mapped_column(String(50), index=True)
    instrument_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HourlyMarketPrice(Base):
    __tablename__ = "hourly_market_prices"
    __table_args__ = (UniqueConstraint("market_code", "ticker", "as_of", name="uq_hourly_market_prices_market_ticker_asof"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    ticker: Mapped[str] = mapped_column(String(50), index=True)
    instrument_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_price: Mapped[float] = mapped_column(Float)
    previous_close: Mapped[float] = mapped_column(Float)
    return_1h_pct: Mapped[float] = mapped_column(Float, default=0.0)
    return_1d_pct: Mapped[float] = mapped_column(Float, default=0.0)
    intraday_volatility_pct: Mapped[float] = mapped_column(Float, default=0.0)
    latest_volume: Mapped[float] = mapped_column(Float, default=0.0)
    avg_hourly_dollar_volume: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class LLMDecisionLog(Base):
    __tablename__ = "llm_decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(255), index=True)
    request_model_id: Mapped[str] = mapped_column(String(255), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    prompt_text: Mapped[str] = mapped_column(Text)
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class RunRequest(Base):
    __tablename__ = "run_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(255), index=True)
    market_code: Mapped[str] = mapped_column(String(30), index=True)
    trigger_source: Mapped[str] = mapped_column(String(50), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)



class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    target_type: Mapped[str] = mapped_column(String(30), index=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    market_code: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    trigger_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
