from __future__ import annotations

from app.config.loader import load_runtime_config
from app.market_data.models import Candidate, MarketSnapshot


class MarketScreener:
    def __init__(self) -> None:
        self.runtime_config = load_runtime_config()

    def screen(self, snapshot: MarketSnapshot) -> list[Candidate]:
        config = self.runtime_config.screening
        candidates: list[Candidate] = []
        for price in snapshot.prices.values():
            if not self._passes_liquidity_filters(snapshot.market_code, price.avg_hourly_dollar_volume):
                continue

            score = self._score(price.return_1h_pct, price.return_1d_pct, price.intraday_volatility_pct, price.avg_hourly_dollar_volume)
            reasons = self._reasons(price.return_1h_pct, price.return_1d_pct, price.intraday_volatility_pct, price.avg_hourly_dollar_volume)
            candidates.append(
                Candidate(
                    ticker=price.ticker,
                    instrument_name=price.instrument_name,
                    score=score,
                    reasons=reasons,
                    snapshot=price,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[: config.candidate_limit]

    def _passes_liquidity_filters(self, market_code: str, avg_hourly_dollar_volume: float) -> bool:
        config = self.runtime_config.screening
        if market_code == "US":
            return avg_hourly_dollar_volume >= (config.min_avg_dollar_volume_usd / 6.5)
        return avg_hourly_dollar_volume >= (config.min_avg_trading_value_krw / 6.5)

    def _score(
        self,
        return_1h_pct: float,
        return_1d_pct: float,
        intraday_volatility_pct: float,
        avg_hourly_dollar_volume: float,
    ) -> float:
        liquidity_score = min(avg_hourly_dollar_volume / 10_000_000, 25)
        momentum_score = (return_1h_pct * 4.0) + (return_1d_pct * 1.8)
        volatility_penalty = max(intraday_volatility_pct - 8.0, 0) * 1.2
        return round(momentum_score + liquidity_score - volatility_penalty, 4)

    def _reasons(
        self,
        return_1h_pct: float,
        return_1d_pct: float,
        intraday_volatility_pct: float,
        avg_hourly_dollar_volume: float,
    ) -> list[str]:
        reasons = [f"1h return {return_1h_pct:.2f}%", f"1d return {return_1d_pct:.2f}%"]
        reasons.append(f"avg hourly turnover {avg_hourly_dollar_volume:,.0f}")
        if intraday_volatility_pct > 8:
            reasons.append(f"high volatility {intraday_volatility_pct:.2f}%")
        return reasons
