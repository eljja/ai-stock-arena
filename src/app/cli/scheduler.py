from __future__ import annotations

import typer

from app.db.session import SessionLocal
from app.services.admin import get_scheduler_status
from app.services.runtime_scheduler import RuntimeSchedulerService

cli = typer.Typer(add_completion=False)


@cli.command()
def status() -> None:
    with SessionLocal() as session:
        scheduler_status = get_scheduler_status(session)
    typer.echo(
        f"Cadence: every {scheduler_status['cadence_minutes']} minutes | "
        f"Weekdays: {scheduler_status['active_weekdays']}"
    )
    for market in scheduler_status["markets"]:
        typer.echo(
            f"{market['market_code']} | enabled={market['enabled']} | due={market['is_due']} | "
            f"window={market['in_active_window']} | last={market['last_completed_at']} | next={market['next_run_at']}"
        )


@cli.command()
def run_once(market_code: str | None = None) -> None:
    service = RuntimeSchedulerService()
    if market_code:
        message = service.run_market_cycle(market_code.upper())
        typer.echo(message)
        return

    messages = service.run_pending_once()
    if not messages:
        typer.echo("No market runs were due.")
        return
    for message in messages:
        typer.echo(message)


@cli.command()
def serve(poll_seconds: int = 30) -> None:
    RuntimeSchedulerService().run_forever(poll_seconds=poll_seconds)


def run_scheduler_cli() -> None:
    cli()


if __name__ == "__main__":
    cli()
