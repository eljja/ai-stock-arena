from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

from app.services.runtime_secrets import get_runtime_secret
from app.llm.schemas import ChatCompletionResult, PromptGenerationResult, TradingDecision

BASE_URL = "https://openrouter.ai/api/v1"
JSON_SYSTEM_PROMPT = (
    "You are a disciplined portfolio manager. Always follow the requested JSON schema exactly. "
    "Do not wrap the JSON in markdown fences."
)


@dataclass(slots=True)
class OpenRouterModel:
    model_id: str
    display_name: str
    context_length: int | None
    prompt_price_per_token: float | None
    completion_price_per_token: float | None
    request_price: float | None
    metadata_json: dict

    @property
    def prompt_price_per_million(self) -> float | None:
        if self.prompt_price_per_token is None:
            return None
        return self.prompt_price_per_token * 1_000_000

    @property
    def completion_price_per_million(self) -> float | None:
        if self.completion_price_per_token is None:
            return None
        return self.completion_price_per_token * 1_000_000

    @property
    def is_free_variant(self) -> bool:
        return self.model_id.endswith(":free")

    @property
    def has_zero_token_cost(self) -> bool:
        prompt = self.prompt_price_per_token or 0.0
        completion = self.completion_price_per_token or 0.0
        return prompt == 0.0 and completion == 0.0

    @property
    def is_free_like(self) -> bool:
        return self.is_free_variant or self.has_zero_token_cost

    @property
    def pricing_label(self) -> str:
        prompt = self.prompt_price_per_million
        completion = self.completion_price_per_million
        request = self.request_price
        return (
            f"input=${prompt:.4f}/1M, output=${completion:.4f}/1M, request=${request or 0:.6f}"
            if prompt is not None and completion is not None
            else "pricing unavailable"
        )


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, timeout_seconds: float = 30.0) -> None:
        self.api_key = api_key or get_runtime_secret("openrouter_api_key")
        self.timeout_seconds = timeout_seconds

    def list_models(self) -> list[OpenRouterModel]:
        self._ensure_api_key()
        response = httpx.get(
            f"{BASE_URL}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", [])
        return [self._map_model(item) for item in items]

    def catalog(
        self,
        sort_by: str = "price-low",
        free_mode: str = "include",
    ) -> list[OpenRouterModel]:
        models = self.list_models()
        if free_mode == "only":
            models = [model for model in models if model.is_free_like]
        elif free_mode == "exclude":
            models = [model for model in models if not model.is_free_like]

        if sort_by == "price-low":
            models.sort(key=_price_sort_key)
        elif sort_by == "price-high":
            models.sort(key=_price_sort_key, reverse=True)
        elif sort_by == "name":
            models.sort(key=lambda model: model.display_name.lower())
        elif sort_by == "popular":
            models.sort(key=_popularity_sort_key)
        return models

    def generate_meta_prompt(self, model_id: str, market_code: str) -> PromptGenerationResult:
        completion = self.chat_completion(
            model_id=model_id,
            user_prompt=_meta_prompt_request(market_code),
            system_prompt=(
                "You design trading prompts for yourself. Return only plain text. "
                "Do not include explanations or markdown fences."
            ),
            temperature=0.3,
        )
        return PromptGenerationResult(
            prompt_content=completion.content.strip(),
            raw_response=completion.content,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            total_tokens=completion.total_tokens,
            estimated_cost_usd=None,
        )

    def request_trading_decision(
        self,
        model_id: str,
        decision_prompt: str,
    ) -> TradingDecision:
        completion = self.chat_completion(
            model_id=model_id,
            user_prompt=decision_prompt,
            system_prompt=JSON_SYSTEM_PROMPT,
            temperature=0.2,
        )
        payload = _normalize_decision_payload(_extract_json_object(completion.content))
        decision = TradingDecision.model_validate(payload)
        decision.raw_response = completion.content
        decision.prompt_tokens = completion.prompt_tokens
        decision.completion_tokens = completion.completion_tokens
        decision.total_tokens = completion.total_tokens
        return decision

    def probe_model(self, model_id: str) -> tuple[bool, str]:
        try:
            completion = self.chat_completion(
                model_id=model_id,
                user_prompt="Reply with READY only.",
                system_prompt="Return the single word READY.",
                temperature=0.0,
            )
        except httpx.HTTPStatusError as exc:
            return False, f"HTTP {exc.response.status_code}"
        except Exception as exc:  # pragma: no cover
            return False, str(exc)

        normalized = completion.content.strip().upper()
        if "READY" in normalized:
            return True, normalized
        return True, normalized or "OK"

    def chat_completion(
        self,
        model_id: str,
        user_prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> ChatCompletionResult:
        self._ensure_api_key()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = self._post_with_retry(
            model_id=model_id,
            messages=messages,
            temperature=temperature,
        )
        payload = response.json()
        usage = payload.get("usage") or {}
        return ChatCompletionResult(
            content=payload["choices"][0]["message"]["content"],
            prompt_tokens=_to_int(usage.get("prompt_tokens") or usage.get("input_tokens")),
            completion_tokens=_to_int(usage.get("completion_tokens") or usage.get("output_tokens")),
            total_tokens=_to_int(usage.get("total_tokens")),
        )

    def _post_with_retry(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_attempts: int = 4,
    ) -> httpx.Response:
        last_error: httpx.HTTPStatusError | None = None
        for attempt in range(max_attempts):
            response = httpx.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=self.timeout_seconds,
            )
            try:
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code != 429 or attempt == max_attempts - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenRouter request failed without an HTTP response.")

    def _ensure_api_key(self) -> None:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")

    def _map_model(self, item: dict) -> OpenRouterModel:
        pricing = item.get("pricing") or {}
        return OpenRouterModel(
            model_id=item["id"],
            display_name=item.get("name") or item["id"],
            context_length=item.get("context_length"),
            prompt_price_per_token=_safe_float(pricing.get("prompt")),
            completion_price_per_token=_safe_float(pricing.get("completion")),
            request_price=_safe_float(pricing.get("request")),
            metadata_json=item,
        )


