"""Tests for analysis result exporter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.models import AnalysisResult
from src.export.analysis_exporter import (
    export_json,
    export_markdown,
    export_summary,
)


def _make_result(
    ticker: str = "AAPL",
    analysis_type: str = "dcf",
    content: str = "# DCF Analysis\nTest content.",
    token_count: int = 500,
) -> AnalysisResult:
    return AnalysisResult(
        ticker=ticker,
        analysis_type=analysis_type,
        content=content,
        timestamp="2026-03-07T00:00:00Z",
        model_used="claude-sonnet-4-6",
        token_count=token_count,
    )


class TestExportJson:
    """Tests for export_json."""

    def test_creates_ticker_files(self, tmp_path):
        results = [
            _make_result(ticker="AAPL", analysis_type="dcf"),
            _make_result(ticker="AAPL", analysis_type="comps"),
            _make_result(ticker="MSFT", analysis_type="dcf"),
        ]

        written = export_json(results, tmp_path)

        assert (tmp_path / "AAPL.json").exists()
        assert (tmp_path / "MSFT.json").exists()
        assert (tmp_path / "index.json").exists()
        assert len(written) == 3  # AAPL.json + MSFT.json + index.json

    def test_ticker_json_contains_all_analyses(self, tmp_path):
        results = [
            _make_result(ticker="AAPL", analysis_type="dcf"),
            _make_result(ticker="AAPL", analysis_type="comps"),
        ]

        export_json(results, tmp_path)

        data = json.loads((tmp_path / "AAPL.json").read_text(encoding="utf-8"))
        assert len(data) == 2
        types = {a["analysis_type"] for a in data}
        assert types == {"dcf", "comps"}

    def test_index_json_structure(self, tmp_path):
        results = [
            _make_result(ticker="AAPL", analysis_type="dcf"),
            _make_result(ticker="AAPL", analysis_type="comps"),
            _make_result(ticker="MSFT", analysis_type="dcf"),
        ]

        export_json(results, tmp_path)

        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert "AAPL" in index
        assert "MSFT" in index
        assert set(index["AAPL"]) == {"dcf", "comps"}
        assert index["MSFT"] == ["dcf"]

    def test_creates_output_dir(self, tmp_path):
        output_dir = tmp_path / "nested" / "output"
        results = [_make_result()]

        export_json(results, output_dir)

        assert output_dir.exists()
        assert (output_dir / "AAPL.json").exists()

    def test_empty_results(self, tmp_path):
        written = export_json([], tmp_path)

        # Should only create the index file
        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert index == {}
        assert len(written) == 1


class TestExportMarkdown:
    """Tests for export_markdown."""

    def test_creates_markdown_files(self, tmp_path):
        results = [
            _make_result(ticker="AAPL", analysis_type="dcf"),
            _make_result(ticker="MSFT", analysis_type="comps"),
        ]

        written = export_markdown(results, tmp_path)

        assert (tmp_path / "AAPL.md").exists()
        assert (tmp_path / "MSFT.md").exists()
        assert len(written) == 2

    def test_markdown_content_structure(self, tmp_path):
        results = [
            _make_result(
                ticker="AAPL",
                analysis_type="dcf",
                content="Test DCF content",
            ),
        ]

        export_markdown(results, tmp_path)

        content = (tmp_path / "AAPL.md").read_text(encoding="utf-8")
        assert "# Financial Analysis: AAPL" in content
        assert "## Dcf" in content
        assert "Test DCF content" in content
        assert "claude-sonnet-4-6" in content

    def test_multiple_analyses_per_ticker(self, tmp_path):
        results = [
            _make_result(ticker="AAPL", analysis_type="dcf", content="DCF content"),
            _make_result(ticker="AAPL", analysis_type="comps", content="Comps content"),
        ]

        export_markdown(results, tmp_path)

        content = (tmp_path / "AAPL.md").read_text(encoding="utf-8")
        assert "## Dcf" in content
        assert "## Comps" in content
        assert "DCF content" in content
        assert "Comps content" in content


class TestExportSummary:
    """Tests for export_summary."""

    def test_summary_structure(self):
        results = [
            _make_result(ticker="AAPL", analysis_type="dcf", token_count=500),
            _make_result(ticker="AAPL", analysis_type="comps", token_count=300),
            _make_result(ticker="MSFT", analysis_type="dcf", token_count=400),
        ]

        summary = export_summary(results)

        assert summary["total_analyses"] == 3
        assert set(summary["tickers_analyzed"]) == {"AAPL", "MSFT"}
        assert summary["total_tokens"] == 1200

    def test_analyses_by_ticker(self):
        results = [
            _make_result(ticker="AAPL", analysis_type="dcf"),
            _make_result(ticker="AAPL", analysis_type="comps"),
        ]

        summary = export_summary(results)

        assert summary["analyses_by_ticker"]["AAPL"] == ["dcf", "comps"]

    def test_empty_results(self):
        summary = export_summary([])

        assert summary["total_analyses"] == 0
        assert summary["tickers_analyzed"] == []
        assert summary["total_tokens"] == 0
