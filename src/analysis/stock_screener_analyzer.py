"""Stock screening criteria generator analyzer."""

from __future__ import annotations

from src.analysis.base import Analyzer
from src.analysis.templates import STOCK_SCREENER
from src.core.models import AnalysisInput


class StockScreenerAnalyzer(Analyzer):
    """Generates stock screening criteria for a given investment style."""

    @property
    def name(self) -> str:
        return "stock_screener"

    @property
    def required_data_fields(self) -> list[str]:
        return []

    def _system_prompt(self) -> str:
        return STOCK_SCREENER.system_prompt

    def _user_prompt(self, data: AnalysisInput) -> str:
        style = data.params.get("style", "growth")
        sector = data.params.get("sector", "all sectors")
        market = data.params.get("market", "US")
        return STOCK_SCREENER.user_prompt.format(
            financials_summary=self._format_financials_summary(data),
            style=style,
            sector=sector,
            market=market,
        )
