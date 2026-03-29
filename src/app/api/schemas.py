from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app_name: str


class ModelSummary(BaseModel):
    model_id: str
    display_name: str
    request_model_id: str
    search_mode: str
    is_selected: bool
    is_available: bool
    api_enabled: bool
    is_free_like: bool
    pricing_label: str
    prompt_price_per_million: float | None
    completion_price_per_million: float | None
    context_length: int | None
    probe_detail: str | None
    custom_prompt: str | None
    uses_custom_prompt: bool
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


class ModelRanking(BaseModel):
    model_id: str
    display_name: str
    search_mode: str
    is_free_like: bool
    pricing_label: str
    current_return_pct: float | None
    return_1d_pct: float | None
    return_1w_pct: float | None
    return_1m_pct: float | None
    kr_return_pct: float | None
    us_return_pct: float | None
    composite_score: float | None
    max_drawdown: float | None
    win_rate: float | None
    trade_count: int
    llm_cost_usd: float | None
    updated_at: datetime | None


class RuntimeSettingsResponse(BaseModel):
    decision_interval_minutes: int
    active_weekdays: list[int]
    markets: dict[str, dict]
    news_enabled: bool
    news_mode: str
    news_collection_policy: str
    news_refresh_interval_minutes: int


class MarketSchedulerStatus(BaseModel):
    market_code: str
    market_timezone: str
    window_label_utc: str
    enabled: bool
    in_active_window: bool
    is_due: bool
    news_in_active_window: bool
    news_is_due: bool
    news_last_started_at: datetime | None
    news_last_completed_at: datetime | None
    news_last_status: str | None
    news_last_message: str | None
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_status: str | None
    last_message: str | None
    next_run_at: datetime | None


class SchedulerStatusResponse(BaseModel):
    cadence_minutes: int
    active_weekdays: list[int]
    markets: list[MarketSchedulerStatus]


class RuntimeSettingsUpdate(BaseModel):
    decision_interval_minutes: int | None = None
    active_weekdays: list[int] | None = None
    markets: dict[str, dict] | None = None
    news_enabled: bool | None = None
    news_mode: str | None = None
    news_collection_policy: str | None = None
    news_refresh_interval_minutes: int | None = None


class ResetResponse(BaseModel):
    deleted_logs: int
    deleted_run_requests: int
    deleted_positions: int
    deleted_trades: int
    deleted_snapshots: int
    deleted_news_items: int
    deleted_news_batches: int


class RuntimeSecretsResponse(BaseModel):
    openrouter_api_key: str | None
    marketaux_api_token: str | None


class RuntimeSecretsUpdate(BaseModel):
    openrouter_api_key: str | None = None
    marketaux_api_token: str | None = None


class MarketFeeSettingSummary(BaseModel):
    market_code: str
    market_name: str
    currency: str
    buy_commission_pct: float
    sell_commission_pct: float
    sell_tax_pct: float
    sell_regulatory_fee_pct: float


class MarketFeeSettingUpdate(BaseModel):
    buy_commission_pct: float | None = None
    sell_commission_pct: float | None = None
    sell_tax_pct: float | None = None
    sell_regulatory_fee_pct: float | None = None


class AdminActionResponse(BaseModel):
    messages: list[str]


class ModelProfileUpsertRequest(BaseModel):
    profile_id: str
    request_model_id: str
    display_name: str
    provider: str = "openrouter"
    search_mode: str = "off"
    select_profile: bool = True
    api_enabled: bool = True
    custom_prompt: str | None = None
    prompt_price_per_million: float | None = None
    completion_price_per_million: float | None = None
    context_length: int | None = None


class ModelSelectionUpdate(BaseModel):
    is_selected: bool


class ModelRuntimeUpdate(BaseModel):
    is_selected: bool | None = None
    api_enabled: bool | None = None
    custom_prompt: str | None = None


class NewsItemSummary(BaseModel):
    title: str
    summary: str | None
    source: str | None
    url: str | None
    published_at: datetime | None
    tickers: list[str]


class NewsBatchSummary(BaseModel):
    batch_key: str
    market_code: str
    source: str
    summary: str | None
    is_active: bool
    created_at: datetime
    items: list[NewsItemSummary]


class MarketInstrumentSummary(BaseModel):
    market_code: str
    ticker: str
    instrument_name: str | None
    is_active: bool
    first_seen_at: datetime
    last_seen_at: datetime
    delisted_at: datetime | None


class MarketPriceHistoryPoint(BaseModel):
    market_code: str
    ticker: str
    instrument_name: str | None
    current_price: float
    return_1h_pct: float
    return_1d_pct: float
    intraday_volatility_pct: float
    latest_volume: float
    avg_hourly_dollar_volume: float
    currency: str | None
    as_of: datetime
    is_active: bool


class LLMDecisionLogSummary(BaseModel):
    id: int
    model_id: str
    request_model_id: str
    market_code: str
    status: str
    prompt_text: str
    input_payload: dict | None
    raw_output_text: str | None
    parsed_output: dict | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    error_message: str | None
    created_at: datetime


class RunRequestSummary(BaseModel):
    id: int
    model_id: str
    market_code: str
    trigger_source: str
    status: str
    candidate_count: int | None
    snapshot_as_of: datetime | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    summary_message: str | None
    error_message: str | None


class CopyTradePosition(BaseModel):
    ticker: str
    instrument_name: str | None
    quantity: float
    current_price: float | None
    market_value: float
    target_weight_pct: float
    avg_entry_price: float
    last_action: str | None
    last_action_at: datetime | None


class CopyTradeResponse(BaseModel):
    model_id: str
    market_code: str
    as_of: datetime
    total_equity: float
    cash_weight_pct: float
    positions: list[CopyTradePosition]
    recent_trades: list[TradeSummary]


class ExecutionEventSummary(BaseModel):
    id: int
    event_type: str
    target_type: str
    model_id: str | None
    market_code: str | None
    trigger_source: str | None
    status: str
    code: str | None
    message: str | None
    created_at: datetime
