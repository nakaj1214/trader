"""Precedent transaction analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import PRECEDENT
from src.core.models import AnalysisInput


class PrecedentAnalyzer(Analyzer):
    """Performs precedent transaction analysis using LLM."""

    @property
    def name(self) -> str:
        return "precedent"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue"]

    def _system_prompt(self) -> str:
        return PRECEDENT.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return PRECEDENT.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
