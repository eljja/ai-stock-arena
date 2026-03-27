from __future__ import annotations

import typer
from sqlalchemy import select

from app.db.models import Portfolio, Position
from app.db.session import SessionLocal
from app.market_data.provider import YahooMarketDataProvider
from app.market_data.screener import MarketScreener
from app.services.bootstrap import create_schema
from app.services.setup_helpers import ensure_model_market_state
from app.trading.engine import TradingEngine

cli = typer.Typer(add_completion=False)


@cli.command()
def screen(market_code: str, limit: int = 10) -> None:
    create_schema()
    provider = YahooMarketDataProvider()
    screener = MarketScreener()
    snapshot = provider.fetch_market_snapshot(market_code.upper())
    candidates = screener.screen(snapshot)[:limit]

    typer.echo(f"AI Stock Arena screen for {snapshot.market_code} at {snapshot.as_of.isoformat()}")
    for idx, candidate in enumerate(candidates, start=1):
        price = candidate.snapshot
        typer.echo(
            f"{idx}. {candidate.ticker} | {candidate.instrument_name} | score={candidate.score:.2f} | "
            f"price={price.current_price:.2f} | 1h={price.return_1h_pct:.2f}% | 1d={price.return_1d_pct:.2f}%"
        )


@cli.command()
def demo_cycle(
    market_code: str,
    model_id: str = "demo/manual-strategy",
    picks: int = 3,
    budget_ratio: float = 0.9,
) -> None:
    create_schema()
    provider = YahooMarketDataProvider()
    screener = MarketScreener()
    engine = TradingEngine()

    market_code = market_code.upper()
    snapshot = provider.fetch_market_snapshot(market_code)
    candidates = screener.screen(snapshot)[: max(picks, 1)]
    if not candidates:
        raise typer.Exit(code=1)

    with SessionLocal() as session:
        ensure_model_market_state(session, model_id=model_id, market_code=market_code, display_name="Manual Demo Strategy")
        session.commit()

        portfolio = session.scalar(
            select(Portfolio).where(
                Portfolio.model_id == model_id,
                Portfolio.market_code == market_code,
            )
        )
        current_positions = session.scalars(
            select(Position).where(
                Position.model_id == model_id,
                Position.market_code == market_code,
            )
        ).all()
        held_tickers = {position.ticker for position in current_positions}
        target_tickers = {candidate.ticker for candidate in candidates}

        for position in current_positions:
            if position.ticker not in target_tickers:
                position_snapshot = snapshot.prices.get(position.ticker)
                if position_snapshot is None:
                    continue
                result = engine.execute_sell(
                    session,
                    model_id=model_id,
                    market_code=market_code,
                    snapshot=position_snapshot,
                    quantity=position.quantity,
                    reason="Dropped from top screened set in demo cycle.",
                    prompt_snapshot="MANUAL_DEMO",
                    decision_payload={"source": "demo_cycle", "action": "sell"},
                )
                typer.echo(result.message)

        session.flush()
        portfolio = session.scalar(
            select(Portfolio).where(
                Portfolio.model_id == model_id,
                Portfolio.market_code == market_code,
            )
        )
        if portfolio is None:
            raise typer.Exit(code=1)

        buy_candidates = [candidate for candidate in candidates if candidate.ticker not in held_tickers]
        if buy_candidates:
            capital_per_pick = (portfolio.available_cash * budget_ratio) / max(len(buy_candidates), 1)
            for candidate in buy_candidates:
                snapshot_price = candidate.snapshot
                quantity = int(capital_per_pick // snapshot_price.current_price)
                if quantity <= 0:
                    continue
                result = engine.execute_buy(
                    session,
                    model_id=model_id,
                    market_code=market_code,
                    snapshot=snapshot_price,
                    quantity=quantity,
                    reason="Entered top screened set in demo cycle.",
                    prompt_snapshot="MANUAL_DEMO",
                    decision_payload={"source": "demo_cycle", "action": "buy", "score": candidate.score},
                )
                typer.echo(result.message)

        latest_prices = {ticker: item.current_price for ticker, item in snapshot.prices.items()}
        engine.refresh_portfolio_totals(session, model_id=model_id, market_code=market_code, latest_prices=latest_prices)
        perf = engine.record_snapshot(session, model_id=model_id, market_code=market_code)
        session.commit()

        typer.echo(
            f"Portfolio equity={perf.total_equity:,.2f} {portfolio.currency} | cash={perf.available_cash:,.2f} | "
            f"return={perf.total_return_pct:.2f}%"
        )


def run_screen() -> None:
    cli()


if __name__ == "__main__":
    cli()
