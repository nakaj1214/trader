"""Typer CLI entry point for the Trader pipeline.

Commands:
    run       Full pipeline (screen -> predict -> track -> enrich -> notify -> export)
    screen    Run screening only
    predict   Run prediction only
    export    Run export only
    version   Show version info
"""

from __future__ import annotations

from typing import Annotated

import structlog
import typer

logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="trader",
    help="Automated trading analysis and signal system.",
    no_args_is_help=True,
)


@app.command()
def run(
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
    market: Annotated[str, typer.Option("--market", "-m", help="Market to analyze.")] = "us",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Run without side effects.")] = False,
) -> None:
    """Run the full analysis pipeline."""
    from src.core.config import load_config
    from src.core.meta import build_run_meta, save_config_snapshot

    cfg = load_config(path=config)
    meta = build_run_meta()
    save_config_snapshot(cfg.model_dump(), meta)

    logger.info(
        "pipeline_start",
        market=market,
        dry_run=dry_run,
        git_hash=meta.git_hash,
    )

    # TODO: Phase B - wire up pipeline stages
    typer.echo(f"Pipeline started (market={market}, dry_run={dry_run})")
    typer.echo("Pipeline stages will be connected in Phase B.")


@app.command()
def screen(
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
    market: Annotated[str, typer.Option("--market", "-m", help="Market to screen.")] = "us",
) -> None:
    """Run screening only."""
    from src.core.config import load_config

    cfg = load_config(path=config)
    logger.info("screen_start", market=market)

    # TODO: Phase B - integrate screening module
    typer.echo(f"Screening started (market={market})")


@app.command()
def predict(
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
) -> None:
    """Run prediction only."""
    from src.core.config import load_config

    cfg = load_config(path=config)
    logger.info("predict_start")

    # TODO: Phase B - integrate prediction module
    typer.echo("Prediction started.")


@app.command()
def export(
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
) -> None:
    """Run export only."""
    from src.core.config import load_config

    cfg = load_config(path=config)
    logger.info("export_start")

    # TODO: Phase B - integrate export module
    typer.echo("Export started.")


@app.command()
def version() -> None:
    """Show version information."""
    from src.core.meta import build_run_meta

    meta = build_run_meta()
    typer.echo(f"trader v2.0.0")
    typer.echo(f"Python {meta.python_version}")
    if meta.git_hash:
        typer.echo(f"Git: {meta.git_hash}")


if __name__ == "__main__":
    app()
