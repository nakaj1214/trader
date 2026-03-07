"""Head-to-head stock comparison analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import STOCK_COMPARISON
from src.core.models import AnalysisInput


class StockComparisonAnalyzer(Analyzer):
    """Compares two stocks side by side for investment decision."""

    @property
    def name(self) -> str:
        return "stock_comparison"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue", "ebitda"]

    def _validate_input(self, data: AnalysisInput) -> None:
        """Validate that comparison data is provided."""
        super()._validate_input(data)
        if data.comparison_data is None:
            raise ValueError(
                "Stock comparison requires comparison_data. "
                "Use --compare <TICKER> to specify a comparison stock."
            )

    def _user_prompt(self, data: AnalysisInput) -> str:
        style = data.params.get("style", "growth")
        timeframe = data.params.get("timeframe", "5 years")
        comparison_summary = (
            self._format_financials_summary(data.comparison_data)
            if data.comparison_data
            else "No comparison data available"
        )
        return STOCK_COMPARISON.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
            comparison_summary=comparison_summary,
            style=style,
            timeframe=timeframe,
        )

    def _system_prompt(self) -> str:
        return STOCK_COMPARISON.system_prompt
