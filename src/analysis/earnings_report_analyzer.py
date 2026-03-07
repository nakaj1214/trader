"""Earnings report breakdown analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import EARNINGS_REPORT
from src.core.models import AnalysisInput


class EarningsReportAnalyzer(Analyzer):
    """Breaks down earnings reports into actionable insights."""

    @property
    def name(self) -> str:
        return "earnings_report"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue", "netIncome", "income_stmt"]

    def _system_prompt(self) -> str:
        return EARNINGS_REPORT.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return EARNINGS_REPORT.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
