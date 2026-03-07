"""Tests for analysis runner orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.config import AnalysisConfig, LLMConfig
from src.core.models import AnalysisInput, AnalysisResult


def _make_config(**overrides) -> AnalysisConfig:
    """Create a test AnalysisConfig."""
    defaults = {
        "enabled": True,
        "max_tickers": 5,
        "max_concurrent": 2,
        "enabled_analyses": ["dcf", "comps"],
    }
    defaults.update(overrides)
    return AnalysisConfig(**defaults)


def _make_input(ticker: str = "AAPL") -> AnalysisInput:
    return AnalysisInput(
        ticker=ticker,
        company_name=f"{ticker} Inc.",
        financials={"revenue": 100_000_000},
    )


def _make_result(ticker: str, atype: str) -> AnalysisResult:
    return AnalysisResult(
        ticker=ticker,
        analysis_type=atype,
        content="Test analysis content",
        timestamp="2026-03-07T00:00:00Z",
        model_used="test-model",
        token_count=100,
    )


class TestAnalysisRunner:
    """Tests for AnalysisRunner."""

    @patch("src.analysis.runner._get_all_analyzers")
    def test_run_returns_results(self, mock_get_analyzers):
        from src.analysis.runner import AnalysisRunner

        mock_analyzer = MagicMock()
        mock_analyzer.name = "dcf"
        mock_analyzer.analyze.return_value = _make_result("AAPL", "dcf")
        mock_get_analyzers.return_value = {"dcf": mock_analyzer}

        mock_llm = MagicMock()
        mock_collector = MagicMock()
        mock_collector.collect.return_value = _make_input("AAPL")

        config = _make_config(enabled_analyses=["dcf"])
        runner = AnalysisRunner(config=config, llm=mock_llm, collector=mock_collector)

        results = runner.run(["AAPL"])

        assert len(results) == 1
        assert results[0].ticker == "AAPL"
        assert results[0].analysis_type == "dcf"

    @patch("src.analysis.runner._get_all_analyzers")
    def test_run_limits_tickers(self, mock_get_analyzers):
        from src.analysis.runner import AnalysisRunner

        mock_analyzer = MagicMock()
        mock_analyzer.name = "dcf"
        mock_analyzer.analyze.return_value = _make_result("AAPL", "dcf")
        mock_get_analyzers.return_value = {"dcf": mock_analyzer}

        mock_llm = MagicMock()
        mock_collector = MagicMock()
        mock_collector.collect.return_value = _make_input()

        config = _make_config(max_tickers=2, enabled_analyses=["dcf"])
        runner = AnalysisRunner(config=config, llm=mock_llm, collector=mock_collector)

        results = runner.run(["AAPL", "MSFT", "GOOGL"])

        # Should only process 2 tickers due to max_tickers
        assert mock_collector.collect.call_count == 2

    @patch("src.analysis.runner._get_all_analyzers")
    def test_run_custom_analysis_types(self, mock_get_analyzers):
        from src.analysis.runner import AnalysisRunner

        dcf_analyzer = MagicMock()
        dcf_analyzer.name = "dcf"
        dcf_analyzer.analyze.return_value = _make_result("AAPL", "dcf")

        comps_analyzer = MagicMock()
        comps_analyzer.name = "comps"
        comps_analyzer.analyze.return_value = _make_result("AAPL", "comps")

        mock_get_analyzers.return_value = {
            "dcf": dcf_analyzer,
            "comps": comps_analyzer,
        }

        mock_llm = MagicMock()
        mock_collector = MagicMock()
        mock_collector.collect.return_value = _make_input()

        config = _make_config(enabled_analyses=["dcf", "comps"])
        runner = AnalysisRunner(config=config, llm=mock_llm, collector=mock_collector)

        # Explicitly request only "dcf"
        results = runner.run(["AAPL"], analysis_types=["dcf"])

        assert len(results) == 1
        assert results[0].analysis_type == "dcf"

    @patch("src.analysis.runner._get_all_analyzers")
    def test_run_isolates_errors(self, mock_get_analyzers):
        from src.analysis.runner import AnalysisRunner

        good_analyzer = MagicMock()
        good_analyzer.name = "dcf"
        good_analyzer.analyze.return_value = _make_result("AAPL", "dcf")

        bad_analyzer = MagicMock()
        bad_analyzer.name = "comps"
        bad_analyzer.analyze.side_effect = RuntimeError("LLM error")

        mock_get_analyzers.return_value = {
            "dcf": good_analyzer,
            "comps": bad_analyzer,
        }

        mock_llm = MagicMock()
        mock_collector = MagicMock()
        mock_collector.collect.return_value = _make_input()

        config = _make_config(enabled_analyses=["dcf", "comps"])
        runner = AnalysisRunner(config=config, llm=mock_llm, collector=mock_collector)

        # Should not raise; bad analysis is isolated
        results = runner.run(["AAPL"])

        assert len(results) == 1
        assert results[0].analysis_type == "dcf"

    @patch("src.analysis.runner._get_all_analyzers")
    def test_run_single_unknown_type_raises(self, mock_get_analyzers):
        from src.analysis.runner import AnalysisRunner

        mock_get_analyzers.return_value = {}

        mock_llm = MagicMock()
        mock_collector = MagicMock()
        config = _make_config()
        runner = AnalysisRunner(config=config, llm=mock_llm, collector=mock_collector)

        with pytest.raises(ValueError, match="Unknown analysis type"):
            runner.run_single("AAPL", "nonexistent_type")

    @patch("src.analysis.runner._get_all_analyzers")
    def test_run_skips_types_not_in_analyzers(self, mock_get_analyzers):
        from src.analysis.runner import AnalysisRunner

        # Only dcf analyzer available, but config requests dcf + comps
        dcf_analyzer = MagicMock()
        dcf_analyzer.name = "dcf"
        dcf_analyzer.analyze.return_value = _make_result("AAPL", "dcf")
        mock_get_analyzers.return_value = {"dcf": dcf_analyzer}

        mock_llm = MagicMock()
        mock_collector = MagicMock()
        mock_collector.collect.return_value = _make_input()

        config = _make_config(enabled_analyses=["dcf", "comps"])
        runner = AnalysisRunner(config=config, llm=mock_llm, collector=mock_collector)

        # run() skips "comps" since it's not in analyzers dict
        results = runner.run(["AAPL"])
        assert len(results) == 1
        assert results[0].analysis_type == "dcf"


class TestGetAllAnalyzers:
    """Tests for the _get_all_analyzers factory."""

    def test_returns_all_nineteen(self):
        from src.analysis.runner import _get_all_analyzers

        analyzers = _get_all_analyzers()

        expected_names = {
            # Investment banking analyses
            "dcf", "comps", "financial_statement", "sensitivity",
            "ma", "lbo", "precedent", "ipo",
            "credit", "sotp", "operating_model", "ic_memo",
            # Retail investor analyses
            "stock_analysis", "stock_screener", "earnings_report",
            "risk_assessment", "stock_comparison", "portfolio_builder",
            "entry_timing",
        }
        assert set(analyzers.keys()) == expected_names

    def test_all_have_name_property(self):
        from src.analysis.runner import _get_all_analyzers

        analyzers = _get_all_analyzers()
        for name, analyzer in analyzers.items():
            assert analyzer.name == name
