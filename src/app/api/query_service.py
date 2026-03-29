from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    CopyTradePosition,
    CopyTradeResponse,
    LLMDecisionLogSummary,
    ModelRanking,
    MarketInstrumentSummary,
    MarketPriceHistoryPoint,
    RunRequestSummary,
    ModelSummary,
    NewsBatchSummary,
    NewsItemSummary,
    OverviewResponse,
    PortfolioSummary,
    PositionSummary,
    RuntimeSettingsResponse,
    SchedulerStatusResponse,
    SnapshotSummary,
    TradeSummary,
)
from app.db.models import (
    LLMDecisionLog,
    HourlyMarketPrice,
    LLMModel,
    MarketInstrument,
    MarketSetting,
    PerformanceSnapshot,
    Portfolio,
    Position,
    RunRequest,
    SharedNewsBatch,
    SharedNewsItem,
    Trade,
)
from app.services.admin import get_runtime_settings, get_scheduler_status
from app.services.market_history import tracked_tickers_for_market


def get_overview(
    session: Session,
    market_code: str | None = None,
    selected_only: bool = False,
) -> OverviewResponse:
    enabled_market_codes = _enabled_market_codes(session, market_code)
    models = list_models(session=session, selected_only=selected_only)
    portfolios = list_portfolios(session=session, market_code=market_code, selected_only=selected_only)

    latest_trade_stmt = select(func.max(Trade.created_at))
    latest_snapshot_stmt = select(func.max(PerformanceSnapshot.created_at))
    if enabled_market_codes:
        latest_trade_stmt = latest_trade_stmt.where(Trade.market_code.in_(enabled_market_codes))
        latest_snapshot_stmt = latest_snapshot_stmt.where(PerformanceSnapshot.market_code.in_(enabled_market_codes))
    if selected_only:
        latest_trade_stmt = latest_trade_stmt.join(LLMModel, LLMModel.model_id == Trade.model_id).where(
            LLMModel.is_selected.is_(True)
        )
        latest_snapshot_stmt = latest_snapshot_stmt.join(
            LLMModel,
            LLMModel.model_id == PerformanceSnapshot.model_id,
        ).where(LLMModel.is_selected.is_(True))

    combined_initial_cash = sum(item.initial_cash for item in portfolios)
    combined_available_cash = sum(item.available_cash for item in portfolios)
    combined_invested_value = sum(item.invested_value for item in portfolios)
    combined_total_equity = sum(item.total_equity for item in portfolios)
    combined_return_pct = (
        ((combined_total_equity - combined_initial_cash) / combined_initial_cash) * 100
        if combined_initial_cash
        else 0.0
    )

    return OverviewResponse(
        selected_model_count=sum(1 for item in models if item.is_selected),
        model_count=len(models),
        free_model_count=sum(1 for item in models if item.is_free_like),
        available_model_count=sum(1 for item in models if item.is_available),
        portfolio_count=len(portfolios),
        combined_initial_cash=combined_initial_cash,
        combined_available_cash=combined_available_cash,
        combined_invested_value=combined_invested_value,
        combined_total_equity=combined_total_equity,
        combined_return_pct=combined_return_pct,
        latest_trade_at=session.scalar(latest_trade_stmt),
        latest_snapshot_at=session.scalar(latest_snapshot_stmt),
    )


def list_models(session: Session, selected_only: bool = False) -> list[ModelSummary]:
    stmt = select(LLMModel).order_by(
        LLMModel.is_selected.desc(),
        LLMModel.is_available.desc(),
        LLMModel.model_id.asc(),
    )
    if selected_only:
        stmt = stmt.where(LLMModel.is_selected.is_(True))

    models = session.scalars(stmt).all()
    return [_serialize_model(model) for model in models]


