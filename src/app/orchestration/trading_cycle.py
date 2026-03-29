from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LLMDecisionLog, LLMModel, ModelMarketPrompt, Portfolio, Position
from app.llm.openrouter import OpenRouterClient
from app.llm.schemas import TradingDecision
from app.market_data.models import Candidate, MarketSnapshot
from app.services.setup_helpers import ensure_model_market_state
from app.services.shared_news import recent_news_context
from app.trading.engine import TradingEngine


class TradingCycleService:
    def __init__(self) -> None:
        self.client = OpenRouterClient()
        self.engine = TradingEngine()

    def ensure_active_prompt(self, session: Session, model_id: str, market_code: str) -> ModelMarketPrompt:
        prompt = session.scalar(
            select(ModelMarketPrompt).where(
                ModelMarketPrompt.model_id == model_id,
                ModelMarketPrompt.market_code == market_code,
                ModelMarketPrompt.is_active.is_(True),
            )
        )
        if prompt is None:
            ensure_model_market_state(session, model_id=model_id, market_code=market_code, display_name=model_id)
            session.flush()
            prompt = session.scalar(
                select(ModelMarketPrompt).where(
                    ModelMarketPrompt.model_id == model_id,
                    ModelMarketPrompt.market_code == market_code,
                    ModelMarketPrompt.is_active.is_(True),
                )
            )
        if prompt is None:
            raise ValueError(f"Prompt row missing for model={model_id}, market={market_code}")
        request_model_id = _resolve_request_model_id(session, model_id)
        if prompt.prompt_content == "PENDING_GENERATION":
            generated = self.client.generate_meta_prompt(model_id=request_model_id, market_code=market_code)
            prompt.prompt_content = generated.prompt_content
            prompt.source_meta_prompt = generated.raw_response
            session.flush()
        return prompt

    def request_decision(
        self,
        session: Session,
        model_id: str,
        market_code: str,
        snapshot: MarketSnapshot,
        candidates: list[Candidate],
    ) -> tuple[TradingDecision, str]:
        prompt = self.ensure_active_prompt(session, model_id, market_code)
        portfolio_payload = _portfolio_payload(session, model_id, market_code)
        position_payload = _position_payload(session, model_id, market_code)
        candidate_payload = _candidate_payload(candidates)
        news_payload = recent_news_context(session, market_code, minutes=60, limit=10)
        prompt_text = build_decision_prompt(
            market_code=market_code,
            custom_prompt=prompt.prompt_content,
            portfolio=portfolio_payload,
            positions=position_payload,
            candidates=candidates,
            snapshot=snapshot,
            news_items=_news_headline_payload(news_payload),
        )
        model_record = session.scalar(select(LLMModel).where(LLMModel.model_id == model_id))
        request_model_id = _resolve_request_model_id(session, model_id)
        input_payload = {
            "market_code": market_code,
            "snapshot_as_of": snapshot.as_of.isoformat(),
            "portfolio": portfolio_payload,
            "positions": position_payload,
            "candidates": candidate_payload,
            "shared_news": news_payload,
        }
        try:
            decision = self.client.request_trading_decision(model_id=request_model_id, decision_prompt=prompt_text)
            decision.estimated_cost_usd = _estimate_llm_cost_usd(model_record, decision.prompt_tokens, decision.completion_tokens)
            session.add(
                LLMDecisionLog(
                    model_id=model_id,
                    request_model_id=request_model_id,
                    market_code=market_code,
                    status="success",
                    prompt_text=prompt_text,
                    input_payload=input_payload,
                    raw_output_text=decision.raw_response,
                    parsed_output=decision.model_dump(exclude={"raw_response"}),
                    error_message=None,
                )
            )
            session.flush()
            return decision, prompt.prompt_content
        except Exception as exc:
            session.add(
                LLMDecisionLog(
                    model_id=model_id,
                    request_model_id=request_model_id,
                    market_code=market_code,
                    status="error",
                    prompt_text=prompt_text,
                    input_payload=input_payload,
                    raw_output_text=None,
                    parsed_output=None,
                    error_message=str(exc),
                )
            )
            session.flush()
            raise

    def execute_decision(
        self,
        session: Session,
        model_id: str,
        market_code: str,
        decision: TradingDecision,
        snapshot: MarketSnapshot,
        prompt_text: str,
    ) -> list[str]:
        messages: list[str] = []
        positions = {
            position.ticker: position
            for position in session.scalars(
                select(Position).where(
                    Position.model_id == model_id,
                    Position.market_code == market_code,
                )
            ).all()
        }

        sell_instructions = [item for item in decision.instructions if item.action == "SELL"]
        buy_instructions = [item for item in decision.instructions if item.action == "BUY"]

        for instruction in sell_instructions:
            snapshot_item = snapshot.prices.get(instruction.ticker)
            current_position = positions.get(instruction.ticker)
            if snapshot_item is None or current_position is None:
                continue
            quantity = min(instruction.quantity or int(current_position.quantity), int(current_position.quantity))
            if quantity <= 0:
                continue
            result = self.engine.execute_sell(
                session,
                model_id=model_id,
                market_code=market_code,
                snapshot=snapshot_item,
                quantity=quantity,
                reason=instruction.thesis,
                prompt_snapshot=prompt_text,
                decision_payload=instruction.model_dump(),
            )
            messages.append(result.message)

        portfolio = session.scalar(
            select(Portfolio).where(
                Portfolio.model_id == model_id,
                Portfolio.market_code == market_code,
            )
        )
        if portfolio is None:
            raise ValueError(f"Portfolio missing for model={model_id}, market={market_code}")

        for instruction in buy_instructions:
            snapshot_item = snapshot.prices.get(instruction.ticker)
            if snapshot_item is None:
                continue
            quantity = instruction.quantity or _quantity_from_cash_amount(
                instruction.cash_amount,
                snapshot_item.current_price,
            )
            if quantity <= 0:
                continue
            result = self.engine.execute_buy(
                session,
                model_id=model_id,
                market_code=market_code,
                snapshot=snapshot_item,
                quantity=quantity,
                reason=instruction.thesis,
                prompt_snapshot=prompt_text,
                decision_payload=instruction.model_dump(),
            )
            messages.append(result.message)

        latest_prices = {ticker: item.current_price for ticker, item in snapshot.prices.items()}
        self.engine.refresh_portfolio_totals(session, model_id, market_code, latest_prices=latest_prices)
        self.engine.record_snapshot(session, model_id, market_code)
        session.flush()
        return messages


