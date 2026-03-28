from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.loader import load_runtime_config, load_settings, parse_default_model_ids
from app.db.base import Base
from app.db.models import LLMModel, MarketSetting, ModelMarketPrompt, Portfolio
from app.db.session import engine
from app.llm.openrouter import OpenRouterClient, OpenRouterModel
from app.services.admin import get_runtime_settings

MARKET_LABELS = {
    "KR": "Korea Equity Market",
    "US": "United States Equity Market",
}


@dataclass(slots=True)
class BootstrapSummary:
    synced_models: int
    selected_models: int
    market_settings_upserted: int
    portfolios_created: int
    prompt_placeholders_created: int


@dataclass(slots=True)
class ModelProbeResult:
    model_id: str
    success: bool
    detail: str


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


def bootstrap_database(session: Session, sync_openrouter_models: bool = True) -> BootstrapSummary:
    runtime_config = load_runtime_config()
    settings = load_settings()
    selected_model_ids = set(parse_default_model_ids(settings))
    get_runtime_settings(session)

    synced_models = 0
    if sync_openrouter_models:
        synced_models = sync_models_from_openrouter(session, selected_model_ids)

    market_settings_upserted = upsert_market_settings(session, runtime_config.app.max_positions_per_market)
    session.flush()
    portfolios_created, prompt_placeholders_created = initialize_selected_model_state(session)
    selected_models = count_selected_models(session)

    session.commit()
    return BootstrapSummary(
        synced_models=synced_models,
        selected_models=selected_models,
        market_settings_upserted=market_settings_upserted,
        portfolios_created=portfolios_created,
        prompt_placeholders_created=prompt_placeholders_created,
    )


def sync_models_from_openrouter(session: Session, selected_model_ids: set[str]) -> int:
    client = OpenRouterClient()
    synced = 0
    for external_model in client.list_models():
        upsert_openrouter_model(session, external_model, selected_model_ids)
        synced += 1
    return synced


def probe_and_select_free_models(
    session: Session,
    target_count: int = 3,
    candidate_limit: int = 12,
    sort_by: str = "price-low",
) -> list[ModelProbeResult]:
    client = OpenRouterClient()
    catalog = client.catalog(sort_by=sort_by, free_mode="only")[:candidate_limit]

    free_model_ids = {model.model_id for model in catalog}
    for existing in session.scalars(select(LLMModel).where(LLMModel.model_id.in_(free_model_ids))).all():
        existing.is_selected = False

    results: list[ModelProbeResult] = []
    selected_count = 0
    for external_model in catalog:
        record = upsert_openrouter_model(session, external_model, selected_model_ids=set())
        success, detail = client.probe_model(external_model.model_id)
        record.is_available = success
        record.metadata_json = {
            **(record.metadata_json or {}),
            "probe": {"success": success, "detail": detail},
            "probe_detail": detail,
            "is_free_like": external_model.is_free_like,
        }
        if success and selected_count < target_count:
            record.is_selected = True
            selected_count += 1
        else:
            record.is_selected = False
        results.append(ModelProbeResult(record.model_id, success, detail))

    session.flush()
    initialize_selected_model_state(session)
    session.commit()
    return results


def upsert_openrouter_model(
    session: Session,
    external_model: OpenRouterModel,
    selected_model_ids: set[str],
) -> LLMModel:
    existing = session.scalar(select(LLMModel).where(LLMModel.model_id == external_model.model_id))
    if existing is None:
        existing = LLMModel(
            provider="openrouter",
            model_id=external_model.model_id,
            display_name=external_model.display_name,
        )
        session.add(existing)
    existing.display_name = external_model.display_name
    existing.context_length = external_model.context_length
    existing.prompt_price_per_million = external_model.prompt_price_per_million
    existing.completion_price_per_million = external_model.completion_price_per_million
    previous_metadata = existing.metadata_json or {}
    existing.metadata_json = {
        **previous_metadata,
        **external_model.metadata_json,
        "request_model_id": external_model.model_id,
        "base_model_id": external_model.model_id.replace(":online", ""),
        "search_mode": previous_metadata.get("search_mode", "off"),
        "is_free_like": external_model.is_free_like,
        "pricing_label": external_model.pricing_label,
        "probe_detail": previous_metadata.get("probe_detail"),
    }
    existing.is_available = True
    existing.is_selected = (
        external_model.model_id in selected_model_ids if selected_model_ids else existing.is_selected
    )
    return existing


