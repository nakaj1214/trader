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
    market: Annotated[str, typer.Option("--market", "-m", help="Market to analyze (us, jp, all).")] = "all",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Run without side effects.")] = False,
) -> None:
    """Run the full analysis pipeline."""
    from src.core.config import load_config
    from src.core.meta import build_run_meta, save_config_snapshot
    from src.orchestrator import run_pipeline

    cfg = load_config(path=config)
    meta = build_run_meta()
    config_dict = cfg.model_dump()
    save_config_snapshot(config_dict, meta)

    logger.info(
        "pipeline_start",
        market=market,
        dry_run=dry_run,
        git_hash=meta.git_hash,
    )

    markets = _resolve_markets(market, config_dict)
    result = run_pipeline(config_dict, markets=markets, dry_run=dry_run)

    if result.ok:
        typer.echo("Pipeline completed successfully.")
    else:
        failed = [s.name for s in result.steps if not s.success]
        typer.echo(f"Pipeline completed with failures: {', '.join(failed)}")
        raise typer.Exit(code=1)


@app.command()
def screen(
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
    market: Annotated[str, typer.Option("--market", "-m", help="Market to screen (us, jp, all).")] = "us",
) -> None:
    """Run screening only."""
    import copy

    from src.core.config import load_config
    from src.screening.scorer import screen as run_screen

    cfg = load_config(path=config)
    config_dict = cfg.model_dump()
    markets = _resolve_markets(market, config_dict)

    screen_config = copy.deepcopy(config_dict)
    screen_config["screening"]["markets"] = markets

    market_arg = markets[0] if len(markets) == 1 else "us"
    screened = run_screen(screen_config, market=market_arg)

    if screened.empty:
        typer.echo("No stocks passed screening filters.")
    else:
        typer.echo(f"Top {len(screened)} stocks:")
        for _, row in screened.iterrows():
            price = row["current_price"]
            ticker = row["ticker"]
            score = row.get("score", 0)
            typer.echo(f"  {ticker}: {price:.2f} (score: {score:.4f})")


@app.command()
def predict(
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
    market: Annotated[str, typer.Option("--market", "-m", help="Market to predict.")] = "us",
) -> None:
    """Run screening + prediction."""
    import copy

    from src.core.config import load_config
    from src.prediction.ensemble import predict as run_predict
    from src.screening.scorer import screen as run_screen

    cfg = load_config(path=config)
    config_dict = cfg.model_dump()
    markets = _resolve_markets(market, config_dict)

    screen_config = copy.deepcopy(config_dict)
    screen_config["screening"]["markets"] = markets

    market_arg = markets[0] if len(markets) == 1 else "us"
    screened = run_screen(screen_config, market=market_arg)

    if screened.empty:
        typer.echo("No stocks passed screening. Cannot predict.")
        return

    predictions = run_predict(screened, config_dict)
    if predictions.empty:
        typer.echo("No bullish predictions generated.")
    else:
        typer.echo(f"Bullish predictions ({len(predictions)}):")
        for _, row in predictions.iterrows():
            typer.echo(
                f"  {row['ticker']}: ${row['current_price']:.2f} -> "
                f"${row['predicted_price']:.2f} ({row['predicted_change_pct']:+.1f}%)"
            )


@app.command()
def export(
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
) -> None:
    """Run export only (regenerate dashboard JSON from DB/Sheets data)."""
    from src.core.config import load_config
    from src.export.json_exporter import export_dashboard_json
    from src.orchestrator import (
        _export_alpha_survey,
        _export_comparison,
        _export_macro,
        _export_walkforward,
        _load_all_records,
    )

    cfg = load_config(path=config)
    config_dict = cfg.model_dump()

    records = _load_all_records(config_dict)
    if not records:
        typer.echo("No records found in DB or Google Sheets.")
        return

    typer.echo(f"Exporting {len(records)} records...")
    export_dashboard_json(records, enrichment=None, config=config_dict)
    _export_comparison(records, config_dict)
    _export_walkforward(records, config_dict)
    _export_alpha_survey()
    _export_macro(config_dict)
    typer.echo("Export complete.")


