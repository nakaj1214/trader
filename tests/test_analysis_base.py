"""Tests for the Analyzer base class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.analysis.base import Analyzer
from src.core.models import AnalysisInput, AnalysisResult


def _make_input(**overrides) -> AnalysisInput:
    """Create a test AnalysisInput with sensible defaults."""
    defaults = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "industry": "Consumer Electronics",
        "sector": "Technology",
        "market_cap": 3_000_000_000_000,
        "financials": {
            "revenue": 383_285_000_000,
            "ebitda": 130_541_000_000,
            "netIncome": 96_995_000_000,
        },
    }
    defaults.update(overrides)
    return AnalysisInput(**defaults)


class ConcreteAnalyzer(Analyzer):
    """Test implementation of the abstract Analyzer."""

    @property
    def name(self) -> str:
        return "test_analyzer"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue"]

    def _system_prompt(self) -> str:
        return "You are a test analyst."

    def _user_prompt(self, data: AnalysisInput) -> str:
        return f"Analyze {data.ticker}: {self._format_financials_summary(data)}"


class TestAnalyzerAnalyze:
    """Tests for Analyzer.analyze method."""

    def test_returns_analysis_result(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = ("Generated analysis content", 500)
        mock_llm._config = MagicMock(model="test-model")

        result = analyzer.analyze(data, mock_llm)

        assert isinstance(result, AnalysisResult)
        assert result.ticker == "AAPL"
        assert result.analysis_type == "test_analyzer"
        assert result.content == "Generated analysis content"
        assert result.token_count == 500
        assert result.model_used == "test-model"

    def test_calls_llm_with_prompts(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = ("content", 100)
        mock_llm._config = MagicMock(model="test-model")

        analyzer.analyze(data, mock_llm)

        mock_llm.generate.assert_called_once()
        args, _ = mock_llm.generate.call_args
        user_prompt, system_prompt = args
        assert "AAPL" in user_prompt
        assert "test analyst" in system_prompt

    def test_timestamp_in_iso_format(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = ("content", 100)
        mock_llm._config = MagicMock(model="test-model")

        result = analyzer.analyze(data, mock_llm)

        # ISO format should contain T separator
        assert "T" in result.timestamp


class TestAnalyzerValidateInput:
    """Tests for Analyzer._validate_input (logs warning for missing fields)."""

    def test_no_warning_when_data_present(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input()
        # Should not raise
        analyzer._validate_input(data)

    def test_warning_when_field_missing(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input(financials={})
        # Should not raise, just logs a warning
        analyzer._validate_input(data)


class TestFormatFinancialsSummary:
    """Tests for Analyzer._format_financials_summary."""

    def test_includes_company_info(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input()

        summary = analyzer._format_financials_summary(data)

        assert "Apple Inc." in summary
        assert "AAPL" in summary
        assert "Technology" in summary
        assert "Consumer Electronics" in summary

    def test_includes_market_cap(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input()

        summary = analyzer._format_financials_summary(data)

        assert "Market Cap" in summary

    def test_includes_financial_data(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input()

        summary = analyzer._format_financials_summary(data)

        assert "revenue" in summary
        assert "Financial Data" in summary

    def test_handles_none_sector(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input(sector=None, industry=None)

        summary = analyzer._format_financials_summary(data)

        assert "Sector" not in summary
        assert "Industry" not in summary

    def test_handles_empty_financials(self):
        analyzer = ConcreteAnalyzer()
        data = _make_input(financials={})

        summary = analyzer._format_financials_summary(data)

        assert "Apple Inc." in summary
        assert "Financial Data" not in summary
