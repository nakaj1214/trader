"""Analysis orchestrator for running multiple analyzers.

Manages the execution of financial analyses across tickers,
with concurrent execution support and error isolation.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import structlog

from src.analysis.base import Analyzer
from src.analysis.data_collector import AnalysisDataCollector
from src.analysis.llm_client import LLMClient
from src.core.config import AnalysisConfig
from src.core.models import AnalysisResult

logger = structlog.get_logger(__name__)


def _get_all_analyzers() -> dict[str, Analyzer]:
    """Import and instantiate all available analyzers."""
    from src.analysis.comps_analyzer import CompsAnalyzer
    from src.analysis.credit_analyzer import CreditAnalyzer
    from src.analysis.dcf_analyzer import DCFAnalyzer
    from src.analysis.earnings_report_analyzer import EarningsReportAnalyzer
    from src.analysis.entry_timing_analyzer import EntryTimingAnalyzer
    from src.analysis.financial_statement_analyzer import FinancialStatementAnalyzer
    from src.analysis.ic_memo_analyzer import ICMemoAnalyzer
    from src.analysis.ipo_analyzer import IPOAnalyzer
    from src.analysis.lbo_analyzer import LBOAnalyzer
    from src.analysis.ma_analyzer import MAAnalyzer
    from src.analysis.operating_model_analyzer import OperatingModelAnalyzer
    from src.analysis.portfolio_builder_analyzer import PortfolioBuilderAnalyzer
    from src.analysis.precedent_analyzer import PrecedentAnalyzer
    from src.analysis.risk_assessment_analyzer import RiskAssessmentAnalyzer
    from src.analysis.sensitivity_analyzer import SensitivityAnalyzer
    from src.analysis.sotp_analyzer import SOTPAnalyzer
    from src.analysis.stock_analysis_analyzer import StockAnalysisAnalyzer
    from src.analysis.stock_comparison_analyzer import StockComparisonAnalyzer
    from src.analysis.stock_screener_analyzer import StockScreenerAnalyzer

    analyzers: list[Analyzer] = [
        # Investment banking analyses
        DCFAnalyzer(),
        CompsAnalyzer(),
        FinancialStatementAnalyzer(),
        SensitivityAnalyzer(),
        MAAnalyzer(),
        LBOAnalyzer(),
        PrecedentAnalyzer(),
        IPOAnalyzer(),
        CreditAnalyzer(),
        SOTPAnalyzer(),
        OperatingModelAnalyzer(),
        ICMemoAnalyzer(),
        # Retail investor analyses
        StockAnalysisAnalyzer(),
        StockScreenerAnalyzer(),
        EarningsReportAnalyzer(),
        RiskAssessmentAnalyzer(),
        StockComparisonAnalyzer(),
        PortfolioBuilderAnalyzer(),
        EntryTimingAnalyzer(),
    ]
    return {a.name: a for a in analyzers}


class AnalysisRunner:
    """Orchestrates the execution of financial analyses."""

    def __init__(
        self,
        config: AnalysisConfig,
        llm: LLMClient,
        collector: AnalysisDataCollector | None = None,
        comparison_ticker: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self._config = config
        self._llm = llm
        self._collector = collector or AnalysisDataCollector()
        self._analyzers = _get_all_analyzers()
        self._comparison_ticker = comparison_ticker
        self._params = params or {}

    def run(
        self,
        tickers: list[str],
        analysis_types: list[str] | None = None,
    ) -> list[AnalysisResult]:
        """Run analyses on multiple tickers.

        Args:
            tickers: List of stock tickers to analyze.
            analysis_types: Types of analysis to run. If None,
                uses config.enabled_analyses.

        Returns:
            List of completed AnalysisResult objects.
        """
        types = analysis_types or self._config.enabled_analyses
        limited_tickers = tickers[: self._config.max_tickers]

        logger.info(
            "analysis_run_started",
            tickers=limited_tickers,
            analysis_types=types,
            max_concurrent=self._config.max_concurrent,
        )

        tasks: list[tuple[str, str]] = [
            (ticker, atype)
            for ticker in limited_tickers
            for atype in types
            if atype in self._analyzers
        ]

        results: list[AnalysisResult] = []

        with ThreadPoolExecutor(max_workers=self._config.max_concurrent) as executor:
            futures = {
                executor.submit(self.run_single, ticker, atype): (ticker, atype)
                for ticker, atype in tasks
            }

            for future in as_completed(futures):
                ticker, atype = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(
                        "analysis_complete",
                        ticker=ticker,
                        analysis_type=atype,
                        token_count=result.token_count,
                    )
                except Exception:
                    logger.warning(
                        "analysis_failed",
                        ticker=ticker,
                        analysis_type=atype,
                        exc_info=True,
                    )

        logger.info(
            "analysis_run_complete",
            total_tasks=len(tasks),
            successful=len(results),
            failed=len(tasks) - len(results),
        )

        return results

    def run_single(self, ticker: str, analysis_type: str) -> AnalysisResult:
        """Run a single analysis on one ticker.

        Args:
            ticker: Stock ticker symbol.
            analysis_type: Type of analysis to run.

        Returns:
            AnalysisResult with the generated content.

        Raises:
            ValueError: If analysis_type is not recognized.
            DataCollectionError: If required data cannot be collected.
        """
        analyzer = self._analyzers.get(analysis_type)
        if analyzer is None:
            raise ValueError(
                f"Unknown analysis type: '{analysis_type}'. "
                f"Available: {sorted(self._analyzers.keys())}"
            )

        start_time = time.monotonic()

        if analysis_type == "stock_comparison" and self._comparison_ticker:
            data = self._collector.collect_pair(ticker, self._comparison_ticker)
        else:
            data = self._collector.collect(ticker)

        if self._params:
            data = data.model_copy(update={"params": self._params})

        result = analyzer.analyze(data, self._llm)

        elapsed = time.monotonic() - start_time
        logger.info(
            "analysis_single_complete",
            ticker=ticker,
            analysis_type=analysis_type,
            elapsed_seconds=round(elapsed, 2),
            token_count=result.token_count,
        )

        return result