def list_portfolios(
    session: Session,
    market_code: str | None = None,
    selected_only: bool = False,
) -> list[PortfolioSummary]:
    enabled_market_codes = _enabled_market_codes(session, market_code)
    markets = _market_map(session)
    position_counts = _position_counts(session, enabled_market_codes)
    snapshot_times = _latest_snapshot_times(session, enabled_market_codes)

    stmt = select(Portfolio).order_by(Portfolio.market_code.asc(), Portfolio.total_equity.desc())
    if enabled_market_codes:
        stmt = stmt.where(Portfolio.market_code.in_(enabled_market_codes))
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == Portfolio.model_id).where(LLMModel.is_selected.is_(True))

    portfolios = session.scalars(stmt).all()
    return [
        PortfolioSummary(
            model_id=portfolio.model_id,
            market_code=portfolio.market_code,
            market_name=markets.get(portfolio.market_code, portfolio.market_code),
            currency=portfolio.currency,
            initial_cash=portfolio.initial_cash,
            available_cash=portfolio.available_cash,
            invested_value=portfolio.invested_value,
            total_equity=portfolio.total_equity,
            total_realized_pnl=portfolio.total_realized_pnl,
            total_unrealized_pnl=portfolio.total_unrealized_pnl,
            total_return_pct=_pct(portfolio.total_equity, portfolio.initial_cash),
            position_count=position_counts.get((portfolio.model_id, portfolio.market_code), 0),
            latest_snapshot_at=snapshot_times.get((portfolio.model_id, portfolio.market_code)),
            updated_at=portfolio.updated_at,
        )
        for portfolio in portfolios
    ]


def list_positions(
    session: Session,
    market_code: str | None = None,
    model_id: str | None = None,
    selected_only: bool = False,
) -> list[PositionSummary]:
    enabled_market_codes = _enabled_market_codes(session, market_code)
    stmt = select(Position).order_by(
        Position.market_code.asc(),
        Position.model_id.asc(),
        Position.market_value.desc(),
    )
    if enabled_market_codes:
        stmt = stmt.where(Position.market_code.in_(enabled_market_codes))
    if model_id:
        stmt = stmt.where(Position.model_id == model_id)
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == Position.model_id).where(LLMModel.is_selected.is_(True))

    positions = session.scalars(stmt).all()
    return [
        PositionSummary(
            model_id=position.model_id,
            market_code=position.market_code,
            ticker=position.ticker,
            instrument_name=position.instrument_name,
            quantity=position.quantity,
            avg_entry_price=position.avg_entry_price,
            current_price=position.current_price,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            unrealized_pnl_pct=position.unrealized_pnl_pct,
            opened_at=position.opened_at,
            updated_at=position.updated_at,
        )
        for position in positions
    ]


def list_trades(
    session: Session,
    market_code: str | None = None,
    model_id: str | None = None,
    selected_only: bool = False,
    limit: int = 100,
) -> list[TradeSummary]:
    enabled_market_codes = _enabled_market_codes(session, market_code)
    stmt = select(Trade).order_by(Trade.created_at.desc(), Trade.id.desc())
    if enabled_market_codes:
        stmt = stmt.where(Trade.market_code.in_(enabled_market_codes))
    if model_id:
        stmt = stmt.where(Trade.model_id == model_id)
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == Trade.model_id).where(LLMModel.is_selected.is_(True))

    trades = session.scalars(stmt.limit(limit)).all()
    return [_serialize_trade(trade) for trade in trades]


def list_snapshots(
    session: Session,
    market_code: str | None = None,
    model_id: str | None = None,
    selected_only: bool = False,
    limit: int = 300,
) -> list[SnapshotSummary]:
    enabled_market_codes = _enabled_market_codes(session, market_code)
    stmt = select(PerformanceSnapshot).order_by(
        PerformanceSnapshot.created_at.desc(),
        PerformanceSnapshot.id.desc(),
    )
    if enabled_market_codes:
        stmt = stmt.where(PerformanceSnapshot.market_code.in_(enabled_market_codes))
    if model_id:
        stmt = stmt.where(PerformanceSnapshot.model_id == model_id)
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == PerformanceSnapshot.model_id).where(LLMModel.is_selected.is_(True))

    snapshots = list(reversed(session.scalars(stmt.limit(limit)).all()))
    return [_serialize_snapshot(snapshot) for snapshot in snapshots]


