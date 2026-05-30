from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.api.query_service import (
    get_copy_trade,
    get_overview,
    get_rankings_with_meta,
    get_runtime_settings_response,
    get_scheduler_status_response,
    list_execution_events,
    list_llm_logs,
    list_market_instruments,
    list_market_price_history,
    list_models,
    list_news_batches,
    list_news_items,
    list_portfolios,
    list_positions,
    list_run_requests,
    list_snapshots,
    list_trades,
    refresh_rankings_cache,
)
from app.api.schemas import (
    AdminActionResponse,
    CopyTradeResponse,
    ExecutionEventSummary,
    HealthResponse,
    LLMDecisionLogSummary,
    MarketFeeSettingSummary,
    MarketFeeSettingUpdate,
    MarketInstrumentSummary,
    MarketPriceHistoryPoint,
    ModelProfileUpsertRequest,
    ModelRanking,
    ModelRuntimeUpdate,
    ModelSelectionUpdate,
    ModelSummary,
    NewsBatchSummary,
    NewsItemSummary,
    OverviewResponse,
    PortfolioSummary,
    PositionSummary,
    ResetResponse,
    RunRequestSummary,
    RuntimeSecretsResponse,
    RuntimeSecretsUpdate,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdate,
    SchedulerStatusResponse,
    SnapshotSummary,
    TradeSummary,
)
from app.config.loader import load_runtime_config, load_settings
from app.db.session import SessionLocal, get_session
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


def _public_site_url() -> str:
    configured = (settings.api_base_url or "").rstrip("/")
    if "127.0.0.1" in configured or "localhost" in configured:
        return "https://aistockarena.com"
    if configured.endswith("/api"):
        return configured[: -len("/api")]
    return configured or "https://aistockarena.com"


PUBLIC_SITE_URL = _public_site_url()
ROOT = Path(__file__).resolve().parents[3]
BRAND_ASSETS_DIR = ROOT / "assets" / "brand"


def _warm_rankings_cache_once() -> None:
    def worker() -> None:
        try:
            with SessionLocal() as session:
                refresh_rankings_cache(session)
                session.commit()
        except Exception:
            return

    threading.Thread(target=worker, daemon=True, name="api-rankings-warmup").start()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _warm_rankings_cache_once()
    yield


app = FastAPI(
    title="AI Stock Arena API",
    version="0.1.0",
    lifespan=lifespan,
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


def _brand_asset_response(filename: str, media_type: str) -> FileResponse:
    return FileResponse(
        BRAND_ASSETS_DIR / filename,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/favicon.png", include_in_schema=False)
def favicon_png() -> FileResponse:
    return _brand_asset_response("favicon.png", "image/png")


@app.head("/favicon.png", include_in_schema=False)
def favicon_png_head() -> Response:
    return Response(headers={"Cache-Control": "public, max-age=86400"}, media_type="image/png")


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico() -> FileResponse:
    return _brand_asset_response("favicon.ico", "image/x-icon")


@app.head("/favicon.ico", include_in_schema=False)
def favicon_ico_head() -> Response:
    return Response(headers={"Cache-Control": "public, max-age=86400"}, media_type="image/x-icon")


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg() -> FileResponse:
    return _brand_asset_response("aistockarena-icon.svg", "image/svg+xml")


@app.head("/favicon.svg", include_in_schema=False)
def favicon_svg_head() -> Response:
    return Response(headers={"Cache-Control": "public, max-age=86400"}, media_type="image/svg+xml")


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots_txt() -> PlainTextResponse:
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            "Disallow: /_stcore/",
            "",
            f"Sitemap: {PUBLIC_SITE_URL}/sitemap.xml",
            "",
        ]
    )
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")


