"""Analysis result exporter for JSON, Markdown, and Slack summaries."""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import structlog

from src.core.models import AnalysisResult

logger = structlog.get_logger(__name__)


def export_json(
    results: list[AnalysisResult],
    output_dir: Path,
) -> list[Path]:
    """Export analysis results as JSON files, grouped by ticker.

    Args:
        results: List of analysis results to export.
        output_dir: Directory to write JSON files.

    Returns:
        List of written file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result.ticker].append(result.model_dump())

    written: list[Path] = []
    for ticker, analyses in grouped.items():
        output_path = output_dir / f"{ticker}.json"
        _atomic_write_json(output_path, analyses)
        written.append(output_path)
        logger.info("analysis_json_exported", ticker=ticker, path=str(output_path))

    # Write index file listing all available analyses
    index = {
        ticker: [a["analysis_type"] for a in analyses]
        for ticker, analyses in grouped.items()
    }
    index_path = output_dir / "index.json"
    _atomic_write_json(index_path, index)
    written.append(index_path)

    return written


def export_markdown(
    results: list[AnalysisResult],
    output_dir: Path,
) -> list[Path]:
    """Export analysis results as Markdown files, grouped by ticker.

    Args:
        results: List of analysis results to export.
        output_dir: Directory to write Markdown files.

    Returns:
        List of written file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[AnalysisResult]] = defaultdict(list)
    for result in results:
        grouped[result.ticker].append(result)

    written: list[Path] = []
    for ticker, analyses in grouped.items():
        output_path = output_dir / f"{ticker}.md"
        content = _build_markdown(ticker, analyses)
        output_path.write_text(content, encoding="utf-8")
        written.append(output_path)
        logger.info("analysis_markdown_exported", ticker=ticker, path=str(output_path))

    return written


def export_summary(results: list[AnalysisResult]) -> dict[str, Any]:
    """Generate a summary dict for Slack notification.

    Args:
        results: List of analysis results.

    Returns:
        Summary dict with tickers, types, and counts.
    """
    summary: dict[str, list[str]] = defaultdict(list)
    for result in results:
        summary[result.ticker].append(result.analysis_type)

    return {
        "total_analyses": len(results),
        "tickers_analyzed": list(summary.keys()),
        "analyses_by_ticker": dict(summary),
        "total_tokens": sum(r.token_count for r in results),
    }


def _build_markdown(ticker: str, analyses: list[AnalysisResult]) -> str:
    """Build a Markdown document from analysis results."""
    sections = [f"# Financial Analysis: {ticker}\n"]

    for analysis in analyses:
        type_title = analysis.analysis_type.replace("_", " ").title()
        sections.append(f"## {type_title}\n")
        sections.append(f"*Model: {analysis.model_used} | "
                        f"Generated: {analysis.timestamp} | "
                        f"Tokens: {analysis.token_count}*\n")
        sections.append(analysis.content)
        sections.append("\n---\n")

    return "\n".join(sections)


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically using tmp + rename pattern."""
    dir_path = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