def list_rankings(
    session: Session,
    selected_only: bool = True,
) -> list[ModelRanking]:
    portfolios = list_portfolios(session=session, selected_only=selected_only)
    models_by_id = {item.model_id: item for item in list_models(session=session, selected_only=selected_only)}
    histories = _snapshot_histories(session=session, selected_only=selected_only)
    trade_counts = _trade_counts(session=session, selected_only=selected_only)
    llm_costs = _llm_cost_totals(session=session, selected_only=selected_only)

    by_model: dict[str, list[PortfolioSummary]] = defaultdict(list)
    for portfolio in portfolios:
        by_model[portfolio.model_id].append(portfolio)

    rankings: list[ModelRanking] = []
    for model_id, model in models_by_id.items():
        model_portfolios = by_model.get(model_id, [])
        market_returns = {item.market_code: item.total_return_pct for item in model_portfolios}
        current_return_pct = _mean(list(market_returns.values()))

        period_returns = {"1d": [], "1w": [], "1m": []}
        composite_scores: list[float] = []
        max_drawdowns: list[float] = []
        win_rates: list[float] = []
        updated_at: datetime | None = None
        for history_key, history in histories.items():
            history_model_id, _history_market_code = history_key
            if history_model_id != model_id:
                continue
            latest = history[-1] if history else None
            if latest is not None:
                updated_at = max(updated_at, latest.created_at) if updated_at else latest.created_at
                composite_scores.append(latest.composite_score)
                max_drawdowns.append(latest.max_drawdown)
                win_rates.append(latest.win_rate)
            period_returns["1d"].append(_period_delta(history, timedelta(days=1)))
            period_returns["1w"].append(_period_delta(history, timedelta(days=7)))
            period_returns["1m"].append(_period_delta(history, timedelta(days=30)))

        rankings.append(
            ModelRanking(
                model_id=model_id,
                display_name=model.display_name,
                search_mode=model.search_mode,
                is_free_like=model.is_free_like,
                pricing_label=model.pricing_label,
                current_return_pct=current_return_pct,
                return_1d_pct=_mean([item for item in period_returns["1d"] if item is not None]),
                return_1w_pct=_mean([item for item in period_returns["1w"] if item is not None]),
                return_1m_pct=_mean([item for item in period_returns["1m"] if item is not None]),
                kr_return_pct=market_returns.get("KR"),
                us_return_pct=market_returns.get("US"),
                composite_score=_mean(composite_scores),
                max_drawdown=_mean(max_drawdowns),
                win_rate=_mean(win_rates),
                trade_count=trade_counts.get(model_id, 0),
                llm_cost_usd=llm_costs.get(model_id, 0.0),
                updated_at=updated_at or model.updated_at,
            )
        )

    rankings.sort(key=lambda item: (item.current_return_pct is None, -(item.current_return_pct or -10_000)))
    return rankings


def list_market_instruments(
    session: Session,
    market_code: str | None = None,
    active_only: bool = False,
) -> list[MarketInstrumentSummary]:
    stmt = select(MarketInstrument).order_by(MarketInstrument.market_code.asc(), MarketInstrument.is_active.desc(), MarketInstrument.ticker.asc())
    if market_code:
        stmt = stmt.where(MarketInstrument.market_code == market_code)
    if active_only:
        stmt = stmt.where(MarketInstrument.is_active.is_(True))
    instruments = session.scalars(stmt).all()
    return [
        MarketInstrumentSummary(
            market_code=item.market_code,
            ticker=item.ticker,
            instrument_name=item.instrument_name,
            is_active=item.is_active,
            first_seen_at=item.first_seen_at,
            last_seen_at=item.last_seen_at,
            delisted_at=item.delisted_at,
        )
        for item in instruments
    ]


