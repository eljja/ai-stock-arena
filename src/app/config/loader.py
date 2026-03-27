from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from app.config.models import (
    AppConfig,
    MarketConfig,
    ProvidersConfig,
    RuntimeConfig,
    ScreeningConfig,
    ScoreWeights,
    Settings,
)


def load_settings() -> Settings:
    return Settings()


def load_runtime_config(config_path: Path | None = None) -> RuntimeConfig:
    settings = load_settings()
    resolved_path = Path(config_path or settings.config_file)
    raw = _load_toml(resolved_path)

    scoring_raw = raw.get("scoring", {})
    return RuntimeConfig(
        app=AppConfig.model_validate(raw.get("app", {})),
        markets={
            market_name: MarketConfig.model_validate(market_value)
            for market_name, market_value in raw.get("markets", {}).items()
        },
        screening=ScreeningConfig.model_validate(raw.get("screening", {})),
        scoring_weights=ScoreWeights.model_validate(scoring_raw.get("weights", {})),
        providers=ProvidersConfig.model_validate(raw.get("providers", {})),
        config_path=resolved_path,
    )


def parse_default_model_ids(settings: Settings) -> list[str]:
    return [model_id.strip() for model_id in settings.default_model_ids.split(",") if model_id.strip()]


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file)
