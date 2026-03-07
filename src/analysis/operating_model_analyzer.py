"""Operating model and unit economics analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import OPERATING_MODEL
from src.core.models import AnalysisInput


class OperatingModelAnalyzer(Analyzer):
    """Builds an operating model using LLM."""

    @property
    def name(self) -> str:
        return "operating_model"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue"]

    def _system_prompt(self) -> str:
        return OPERATING_MODEL.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return OPERATING_MODEL.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
