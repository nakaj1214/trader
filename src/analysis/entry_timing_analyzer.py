"""Entry timing analysis analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import ENTRY_TIMING
from src.core.models import AnalysisInput


class EntryTimingAnalyzer(Analyzer):
    """Analyzes optimal entry points based on valuation and price action."""

    @property
    def name(self) -> str:
        return "entry_timing"

    @property
    def required_data_fields(self) -> list[str]:
        return ["revenue", "trailingPE"]

    def _system_prompt(self) -> str:
        return ENTRY_TIMING.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        return ENTRY_TIMING.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
        )
