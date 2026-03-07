"""Investment committee memo analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import IC_MEMO
from src.core.models import AnalysisInput


class ICMemoAnalyzer(Analyzer):
    """Generates an investment committee memo using LLM."""

    @property
    def name(self) -> str:
        return "ic_memo"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue", "ebitda"]

    def _system_prompt(self) -> str:
        return IC_MEMO.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return IC_MEMO.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
