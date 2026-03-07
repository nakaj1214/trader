"""Abstract base class for financial analyzers.

All analyzers implement this interface, providing a consistent
way to run LLM-driven financial analyses with structured output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import structlog

from src.analysis.llm_client import LLMClient
from src.core.models import AnalysisInput, AnalysisResult

logger = structlog.get_logger(__name__)


class Analyzer(ABC):
    """Abstract base for all financial analyzers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Analysis type identifier (e.g. 'dcf', 'comps')."""

    @property
    @abstractmethod
    def required_data_fields(self) -> list[str]:
        """List of required fields in AnalysisInput.financials."""

    @abstractmethod
    def _system_prompt(self) -> str:
        """Return the system prompt for the LLM (role setting)."""

    @abstractmethod
    def _user_prompt(self, data: AnalysisInput) -> str:
        """Return the user prompt with injected financial data."""

    def analyze(
        self,
        data: AnalysisInput,
        llm: LLMClient,
    ) -> AnalysisResult:
        """Run the analysis on the given input data.

        Args:
            data: Financial data for the target company.
            llm: LLM client to generate the analysis.

        Returns:
            AnalysisResult with the generated content.

        Raises:
            ValueError: If required data fields are missing.
        """
        self._validate_input(data)

        system_prompt = self._system_prompt()
        user_prompt = self._user_prompt(data)

        logger.info(
            "analysis_started",
            analyzer=self.name,
            ticker=data.ticker,
        )

        content, token_count = llm.generate(user_prompt, system_prompt)

        return AnalysisResult(
            ticker=data.ticker,
            analysis_type=self.name,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_used=llm._config.model,
            token_count=token_count,
        )

    def _validate_input(self, data: AnalysisInput) -> None:
        """Validate that required financial data fields are present."""
        missing = [
            field for field in self.required_data_fields
            if field not in data.financials or data.financials[field] is None
        ]
        if missing:
            logger.warning(
                "analysis_data_incomplete",
                analyzer=self.name,
                ticker=data.ticker,
                missing_fields=missing,
            )

    def _format_financials_summary(self, data: AnalysisInput) -> str:
        """Format financial data into a readable summary for the LLM."""
        lines = [
            f"Company: {data.company_name} ({data.ticker})",
        ]
        if data.sector:
            lines.append(f"Sector: {data.sector}")
        if data.industry:
            lines.append(f"Industry: {data.industry}")
        if data.market_cap is not None:
            lines.append(f"Market Cap: ${data.market_cap:,.0f}")

        if data.financials:
            lines.append("")
            lines.append("Financial Data:")
            for key, value in data.financials.items():
                if value is not None:
                    if isinstance(value, float):
                        lines.append(f"  {key}: ${value:,.2f}")
                    else:
                        lines.append(f"  {key}: {value}")

        return "\n".join(lines)
