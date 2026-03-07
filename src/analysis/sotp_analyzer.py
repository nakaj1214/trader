"""Sum-of-the-parts (SOTP) valuation analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import SOTP
from src.core.models import AnalysisInput


class SOTPAnalyzer(Analyzer):
    """Performs SOTP valuation analysis using LLM."""

    @property
    def name(self) -> str:
        return "sotp"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue"]

    def _system_prompt(self) -> str:
        return SOTP.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return SOTP.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
