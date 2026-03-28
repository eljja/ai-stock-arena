from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ModelSummary,
    OverviewResponse,
    PortfolioSummary,
    PositionSummary,
    SnapshotSummary,
    TradeSummary,
)
from app.db.models import LLMModel, MarketSetting, PerformanceSnapshot, Portfolio, Position, Trade


def get_overview(
    session: Session,
    market_code: str | None = None,
    selected_only: bool = False,
) -> OverviewResponse:
    models = list_models(session=session, selected_only=selected_only)
    portfolios = list_portfolios(session=session, market_code=market_code, selected_only=selected_only)

    latest_trade_stmt = select(func.max(Trade.created_at))
    latest_snapshot_stmt = select(func.max(PerformanceSnapshot.created_at))
    if market_code:
        latest_trade_stmt = latest_trade_stmt.where(Trade.market_code == market_code)
        latest_snapshot_stmt = latest_snapshot_stmt.where(PerformanceSnapshot.market_code == market_code)
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
    markets = _market_map(session)
    position_counts = _position_counts(session)
    snapshot_times = _latest_snapshot_times(session)

    stmt = select(Portfolio).order_by(Portfolio.market_code.asc(), Portfolio.total_equity.desc())
    if market_code:
        stmt = stmt.where(Portfolio.market_code == market_code)
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
    stmt = select(Position).order_by(
        Position.market_code.asc(),
        Position.model_id.asc(),
        Position.market_value.desc(),
    )
    if market_code:
        stmt = stmt.where(Position.market_code == market_code)
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
    stmt = select(Trade).order_by(Trade.created_at.desc(), Trade.id.desc()).limit(limit)
    if market_code:
        stmt = stmt.where(Trade.market_code == market_code)
    if model_id:
        stmt = stmt.where(Trade.model_id == model_id)
    if selected_only:
        stmt = stmt.join(LLMModel, LLMModel.model_id == Trade.model_id).where(LLMModel.is_selected.is_(True))

    trades = session.scalars(stmt).all()
    return [
        TradeSummary(
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
        for trade in trades
    ]


def list_snapshots(
    session: Session,
    market_code: str | None = None,
    model_id: str | None = None,
    selected_only: bool = False,
    limit: int = 300,
) -> list[SnapshotSummary]:
    stmt = select(PerformanceSnapshot).order_by(
        PerformanceSnapshot.created_at.desc(),
        PerformanceSnapshot.id.desc(),
    ).limit(limit)
    if market_code:
        stmt = stmt.where(PerformanceSnapshot.market_code == market_code)
    if model_id:
        stmt = stmt.where(PerformanceSnapshot.model_id == model_id)
    if selected_only:
        stmt = stmt.join(
            LLMModel,
            LLMModel.model_id == PerformanceSnapshot.model_id,
        ).where(LLMModel.is_selected.is_(True))

    snapshots = list(reversed(session.scalars(stmt).all()))
    return [
        SnapshotSummary(
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
        for snapshot in snapshots
    ]


def _serialize_model(model: LLMModel) -> ModelSummary:
    metadata = model.metadata_json or {}
    return ModelSummary(
        model_id=model.model_id,
        display_name=model.display_name,
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
    markets = session.scalars(select(MarketSetting)).all()
    return {market.market_code: market.market_name for market in markets}


def _position_counts(session: Session) -> dict[tuple[str, str], int]:
    rows: Iterable[tuple[str, str, int]] = session.execute(
        select(Position.model_id, Position.market_code, func.count(Position.id)).group_by(
            Position.model_id,
            Position.market_code,
        )
    ).all()
    return {(model_id, market_code): count for model_id, market_code, count in rows}


def _latest_snapshot_times(session: Session) -> dict[tuple[str, str], datetime]:
    rows = session.execute(
        select(
            PerformanceSnapshot.model_id,
            PerformanceSnapshot.market_code,
            func.max(PerformanceSnapshot.created_at),
        ).group_by(PerformanceSnapshot.model_id, PerformanceSnapshot.market_code)
    ).all()
    return {(model_id, market_code): created_at for model_id, market_code, created_at in rows}


def _pct(current_value: float, basis_value: float) -> float:
    if not basis_value:
        return 0.0
    return ((current_value - basis_value) / basis_value) * 100
