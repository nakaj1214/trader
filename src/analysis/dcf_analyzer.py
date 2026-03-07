"""DCF (Discounted Cash Flow) valuation analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import DCF
from src.core.models import AnalysisInput


class DCFAnalyzer(Analyzer):
    """Performs DCF valuation analysis using LLM."""

    @property
    def name(self) -> str:
        return "dcf"

    @property
    def required_data_fields(self) -> list[str]:
        return ["free_cash_flow", "revenue"]

    def _system_prompt(self) -> str:
        return DCF.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return DCF.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
