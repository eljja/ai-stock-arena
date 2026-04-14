from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MarketSetting, PerformanceSnapshot, Portfolio, Position, Trade
from app.market_data.models import PriceSnapshot
from app.trading.costs import calculate_buy_costs, calculate_sell_costs


@dataclass(slots=True)
class TradeResult:
    success: bool
    message: str
    realized_pnl: float = 0.0


class TradingEngine:
    def execute_buy(
        self,
        session: Session,
        model_id: str,
        market_code: str,
        snapshot: PriceSnapshot,
        quantity: float,
        reason: str,
        prompt_snapshot: str | None = None,
        decision_payload: dict | None = None,
    ) -> TradeResult:
        market = self._get_market_setting(session, market_code)
        portfolio = self._get_portfolio(session, model_id, market_code)
        costs = calculate_buy_costs(market, quantity, snapshot.current_price)

        required_cash = abs(costs.net_cash_change)
        if portfolio.available_cash < required_cash:
            return TradeResult(False, f"Insufficient cash for {snapshot.ticker}")

        position = session.scalar(
            select(Position).where(
                Position.model_id == model_id,
                Position.market_code == market_code,
                Position.ticker == snapshot.ticker,
            )
        )
        if position is None:
            position = Position(
                model_id=model_id,
                market_code=market_code,
                ticker=snapshot.ticker,
                instrument_name=snapshot.instrument_name,
                quantity=0.0,
                avg_entry_price=0.0,
                current_price=snapshot.current_price,
                market_value=0.0,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
            )
            session.add(position)

        total_quantity = position.quantity + quantity
        total_cost_basis = (position.avg_entry_price * position.quantity) + (snapshot.current_price * quantity)
        position.quantity = total_quantity
        position.avg_entry_price = total_cost_basis / total_quantity
        position.current_price = snapshot.current_price
        position.market_value = position.quantity * snapshot.current_price
        position.unrealized_pnl = position.market_value - (position.quantity * position.avg_entry_price)
        position.unrealized_pnl_pct = _pct(position.current_price, position.avg_entry_price)
        position.updated_at = datetime.now(UTC)

        portfolio.available_cash += costs.net_cash_change
        self.refresh_portfolio_totals(session, model_id, market_code, {snapshot.ticker: snapshot.current_price})

        session.add(
            Trade(
                model_id=model_id,
                market_code=market_code,
                ticker=snapshot.ticker,
                instrument_name=snapshot.instrument_name,
                side="BUY",
                quantity=quantity,
                price=snapshot.current_price,
                gross_amount=costs.gross_amount,
                commission_amount=costs.commission_amount,
                tax_amount=costs.tax_amount,
                regulatory_fee_amount=costs.regulatory_fee_amount,
                net_amount=costs.net_cash_change,
                realized_pnl=0.0,
                reason=reason,
                prompt_snapshot=prompt_snapshot,
                decision_payload=decision_payload,
            )
        )
        session.flush()
        return TradeResult(True, f"Bought {quantity} {snapshot.ticker}")

    def execute_sell(
        self,
        session: Session,
        model_id: str,
        market_code: str,
        snapshot: PriceSnapshot,
        quantity: float,
        reason: str,
        prompt_snapshot: str | None = None,
        decision_payload: dict | None = None,
    ) -> TradeResult:
        market = self._get_market_setting(session, market_code)
        portfolio = self._get_portfolio(session, model_id, market_code)
        position = session.scalar(
            select(Position).where(
                Position.model_id == model_id,
                Position.market_code == market_code,
                Position.ticker == snapshot.ticker,
            )
        )
        if position is None or position.quantity < quantity:
            return TradeResult(False, f"Insufficient position for {snapshot.ticker}")

        costs = calculate_sell_costs(market, quantity, snapshot.current_price)
        realized_pnl = ((snapshot.current_price - position.avg_entry_price) * quantity) - costs.commission_amount - costs.tax_amount - costs.regulatory_fee_amount

        portfolio.available_cash += costs.net_cash_change
        portfolio.total_realized_pnl += realized_pnl

        position.quantity -= quantity
        position.current_price = snapshot.current_price
        if position.quantity <= 0:
            session.delete(position)
        else:
            position.market_value = position.quantity * snapshot.current_price
            position.unrealized_pnl = position.market_value - (position.quantity * position.avg_entry_price)
            position.unrealized_pnl_pct = _pct(position.current_price, position.avg_entry_price)
            position.updated_at = datetime.now(UTC)

        self.refresh_portfolio_totals(session, model_id, market_code, {snapshot.ticker: snapshot.current_price})

        session.add(
            Trade(
                model_id=model_id,
                market_code=market_code,
                ticker=snapshot.ticker,
                instrument_name=snapshot.instrument_name,
                side="SELL",
                quantity=quantity,
                price=snapshot.current_price,
                gross_amount=costs.gross_amount,
                commission_amount=costs.commission_amount,
                tax_amount=costs.tax_amount,
                regulatory_fee_amount=costs.regulatory_fee_amount,
                net_amount=costs.net_cash_change,
                realized_pnl=realized_pnl,
                reason=reason,
                prompt_snapshot=prompt_snapshot,
                decision_payload=decision_payload,
            )
        )
        session.flush()
        return TradeResult(True, f"Sold {quantity} {snapshot.ticker}", realized_pnl=realized_pnl)

    def refresh_portfolio_totals(
        self,
        session: Session,
        model_id: str,
        market_code: str,
        latest_prices: dict[str, float] | None = None,
    ) -> None:
        portfolio = self._get_portfolio(session, model_id, market_code)
        positions = session.scalars(
            select(Position).where(
                Position.model_id == model_id,
                Position.market_code == market_code,
            )
        ).all()

        invested_value = 0.0
        total_unrealized_pnl = 0.0
        latest_prices = latest_prices or {}
        for position in positions:
            latest_price = latest_prices.get(position.ticker, position.current_price or position.avg_entry_price)
            position.current_price = latest_price
            position.market_value = position.quantity * latest_price
            position.unrealized_pnl = position.market_value - (position.quantity * position.avg_entry_price)
            position.unrealized_pnl_pct = _pct(latest_price, position.avg_entry_price)
            position.updated_at = datetime.now(UTC)
            invested_value += position.market_value
            total_unrealized_pnl += position.unrealized_pnl

        portfolio.invested_value = invested_value
        portfolio.total_unrealized_pnl = total_unrealized_pnl
        portfolio.total_equity = portfolio.available_cash + invested_value
        portfolio.updated_at = datetime.now(UTC)

    def record_snapshot(self, session: Session, model_id: str, market_code: str) -> PerformanceSnapshot:
        portfolio = self._get_portfolio(session, model_id, market_code)
        prior_snapshots = session.scalars(
            select(PerformanceSnapshot).where(
                PerformanceSnapshot.model_id == model_id,
                PerformanceSnapshot.market_code == market_code,
            ).order_by(PerformanceSnapshot.created_at.asc(), PerformanceSnapshot.id.asc())
        ).all()
        trades = session.scalars(
            select(Trade).where(
                Trade.model_id == model_id,
                Trade.market_code == market_code,
            )
        ).all()
        sell_trades = [trade for trade in trades if trade.side == "SELL"]
        wins = [trade for trade in sell_trades if trade.realized_pnl > 0]
        losses = [trade for trade in sell_trades if trade.realized_pnl < 0]
        gross_profit = sum(trade.realized_pnl for trade in wins)
        gross_loss = abs(sum(trade.realized_pnl for trade in losses))
        profit_factor = gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit else 0.0)
        win_rate = (len(wins) / len(sell_trades)) * 100 if sell_trades else 0.0
        turnover = sum(abs(trade.gross_amount) for trade in trades) / portfolio.initial_cash if portfolio.initial_cash else 0.0
        total_return_pct = ((portfolio.total_equity - portfolio.initial_cash) / portfolio.initial_cash) * 100 if portfolio.initial_cash else 0.0
        peak_equity = max([portfolio.initial_cash, portfolio.total_equity, *[item.total_equity for item in prior_snapshots]])
        current_drawdown = ((portfolio.total_equity - peak_equity) / peak_equity) * 100 if peak_equity else 0.0
        previous_max_drawdown = min([0.0, *[item.max_drawdown for item in prior_snapshots]])
        max_drawdown = min(previous_max_drawdown, current_drawdown)

        snapshot = PerformanceSnapshot(
            model_id=model_id,
            market_code=market_code,
            available_cash=portfolio.available_cash,
            invested_value=portfolio.invested_value,
            total_equity=portfolio.total_equity,
            total_return_pct=total_return_pct,
            daily_return_pct=0.0,
            realized_pnl=portfolio.total_realized_pnl,
            unrealized_pnl=portfolio.total_unrealized_pnl,
            volatility=0.0,
            sharpe_ratio=0.0,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            turnover=turnover,
            avg_holding_hours=0.0,
            composite_score=0.0,
        )
        session.add(snapshot)
        session.flush()
        return snapshot

    def _get_market_setting(self, session: Session, market_code: str) -> MarketSetting:
        market = session.scalar(select(MarketSetting).where(MarketSetting.market_code == market_code))
        if market is None:
            raise ValueError(f"Missing market setting for {market_code}")
        return market

    def _get_portfolio(self, session: Session, model_id: str, market_code: str) -> Portfolio:
        portfolio = session.scalar(
            select(Portfolio).where(
                Portfolio.model_id == model_id,
                Portfolio.market_code == market_code,
            )
        )
        if portfolio is None:
            raise ValueError(f"Missing portfolio for model={model_id}, market={market_code}")
        return portfolio


def _pct(current_price: float, basis_price: float) -> float:
    if not basis_price:
        return 0.0
    return ((current_price - basis_price) / basis_price) * 100
