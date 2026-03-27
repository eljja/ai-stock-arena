from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config.loader import load_settings

BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(slots=True)
class OpenRouterModel:
    model_id: str
    display_name: str
    context_length: int | None
    prompt_price_per_million: float | None
    completion_price_per_million: float | None
    metadata_json: dict


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, timeout_seconds: float = 30.0) -> None:
        settings = load_settings()
        self.api_key = api_key or settings.openrouter_api_key
        self.timeout_seconds = timeout_seconds

    def list_models(self) -> list[OpenRouterModel]:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")

        response = httpx.get(
            f"{BASE_URL}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", [])
        return [self._map_model(item) for item in items]

    def _map_model(self, item: dict) -> OpenRouterModel:
        pricing = item.get("pricing") or {}
        return OpenRouterModel(
            model_id=item["id"],
            display_name=item.get("name") or item["id"],
            context_length=item.get("context_length"),
            prompt_price_per_million=_safe_float(pricing.get("prompt")),
            completion_price_per_million=_safe_float(pricing.get("completion")),
            metadata_json=item,
        )


def _safe_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
