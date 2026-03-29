from __future__ import annotations

import typer

from app.db.session import SessionLocal
from app.services.bootstrap import create_schema
from app.services.shared_news import refresh_shared_news_for_market, run_due_news_refreshes

cli = typer.Typer(add_completion=False)


@cli.command()
def collect(market_code: str) -> None:
    create_schema()
    with SessionLocal() as session:
        message = refresh_shared_news_for_market(session, market_code.upper())
        session.commit()
    typer.echo(message)


@cli.command()
def collect_due() -> None:
    create_schema()
    with SessionLocal() as session:
        messages = run_due_news_refreshes(session)
        session.commit()
    if not messages:
        typer.echo("No shared news refresh was due.")
        return
    for message in messages:
        typer.echo(message)


if __name__ == "__main__":
    cli()
