"""Tests for retail investor analysis analyzers (7 types)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.analysis.earnings_report_analyzer import EarningsReportAnalyzer
from src.analysis.entry_timing_analyzer import EntryTimingAnalyzer
from src.analysis.portfolio_builder_analyzer import PortfolioBuilderAnalyzer
from src.analysis.risk_assessment_analyzer import RiskAssessmentAnalyzer
from src.analysis.stock_analysis_analyzer import StockAnalysisAnalyzer
from src.analysis.stock_comparison_analyzer import StockComparisonAnalyzer
from src.analysis.stock_screener_analyzer import StockScreenerAnalyzer
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
            "totalDebt": 111_000_000_000,
            "beta": 1.28,
            "trailingPE": 28.5,
            "income_stmt": {"TotalRevenue": 383_285_000_000},
        },
    }
    defaults.update(overrides)
    return AnalysisInput(**defaults)


def _make_comparison_input() -> AnalysisInput:
    """Create a comparison AnalysisInput for stock comparison tests."""
    return AnalysisInput(
        ticker="MSFT",
        company_name="Microsoft Corporation",
        industry="Software",
        sector="Technology",
        market_cap=2_800_000_000_000,
        financials={
            "revenue": 211_915_000_000,
            "ebitda": 100_000_000_000,
            "netIncome": 72_361_000_000,
        },
    )


def _mock_llm() -> MagicMock:
    """Create a mock LLM client."""
    mock = MagicMock()
    mock.generate.return_value = ("Generated analysis content", 500)
    mock._config = MagicMock(model="test-model")
    return mock


# --- Name and required_data_fields tests ---


class TestAnalyzerNames:
    """Verify name property for all 7 analyzers."""

    def test_stock_analysis_name(self):
        assert StockAnalysisAnalyzer().name == "stock_analysis"

    def test_stock_screener_name(self):
        assert StockScreenerAnalyzer().name == "stock_screener"

    def test_earnings_report_name(self):
        assert EarningsReportAnalyzer().name == "earnings_report"

    def test_risk_assessment_name(self):
        assert RiskAssessmentAnalyzer().name == "risk_assessment"

    def test_stock_comparison_name(self):
        assert StockComparisonAnalyzer().name == "stock_comparison"

    def test_portfolio_builder_name(self):
        assert PortfolioBuilderAnalyzer().name == "portfolio_builder"

    def test_entry_timing_name(self):
        assert EntryTimingAnalyzer().name == "entry_timing"


class TestRequiredDataFields:
    """Verify required_data_fields for all 7 analyzers."""

    def test_stock_analysis_fields(self):
        assert StockAnalysisAnalyzer().required_data_fields == [
            "revenue", "ebitda", "netIncome", "totalDebt",
        ]

    def test_earnings_report_fields(self):
        assert EarningsReportAnalyzer().required_data_fields == [
            "revenue", "netIncome", "income_stmt",
        ]

    def test_risk_assessment_fields(self):
        assert RiskAssessmentAnalyzer().required_data_fields == [
            "totalDebt", "revenue", "beta",
        ]

    def test_entry_timing_fields(self):
        assert EntryTimingAnalyzer().required_data_fields == [
            "revenue", "trailingPE",
        ]

    def test_stock_comparison_fields(self):
        assert StockComparisonAnalyzer().required_data_fields == [
            "revenue", "ebitda",
        ]

    def test_stock_screener_fields(self):
        assert StockScreenerAnalyzer().required_data_fields == []

    def test_portfolio_builder_fields(self):
        assert PortfolioBuilderAnalyzer().required_data_fields == []


# --- Category A: Single-ticker analyzers ---


class TestCategoryAAnalyzers:
    """Tests for single-ticker analyzers (stock_analysis, earnings_report, risk_assessment, entry_timing)."""

    @pytest.mark.parametrize("analyzer_cls", [
        StockAnalysisAnalyzer,
        EarningsReportAnalyzer,
        RiskAssessmentAnalyzer,
        EntryTimingAnalyzer,
    ])
    def test_returns_analysis_result(self, analyzer_cls):
        analyzer = analyzer_cls()
        data = _make_input()
        result = analyzer.analyze(data, _mock_llm())

        assert isinstance(result, AnalysisResult)
        assert result.ticker == "AAPL"
        assert result.analysis_type == analyzer.name
        assert result.content == "Generated analysis content"
        assert result.token_count == 500

    @pytest.mark.parametrize("analyzer_cls", [
        StockAnalysisAnalyzer,
        EarningsReportAnalyzer,
        RiskAssessmentAnalyzer,
        EntryTimingAnalyzer,
    ])
    def test_prompt_contains_ticker(self, analyzer_cls):
        analyzer = analyzer_cls()
        data = _make_input()
        llm = _mock_llm()

        analyzer.analyze(data, llm)

        llm.generate.assert_called_once()
        user_prompt = llm.generate.call_args[0][0]
        assert "AAPL" in user_prompt


# --- Category B: Stock comparison ---


class TestStockComparisonAnalyzer:
    """Tests for the stock comparison analyzer."""

    def test_analyze_with_comparison_data(self):
        analyzer = StockComparisonAnalyzer()
        comparison = _make_comparison_input()
        data = _make_input(comparison_data=comparison)

        result = analyzer.analyze(data, _mock_llm())

        assert isinstance(result, AnalysisResult)
        assert result.analysis_type == "stock_comparison"

    def test_prompt_contains_both_tickers(self):
        analyzer = StockComparisonAnalyzer()
        comparison = _make_comparison_input()
        data = _make_input(comparison_data=comparison)
        llm = _mock_llm()

        analyzer.analyze(data, llm)

        user_prompt = llm.generate.call_args[0][0]
        assert "AAPL" in user_prompt
        assert "MSFT" in user_prompt
        assert "Microsoft" in user_prompt

    def test_raises_without_comparison_data(self):
        analyzer = StockComparisonAnalyzer()
        data = _make_input()

        with pytest.raises(ValueError, match="comparison_data"):
            analyzer.analyze(data, _mock_llm())

    def test_uses_params_for_style_and_timeframe(self):
        analyzer = StockComparisonAnalyzer()
        comparison = _make_comparison_input()
        data = _make_input(
            comparison_data=comparison,
            params={"style": "value", "timeframe": "10 years"},
        )
        llm = _mock_llm()

        analyzer.analyze(data, llm)

        user_prompt = llm.generate.call_args[0][0]
        assert "value" in user_prompt
        assert "10 years" in user_prompt


# --- Category C: Strategy parameter analyzers ---


class TestStockScreenerAnalyzer:
    """Tests for the stock screener analyzer."""

    def test_analyze_with_defaults(self):
        analyzer = StockScreenerAnalyzer()
        data = _make_input()

        result = analyzer.analyze(data, _mock_llm())

        assert isinstance(result, AnalysisResult)
        assert result.analysis_type == "stock_screener"

    def test_default_params_in_prompt(self):
        analyzer = StockScreenerAnalyzer()
        data = _make_input()
        llm = _mock_llm()

        analyzer.analyze(data, llm)

        user_prompt = llm.generate.call_args[0][0]
        assert "growth" in user_prompt
        assert "US" in user_prompt

    def test_custom_params_in_prompt(self):
        analyzer = StockScreenerAnalyzer()
        data = _make_input(params={
            "style": "dividend",
            "sector": "healthcare",
            "market": "global",
        })
        llm = _mock_llm()

        analyzer.analyze(data, llm)

        user_prompt = llm.generate.call_args[0][0]
        assert "dividend" in user_prompt
        assert "healthcare" in user_prompt
        assert "global" in user_prompt


class TestPortfolioBuilderAnalyzer:
    """Tests for the portfolio builder analyzer."""

    def test_analyze_with_defaults(self):
        analyzer = PortfolioBuilderAnalyzer()
        data = _make_input()

        result = analyzer.analyze(data, _mock_llm())

        assert isinstance(result, AnalysisResult)
        assert result.analysis_type == "portfolio_builder"

    def test_default_params_in_prompt(self):
        analyzer = PortfolioBuilderAnalyzer()
        data = _make_input()
        llm = _mock_llm()

        analyzer.analyze(data, llm)

        user_prompt = llm.generate.call_args[0][0]
        assert "10,000" in user_prompt
        assert "growth" in user_prompt
        assert "5 years" in user_prompt

    def test_custom_params_in_prompt(self):
        analyzer = PortfolioBuilderAnalyzer()
        data = _make_input(params={
            "amount": "50,000",
            "style": "conservative",
            "timeframe": "10 years",
            "num_stocks": "15",
        })
        llm = _mock_llm()

        analyzer.analyze(data, llm)

        user_prompt = llm.generate.call_args[0][0]
        assert "50,000" in user_prompt
        assert "conservative" in user_prompt
        assert "10 years" in user_prompt
        assert "15" in user_prompt


# --- AnalysisInput model tests ---


class TestAnalysisInputExtensions:
    """Tests for the new AnalysisInput fields."""

    def test_backward_compatible_without_new_fields(self):
        data = AnalysisInput(
            ticker="AAPL",
            company_name="Apple Inc.",
        )
        assert data.comparison_data is None
        assert data.params == {}

    def test_with_comparison_data(self):
        comparison = _make_comparison_input()
        data = _make_input(comparison_data=comparison)

        assert data.comparison_data is not None
        assert data.comparison_data.ticker == "MSFT"

    def test_with_params(self):
        data = _make_input(params={"style": "growth", "amount": 50000})

        assert data.params["style"] == "growth"
        assert data.params["amount"] == 50000

    def test_model_dump_roundtrip(self):
        comparison = _make_comparison_input()
        data = _make_input(
            comparison_data=comparison,
            params={"style": "value"},
        )

        dumped = data.model_dump()
        restored = AnalysisInput.model_validate(dumped)

        assert restored.ticker == data.ticker
        assert restored.comparison_data is not None
        assert restored.comparison_data.ticker == "MSFT"
        assert restored.params["style"] == "value"
