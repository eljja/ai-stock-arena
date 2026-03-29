from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import HourlyMarketPrice, LLMDecisionLog, LLMModel, MarketInstrument, Position, Trade
from app.market_data.models import MarketSnapshot, PriceSnapshot
from app.market_data.provider import YahooMarketDataProvider
from app.market_data.universe import UNIVERSE_BY_MARKET


def record_market_snapshot(session: Session, snapshot: MarketSnapshot) -> int:
    market_code = snapshot.market_code
    known_universe = UNIVERSE_BY_MARKET.get(market_code, {})
    existing = {
        instrument.ticker: instrument
        for instrument in session.scalars(
            select(MarketInstrument).where(MarketInstrument.market_code == market_code)
        ).all()
    }

    seen_tickers = set(snapshot.prices.keys())
    inserted = 0
    for ticker, price in snapshot.prices.items():
        _upsert_market_instrument(
            session=session,
            existing=existing,
            market_code=market_code,
            ticker=ticker,
            instrument_name=price.instrument_name,
            as_of=price.as_of or snapshot.as_of,
            is_active=True,
        )

        already_exists = session.scalar(
            select(HourlyMarketPrice.id).where(
                HourlyMarketPrice.market_code == market_code,
                HourlyMarketPrice.ticker == ticker,
                HourlyMarketPrice.as_of == (price.as_of or snapshot.as_of),
            )
        )
        if already_exists is not None:
            continue

        session.add(
            HourlyMarketPrice(
                market_code=market_code,
                ticker=ticker,
                instrument_name=price.instrument_name,
                current_price=price.current_price,
                previous_close=price.previous_close,
                return_1h_pct=price.return_1h_pct,
                return_1d_pct=price.return_1d_pct,
                intraday_volatility_pct=price.intraday_volatility_pct,
                latest_volume=price.latest_volume,
                avg_hourly_dollar_volume=price.avg_hourly_dollar_volume,
                currency=price.currency,
                as_of=price.as_of or snapshot.as_of,
            )
        )
        inserted += 1

    for ticker, instrument_name in known_universe.items():
        if ticker in seen_tickers:
            continue
        _upsert_market_instrument(
            session=session,
            existing=existing,
            market_code=market_code,
            ticker=ticker,
            instrument_name=instrument_name,
            as_of=snapshot.as_of,
            is_active=False,
        )

    session.flush()
    return inserted


def tracked_tickers_for_market(
    session: Session,
    market_code: str,
    selected_only: bool = True,
    top_n: int = 20,
) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    names: dict[str, str | None] = {}

    position_stmt = (
        select(
            Position.ticker,
            func.max(Position.instrument_name),
            func.sum(Position.market_value),
            func.count(Position.id),
        )
        .where(Position.market_code == market_code)
        .group_by(Position.ticker)
    )
    if selected_only:
        position_stmt = position_stmt.join(LLMModel, LLMModel.model_id == Position.model_id).where(LLMModel.is_selected.is_(True))
    for ticker, instrument_name, market_value_sum, holder_count in session.execute(position_stmt).all():
        scores[ticker] += 1_000.0
        scores[ticker] += float(market_value_sum or 0.0) / 1_000.0
        scores[ticker] += float(holder_count or 0) * 50.0
        names[ticker] = instrument_name or names.get(ticker)

    trade_stmt = select(Trade).where(Trade.market_code == market_code).order_by(Trade.created_at.desc(), Trade.id.desc())
    if selected_only:
        trade_stmt = trade_stmt.join(LLMModel, LLMModel.model_id == Trade.model_id).where(LLMModel.is_selected.is_(True))
    for idx, trade in enumerate(session.scalars(trade_stmt.limit(400)).all()):
        weight = max(120.0 - idx * 0.4, 4.0)
        scores[trade.ticker] += weight
        scores[trade.ticker] += float(trade.gross_amount or 0.0) / 10_000.0
        names[trade.ticker] = trade.instrument_name or names.get(trade.ticker)

    latest_logs = _latest_logs_by_model(session=session, market_code=market_code, selected_only=selected_only)
    for log in latest_logs:
        parsed = log.parsed_output if isinstance(log.parsed_output, dict) else {}
        for ticker in _extract_tickers_from_log(parsed):
            scores[ticker] += 80.0
            names.setdefault(ticker, ticker)

    allowed_tickers = set(UNIVERSE_BY_MARKET.get(market_code, {}).keys())
    if not scores:
        fallback = session.scalars(
            select(MarketInstrument.ticker)
            .where(MarketInstrument.market_code == market_code)
            .order_by(MarketInstrument.is_active.desc(), MarketInstrument.last_seen_at.desc(), MarketInstrument.ticker.asc())
        ).all()
        return [ticker for ticker in fallback if ticker in allowed_tickers][:top_n]

    ranked = sorted(
        ((ticker, score) for ticker, score in scores.items() if ticker in allowed_tickers),
        key=lambda item: (-item[1], item[0]),
    )
    return [ticker for ticker, _score in ranked[:top_n]]


