from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.config.loader import load_runtime_config
from app.market_data.models import MarketSnapshot, PriceSnapshot
from app.market_data.universe import UNIVERSE_BY_MARKET

MARKET_CURRENCY = {
    "KR": "KRW",
    "US": "USD",
}


class YahooMarketDataProvider:
    def __init__(self) -> None:
        self.runtime_config = load_runtime_config()
        cache_dir = Path(".cache") / "yfinance"
        cache_dir.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir.resolve()))

    def fetch_market_snapshot(self, market_code: str) -> MarketSnapshot:
        universe = UNIVERSE_BY_MARKET.get(market_code)
        if not universe:
            raise ValueError(f"Unsupported market code: {market_code}")

        tickers = list(universe.keys())
        frame = yf.download(
            tickers=tickers,
            period="5d",
            interval="1h",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=False,
        )
        if frame.empty:
            raise RuntimeError(f"No market data returned for {market_code}")

        prices: dict[str, PriceSnapshot] = {}
        as_of = datetime.now(UTC)
        for ticker, instrument_name in universe.items():
            ticker_frame = self._slice_ticker_frame(frame, ticker)
            if ticker_frame.empty or len(ticker_frame.index) < 3:
                continue

            ticker_frame = ticker_frame.dropna(how="all")
            if ticker_frame.empty:
                continue

            close = ticker_frame["Close"].dropna()
            volume = ticker_frame["Volume"].fillna(0)
            if close.empty:
                continue

            current_price = float(close.iloc[-1])
            previous_close = float(close.iloc[-2]) if len(close) >= 2 else current_price
            one_hour_base = float(close.iloc[-2]) if len(close) >= 2 else current_price
            one_day_base = float(close.iloc[-7]) if len(close) >= 7 else float(close.iloc[0])
            high = ticker_frame["High"].dropna()
            low = ticker_frame["Low"].dropna()
            latest_volume = float(volume.iloc[-1]) if len(volume) else 0.0
            avg_hourly_dollar_volume = float((close * volume).tail(7).mean()) if len(close) else 0.0

            volatility = 0.0
            if not high.empty and not low.empty and current_price:
                day_high = float(high.tail(7).max())
                day_low = float(low.tail(7).min())
                volatility = ((day_high - day_low) / current_price) * 100 if current_price else 0.0

            prices[ticker] = PriceSnapshot(
                ticker=ticker,
                instrument_name=instrument_name,
                current_price=current_price,
                previous_close=previous_close,
                return_1h_pct=_pct_change(current_price, one_hour_base),
                return_1d_pct=_pct_change(current_price, one_day_base),
                intraday_volatility_pct=round(volatility, 4),
                latest_volume=latest_volume,
                avg_hourly_dollar_volume=avg_hourly_dollar_volume,
                market_cap=None,
                currency=MARKET_CURRENCY.get(market_code),
                as_of=as_of,
            )

        return MarketSnapshot(
            market_code=market_code,
            currency=MARKET_CURRENCY.get(market_code, "USD"),
            as_of=as_of,
            prices=prices,
        )

    def _slice_ticker_frame(self, frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if isinstance(frame.columns, pd.MultiIndex):
            try:
                ticker_frame = frame[ticker].copy()
            except KeyError:
                ticker_frame = pd.DataFrame()
        else:
            ticker_frame = frame.copy()
        if not ticker_frame.empty:
            ticker_frame.columns = [str(column) for column in ticker_frame.columns]
        return ticker_frame


def _pct_change(current_value: float, base_value: float) -> float:
    if not base_value:
        return 0.0
    return round(((current_value - base_value) / base_value) * 100, 4)
