from __future__ import annotations

from collections import defaultdict

import typer
from sqlalchemy import select

from app.db.models import LLMModel, PerformanceSnapshot, Portfolio, Position
from app.db.session import SessionLocal
from app.market_data.provider import YahooMarketDataProvider
from app.market_data.screener import MarketScreener
from app.services.bootstrap import create_schema
from app.services.market_history import backfill_tracked_market_history, record_market_snapshot
from app.services.setup_helpers import ensure_model_market_state
from app.trading.engine import TradingEngine

cli = typer.Typer(add_completion=False)


@cli.command()
def screen(market_code: str, limit: int = 10) -> None:
    create_schema()
    provider = YahooMarketDataProvider()
    screener = MarketScreener()
    snapshot = provider.fetch_market_snapshot(market_code.upper())
    with SessionLocal() as session:
        inserted = record_market_snapshot(session, snapshot)
        session.commit()
    candidates = screener.screen(snapshot)[:limit]

    typer.echo(f"AI Stock Arena screen for {snapshot.market_code} at {snapshot.as_of.isoformat()} | stored_rows={inserted}")
    for idx, candidate in enumerate(candidates, start=1):
        price = candidate.snapshot
        typer.echo(
            f"{idx}. {candidate.ticker} | {candidate.instrument_name} | score={candidate.score:.2f} | "
            f"price={price.current_price:.2f} | 1h={price.return_1h_pct:.2f}% | 1d={price.return_1d_pct:.2f}%"
        )


@cli.command()
def collect_history(market_code: str) -> None:
    create_schema()
    provider = YahooMarketDataProvider()
    snapshot = provider.fetch_market_snapshot(market_code.upper())
    with SessionLocal() as session:
        inserted = record_market_snapshot(session, snapshot)
        session.commit()
    typer.echo(
        f"Stored {inserted} hourly market price rows for {snapshot.market_code} at {snapshot.as_of.isoformat()}"
    )


@cli.command()
def backfill_tracked_history(
    market_code: str,
    top_n: int = 20,
    period: str = "730d",
    selected_only: bool = True,
) -> None:
    create_schema()
    provider = YahooMarketDataProvider()
    with SessionLocal() as session:
        result = backfill_tracked_market_history(
            session=session,
            provider=provider,
            market_code=market_code.upper(),
            selected_only=selected_only,
            top_n=top_n,
            period=period,
        )
        session.commit()
    typer.echo(
        f"Backfilled {result['market_code']} | tracked={len(result['tracked_tickers'])} | "
        f"stored={result['stored_tickers']} | inserted_rows={result['inserted_rows']} | "
        f"history_points={result['history_points']}"
    )
    if result["tracked_tickers"]:
        typer.echo("Tracked tickers: " + ", ".join(result["tracked_tickers"]))
    if result["missing_tickers"]:
        typer.echo("Missing tickers: " + ", ".join(result["missing_tickers"]))


@cli.command()
def backfill_mdd(
    market_code: str | None = None,
    model_id: str | None = None,
    selected_only: bool = True,
) -> None:
    create_schema()
    with SessionLocal() as session:
        stmt = select(PerformanceSnapshot).order_by(
            PerformanceSnapshot.model_id.asc(),
            PerformanceSnapshot.market_code.asc(),
            PerformanceSnapshot.created_at.asc(),
            PerformanceSnapshot.id.asc(),
        )
        if market_code:
            stmt = stmt.where(PerformanceSnapshot.market_code == market_code.upper())
        if model_id:
            stmt = stmt.where(PerformanceSnapshot.model_id == model_id)
        elif selected_only:
            stmt = stmt.join(LLMModel, LLMModel.model_id == PerformanceSnapshot.model_id).where(LLMModel.is_selected.is_(True))

        snapshots = session.scalars(stmt).all()
        grouped: dict[tuple[str, str], list[PerformanceSnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            grouped[(snapshot.model_id, snapshot.market_code)].append(snapshot)

        updated = 0
        for _key, history in grouped.items():
            peak_equity = 0.0
            worst_drawdown = 0.0
            for snapshot in history:
                peak_equity = max(peak_equity, snapshot.total_equity)
                drawdown = ((snapshot.total_equity - peak_equity) / peak_equity) * 100 if peak_equity else 0.0
                worst_drawdown = min(worst_drawdown, drawdown)
                if snapshot.max_drawdown != worst_drawdown:
                    snapshot.max_drawdown = worst_drawdown
                    updated += 1

        session.commit()

    typer.echo(f"Backfilled MDD for {len(grouped)} model/market histories | updated_snapshots={updated}")


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
