from __future__ import annotations

import typer
from sqlalchemy import select

from app.db.models import Portfolio
from app.db.session import SessionLocal
from app.market_data.provider import YahooMarketDataProvider
from app.market_data.screener import MarketScreener
from app.orchestration.trading_cycle import TradingCycleService
from app.services.bootstrap import create_schema
from app.services.setup_helpers import ensure_model_market_state

cli = typer.Typer(add_completion=False)


@cli.command()
def generate_prompt(market_code: str, model_id: str) -> None:
    create_schema()
    market_code = market_code.upper()
    service = TradingCycleService()
    with SessionLocal() as session:
        ensure_model_market_state(
            session,
            model_id=model_id,
            market_code=market_code,
            display_name=model_id,
        )
        prompt = service.ensure_active_prompt(session, model_id=model_id, market_code=market_code)
        session.commit()
        typer.echo(f"Stored active prompt for {model_id} / {market_code}")
        typer.echo(prompt.prompt_content)


@cli.command()
def run_cycle(market_code: str, model_id: str, candidate_limit: int = 15) -> None:
    create_schema()
    market_code = market_code.upper()
    provider = YahooMarketDataProvider()
    screener = MarketScreener()
    service = TradingCycleService()

    snapshot = provider.fetch_market_snapshot(market_code)
    candidates = screener.screen(snapshot)[:candidate_limit]
    if not candidates:
        raise typer.Exit(code=1)

    with SessionLocal() as session:
        ensure_model_market_state(
            session,
            model_id=model_id,
            market_code=market_code,
            display_name=model_id,
        )
        session.commit()

        decision, prompt_text = service.request_decision(
            session,
            model_id=model_id,
            market_code=market_code,
            snapshot=snapshot,
            candidates=candidates,
        )
        messages = service.execute_decision(
            session,
            model_id=model_id,
            market_code=market_code,
            decision=decision,
            snapshot=snapshot,
            prompt_text=prompt_text,
        )
        session.commit()

        portfolio = session.scalar(
            select(Portfolio).where(
                Portfolio.model_id == model_id,
                Portfolio.market_code == market_code,
            )
        )
        typer.echo(f"Model: {model_id}")
        typer.echo(f"Market: {market_code}")
        typer.echo(f"Summary: {decision.market_summary}")
        typer.echo(f"Risk: {decision.risk_note}")
        for message in messages:
            typer.echo(f"- {message}")
        if portfolio is not None:
            typer.echo(
                f"Equity={portfolio.total_equity:,.2f} {portfolio.currency} | "
                f"Cash={portfolio.available_cash:,.2f}"
            )


def run_llm() -> None:
    cli()


if __name__ == "__main__":
    cli()