@app.command()
def analyze(
    ticker: Annotated[str, typer.Option("--ticker", "-t", help="Tickers to analyze (comma-separated).")] = "",
    analysis_type: Annotated[str, typer.Option("--type", help="Analysis type (dcf, comps, stock_analysis, all, etc.).")] = "",
    config: Annotated[str | None, typer.Option("--config", "-c", help="Path to config YAML override.")] = None,
    output: Annotated[str, typer.Option("--output", "-o", help="Output directory.")] = "dashboard/data/analysis",
    output_format: Annotated[str, typer.Option("--format", "-f", help="Output format: json, markdown, both.")] = "json",
    compare: Annotated[str, typer.Option("--compare", help="Comparison ticker for stock_comparison analysis.")] = "",
    style: Annotated[str, typer.Option("--style", help="Investment style (growth/dividend/value).")] = "",
    amount: Annotated[str, typer.Option("--amount", help="Investment amount for portfolio_builder.")] = "",
    timeframe: Annotated[str, typer.Option("--timeframe", help="Investment time horizon.")] = "",
    sector: Annotated[str, typer.Option("--sector", help="Target sector for screening.")] = "",
) -> None:
    """Run LLM-driven financial analysis on specified tickers."""
    from pathlib import Path

    from src.analysis.data_collector import DataCollectionError
    from src.analysis.llm_client import create_llm_client
    from src.analysis.runner import AnalysisRunner
    from src.core.config import load_config
    from src.export.analysis_exporter import export_json, export_markdown, export_summary

    cfg = load_config(path=config)

    if not cfg.analysis.enabled:
        typer.echo("Analysis is disabled. Set analysis.enabled=true in config.")
        raise typer.Exit(code=1)

    try:
        llm = create_llm_client(cfg.analysis.llm)
    except ValueError as exc:
        typer.echo(f"LLM setup failed: {exc}")
        raise typer.Exit(code=1) from exc

    types: list[str] | None = None
    if analysis_type and analysis_type != "all":
        types = [t.strip() for t in analysis_type.split(",") if t.strip()]

    ticker_optional_types = {"stock_screener", "portfolio_builder"}
    tickers = [t.strip() for t in ticker.split(",") if t.strip()] if ticker else []
    if not tickers:
        if types and all(t in ticker_optional_types for t in types):
            tickers = ["MARKET"]
        else:
            typer.echo("No tickers specified. Use --ticker AAPL,MSFT")
            raise typer.Exit(code=1)

    if types and "stock_comparison" in types and not compare:
        typer.echo("stock_comparison requires --compare <TICKER>. Example: --compare MSFT")
        raise typer.Exit(code=1)

    params: dict[str, str] = {}
    if style:
        params["style"] = style
    if amount:
        params["amount"] = amount
    if timeframe:
        params["timeframe"] = timeframe
    if sector:
        params["sector"] = sector

    runner = AnalysisRunner(
        config=cfg.analysis,
        llm=llm,
        comparison_ticker=compare or None,
        params=params or None,
    )

    typer.echo(f"Running analysis on {len(tickers)} ticker(s)...")
    try:
        results = runner.run(tickers, analysis_types=types)
    except DataCollectionError as exc:
        typer.echo(f"Data collection failed: {exc}")
        raise typer.Exit(code=1) from exc

    if not results:
        typer.echo("No analyses completed successfully.")
        raise typer.Exit(code=1)

    output_dir = Path(output)
    if output_format in ("json", "both"):
        export_json(results, output_dir)
    if output_format in ("markdown", "both"):
        export_markdown(results, output_dir)

    summary = export_summary(results)
    typer.echo(
        f"Completed {summary['total_analyses']} analyses "
        f"for {len(summary['tickers_analyzed'])} tickers "
        f"({summary['total_tokens']} tokens used)."
    )


@app.command()
def version() -> None:
    """Show version information."""
    from src.core.meta import build_run_meta

    meta = build_run_meta()
    typer.echo("trader v2.0.0")
    typer.echo(f"Python {meta.python_version}")
    if meta.git_hash:
        typer.echo(f"Git: {meta.git_hash}")


def _resolve_markets(market: str, config: dict) -> list[str]:
    """Resolve market argument to a list of market identifiers."""
    if market == "all":
        return config.get("screening", {}).get(
            "markets", ["sp500", "nasdaq100", "nikkei225"]
        )
    if market == "us":
        all_markets = config.get("screening", {}).get(
            "markets", ["sp500", "nasdaq100"]
        )
        return [m for m in all_markets if m != "nikkei225"]
    if market == "jp":
        return ["nikkei225"]
    return [market]


if __name__ == "__main__":
    app()