def backfill_tracked_market_history(
    session: Session,
    provider: YahooMarketDataProvider,
    market_code: str,
    selected_only: bool = True,
    top_n: int = 20,
    period: str = "730d",
) -> dict[str, object]:
    tickers = tracked_tickers_for_market(
        session=session,
        market_code=market_code,
        selected_only=selected_only,
        top_n=top_n,
    )
    if not tickers:
        return {
            "market_code": market_code,
            "tracked_tickers": [],
            "stored_tickers": 0,
            "inserted_rows": 0,
            "history_points": 0,
            "missing_tickers": [],
        }

    histories = provider.fetch_hourly_history(market_code=market_code, tickers=tickers, period=period)
    existing = {
        instrument.ticker: instrument
        for instrument in session.scalars(
            select(MarketInstrument).where(MarketInstrument.market_code == market_code)
        ).all()
    }

    inserted_rows = 0
    history_points = 0
    stored_tickers = 0
    now = datetime.now(UTC)
    missing_tickers: list[str] = []

    for ticker in tickers:
        history = histories.get(ticker, [])
        if not history:
            _upsert_market_instrument(
                session=session,
                existing=existing,
                market_code=market_code,
                ticker=ticker,
                instrument_name=existing.get(ticker).instrument_name if existing.get(ticker) else ticker,
                as_of=now,
                is_active=False,
            )
            missing_tickers.append(ticker)
            continue
        inserted_rows += record_price_history(session, market_code=market_code, ticker=ticker, history=history, existing=existing)
        history_points += len(history)
        stored_tickers += 1

    session.flush()
    return {
        "market_code": market_code,
        "tracked_tickers": tickers,
        "stored_tickers": stored_tickers,
        "inserted_rows": inserted_rows,
        "history_points": history_points,
        "missing_tickers": missing_tickers,
    }


def record_price_history(
    session: Session,
    market_code: str,
    ticker: str,
    history: list[PriceSnapshot],
    existing: dict[str, MarketInstrument] | None = None,
) -> int:
    if not history:
        return 0
    instrument_name = history[-1].instrument_name or ticker
    latest_as_of = max((item.as_of for item in history if item.as_of), default=datetime.now(UTC))
    existing = existing or {}
    _upsert_market_instrument(
        session=session,
        existing=existing,
        market_code=market_code,
        ticker=ticker,
        instrument_name=instrument_name,
        as_of=latest_as_of,
        is_active=True,
    )

    existing_timestamps = {
        _to_utc_naive(timestamp)
        for timestamp in session.scalars(
            select(HourlyMarketPrice.as_of).where(
                HourlyMarketPrice.market_code == market_code,
                HourlyMarketPrice.ticker == ticker,
            )
        ).all()
    }

    inserted = 0
    for price in sorted(history, key=lambda item: item.as_of or latest_as_of):
        as_of = price.as_of or latest_as_of
        as_of_key = _to_utc_naive(as_of)
        if as_of_key in existing_timestamps:
            continue
        session.add(
            HourlyMarketPrice(
                market_code=market_code,
                ticker=ticker,
                instrument_name=price.instrument_name,
                current_price=price.current_price,
                previous_close=price.previous_close,
                return_1h_pct=price.return_1h_pct,
                return_1d_pct=price.return_1d_pct,
                intraday_volatility_pct=price.intraday_volatility_pct,
                latest_volume=price.latest_volume,
                avg_hourly_dollar_volume=price.avg_hourly_dollar_volume,
                currency=price.currency,
                as_of=as_of,
            )
        )
        existing_timestamps.add(as_of_key)
        inserted += 1
    return inserted


def _latest_logs_by_model(session: Session, market_code: str, selected_only: bool) -> list[LLMDecisionLog]:
    stmt = select(LLMDecisionLog).where(LLMDecisionLog.market_code == market_code).order_by(LLMDecisionLog.created_at.desc(), LLMDecisionLog.id.desc())
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == LLMDecisionLog.model_id).where(LLMModel.is_selected.is_(True))
    rows = session.scalars(stmt.limit(500)).all()
    latest_by_model: dict[str, LLMDecisionLog] = {}
    for row in rows:
        latest_by_model.setdefault(row.model_id, row)
    return list(latest_by_model.values())


def _extract_tickers_from_log(parsed_output: dict) -> set[str]:
    tickers: set[str] = set()
    for ticker in parsed_output.get("hold_tickers", []) or []:
        if isinstance(ticker, str) and ticker:
            tickers.add(ticker)
    for instruction in parsed_output.get("instructions", []) or []:
        if not isinstance(instruction, dict):
            continue
        ticker = instruction.get("ticker")
        if isinstance(ticker, str) and ticker:
            tickers.add(ticker)
    return tickers


def _upsert_market_instrument(
    session: Session,
    existing: dict[str, MarketInstrument],
    market_code: str,
    ticker: str,
    instrument_name: str | None,
    as_of: datetime,
    is_active: bool,
) -> MarketInstrument:
    instrument = existing.get(ticker)
    if instrument is None:
        instrument = MarketInstrument(
            market_code=market_code,
            ticker=ticker,
            instrument_name=instrument_name,
            is_active=is_active,
            first_seen_at=as_of,
            last_seen_at=as_of,
            delisted_at=None if is_active else as_of,
        )
        session.add(instrument)
        existing[ticker] = instrument
        return instrument

    instrument.instrument_name = instrument_name or instrument.instrument_name
    if is_active:
        instrument.is_active = True
        instrument.last_seen_at = as_of
        instrument.delisted_at = None
    else:
        instrument.is_active = False
        instrument.last_seen_at = _max_datetime(instrument.last_seen_at, as_of)
        instrument.delisted_at = instrument.delisted_at or as_of
    return instrument

def _max_datetime(left: datetime | None, right: datetime) -> datetime:
    if left is None:
        return right
    left_cmp = _to_utc_naive(left)
    right_cmp = _to_utc_naive(right)
    return left if left_cmp >= right_cmp else right


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


