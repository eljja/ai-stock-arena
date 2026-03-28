from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TradeInstruction(BaseModel):
    ticker: str
    action: Literal["BUY", "SELL", "HOLD"]
    quantity: int | None = Field(default=None, ge=0)
    cash_amount: float | None = Field(default=None, ge=0)
    confidence: float = Field(default=0.5, ge=0, le=1)
    thesis: str


class TradingDecision(BaseModel):
    market_summary: str
    risk_note: str
    instructions: list[TradeInstruction]
    hold_tickers: list[str] = Field(default_factory=list)
    rejected_tickers: list[str] = Field(default_factory=list)
    raw_response: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None


class PromptGenerationResult(BaseModel):
    prompt_content: str
    raw_response: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None


class DecisionContext(BaseModel):
    market_code: str
    portfolio: dict[str, Any]
    current_positions: list[dict[str, Any]]
    candidates: list[dict[str, Any]]


class ChatCompletionResult(BaseModel):
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
