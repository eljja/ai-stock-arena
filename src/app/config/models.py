from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseModel):
    name: str = "ai-stock-arena"
    timezone: str = "Asia/Seoul"
    decision_interval_minutes: int = 60
    max_positions_per_market: int = 10


class MarketConfig(BaseModel):
    enabled: bool = True
    currency: str
    initial_cash: float
    buy_commission_rate: float = 0.0
    sell_commission_rate: float = 0.0
    sell_tax_rate: float = 0.0
    sell_regulatory_fee_rate: float = 0.0


class ScreeningConfig(BaseModel):
    candidate_limit: int = 40
    include_current_positions: bool = True
    min_market_cap_usd: float = 1_000_000_000
    min_avg_dollar_volume_usd: float = 5_000_000
    min_market_cap_krw: float = 300_000_000_000
    min_avg_trading_value_krw: float = 2_000_000_000


class ScoreWeights(BaseModel):
    total_return: float = 0.35
    sharpe_ratio: float = 0.20
    max_drawdown_inverse: float = 0.15
    win_rate: float = 0.10
    profit_factor: float = 0.10
    volatility_inverse: float = 0.05
    turnover_penalty: float = 0.05


class ProvidersConfig(BaseModel):
    prices: str = "yahoo"
    news: str = "pending"
    llm: str = "openrouter"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    app: AppConfig
    markets: dict[str, MarketConfig]
    screening: ScreeningConfig
    scoring_weights: ScoreWeights
    providers: ProvidersConfig
    config_path: Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        default="sqlite:///./ai_stock_arena.db",
        alias="DATABASE_URL",
    )
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    default_model_ids: str = Field(default="", alias="DEFAULT_MODEL_IDS")
    config_file: Path = Field(default=Path("config/defaults.toml"), alias="CONFIG_FILE")
    api_base_url: str | None = Field(default=None, alias="API_BASE_URL")
    admin_token: str | None = Field(default=None, alias="ADMIN_TOKEN")
    marketaux_api_token: str | None = Field(default=None, alias="MARKETAUX_API_TOKEN")

