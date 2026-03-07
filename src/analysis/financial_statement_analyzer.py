"""Three-statement financial model analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import THREE_STATEMENT
from src.core.models import AnalysisInput


class FinancialStatementAnalyzer(Analyzer):
    """Builds a three-statement financial model using LLM."""

    @property
    def name(self) -> str:
        return "financial_statement"

    @property
    def required_data_fields(self) -> list[str]:
        return ["income_stmt", "balance_sheet", "cashflow"]

    def _system_prompt(self) -> str:
        return THREE_STATEMENT.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return THREE_STATEMENT.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
