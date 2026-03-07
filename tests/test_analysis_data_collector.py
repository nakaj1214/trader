"""Tests for financial data collector."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from src.analysis.data_collector import AnalysisDataCollector, DataCollectionError
from src.core.models import AnalysisInput


def _mock_stock(info: dict | None = None):
    """Create a mock yf.Ticker with the given info dict."""
    stock = MagicMock()
    stock.info = info or {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "marketCap": 3_000_000_000_000,
        "totalRevenue": 383_285_000_000,
        "ebitda": 130_541_000_000,
        "netIncome": 96_995_000_000,
        "freeCashflow": 111_443_000_000,
        "trailingPE": 33.5,
        "forwardPE": 29.2,
        "priceToBook": 50.1,
        "returnOnEquity": 1.71,
        "beta": 1.24,
        "debtToEquity": 199.42,
    }
    stock.income_stmt = pd.DataFrame(
        {"2024": [383285e6, 130541e6]},
        index=["Total Revenue", "EBITDA"],
    )
    stock.balance_sheet = pd.DataFrame(
        {"2024": [352583e6, 290437e6]},
        index=["Total Assets", "Total Liabilities"],
    )
    stock.cashflow = pd.DataFrame(
        {"2024": [111443e6, -10959e6]},
        index=["Free Cash Flow", "Capital Expenditure"],
    )
    return stock


class TestCollect:
    """Tests for AnalysisDataCollector.collect."""

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_returns_analysis_input(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_stock()
        collector = AnalysisDataCollector()

        result = collector.collect("AAPL")

        assert isinstance(result, AnalysisInput)
        assert result.ticker == "AAPL"
        assert result.company_name == "Apple Inc."
        assert result.sector == "Technology"
        assert result.industry == "Consumer Electronics"
        assert result.market_cap == 3_000_000_000_000

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_extracts_financials(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _mock_stock()
        collector = AnalysisDataCollector()

        result = collector.collect("AAPL")

        assert "revenue" in result.financials or "totalRevenue" in result.financials
        assert "ebitda" in result.financials
        assert "income_stmt" in result.financials
        assert "balance_sheet" in result.financials
        assert "cashflow" in result.financials

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_normalizes_revenue_field(self, mock_ticker_cls):
        stock = _mock_stock(info={
            "longName": "Test Corp",
            "totalRevenue": 100_000_000,
        })
        mock_ticker_cls.return_value = stock
        collector = AnalysisDataCollector()

        result = collector.collect("TEST")

        assert result.financials.get("revenue") == 100_000_000

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_normalizes_free_cash_flow(self, mock_ticker_cls):
        stock = _mock_stock(info={
            "longName": "Test Corp",
            "freeCashflow": 50_000_000,
        })
        mock_ticker_cls.return_value = stock
        collector = AnalysisDataCollector()

        result = collector.collect("TEST")

        assert result.financials.get("free_cash_flow") == 50_000_000

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_raises_on_api_failure(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("Network error")
        collector = AnalysisDataCollector()

        with pytest.raises(DataCollectionError, match="Failed to fetch"):
            collector.collect("INVALID")

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_raises_on_empty_data(self, mock_ticker_cls):
        stock = MagicMock()
        stock.info = {}
        mock_ticker_cls.return_value = stock
        collector = AnalysisDataCollector()

        with pytest.raises(DataCollectionError, match="No data available"):
            collector.collect("INVALID")

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_uses_short_name_fallback(self, mock_ticker_cls):
        stock = _mock_stock(info={"shortName": "Apple"})
        mock_ticker_cls.return_value = stock
        collector = AnalysisDataCollector()

        result = collector.collect("AAPL")

        assert result.company_name == "Apple"

    @patch("src.analysis.data_collector.yf.Ticker")
    def test_handles_empty_financial_statements(self, mock_ticker_cls):
        stock = _mock_stock(info={"longName": "Empty Corp"})
        stock.income_stmt = pd.DataFrame()
        stock.balance_sheet = pd.DataFrame()
        stock.cashflow = pd.DataFrame()
        mock_ticker_cls.return_value = stock
        collector = AnalysisDataCollector()

        result = collector.collect("EMPTY")

        assert result.financials.get("income_stmt") is None
        assert result.financials.get("balance_sheet") is None
        assert result.financials.get("cashflow") is None


class TestDfToSummary:
    """Tests for AnalysisDataCollector._df_to_summary."""

    def test_returns_none_for_empty_df(self):
        collector = AnalysisDataCollector()
        assert collector._df_to_summary(pd.DataFrame()) is None

    def test_returns_none_for_none(self):
        collector = AnalysisDataCollector()
        assert collector._df_to_summary(None) is None

    def test_extracts_latest_column(self):
        collector = AnalysisDataCollector()
        df = pd.DataFrame(
            {"2024": [100.0, 200.0], "2023": [90.0, 180.0]},
            index=["Revenue", "EBITDA"],
        )

        result = collector._df_to_summary(df)

        assert result is not None
        assert result["Revenue"] == 100.0
        assert result["EBITDA"] == 200.0
