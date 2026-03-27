from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.config.loader import load_settings
from app.llm.schemas import PromptGenerationResult, TradingDecision

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
        settings = load_settings()
        self.api_key = api_key or settings.openrouter_api_key
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
            # Official /models responses do not document popularity ordering.
            pass
        return models

    def generate_meta_prompt(self, model_id: str, market_code: str) -> PromptGenerationResult:
        response_text = self.chat_completion(
            model_id=model_id,
            user_prompt=_meta_prompt_request(market_code),
            system_prompt=(
                "You design trading prompts for yourself. Return only plain text. "
                "Do not include explanations or markdown fences."
            ),
            temperature=0.3,
        )
        return PromptGenerationResult(prompt_content=response_text.strip(), raw_response=response_text)

    def request_trading_decision(
        self,
        model_id: str,
        decision_prompt: str,
    ) -> TradingDecision:
        response_text = self.chat_completion(
            model_id=model_id,
            user_prompt=decision_prompt,
            system_prompt=JSON_SYSTEM_PROMPT,
            temperature=0.2,
        )
        payload = _extract_json_object(response_text)
        decision = TradingDecision.model_validate(payload)
        decision.raw_response = response_text
        return decision

    def chat_completion(
        self,
        model_id: str,
        user_prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        self._ensure_api_key()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

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
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

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


def _safe_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _extract_json_object(raw_text: str) -> dict:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object.")
    return json.loads(raw_text[start : end + 1])


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
