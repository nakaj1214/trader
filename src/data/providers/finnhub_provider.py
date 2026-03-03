"""Finnhub data provider: US stock news and sentiment.

Free plan: 60 requests/minute.
Returns empty results when FINNHUB_API_KEY is not set (degraded mode).
"""

from __future__ import annotations

import os
from typing import Any

import requests
import structlog

from src.data.providers.base import DataProvider, provider_retry

logger = structlog.get_logger(__name__)

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubProvider(DataProvider):
    """Data provider for US stock sentiment via Finnhub API."""

    @property
    def name(self) -> str:
        return "finnhub"

    def is_available(self) -> bool:
        """Check if FINNHUB_API_KEY is configured."""
        return bool(os.environ.get("FINNHUB_API_KEY"))

    @provider_retry
    def fetch_info(self, ticker: str) -> dict[str, Any] | None:
        """Fetch news sentiment for a US stock ticker.

        Returns:
            Dict with score, bullish_pct, bearish_pct, weekly_buzz, signal.
            None if API key is missing or request fails.
        """
        cache_key = f"sentiment:{ticker}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        api_key = os.environ.get("FINNHUB_API_KEY")
        if not api_key:
            return None

        try:
            r = requests.get(
                f"{BASE_URL}/news-sentiment",
                params={"symbol": ticker, "token": api_key},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()

            sentiment = data.get("sentiment", {})
            buzz = data.get("buzz", {})
            bullish = sentiment.get("bullishPercent", 0.5)
            bearish = sentiment.get("bearishPercent", 0.5)

            if bullish >= 0.60:
                signal = "bullish"
            elif bearish >= 0.60:
                signal = "bearish"
            else:
                signal = "neutral"

            result: dict[str, Any] = {
                "score": data.get("companyNewsScore"),
                "bullish_pct": bullish,
                "bearish_pct": bearish,
                "weekly_buzz": buzz.get("weeklyAverage"),
                "signal": signal,
            }
            self._cache_set(cache_key, result)
            return result
        except Exception:
            logger.warning("finnhub_sentiment_failed", ticker=ticker)
            return None
