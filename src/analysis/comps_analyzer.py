"""Comparable company (trading comps) analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import COMPS
from src.core.models import AnalysisInput


class CompsAnalyzer(Analyzer):
    """Performs comparable company analysis using LLM."""

    @property
    def name(self) -> str:
        return "comps"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue"]

    def _system_prompt(self) -> str:
        return COMPS.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return COMPS.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