def list_market_price_history(
    session: Session,
    market_code: str,
    selected_only: bool = True,
    top_n: int = 20,
    limit_per_ticker: int = 0,
) -> list[MarketPriceHistoryPoint]:
    top_tickers = tracked_tickers_for_market(
        session=session,
        market_code=market_code,
        selected_only=selected_only,
        top_n=top_n,
    )
    if not top_tickers:
        return []

    active_map = {
        item.ticker: item
        for item in session.scalars(
            select(MarketInstrument).where(
                MarketInstrument.market_code == market_code,
                MarketInstrument.ticker.in_(top_tickers),
            )
        ).all()
    }
    rows = session.scalars(
        select(HourlyMarketPrice)
        .where(
            HourlyMarketPrice.market_code == market_code,
            HourlyMarketPrice.ticker.in_(top_tickers),
        )
        .order_by(HourlyMarketPrice.as_of.asc(), HourlyMarketPrice.ticker.asc())
    ).all()
    grouped: dict[str, list[HourlyMarketPrice]] = defaultdict(list)
    for row in rows:
        grouped[row.ticker].append(row)

    payload: list[MarketPriceHistoryPoint] = []
    for ticker in top_tickers:
        instrument = active_map.get(ticker)
        history = grouped.get(ticker, [])
        if limit_per_ticker and limit_per_ticker > 0:
            history = history[-limit_per_ticker:]
        for row in history:
            payload.append(
                MarketPriceHistoryPoint(
                    market_code=row.market_code,
                    ticker=row.ticker,
                    instrument_name=row.instrument_name,
                    current_price=row.current_price,
                    return_1h_pct=row.return_1h_pct,
                    return_1d_pct=row.return_1d_pct,
                    intraday_volatility_pct=row.intraday_volatility_pct,
                    latest_volume=row.latest_volume,
                    avg_hourly_dollar_volume=row.avg_hourly_dollar_volume,
                    currency=row.currency,
                    as_of=row.as_of,
                    is_active=instrument.is_active if instrument else True,
                )
            )
    return payload


def list_news_batches(
    session: Session,
    market_code: str | None = None,
    limit: int = 5,
) -> list[NewsBatchSummary]:
    stmt = select(SharedNewsBatch).order_by(SharedNewsBatch.created_at.desc())
    if market_code:
        stmt = stmt.where(SharedNewsBatch.market_code == market_code)
    batches = session.scalars(stmt.limit(limit)).all()
    batch_keys = [batch.batch_key for batch in batches]
    items_by_batch: dict[str, list[NewsItemSummary]] = defaultdict(list)
    if batch_keys:
        items = session.scalars(
            select(SharedNewsItem).where(SharedNewsItem.batch_key.in_(batch_keys)).order_by(SharedNewsItem.published_at.desc())
        ).all()
        for item in items:
            items_by_batch[item.batch_key].append(
                NewsItemSummary(
                    title=item.title,
                    summary=item.summary,
                    source=item.source,
                    url=item.url,
                    published_at=item.published_at,
                    tickers=list(item.tickers_json or []),
                )
            )
    return [
        NewsBatchSummary(
            batch_key=batch.batch_key,
            market_code=batch.market_code,
            source=batch.source,
            summary=batch.summary,
            is_active=batch.is_active,
            created_at=batch.created_at,
            items=items_by_batch.get(batch.batch_key, []),
        )
        for batch in batches
    ]


