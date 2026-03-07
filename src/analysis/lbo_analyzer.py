"""Leveraged buyout (LBO) analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import LBO
from src.core.models import AnalysisInput


class LBOAnalyzer(Analyzer):
    """Performs LBO analysis using LLM."""

    @property
    def name(self) -> str:
        return "lbo"

    @property
    def required_data_fields(self) -> list[str]:
        return ["ebitda", "revenue"]

    def _system_prompt(self) -> str:
        return LBO.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return LBO.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