def build_decision_prompt(
    market_code: str,
    custom_prompt: str,
    portfolio: dict,
    positions: list[dict],
    candidates: list[Candidate],
    snapshot: MarketSnapshot,
    news_items: str,
) -> str:
    candidate_payload = _candidate_payload(candidates)
    return f"""
{custom_prompt}

You are making one hourly virtual trading decision for market {market_code}.
Use English only.
Prefer the latest 1 hour of price movement over older signals.
Do not exceed 10 total positions after execution.
Respect transaction costs and current cash.

Portfolio state:
{portfolio}

Current positions:
{positions}

Screened candidates:
{candidate_payload}

Snapshot timestamp:
{snapshot.as_of.isoformat()}

News headlines collected during the last 60 minutes:
{news_items}

Return JSON with this schema exactly:
{{
  "market_summary": "short summary",
  "risk_note": "main risk to monitor",
  "hold_tickers": ["TICKER"],
  "rejected_tickers": ["TICKER"],
  "instructions": [
    {{
      "ticker": "AAPL",
      "action": "BUY",
      "quantity": 10,
      "cash_amount": null,
      "confidence": 0.72,
      "thesis": "Why this trade should be executed now"
    }},
    {{
      "ticker": "MSFT",
      "action": "SELL",
      "quantity": 5,
      "cash_amount": null,
      "confidence": 0.61,
      "thesis": "Why this reduction or exit should happen now"
    }}
  ]
}}

Rules:
- action must be BUY, SELL, or HOLD
- include only actionable trades in instructions
- for BUY, provide either quantity or cash_amount
- for SELL, quantity is required
- do not recommend fractional shares
- do not mention markdown fences
- treat the news headlines as shared benchmark context; do not assume access to any hidden or private news tool
""".strip()


def _portfolio_payload(session: Session, model_id: str, market_code: str) -> dict:
    portfolio = session.scalar(
        select(Portfolio).where(
            Portfolio.model_id == model_id,
            Portfolio.market_code == market_code,
        )
    )
    if portfolio is None:
        raise ValueError(f"Portfolio missing for model={model_id}, market={market_code}")
    return {
        "currency": portfolio.currency,
        "initial_cash": portfolio.initial_cash,
        "available_cash": portfolio.available_cash,
        "invested_value": portfolio.invested_value,
        "total_equity": portfolio.total_equity,
        "total_realized_pnl": portfolio.total_realized_pnl,
        "total_unrealized_pnl": portfolio.total_unrealized_pnl,
    }


def _position_payload(session: Session, model_id: str, market_code: str) -> list[dict]:
    positions = session.scalars(
        select(Position).where(
            Position.model_id == model_id,
            Position.market_code == market_code,
        )
    ).all()
    return [
        {
            "ticker": position.ticker,
            "instrument_name": position.instrument_name,
            "quantity": position.quantity,
            "avg_entry_price": position.avg_entry_price,
            "current_price": position.current_price,
            "market_value": position.market_value,
            "unrealized_pnl": position.unrealized_pnl,
            "unrealized_pnl_pct": position.unrealized_pnl_pct,
        }
        for position in positions
    ]


def _candidate_payload(candidates: list[Candidate]) -> list[dict]:
    return [
        {
            "ticker": candidate.ticker,
            "instrument_name": candidate.instrument_name,
            "screen_score": candidate.score,
            "reasons": candidate.reasons,
            "price": candidate.snapshot.current_price if candidate.snapshot else None,
            "return_1h_pct": candidate.snapshot.return_1h_pct if candidate.snapshot else None,
            "return_1d_pct": candidate.snapshot.return_1d_pct if candidate.snapshot else None,
            "intraday_volatility_pct": candidate.snapshot.intraday_volatility_pct if candidate.snapshot else None,
        }
        for candidate in candidates
    ]


def _resolve_request_model_id(session: Session, model_id: str) -> str:
    model = session.scalar(select(LLMModel).where(LLMModel.model_id == model_id))
    if model is None:
        return model_id
    metadata = model.metadata_json or {}
    return metadata.get("request_model_id") or model.model_id


def _estimate_llm_cost_usd(
    model_record: LLMModel | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    if model_record is None:
        return None
    if prompt_tokens is None and completion_tokens is None:
        return None
    prompt_cost = ((prompt_tokens or 0) / 1_000_000) * (model_record.prompt_price_per_million or 0.0)
    completion_cost = ((completion_tokens or 0) / 1_000_000) * (model_record.completion_price_per_million or 0.0)
    return round(prompt_cost + completion_cost, 8)


def _quantity_from_cash_amount(cash_amount: float | None, current_price: float) -> int:
    if not cash_amount or current_price <= 0:
        return 0
    return int(cash_amount // current_price)




def _news_headline_payload(news_items: list[dict]) -> str:
    headlines: list[str] = []
    for item in news_items:
        title = str(item.get("title") or "").strip()
        if title:
            headlines.append(f"- {title}")
    return "\n".join(headlines) if headlines else "- No shared news headlines available in the last 60 minutes."
