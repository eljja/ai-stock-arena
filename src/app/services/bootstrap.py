from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.loader import load_runtime_config, load_settings, parse_default_model_ids
from app.db.base import Base
from app.db.models import LLMModel, MarketSetting, ModelMarketPrompt, Portfolio
from app.db.session import engine
from app.llm.openrouter import OpenRouterClient

MARKET_LABELS = {
    "KOSPI": "Korea Composite Stock Price Index",
    "KOSDAQ": "Korea Securities Dealers Automated Quotations",
    "US": "United States Equity Market",
}


@dataclass(slots=True)
class BootstrapSummary:
    synced_models: int
    selected_models: int
    market_settings_upserted: int
    portfolios_created: int
    prompt_placeholders_created: int


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


def bootstrap_database(session: Session, sync_openrouter_models: bool = True) -> BootstrapSummary:
    runtime_config = load_runtime_config()
    settings = load_settings()
    selected_model_ids = set(parse_default_model_ids(settings))

    synced_models = 0
    if sync_openrouter_models:
        synced_models = sync_models_from_openrouter(session, selected_model_ids)

    market_settings_upserted = upsert_market_settings(session, runtime_config.app.max_positions_per_market)
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
        existing.metadata_json = external_model.metadata_json
        existing.is_available = True
        existing.is_selected = external_model.model_id in selected_model_ids if selected_model_ids else existing.is_selected
        synced += 1
    return synced


def upsert_market_settings(session: Session, max_positions: int) -> int:
    runtime_config = load_runtime_config()
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