def _price_sort_key(model: OpenRouterModel) -> tuple[float, float, str]:
    prompt = model.prompt_price_per_million
    completion = model.completion_price_per_million
    combined = (prompt or 0.0) + (completion or 0.0)
    return combined, prompt or 0.0, model.display_name.lower()


def _popularity_sort_key(model: OpenRouterModel) -> tuple[int, int, int, float, str]:
    model_id = model.model_id.lower()
    family_order = [
        "gpt-oss",
        "qwen",
        "gemma",
        "llama",
        "deepseek",
        "mistral",
        "kimi",
        "glm",
        "arcee",
        "ministral",
    ]
    family_rank = next((index for index, token in enumerate(family_order) if token in model_id), len(family_order))
    preview_penalty = 1 if "preview" in model_id else 0
    free_rank = 0 if model.is_free_like else 1
    price_rank = (model.prompt_price_per_million or 0.0) + (model.completion_price_per_million or 0.0)
    return family_rank, preview_penalty, free_rank, price_rank, model.display_name.lower()


def _safe_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _to_int(value: int | str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _extract_json_object(raw_text: str) -> dict:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object.")
    return json.loads(raw_text[start : end + 1])



def _normalize_decision_payload(payload: dict) -> dict:
    normalized = dict(payload or {})

    if "instructions" not in normalized:
        instructions: list[dict] = []
        for item in normalized.get("buy_orders", []) or []:
            instructions.append(
                {
                    "ticker": item.get("ticker"),
                    "action": "BUY",
                    "quantity": item.get("quantity"),
                    "cash_amount": item.get("cash_amount"),
                    "confidence": item.get("confidence", 0.5),
                    "thesis": item.get("reason") or item.get("thesis") or "Buy signal.",
                }
            )
        for item in normalized.get("sell_orders", []) or []:
            instructions.append(
                {
                    "ticker": item.get("ticker"),
                    "action": "SELL",
                    "quantity": item.get("quantity"),
                    "cash_amount": None,
                    "confidence": item.get("confidence", 0.5),
                    "thesis": item.get("reason") or item.get("thesis") or "Sell signal.",
                }
            )
        normalized["instructions"] = instructions

    normalized.setdefault("market_summary", normalized.get("reasoning") or normalized.get("market_outlook") or "No summary provided.")
    normalized.setdefault("risk_note", normalized.get("news_sentiment") or "Risk not provided.")
    normalized.setdefault("hold_tickers", normalized.get("hold_tickers") or [])
    normalized.setdefault("rejected_tickers", normalized.get("rejected_tickers") or [])

    clean_instructions: list[dict] = []
    for item in normalized.get("instructions", []) or []:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").upper().strip()
        if action not in {"BUY", "SELL", "HOLD"}:
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        quantity = item.get("quantity")
        cash_amount = item.get("cash_amount")
        try:
            quantity = int(float(quantity)) if quantity not in (None, "") else None
        except Exception:
            quantity = None
        try:
            cash_amount = float(cash_amount) if cash_amount not in (None, "") else None
        except Exception:
            cash_amount = None
        try:
            confidence = float(item.get("confidence", 0.5))
        except Exception:
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        thesis = str(item.get("thesis") or item.get("reason") or "No thesis provided.").strip() or "No thesis provided."
        clean_instructions.append(
            {
                "ticker": ticker,
                "action": action,
                "quantity": quantity,
                "cash_amount": cash_amount,
                "confidence": confidence,
                "thesis": thesis,
            }
        )
    normalized["instructions"] = clean_instructions
    return normalized


def _meta_prompt_request(market_code: str) -> str:
    return f"""
Design the best reusable hourly trading prompt for the {market_code} market.

Requirements:
- prioritize the latest 1 hour of price action over older information
- use the latest 24 hours of news as supporting context when available
- keep the portfolio at 10 positions or fewer
- consider cash, existing positions, average entry price, unrealized PnL, and transaction costs
- support both buy and sell decisions
- produce instructions that are realistic for a virtual trading benchmark
- optimize the prompt for your own reasoning style

Return only the final prompt text in English.
""".strip()
