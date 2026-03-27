from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PriceSnapshot:
    ticker: str
    instrument_name: str
    current_price: float
    previous_close: float
    return_1h_pct: float
    return_1d_pct: float
    intraday_volatility_pct: float
    latest_volume: float
    avg_hourly_dollar_volume: float
    market_cap: float | None = None
    currency: str | None = None
    as_of: datetime | None = None


@dataclass(slots=True)
class Candidate:
    ticker: str
    instrument_name: str
    score: float
    reasons: list[str] = field(default_factory=list)
    snapshot: PriceSnapshot | None = None


@dataclass(slots=True)
class MarketSnapshot:
    market_code: str
    currency: str
    as_of: datetime
    prices: dict[str, PriceSnapshot]
