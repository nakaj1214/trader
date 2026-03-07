"""Credit analysis and debt capacity analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import CREDIT
from src.core.models import AnalysisInput


class CreditAnalyzer(Analyzer):
    """Performs credit analysis using LLM."""

    @property
    def name(self) -> str:
        return "credit"

    @property
    def required_data_fields(self) -> list[str]:
        return ["ebitda", "totalDebt"]

    def _system_prompt(self) -> str:
        return CREDIT.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return CREDIT.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