def list_llm_logs(
    session: Session,
    model_id: str | None = None,
    market_code: str | None = None,
    limit: int = 20,
) -> list[LLMDecisionLogSummary]:
    stmt = select(LLMDecisionLog).order_by(LLMDecisionLog.created_at.desc(), LLMDecisionLog.id.desc())
    if model_id:
        stmt = stmt.where(LLMDecisionLog.model_id == model_id)
    if market_code:
        stmt = stmt.where(LLMDecisionLog.market_code == market_code)
    logs = session.scalars(stmt.limit(limit)).all()
    return [
        LLMDecisionLogSummary(
            id=log.id,
            model_id=log.model_id,
            request_model_id=log.request_model_id,
            market_code=log.market_code,
            status=log.status,
            prompt_text=log.prompt_text,
            input_payload=log.input_payload,
            raw_output_text=log.raw_output_text,
            parsed_output=log.parsed_output,
            prompt_tokens=_log_int(log, "prompt_tokens"),
            completion_tokens=_log_int(log, "completion_tokens"),
            total_tokens=_log_int(log, "total_tokens"),
            estimated_cost_usd=_log_float(log, "estimated_cost_usd"),
            error_message=log.error_message,
            created_at=log.created_at,
        )
        for log in logs
    ]


def list_run_requests(
    session: Session,
    model_id: str | None = None,
    market_code: str | None = None,
    status: str | None = None,
    selected_only: bool = False,
    limit: int = 50,
) -> list[RunRequestSummary]:
    stmt = select(RunRequest).order_by(RunRequest.requested_at.desc(), RunRequest.id.desc())
    if model_id:
        stmt = stmt.where(RunRequest.model_id == model_id)
    if market_code:
        stmt = stmt.where(RunRequest.market_code == market_code)
    if status:
        stmt = stmt.where(RunRequest.status == status)
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == RunRequest.model_id).where(LLMModel.is_selected.is_(True))
    runs = session.scalars(stmt.limit(limit)).all()
    return [
        RunRequestSummary(
            id=run.id,
            model_id=run.model_id,
            market_code=run.market_code,
            trigger_source=run.trigger_source,
            status=run.status,
            candidate_count=run.candidate_count,
            snapshot_as_of=run.snapshot_as_of,
            requested_at=run.requested_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            summary_message=run.summary_message,
            error_message=run.error_message,
        )
        for run in runs
    ]

def get_copy_trade(session: Session, model_id: str, market_code: str) -> CopyTradeResponse:
    portfolio = session.scalar(
        select(Portfolio).where(Portfolio.model_id == model_id, Portfolio.market_code == market_code)
    )
    if portfolio is None:
        raise ValueError(f"Portfolio not found for model={model_id} market={market_code}")

    positions = session.scalars(
        select(Position).where(Position.model_id == model_id, Position.market_code == market_code).order_by(Position.market_value.desc())
    ).all()
    trades = session.scalars(
        select(Trade).where(Trade.model_id == model_id, Trade.market_code == market_code).order_by(Trade.created_at.desc())
    ).all()
    latest_trade_by_ticker: dict[str, Trade] = {}
    for trade in trades:
        latest_trade_by_ticker.setdefault(trade.ticker, trade)

    total_equity = portfolio.total_equity or 0.0
    position_payload = []
    for position in positions:
        latest_trade = latest_trade_by_ticker.get(position.ticker)
        position_payload.append(
            CopyTradePosition(
                ticker=position.ticker,
                instrument_name=position.instrument_name,
                quantity=position.quantity,
                current_price=position.current_price,
                market_value=position.market_value,
                target_weight_pct=((position.market_value / total_equity) * 100) if total_equity else 0.0,
                avg_entry_price=position.avg_entry_price,
                last_action=latest_trade.side if latest_trade else None,
                last_action_at=latest_trade.created_at if latest_trade else None,
            )
        )

    recent_trades = [_serialize_trade(trade) for trade in trades[:10]]
    return CopyTradeResponse(
        model_id=model_id,
        market_code=market_code,
        as_of=portfolio.updated_at,
        total_equity=portfolio.total_equity,
        cash_weight_pct=((portfolio.available_cash / total_equity) * 100) if total_equity else 0.0,
        positions=position_payload,
        recent_trades=recent_trades,
    )


