from __future__ import annotations

import typer

from app.db.session import SessionLocal
from app.services.bootstrap import bootstrap_database, create_schema


cli = typer.Typer(add_completion=False)


def run(skip_openrouter_sync: bool = False) -> None:
    create_schema()
    with SessionLocal() as session:
        summary = bootstrap_database(session, sync_openrouter_models=not skip_openrouter_sync)

    typer.echo("AI Stock Arena bootstrap complete")
    typer.echo(f"- OpenRouter models synced: {summary.synced_models}")
    typer.echo(f"- Selected models: {summary.selected_models}")
    typer.echo(f"- Market settings upserted: {summary.market_settings_upserted}")
    typer.echo(f"- Portfolios created: {summary.portfolios_created}")
    typer.echo(f"- Prompt placeholders created: {summary.prompt_placeholders_created}")


@cli.command()
def main(skip_openrouter_sync: bool = typer.Option(False, help="Skip pulling model list from OpenRouter.")) -> None:
    """Create schema and seed market/model bootstrap data."""
    run(skip_openrouter_sync=skip_openrouter_sync)


if __name__ == "__main__":
    cli()
