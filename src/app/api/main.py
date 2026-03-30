from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.query_service import (
    get_copy_trade,
    list_execution_events,
    get_overview,
    get_runtime_settings_response,
    get_scheduler_status_response,
    list_llm_logs,
    list_market_instruments,
    list_market_price_history,
    list_models,
    list_news_batches,
    list_portfolios,
    list_positions,
    list_run_requests,
    list_rankings,
    list_snapshots,
    list_trades,
)
from app.api.schemas import (
    CopyTradeResponse,
    ExecutionEventSummary,
    HealthResponse,
    MarketFeeSettingSummary,
    MarketFeeSettingUpdate,
    LLMDecisionLogSummary,
    MarketInstrumentSummary,
    MarketPriceHistoryPoint,
    ModelProfileUpsertRequest,
    ModelSelectionUpdate,
    ModelRuntimeUpdate,
    ModelRanking,
    AdminActionResponse,
    ModelSummary,
    NewsBatchSummary,
    OverviewResponse,
    PortfolioSummary,
    PositionSummary,
    RunRequestSummary,
    ResetResponse,
    RuntimeSecretsResponse,
    RuntimeSecretsUpdate,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdate,
    SchedulerStatusResponse,
    SnapshotSummary,
    TradeSummary,
)
from app.config.loader import load_runtime_config, load_settings
from app.db.session import get_session
from app.services.admin import (
    create_or_update_model_profile,
    delete_model_profile,
    disable_nonzero_cost_free_experiment_models,
    list_market_fee_settings,
    reset_simulation,
    run_manual_news_refreshes,
    run_manual_trade_cycles,
    set_model_selection,
    update_market_fee_settings,
    update_model_runtime,
    update_runtime_settings,
)
from app.services.runtime_secrets import get_runtime_secrets, update_runtime_secrets

runtime_config = load_runtime_config()
settings = load_settings()

app = FastAPI(
    title="AI Stock Arena API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> str:
    if not settings.admin_token:
        raise HTTPException(status_code=403, detail="ADMIN_TOKEN is not configured.")
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token.")
    return x_admin_token


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app_name=runtime_config.app.name)


@app.get("/runtime-settings", response_model=RuntimeSettingsResponse)
def runtime_settings(session: Session = Depends(get_session)) -> RuntimeSettingsResponse:
    return get_runtime_settings_response(session=session)


@app.get("/scheduler-status", response_model=SchedulerStatusResponse)
def scheduler_status(session: Session = Depends(get_session)) -> SchedulerStatusResponse:
    return get_scheduler_status_response(session=session)


