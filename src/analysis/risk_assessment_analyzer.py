"""Downside risk assessment analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import RISK_ASSESSMENT
from src.core.models import AnalysisInput


class RiskAssessmentAnalyzer(Analyzer):
    """Analyzes downside risk including industry threats and worst-case scenarios."""

    @property
    def name(self) -> str:
        return "risk_assessment"

    @property
    def required_data_fields(self) -> list[str]:
        return ["totalDebt", "revenue", "beta"]

    def _system_prompt(self) -> str:
        return RISK_ASSESSMENT.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return RISK_ASSESSMENT.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
