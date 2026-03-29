from __future__ import annotations

import typer
from sqlalchemy import select

from app.db.models import Portfolio, RunRequest
from app.db.session import SessionLocal
from app.market_data.provider import YahooMarketDataProvider
from app.market_data.screener import MarketScreener
from app.orchestration.trading_cycle import TradingCycleService
from app.services.bootstrap import create_schema
from app.services.run_requests import create_run_request, mark_run_request_finished, mark_run_request_started
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
        run = create_run_request(
            session,
            model_id=model_id,
            market_code=market_code,
            trigger_source="manual_cli",
            candidate_count=len(candidates),
            snapshot_as_of=snapshot.as_of,
            summary_message=f"Queued manual run for {model_id} / {market_code}.",
        )
        session.commit()
        run_id = run.id

    with SessionLocal() as session:
        run = session.get(RunRequest, run_id)
        if run is not None:
            mark_run_request_started(session, run, message=f"Running manual cycle for {model_id} / {market_code}.")
            session.commit()

    try:
        with SessionLocal() as session:
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
            portfolio = session.scalar(
                select(Portfolio).where(
                    Portfolio.model_id == model_id,
                    Portfolio.market_code == market_code,
                )
            )
            session.commit()

            equity_text = None
            cash_text = None
            currency = None
            if portfolio is not None:
                equity_text = portfolio.total_equity
                cash_text = portfolio.available_cash
                currency = portfolio.currency
            summary = f"Manual run finished for {model_id} / {market_code}: {len(messages)} actions executed."

        with SessionLocal() as session:
            run = session.get(RunRequest, run_id)
            if run is not None:
                mark_run_request_finished(session, run, status="success", message=summary)
                session.commit()
    except Exception as exc:
        with SessionLocal() as session:
            run = session.get(RunRequest, run_id)
            if run is not None:
                mark_run_request_finished(
                    session,
                    run,
                    status="error",
                    message=f"Manual run failed for {model_id} / {market_code}.",
                    error_message=str(exc),
                )
                session.commit()
        raise

    typer.echo(f"Model: {model_id}")
    typer.echo(f"Market: {market_code}")
    typer.echo(f"Summary: {decision.market_summary}")
    typer.echo(f"Risk: {decision.risk_note}")
    for message in messages:
        typer.echo(f"- {message}")
    if equity_text is not None and cash_text is not None and currency:
        typer.echo(f"Equity={equity_text:,.2f} {currency} | Cash={cash_text:,.2f}")


def run_llm() -> None:
    cli()


if __name__ == "__main__":
    cli()
