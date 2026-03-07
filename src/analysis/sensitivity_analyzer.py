"""Sensitivity and scenario analysis analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import SENSITIVITY
from src.core.models import AnalysisInput


class SensitivityAnalyzer(Analyzer):
    """Performs sensitivity and scenario analysis using LLM."""

    @property
    def name(self) -> str:
        return "sensitivity"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue", "ebitda"]

    def _system_prompt(self) -> str:
        return SENSITIVITY.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return SENSITIVITY.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
