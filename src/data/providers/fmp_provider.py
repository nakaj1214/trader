"""Financial Modeling Prep data provider: global financial metrics fallback.

Free plan: 250 requests/day.
Returns empty results when FMP_API_KEY is not set (degraded mode).
"""

from __future__ import annotations

import os
from typing import Any

import requests
import structlog

from src.data.providers.base import DataProvider, provider_retry

logger = structlog.get_logger(__name__)

BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPProvider(DataProvider):
    """Data provider for financial metrics via FMP API."""

    @property
    def name(self) -> str:
        return "fmp"

    def is_available(self) -> bool:
        """Check if FMP_API_KEY is configured."""
        return bool(os.environ.get("FMP_API_KEY"))

    @provider_retry
    def fetch_info(self, ticker: str) -> dict[str, Any] | None:
        """Fetch key financial metrics (PBR, ROE) for a ticker.

        Works with both US tickers ("AAPL") and JP tickers ("7203.T").

        Returns:
            Dict with priceToBook and returnOnEquity fields.
            None if API key is missing or request fails.
        """
        cache_key = f"metrics:{ticker}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        api_key = os.environ.get("FMP_API_KEY")
        if not api_key:
            return None

        try:
            r = requests.get(
                f"{BASE_URL}/key-metrics/{ticker}",
                params={"period": "quarter", "limit": 1, "apikey": api_key},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                self._cache_set(cache_key, {})
                return {}

            latest = data[0]
            result: dict[str, Any] = {}

            if (pb := latest.get("pbRatio")) is not None:
                try:
                    result["priceToBook"] = float(pb)
                except (ValueError, TypeError):
                    pass
            if (roe := latest.get("roe")) is not None:
                try:
                    result["returnOnEquity"] = float(roe)
                except (ValueError, TypeError):
                    pass

            self._cache_set(cache_key, result)
            return result
        except Exception:
            logger.warning("fmp_metrics_failed", ticker=ticker)
            return None
