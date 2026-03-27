from __future__ import annotations

import typer

from app.llm.openrouter import OpenRouterClient

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


def run_models() -> None:
    cli()


if __name__ == "__main__":
    cli()
