from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LLMModel, MarketSetting, ModelMarketPrompt, Portfolio


def ensure_model_market_state(
    session: Session,
    model_id: str,
    market_code: str,
    display_name: str | None = None,
) -> None:
    model = session.scalar(select(LLMModel).where(LLMModel.model_id == model_id))
    if model is None:
        model = LLMModel(
            provider="manual",
            model_id=model_id,
            display_name=display_name or model_id,
            is_available=True,
            is_selected=False,
            metadata_json={"api_enabled": True},
        )
        session.add(model)
        session.flush()

    market = session.scalar(select(MarketSetting).where(MarketSetting.market_code == market_code))
    if market is None:
        raise ValueError(f"Missing market setting for {market_code}")

    portfolio = session.scalar(
        select(Portfolio).where(
            Portfolio.model_id == model_id,
            Portfolio.market_code == market_code,
        )
    )
    if portfolio is None:
        session.add(
            Portfolio(
                model_id=model_id,
                market_code=market_code,
                currency=market.currency,
                initial_cash=market.initial_cash,
                available_cash=market.initial_cash,
                invested_value=0.0,
                total_equity=market.initial_cash,
                total_realized_pnl=0.0,
                total_unrealized_pnl=0.0,
            )
        )

    prompt = session.scalar(
        select(ModelMarketPrompt).where(
            ModelMarketPrompt.model_id == model_id,
            ModelMarketPrompt.market_code == market_code,
            ModelMarketPrompt.version == 1,
        )
    )
    custom_prompt = resolve_profile_prompt(model, market_code)
    if prompt is None:
        session.add(
            ModelMarketPrompt(
                model_id=model_id,
                market_code=market_code,
                version=1,
                prompt_content=custom_prompt or "PENDING_GENERATION",
                source_meta_prompt="Admin custom prompt." if custom_prompt else "Pending model-specific prompt generation.",
                is_active=True,
            )
        )
    elif custom_prompt and prompt.prompt_content == "PENDING_GENERATION":
        prompt.prompt_content = custom_prompt
        prompt.source_meta_prompt = "Admin custom prompt."
    session.flush()


def resolve_profile_prompt(model: LLMModel | None, market_code: str) -> str | None:
    if model is None:
        return None
    metadata = model.metadata_json or {}
    raw_prompt = metadata.get("custom_prompt")
    if not raw_prompt:
        return None
    market_name = {
        "KR": "Korea equity market",
        "US": "United States equity market",
    }.get(market_code, market_code)
    try:
        return str(raw_prompt).format(
            market_code=market_code,
            market_name=market_name,
            request_model_id=(metadata.get("request_model_id") or model.model_id),
            profile_id=model.model_id,
            display_name=model.display_name,
        )
    except Exception:
        return str(raw_prompt)