@app.head("/robots.txt", include_in_schema=False)
def robots_txt_head() -> Response:
    return Response(media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml() -> Response:
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{PUBLIC_SITE_URL}/</loc>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    return Response(content=body, media_type="application/xml; charset=utf-8")


@app.head("/sitemap.xml", include_in_schema=False)
def sitemap_xml_head() -> Response:
    return Response(media_type="application/xml; charset=utf-8")


@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
def llms_txt() -> PlainTextResponse:
    body = "\n".join(
        [
            "# AI Stock Arena",
            "",
            "AI Stock Arena is a live LLM stock trading benchmark for KR and US markets.",
            "It compares model decisions using shared market data, shared news context, simulated portfolios, trades, positions, and public benchmark APIs.",
            "",
            f"- Dashboard: {PUBLIC_SITE_URL}/",
            f"- API base: {PUBLIC_SITE_URL}/api",
            f"- Rankings: {PUBLIC_SITE_URL}/api/rankings?selected_only=true",
            f"- Runtime status: {PUBLIC_SITE_URL}/api/scheduler-status",
            "",
        ]
    )
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")


@app.head("/llms.txt", include_in_schema=False)
def llms_txt_head() -> Response:
    return Response(media_type="text/plain; charset=utf-8")


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
    response: Response,
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> list[ModelRanking]:
    rankings_payload, meta = get_rankings_with_meta(session=session, selected_only=selected_only)
    cache_status = str(meta.get("cache_status") or "")
    cache_updated_at = str(meta.get("cache_updated_at") or "")
    if cache_status:
        response.headers["X-Rankings-Cache-Status"] = cache_status
    if cache_updated_at:
        response.headers["X-Rankings-Cache-Updated-At"] = cache_updated_at
    return rankings_payload


@app.get("/dashboard-initial")
def dashboard_initial(
    response: Response,
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    rankings_payload, meta = get_rankings_with_meta(session=session, selected_only=selected_only)
    cache_status = str(meta.get("cache_status") or "")
    cache_updated_at = str(meta.get("cache_updated_at") or "")
    if cache_status:
        response.headers["X-Rankings-Cache-Status"] = cache_status
    if cache_updated_at:
        response.headers["X-Rankings-Cache-Updated-At"] = cache_updated_at
    return {
        "overview": get_overview(session=session, selected_only=selected_only).model_dump(mode="json"),
        "settings": get_runtime_settings_response(session=session).model_dump(mode="json"),
        "scheduler": get_scheduler_status_response(session=session).model_dump(mode="json"),
        "models": [item.model_dump(mode="json") for item in list_models(session=session, selected_only=False)],
        "rankings": [item.model_dump(mode="json") for item in rankings_payload],
    }


@app.get("/dashboard-performance")
def dashboard_performance(
    selected_only: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return {
        "portfolios": [item.model_dump(mode="json") for item in list_portfolios(session=session, selected_only=selected_only)],
        "positions": [item.model_dump(mode="json") for item in list_positions(session=session, selected_only=selected_only)],
        "trades": [item.model_dump(mode="json") for item in list_trades(session=session, selected_only=selected_only, limit=200)],
        "snapshots": [item.model_dump(mode="json") for item in list_snapshots(session=session, selected_only=selected_only, limit=2000)],
        "logs": [item.model_dump(mode="json") for item in list_llm_logs(session=session, limit=200)],
    }


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
    tickers: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[MarketPriceHistoryPoint]:
    ticker_list = [item.strip() for item in (tickers or "").split(",") if item.strip()]
    return list_market_price_history(
        session=session,
        market_code=market_code,
        selected_only=selected_only,
        top_n=top_n,
        limit_per_ticker=limit_per_ticker,
        tickers=ticker_list or None,
    )


@app.get("/news", response_model=list[NewsBatchSummary])
def news(
    market_code: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[NewsBatchSummary]:
    return list_news_batches(session=session, market_code=market_code, limit=limit)


@app.get("/news-items", response_model=list[NewsItemSummary])
def news_items(
    market_code: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[NewsItemSummary]:
    return list_news_items(session=session, market_code=market_code, limit=limit)


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