def get_runtime_settings_response(session: Session) -> RuntimeSettingsResponse:
    settings = get_runtime_settings(session)
    return RuntimeSettingsResponse(**settings)


def get_scheduler_status_response(session: Session) -> SchedulerStatusResponse:
    status = get_scheduler_status(session)
    return SchedulerStatusResponse(**status)


def _serialize_model(model: LLMModel) -> ModelSummary:
    metadata = model.metadata_json or {}
    return ModelSummary(
        model_id=model.model_id,
        display_name=model.display_name,
        request_model_id=metadata.get("request_model_id") or model.model_id,
        search_mode=metadata.get("search_mode", "off"),
        is_selected=model.is_selected,
        is_available=model.is_available,
        is_free_like=bool(metadata.get("is_free_like", _infer_is_free_like(model))),
        pricing_label=metadata.get("pricing_label") or _pricing_label(model),
        prompt_price_per_million=model.prompt_price_per_million,
        completion_price_per_million=model.completion_price_per_million,
        context_length=model.context_length,
        probe_detail=metadata.get("probe_detail"),
        updated_at=model.updated_at,
    )


def _serialize_trade(trade: Trade) -> TradeSummary:
    return TradeSummary(
        id=trade.id,
        model_id=trade.model_id,
        market_code=trade.market_code,
        ticker=trade.ticker,
        instrument_name=trade.instrument_name,
        side=trade.side,
        quantity=trade.quantity,
        price=trade.price,
        gross_amount=trade.gross_amount,
        commission_amount=trade.commission_amount,
        tax_amount=trade.tax_amount,
        regulatory_fee_amount=trade.regulatory_fee_amount,
        net_amount=trade.net_amount,
        realized_pnl=trade.realized_pnl,
        reason=trade.reason,
        created_at=trade.created_at,
    )


def _serialize_snapshot(snapshot: PerformanceSnapshot) -> SnapshotSummary:
    return SnapshotSummary(
        model_id=snapshot.model_id,
        market_code=snapshot.market_code,
        available_cash=snapshot.available_cash,
        invested_value=snapshot.invested_value,
        total_equity=snapshot.total_equity,
        total_return_pct=snapshot.total_return_pct,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=snapshot.unrealized_pnl,
        volatility=snapshot.volatility,
        sharpe_ratio=snapshot.sharpe_ratio,
        max_drawdown=snapshot.max_drawdown,
        win_rate=snapshot.win_rate,
        profit_factor=snapshot.profit_factor,
        turnover=snapshot.turnover,
        avg_holding_hours=snapshot.avg_holding_hours,
        composite_score=snapshot.composite_score,
        created_at=snapshot.created_at,
    )


def _top_market_history_tickers(session: Session, market_code: str, selected_only: bool, top_n: int) -> list[str]:
    return tracked_tickers_for_market(
        session=session,
        market_code=market_code,
        selected_only=selected_only,
        top_n=top_n,
    )


def _pricing_label(model: LLMModel) -> str:
    if model.prompt_price_per_million is None or model.completion_price_per_million is None:
        return "pricing unavailable"
    return (
        f"input=${model.prompt_price_per_million:.4f}/1M, "
        f"output=${model.completion_price_per_million:.4f}/1M"
    )


def _infer_is_free_like(model: LLMModel) -> bool:
    prompt = model.prompt_price_per_million or 0.0
    completion = model.completion_price_per_million or 0.0
    return model.model_id.endswith(":free") or (prompt == 0.0 and completion == 0.0)


def _market_map(session: Session) -> dict[str, str]:
    markets = session.scalars(select(MarketSetting).where(MarketSetting.enabled.is_(True))).all()
    return {market.market_code: market.market_name for market in markets}


