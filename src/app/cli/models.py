from __future__ import annotations

import typer

from app.db.session import SessionLocal
from app.llm.openrouter import OpenRouterClient
from app.services.bootstrap import create_schema, probe_and_add_all_free_models, probe_and_add_free_models, probe_and_select_free_models

cli = typer.Typer(add_completion=False)


@cli.command()
def list_models(
    sort_by: str = "price-low",
    free_mode: str = "include",
    limit: int = 30,
) -> None:
    client = OpenRouterClient()
    models = client.catalog(sort_by=sort_by, free_mode=free_mode)[:limit]
    typer.echo(
        "Source links: https://openrouter.ai/models?order=pricing-low-to-high | "
        "https://openrouter.ai/models?order=most-popular"
    )
    if sort_by == "popular":
        typer.echo(
            "Note: the official /models API does not document popularity sorting, "
            "so this output preserves API order."
        )
    for idx, model in enumerate(models, start=1):
        free_label = "FREE" if model.is_free_like else "PAID"
        typer.echo(
            f"{idx}. {model.model_id} | {free_label} | {model.pricing_label} | ctx={model.context_length or 0}"
        )


@cli.command()
def probe_free_models(
    target_count: int = 10,
    candidate_limit: int = 30,
    sort_by: str = "popular",
) -> None:
    create_schema()
    with SessionLocal() as session:
        results = probe_and_select_free_models(
            session,
            target_count=target_count,
            candidate_limit=candidate_limit,
            sort_by=sort_by,
        )

    successes = [result for result in results if result.success]
    failures = [result for result in results if not result.success]
    typer.echo(f"Successful free models: {len(successes)}")
    for result in successes[:target_count]:
        typer.echo(f"- SELECTED {result.model_id} | {result.detail}")
    if failures:
        typer.echo("Failed free models:")
        for result in failures:
            typer.echo(f"- {result.model_id} | {result.detail}")


@cli.command()
def add_free_models(
    additional_count: int = 10,
    candidate_limit: int = 40,
    sort_by: str = "popular",
) -> None:
    create_schema()
    with SessionLocal() as session:
        results = probe_and_add_free_models(
            session,
            additional_count=additional_count,
            candidate_limit=candidate_limit,
            sort_by=sort_by,
        )

    successes = [result for result in results if result.success]
    failures = [result for result in results if not result.success]
    typer.echo(f"Additional free models added: {len(successes)}")
    for result in successes[:additional_count]:
        typer.echo(f"- ADDED {result.model_id} | {result.detail}")
    if failures:
        typer.echo("Failed free models:")
        for result in failures:
            typer.echo(f"- {result.model_id} | {result.detail}")


@cli.command()
def sync_free_models(
    candidate_limit: int = 250,
    sort_by: str = "popular",
) -> None:
    create_schema()
    with SessionLocal() as session:
        results = probe_and_add_all_free_models(
            session,
            candidate_limit=candidate_limit,
            sort_by=sort_by,
        )

    successes = [result for result in results if result.success]
    failures = [result for result in results if not result.success]
    typer.echo(f"Free/experiment models added: {len(successes)}")
    for result in successes:
        typer.echo(f"- ADDED {result.model_id} | {result.detail}")
    if failures:
        typer.echo("Failed models:")
        for result in failures:
            typer.echo(f"- {result.model_id} | {result.detail}")


def run_models() -> None:
    cli()


if __name__ == "__main__":
    cli()
