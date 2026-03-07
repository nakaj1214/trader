"""Portfolio construction recommendation analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import PORTFOLIO_BUILDER
from src.core.models import AnalysisInput


class PortfolioBuilderAnalyzer(Analyzer):
    """Builds diversified stock portfolio recommendations."""

    @property
    def name(self) -> str:
        return "portfolio_builder"

    @property
    def required_data_fields(self) -> list[str]:
        return []

    def _system_prompt(self) -> str:
        return PORTFOLIO_BUILDER.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        amount = data.params.get("amount", "10,000")
        style = data.params.get("style", "growth")
        timeframe = data.params.get("timeframe", "5 years")
        num_stocks = data.params.get("num_stocks", "10")
        return PORTFOLIO_BUILDER.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
            amount=amount,
            style=style,
            timeframe=timeframe,
            num_stocks=num_stocks,
        )