def _enabled_market_codes(session: Session, market_code: str | None = None) -> list[str]:
    stmt = select(MarketSetting.market_code).where(MarketSetting.enabled.is_(True))
    if market_code:
        stmt = stmt.where(MarketSetting.market_code == market_code)
    return list(session.scalars(stmt).all())


def _position_counts(session: Session, enabled_market_codes: list[str]) -> dict[tuple[str, str], int]:
    stmt = select(Position.model_id, Position.market_code, func.count(Position.id))
    if enabled_market_codes:
        stmt = stmt.where(Position.market_code.in_(enabled_market_codes))
    rows: Iterable[tuple[str, str, int]] = session.execute(
        stmt.group_by(Position.model_id, Position.market_code)
    ).all()
    return {(model_id, market_code): count for model_id, market_code, count in rows}


def _latest_snapshot_times(session: Session, enabled_market_codes: list[str]) -> dict[tuple[str, str], datetime]:
    stmt = select(
        PerformanceSnapshot.model_id,
        PerformanceSnapshot.market_code,
        func.max(PerformanceSnapshot.created_at),
    )
    if enabled_market_codes:
        stmt = stmt.where(PerformanceSnapshot.market_code.in_(enabled_market_codes))
    rows = session.execute(
        stmt.group_by(PerformanceSnapshot.model_id, PerformanceSnapshot.market_code)
    ).all()
    return {(model_id, market_code): created_at for model_id, market_code, created_at in rows}


def _snapshot_histories(session: Session, selected_only: bool) -> dict[tuple[str, str], list[PerformanceSnapshot]]:
    stmt = select(PerformanceSnapshot).order_by(PerformanceSnapshot.created_at.asc(), PerformanceSnapshot.id.asc())
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == PerformanceSnapshot.model_id).where(LLMModel.is_selected.is_(True))
    rows = session.scalars(stmt).all()
    grouped: dict[tuple[str, str], list[PerformanceSnapshot]] = defaultdict(list)
    enabled = set(_enabled_market_codes(session))
    for row in rows:
        if row.market_code not in enabled:
            continue
        grouped[(row.model_id, row.market_code)].append(row)
    return grouped


def _trade_counts(session: Session, selected_only: bool) -> dict[str, int]:
    stmt = select(Trade.model_id, func.count(Trade.id)).group_by(Trade.model_id)
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == Trade.model_id).where(LLMModel.is_selected.is_(True))
    enabled = set(_enabled_market_codes(session))
    stmt = stmt.where(Trade.market_code.in_(enabled))
    rows = session.execute(stmt).all()
    return {model_id: count for model_id, count in rows}


def _llm_cost_totals(session: Session, selected_only: bool) -> dict[str, float]:
    stmt = select(LLMDecisionLog)
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == LLMDecisionLog.model_id).where(LLMModel.is_selected.is_(True))
    logs = session.scalars(stmt).all()
    totals: dict[str, float] = defaultdict(float)
    for log in logs:
        totals[log.model_id] += _log_float(log, "estimated_cost_usd") or 0.0
    return dict(totals)


def _period_delta(history: list[PerformanceSnapshot], delta: timedelta) -> float | None:
    if len(history) < 2:
        return None
    latest = history[-1]
    cutoff = latest.created_at - delta
    baseline = None
    for item in history:
        if item.created_at <= cutoff:
            baseline = item
        else:
            break
    if baseline is None:
        return None
    return latest.total_return_pct - baseline.total_return_pct


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _pct(current_value: float, basis_value: float) -> float:
    if not basis_value:
        return 0.0
    return ((current_value - basis_value) / basis_value) * 100


def _log_int(log: LLMDecisionLog, key: str) -> int | None:
    if not isinstance(log.parsed_output, dict):
        return None
    value = log.parsed_output.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _log_float(log: LLMDecisionLog, key: str) -> float | None:
    if not isinstance(log.parsed_output, dict):
        return None
    value = log.parsed_output.get(key)
    if value in (None, ""):
        return None
    return float(value)








