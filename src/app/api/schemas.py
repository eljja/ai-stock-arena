from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app_name: str


class ModelSummary(BaseModel):
    model_id: str
    display_name: str
    is_selected: bool
    is_available: bool
    is_free_like: bool
    pricing_label: str
    prompt_price_per_million: float | None
    completion_price_per_million: float | None
    context_length: int | None
    probe_detail: str | None
    updated_at: datetime


class PortfolioSummary(BaseModel):
    model_id: str
    market_code: str
    market_name: str
    currency: str
    initial_cash: float
    available_cash: float
    invested_value: float
    total_equity: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_return_pct: float
    position_count: int
    latest_snapshot_at: datetime | None
    updated_at: datetime


class PositionSummary(BaseModel):
    model_id: str
    market_code: str
    ticker: str
    instrument_name: str | None
    quantity: float
    avg_entry_price: float
    current_price: float | None
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    opened_at: datetime
    updated_at: datetime


class TradeSummary(BaseModel):
    id: int
    model_id: str
    market_code: str
    ticker: str
    instrument_name: str | None
    side: str
    quantity: float
    price: float
    gross_amount: float
    commission_amount: float
    tax_amount: float
    regulatory_fee_amount: float
    net_amount: float
    realized_pnl: float
    reason: str | None
    created_at: datetime


class SnapshotSummary(BaseModel):
    model_id: str
    market_code: str
    available_cash: float
    invested_value: float
    total_equity: float
    total_return_pct: float
    realized_pnl: float
    unrealized_pnl: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    turnover: float
    avg_holding_hours: float
    composite_score: float
    created_at: datetime


class OverviewResponse(BaseModel):
    selected_model_count: int
    model_count: int
    free_model_count: int
    available_model_count: int
    portfolio_count: int
    combined_initial_cash: float
    combined_available_cash: float
    combined_invested_value: float
    combined_total_equity: float
    combined_return_pct: float
    latest_trade_at: datetime | None
    latest_snapshot_at: datetime | None
