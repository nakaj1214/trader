"""Financial data collector for LLM analysis.

Gathers financial statements, fundamentals, and market data
from existing providers (yfinance, FMP, J-Quants) and packages
them into AnalysisInput for the analysis pipeline.
"""

from __future__ import annotations

from typing import Any

import structlog
import yfinance as yf

from src.core.exceptions import DataProviderError
from src.core.models import AnalysisInput

logger = structlog.get_logger(__name__)


class DataCollectionError(DataProviderError):
    """Raised when required data cannot be collected."""


class AnalysisDataCollector:
    """Collects financial data from multiple providers for analysis."""

    def collect(self, ticker: str) -> AnalysisInput:
        """Collect financial data for a single ticker.

        Args:
            ticker: Stock ticker symbol (e.g. 'AAPL', '7203.T').

        Returns:
            AnalysisInput with all available financial data.

        Raises:
            DataCollectionError: If essential data cannot be fetched.
        """
        logger.info("data_collection_started", ticker=ticker)

        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}
        except Exception as exc:
            raise DataCollectionError(
                f"Failed to fetch data for {ticker}: {exc}"
            ) from exc

        company_name = info.get("longName") or info.get("shortName") or ticker
        if company_name == ticker and not info:
            raise DataCollectionError(
                f"No data available for ticker '{ticker}'. "
                "Verify the ticker symbol is correct."
            )

        financials = self._extract_financials(stock, info)

        return AnalysisInput(
            ticker=ticker,
            company_name=company_name,
            industry=info.get("industry"),
            sector=info.get("sector"),
            market_cap=info.get("marketCap"),
            financials=financials,
        )

    def collect_pair(self, ticker_a: str, ticker_b: str) -> AnalysisInput:
        """Collect financial data for two tickers (for comparison analysis).

        Args:
            ticker_a: Primary stock ticker symbol.
            ticker_b: Comparison stock ticker symbol.

        Returns:
            AnalysisInput with primary data and comparison_data populated.

        Raises:
            DataCollectionError: If either ticker's data cannot be fetched.
        """
        primary = self.collect(ticker_a)
        comparison = self.collect(ticker_b)
        return AnalysisInput(
            **primary.model_dump(exclude={"comparison_data"}),
            comparison_data=comparison,
        )

    def _extract_financials(
        self,
        stock: yf.Ticker,
        info: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract key financial metrics from yfinance data."""
        financials: dict[str, Any] = {}

        # Key metrics from info dict
        metric_keys = [
            "revenue", "totalRevenue", "ebitda", "netIncome",
            "freeCashflow", "totalDebt", "totalCash",
            "operatingMargins", "profitMargins", "grossMargins",
            "returnOnEquity", "returnOnAssets",
            "trailingPE", "forwardPE", "priceToBook",
            "enterpriseValue", "enterpriseToEbitda", "enterpriseToRevenue",
            "beta", "dividendYield", "payoutRatio",
            "debtToEquity", "currentRatio", "quickRatio",
            "revenueGrowth", "earningsGrowth",
        ]
        for key in metric_keys:
            value = info.get(key)
            if value is not None:
                financials[key] = value

        # Normalize common field names
        if "totalRevenue" in financials and "revenue" not in financials:
            financials["revenue"] = financials["totalRevenue"]
        if "freeCashflow" in financials:
            financials["free_cash_flow"] = financials["freeCashflow"]

        # Financial statements (latest annual)
        financials["income_stmt"] = self._df_to_summary(stock.income_stmt)
        financials["balance_sheet"] = self._df_to_summary(stock.balance_sheet)
        financials["cashflow"] = self._df_to_summary(stock.cashflow)

        return financials

    def _df_to_summary(self, df: Any) -> dict[str, Any] | None:
        """Convert a financial statement DataFrame to a summary dict."""
        if df is None or (hasattr(df, "empty") and df.empty):
            return None

        try:
            # Take the most recent year (first column)
            latest = df.iloc[:, 0]
            return {
                str(k): float(v) if v == v else None  # noqa: PLR0124 (NaN check)
                for k, v in latest.items()
                if v is not None
            }
        except (IndexError, AttributeError):
            return None
