"""M&A accretion/dilution analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import MA_ANALYSIS
from src.core.models import AnalysisInput


class MAAnalyzer(Analyzer):
    """Performs M&A accretion/dilution analysis using LLM."""

    @property
    def name(self) -> str:
        return "ma"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue", "ebitda"]

    def _system_prompt(self) -> str:
        return MA_ANALYSIS.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return MA_ANALYSIS.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
