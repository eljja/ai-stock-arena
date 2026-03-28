from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    AdminSetting,
    LLMDecisionLog,
    LLMModel,
    MarketSetting,
    ModelMarketPrompt,
    PerformanceSnapshot,
    Portfolio,
    Position,
    SharedNewsBatch,
    SharedNewsItem,
    Trade,
)
from app.services.setup_helpers import ensure_model_market_state

RUNTIME_SETTINGS_KEY = "runtime_controls"

DEFAULT_RUNTIME_SETTINGS = {
    "decision_interval_minutes": 60,
    "active_weekdays": [0, 1, 2, 3, 4],
    "markets": {
        "KR": {"enabled": True, "window_start": "08:00", "window_end": "16:00"},
        "US": {"enabled": True, "window_start": "08:30", "window_end": "16:30"},
    },
    "news_enabled": False,
    "news_mode": "shared_off",
}


def get_runtime_settings(session: Session) -> dict:
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == RUNTIME_SETTINGS_KEY))
    if setting is None:
        setting = AdminSetting(key=RUNTIME_SETTINGS_KEY, value_json=DEFAULT_RUNTIME_SETTINGS.copy())
        session.add(setting)
        session.flush()
    return {**DEFAULT_RUNTIME_SETTINGS, **(setting.value_json or {})}


def update_runtime_settings(session: Session, payload: dict) -> dict:
    current = get_runtime_settings(session)
    merged = {**current, **payload}
    if "markets" in payload:
        merged["markets"] = {**current.get("markets", {}), **payload["markets"]}
    setting = session.scalar(select(AdminSetting).where(AdminSetting.key == RUNTIME_SETTINGS_KEY))
    if setting is None:
        setting = AdminSetting(key=RUNTIME_SETTINGS_KEY, value_json=merged)
        session.add(setting)
    else:
        setting.value_json = merged
        setting.updated_at = datetime.now(UTC)
    session.flush()
    return merged


def reset_simulation(session: Session, reset_prompts: bool = True) -> dict[str, int]:
    deleted_logs = session.execute(delete(LLMDecisionLog)).rowcount or 0
    deleted_positions = session.execute(delete(Position)).rowcount or 0
    deleted_trades = session.execute(delete(Trade)).rowcount or 0
    deleted_snapshots = session.execute(delete(PerformanceSnapshot)).rowcount or 0
    deleted_news_items = session.execute(delete(SharedNewsItem)).rowcount or 0
    deleted_news_batches = session.execute(delete(SharedNewsBatch)).rowcount or 0

    enabled_markets = {
        market.market_code: market
        for market in session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all()
    }

    for portfolio in session.scalars(select(Portfolio)).all():
        market = enabled_markets.get(portfolio.market_code)
        if market is None:
            session.delete(portfolio)
            continue
        portfolio.currency = market.currency
        portfolio.initial_cash = market.initial_cash
        portfolio.available_cash = market.initial_cash
        portfolio.invested_value = 0.0
        portfolio.total_equity = market.initial_cash
        portfolio.total_realized_pnl = 0.0
        portfolio.total_unrealized_pnl = 0.0

    if reset_prompts:
        for prompt in session.scalars(select(ModelMarketPrompt)).all():
            if prompt.market_code not in enabled_markets:
                session.delete(prompt)
                continue
            prompt.prompt_content = "PENDING_GENERATION"
            prompt.source_meta_prompt = "Pending model-specific prompt generation."

    for model in session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True))).all():
        for market_code in enabled_markets:
            ensure_model_market_state(
                session,
                model_id=model.model_id,
                market_code=market_code,
                display_name=model.display_name,
            )

    session.flush()
    return {
        "deleted_logs": deleted_logs,
        "deleted_positions": deleted_positions,
        "deleted_trades": deleted_trades,
        "deleted_snapshots": deleted_snapshots,
        "deleted_news_items": deleted_news_items,
        "deleted_news_batches": deleted_news_batches,
    }


def create_or_update_model_profile(
    session: Session,
    profile_id: str,
    request_model_id: str,
    display_name: str,
    provider: str = "openrouter",
    search_mode: str = "off",
    select_profile: bool = True,
    prompt_price_per_million: float | None = None,
    completion_price_per_million: float | None = None,
    context_length: int | None = None,
) -> LLMModel:
    model = session.scalar(select(LLMModel).where(LLMModel.model_id == profile_id))
    if model is None:
        model = LLMModel(
            provider=provider,
            model_id=profile_id,
            display_name=display_name,
            is_available=True,
            is_selected=select_profile,
            metadata_json={},
        )
        session.add(model)
    model.display_name = display_name
    model.provider = provider
    model.context_length = context_length
    model.prompt_price_per_million = prompt_price_per_million
    model.completion_price_per_million = completion_price_per_million
    model.is_selected = select_profile
    model.is_available = True
    metadata = model.metadata_json or {}
    metadata.update(
        {
            "request_model_id": request_model_id,
            "base_model_id": request_model_id.replace(":online", ""),
            "search_mode": search_mode,
            "pricing_label": _pricing_label(prompt_price_per_million, completion_price_per_million),
            "is_free_like": bool(request_model_id.endswith(":free") or request_model_id.endswith(":free:online")),
        }
    )
    model.metadata_json = metadata

    if select_profile:
        for market in session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all():
            ensure_model_market_state(session, model_id=profile_id, market_code=market.market_code, display_name=display_name)

    session.flush()
    return model


def delete_model_profile(session: Session, profile_id: str) -> dict[str, int]:
    session.execute(delete(LLMDecisionLog).where(LLMDecisionLog.model_id == profile_id))
    session.execute(delete(Position).where(Position.model_id == profile_id))
    session.execute(delete(Trade).where(Trade.model_id == profile_id))
    session.execute(delete(PerformanceSnapshot).where(PerformanceSnapshot.model_id == profile_id))
    session.execute(delete(Portfolio).where(Portfolio.model_id == profile_id))
    session.execute(delete(ModelMarketPrompt).where(ModelMarketPrompt.model_id == profile_id))
    deleted = session.execute(delete(LLMModel).where(LLMModel.model_id == profile_id)).rowcount or 0
    session.flush()
    return {"deleted_models": deleted}


def _pricing_label(prompt_price_per_million: float | None, completion_price_per_million: float | None) -> str:
    if prompt_price_per_million is None or completion_price_per_million is None:
        return "pricing unavailable"
    return f"input=${prompt_price_per_million:.4f}/1M, output=${completion_price_per_million:.4f}/1M"
