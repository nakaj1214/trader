"""Full stock analysis analyzer (Buy/Hold/Sell recommendation)."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import STOCK_ANALYSIS
from src.core.models import AnalysisInput


class StockAnalysisAnalyzer(Analyzer):
    """Performs comprehensive stock analysis with Buy/Hold/Sell recommendation."""

    @property
    def name(self) -> str:
        return "stock_analysis"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue", "ebitda", "netIncome", "totalDebt"]

    def _system_prompt(self) -> str:
        return STOCK_ANALYSIS.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return STOCK_ANALYSIS.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