def upsert_market_settings(session: Session, max_positions: int) -> int:
    runtime_config = load_runtime_config()
    configured_market_codes = set(runtime_config.markets.keys())

    for existing in session.scalars(select(MarketSetting)).all():
        if existing.market_code not in configured_market_codes:
            existing.enabled = False

    upserted = 0
    for market_code, market_config in runtime_config.markets.items():
        existing = session.scalar(select(MarketSetting).where(MarketSetting.market_code == market_code))
        if existing is None:
            existing = MarketSetting(
                market_code=market_code,
                market_name=MARKET_LABELS.get(market_code, market_code),
                currency=market_config.currency,
                initial_cash=market_config.initial_cash,
            )
            session.add(existing)
        existing.market_name = MARKET_LABELS.get(market_code, market_code)
        existing.currency = market_config.currency
        existing.enabled = market_config.enabled
        existing.initial_cash = market_config.initial_cash
        existing.buy_commission_rate = market_config.buy_commission_rate
        existing.sell_commission_rate = market_config.sell_commission_rate
        existing.sell_tax_rate = market_config.sell_tax_rate
        existing.sell_regulatory_fee_rate = market_config.sell_regulatory_fee_rate
        existing.max_positions = max_positions
        upserted += 1
    return upserted


def initialize_selected_model_state(session: Session) -> tuple[int, int]:
    market_settings = session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all()
    selected_models = session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True))).all()

    portfolios_created = 0
    prompt_placeholders_created = 0
    for model in selected_models:
        for market_setting in market_settings:
            portfolio = session.scalar(
                select(Portfolio).where(
                    Portfolio.model_id == model.model_id,
                    Portfolio.market_code == market_setting.market_code,
                )
            )
            if portfolio is None:
                session.add(
                    Portfolio(
                        model_id=model.model_id,
                        market_code=market_setting.market_code,
                        currency=market_setting.currency,
                        initial_cash=market_setting.initial_cash,
                        available_cash=market_setting.initial_cash,
                        invested_value=0.0,
                        total_equity=market_setting.initial_cash,
                        total_realized_pnl=0.0,
                        total_unrealized_pnl=0.0,
                    )
                )
                portfolios_created += 1

            prompt = session.scalar(
                select(ModelMarketPrompt).where(
                    ModelMarketPrompt.model_id == model.model_id,
                    ModelMarketPrompt.market_code == market_setting.market_code,
                    ModelMarketPrompt.version == 1,
                )
            )
            if prompt is None:
                session.add(
                    ModelMarketPrompt(
                        model_id=model.model_id,
                        market_code=market_setting.market_code,
                        version=1,
                        prompt_content="PENDING_GENERATION",
                        source_meta_prompt=_default_meta_prompt(market_setting.market_code),
                        is_active=True,
                    )
                )
                prompt_placeholders_created += 1

    return portfolios_created, prompt_placeholders_created


def count_selected_models(session: Session) -> int:
    return len(session.scalars(select(LLMModel).where(LLMModel.is_selected.is_(True))).all())


def _default_meta_prompt(market_code: str) -> str:
    return (
        f"You are designing the best possible trading prompt for the {market_code} market. "
        "Prioritize the last 1 hour of price action, use the last 24 hours of news as supporting "
        "context, keep the portfolio under 10 positions, and account for market-specific fees and taxes. "
        "Return a production-ready prompt that will later be used for hourly virtual trading decisions."
    )