@app.get("/overview", response_model=OverviewResponse)
def overview(
    market_code: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> OverviewResponse:
    return get_overview(session=session, market_code=market_code, selected_only=selected_only)


@app.get("/models", response_model=list[ModelSummary])
def models(
    selected_only: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> list[ModelSummary]:
    return list_models(session=session, selected_only=selected_only)


@app.get("/rankings", response_model=list[ModelRanking])
def rankings(
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> list[ModelRanking]:
    return list_rankings(session=session, selected_only=selected_only)


@app.get("/portfolios", response_model=list[PortfolioSummary])
def portfolios(
    market_code: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> list[PortfolioSummary]:
    return list_portfolios(session=session, market_code=market_code, selected_only=selected_only)


@app.get("/positions", response_model=list[PositionSummary])
def positions(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> list[PositionSummary]:
    return list_positions(
        session=session,
        market_code=market_code,
        model_id=model_id,
        selected_only=selected_only,
    )


@app.get("/trades", response_model=list[TradeSummary])
def trades(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[TradeSummary]:
    return list_trades(
        session=session,
        market_code=market_code,
        model_id=model_id,
        selected_only=selected_only,
        limit=limit,
    )


@app.get("/snapshots", response_model=list[SnapshotSummary])
def snapshots(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    selected_only: bool = Query(default=True),
    limit: int = Query(default=300, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> list[SnapshotSummary]:
    return list_snapshots(
        session=session,
        market_code=market_code,
        model_id=model_id,
        selected_only=selected_only,
        limit=limit,
    )


@app.get("/market-instruments", response_model=list[MarketInstrumentSummary])
def market_instruments(
    market_code: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> list[MarketInstrumentSummary]:
    return list_market_instruments(session=session, market_code=market_code, active_only=active_only)


@app.get("/market-price-history", response_model=list[MarketPriceHistoryPoint])
def market_price_history(
    market_code: str = Query(...),
    selected_only: bool = Query(default=True),
    top_n: int = Query(default=20, ge=1, le=50),
    limit_per_ticker: int = Query(default=0, ge=0, le=10000),
    session: Session = Depends(get_session),
) -> list[MarketPriceHistoryPoint]:
    return list_market_price_history(
        session=session,
        market_code=market_code,
        selected_only=selected_only,
        top_n=top_n,
        limit_per_ticker=limit_per_ticker,
    )


@app.get("/news", response_model=list[NewsBatchSummary])
def news(
    market_code: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session),
) -> list[NewsBatchSummary]:
    return list_news_batches(session=session, market_code=market_code, limit=limit)


@app.get("/run-requests", response_model=list[RunRequestSummary])
def run_requests(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    selected_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[RunRequestSummary]:
    return list_run_requests(
        session=session,
        model_id=model_id,
        market_code=market_code,
        status=status,
        selected_only=selected_only,
        limit=limit,
    )

@app.get("/llm-logs", response_model=list[LLMDecisionLogSummary])
def llm_logs(
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[LLMDecisionLogSummary]:
    return list_llm_logs(session=session, model_id=model_id, market_code=market_code, limit=limit)


@app.get("/execution-events", response_model=list[ExecutionEventSummary])
def execution_events(
    event_type: str | None = Query(default=None),
    market_code: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[ExecutionEventSummary]:
    return list_execution_events(
        session=session,
        event_type=event_type,
        market_code=market_code,
        model_id=model_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@app.get("/copy-trade/{model_id:path}", response_model=CopyTradeResponse)
def copy_trade(
    model_id: str,
    market_code: str = Query(...),
    session: Session = Depends(get_session),
) -> CopyTradeResponse:
    try:
        return get_copy_trade(session=session, model_id=model_id, market_code=market_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/admin/settings", response_model=RuntimeSettingsResponse)
def admin_settings(
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RuntimeSettingsResponse:
    return get_runtime_settings_response(session=session)


@app.put("/admin/settings", response_model=RuntimeSettingsResponse)
def update_settings(
    payload: RuntimeSettingsUpdate,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RuntimeSettingsResponse:
    updated = update_runtime_settings(session=session, payload=payload.model_dump(exclude_none=True))
    session.commit()
    return RuntimeSettingsResponse(**updated)


@app.get("/admin/market-fees", response_model=list[MarketFeeSettingSummary])
def admin_market_fees(
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[MarketFeeSettingSummary]:
    return [MarketFeeSettingSummary(**row) for row in list_market_fee_settings(session)]


@app.put("/admin/market-fees/{market_code}", response_model=MarketFeeSettingSummary)
def update_market_fees(
    market_code: str,
    payload: MarketFeeSettingUpdate,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MarketFeeSettingSummary:
    market = update_market_fee_settings(session=session, market_code=market_code.upper(), **payload.model_dump(exclude_none=True))
    session.commit()
    return MarketFeeSettingSummary(
        market_code=market.market_code,
        market_name=market.market_name,
        currency=market.currency,
        buy_commission_pct=(market.buy_commission_rate or 0.0) * 100.0,
        sell_commission_pct=(market.sell_commission_rate or 0.0) * 100.0,
        sell_tax_pct=(market.sell_tax_rate or 0.0) * 100.0,
        sell_regulatory_fee_pct=(market.sell_regulatory_fee_rate or 0.0) * 100.0,
    )


@app.get("/admin/secrets", response_model=RuntimeSecretsResponse)
def admin_secrets(
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RuntimeSecretsResponse:
    return RuntimeSecretsResponse(**get_runtime_secrets(session))


@app.put("/admin/secrets", response_model=RuntimeSecretsResponse)
def update_secrets(
    payload: RuntimeSecretsUpdate,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RuntimeSecretsResponse:
    updated = update_runtime_secrets(session=session, payload=payload.model_dump())
    session.commit()
    return RuntimeSecretsResponse(**updated)


@app.post("/admin/news/refresh", response_model=AdminActionResponse)
def admin_refresh_news(
    market_code: str | None = Query(default=None),
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminActionResponse:
    messages = run_manual_news_refreshes(session=session, market_code=market_code.upper() if market_code else None)
    return AdminActionResponse(messages=messages)


@app.post("/admin/trades/run", response_model=AdminActionResponse)
def admin_run_trades(
    market_code: str | None = Query(default=None),
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminActionResponse:
    messages = run_manual_trade_cycles(session=session, market_code=market_code.upper() if market_code else None)
    return AdminActionResponse(messages=messages)


@app.post("/admin/models/cleanup-free-pricing", response_model=AdminActionResponse)
def admin_cleanup_free_pricing(
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminActionResponse:
    messages = disable_nonzero_cost_free_experiment_models(session=session)
    session.commit()
    return AdminActionResponse(messages=messages)


@app.post("/admin/reset", response_model=ResetResponse)
def admin_reset(
    reset_prompts: bool = Query(default=True),
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ResetResponse:
    result = reset_simulation(session=session, reset_prompts=reset_prompts)
    session.commit()
    return ResetResponse(**result)


@app.post("/admin/models", response_model=ModelSummary)
def upsert_model_profile(
    payload: ModelProfileUpsertRequest,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ModelSummary:
    model = create_or_update_model_profile(
        session=session,
        profile_id=payload.profile_id,
        request_model_id=payload.request_model_id,
        display_name=payload.display_name,
        provider=payload.provider,
        search_mode=payload.search_mode,
        select_profile=payload.select_profile,
        prompt_price_per_million=payload.prompt_price_per_million,
        completion_price_per_million=payload.completion_price_per_million,
        context_length=payload.context_length,
        custom_prompt=payload.custom_prompt,
        api_enabled=payload.api_enabled,
    )
    session.commit()
    return next(item for item in list_models(session=session, selected_only=False) if item.model_id == model.model_id)


@app.patch("/admin/models/{model_id:path}/selection", response_model=ModelSummary)
def update_model_selection(
    model_id: str,
    payload: ModelSelectionUpdate,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ModelSummary:
    try:
        model = set_model_selection(session=session, profile_id=model_id, is_selected=payload.is_selected)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    return next(item for item in list_models(session=session, selected_only=False) if item.model_id == model.model_id)


@app.patch("/admin/models/{model_id:path}", response_model=ModelSummary)
def update_model_runtime_endpoint(
    model_id: str,
    payload: ModelRuntimeUpdate,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ModelSummary:
    try:
        model = update_model_runtime(
            session=session,
            profile_id=model_id,
            is_selected=payload.is_selected,
            api_enabled=payload.api_enabled,
            custom_prompt=payload.custom_prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    return next(item for item in list_models(session=session, selected_only=False) if item.model_id == model.model_id)


@app.delete("/admin/models/{model_id:path}")
def remove_model_profile(
    model_id: str,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    result = delete_model_profile(session=session, profile_id=model_id)
    session.commit()
    return result


