"""Abstract base class for data providers.

All data providers implement this interface, enabling pluggable
data sources with consistent caching, retry, and availability checks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
import structlog
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = structlog.get_logger(__name__)

# Default retry decorator for network calls
provider_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise=True,
)


class DataProvider(ABC):
    """Abstract base for all data providers."""

    def __init__(self, cache_ttl: int = 3600, cache_maxsize: int = 512) -> None:
        self._cache: TTLCache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl)

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""

    def fetch_price(
        self,
        ticker: str,
        period: str = "1y",
    ) -> pd.DataFrame | None:
        """Fetch OHLCV price data for a ticker.

        Override in subclasses that provide price data.
        Returns None by default (provider does not supply prices).
        """
        return None

    def fetch_info(self, ticker: str) -> dict[str, Any] | None:
        """Fetch supplementary info (fundamentals, sentiment, etc.).

        Override in subclasses that provide non-price data.
        Returns None by default.
        """
        return None

    def _cache_get(self, key: str) -> Any | None:
        """Retrieve a value from the session cache."""
        return self._cache.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        """Store a value in the session cache."""
        self._cache[key] = value
