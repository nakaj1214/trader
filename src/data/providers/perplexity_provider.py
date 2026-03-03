"""Perplexity Sonar data provider: AI-powered stock summaries.

Uses the Perplexity chat completions API to generate concise
stock analysis summaries. Disabled by default in config.
"""

from __future__ import annotations

import os
from typing import Any

import requests
import structlog

from src.data.providers.base import DataProvider, provider_retry

logger = structlog.get_logger(__name__)

API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar"


class PerplexityProvider(DataProvider):
    """Data provider for AI-powered stock summaries via Perplexity API."""

    def __init__(self, model: str = DEFAULT_MODEL, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model = model

    @property
    def name(self) -> str:
        return "perplexity"

    def is_available(self) -> bool:
        """Check if PERPLEXITY_API_KEY is configured."""
        return bool(os.environ.get("PERPLEXITY_API_KEY"))

    @provider_retry
    def fetch_info(self, ticker: str) -> dict[str, Any] | None:
        """Fetch an AI-generated summary for the given ticker.

        Returns:
            Dict with 'summary' key containing the analysis text.
            None if API key is missing or request fails.
        """
        cache_key = f"summary:{ticker}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        api_key = os.environ.get("PERPLEXITY_API_KEY")
        if not api_key:
            return None

        prompt = (
            f"Provide a concise investment analysis for {ticker}. "
            f"Include: current market position, recent news catalysts, "
            f"key financial metrics, and short-term outlook. "
            f"Keep the response under 200 words."
        )

        try:
            r = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            choices = data.get("choices", [])
            if not choices:
                return None

            summary = choices[0].get("message", {}).get("content", "")
            result: dict[str, Any] = {"summary": summary}
            self._cache_set(cache_key, result)
            return result
        except Exception:
            logger.warning("perplexity_fetch_failed", ticker=ticker)
            return None
