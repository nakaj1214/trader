"""IPO valuation and pricing analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import IPO
from src.core.models import AnalysisInput


class IPOAnalyzer(Analyzer):
    """Performs IPO valuation analysis using LLM."""

    @property
    def name(self) -> str:
        return "ipo"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue"]

    def _system_prompt(self) -> str:
        return IPO.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return IPO.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
