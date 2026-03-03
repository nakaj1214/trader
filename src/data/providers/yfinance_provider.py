"""YFinance data provider: price data and stock info via yfinance."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import structlog
import yfinance as yf

from src.data.providers.base import DataProvider

logger = structlog.get_logger(__name__)

BATCH_SIZE = 50
BATCH_SLEEP_SECONDS = 1.0
CALENDAR_DAY_FACTOR = 1.5


class YFinanceProvider(DataProvider):
    """Data provider backed by the yfinance library."""

    @property
    def name(self) -> str:
        return "yfinance"

    def is_available(self) -> bool:
        """YFinance is always available (no API key required)."""
        return True

    def fetch_price(
        self,
        ticker: str,
        period: str = "1y",
    ) -> pd.DataFrame | None:
        """Fetch OHLCV data for a single ticker.

        Args:
            ticker: Stock symbol (e.g. "AAPL", "7203.T").
            period: yfinance period string (e.g. "1y", "6mo", "252d").

        Returns:
            DataFrame with OHLCV columns, or None on failure.
        """
        cache_key = f"price:{ticker}:{period}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            df = yf.download(ticker, period=period, progress=False)
            if df.empty or df["Close"].dropna().empty:
                return None
            result = df.dropna(subset=["Close"])
            self._cache_set(cache_key, result)
            return result
        except Exception as exc:
            logger.warning("yfinance_fetch_failed", ticker=ticker, error=str(exc))
            return None

    def fetch_batch_prices(
        self,
        tickers: list[str],
        lookback_days: int = 252,
    ) -> dict[str, pd.DataFrame]:
        """Fetch price data for multiple tickers in batches.

        Args:
            tickers: List of stock symbols.
            lookback_days: Number of trading days of history.

        Returns:
            Mapping of ticker to DataFrame.
        """
        period = f"{int(lookback_days * CALENDAR_DAY_FACTOR)}d"
        data: dict[str, pd.DataFrame] = {}

        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i : i + BATCH_SIZE]
            batch_str = " ".join(batch)
            logger.info(
                "fetching_batch",
                progress=f"{min(i + BATCH_SIZE, len(tickers))}/{len(tickers)}",
            )
            try:
                raw = yf.download(batch_str, period=period, group_by="ticker", progress=False)
            except Exception as exc:
                logger.warning("batch_fetch_error", batch_start=i, error=str(exc))
                continue

            for ticker in batch:
                try:
                    df = raw.copy() if len(batch) == 1 else raw[ticker].copy()
                    if df.empty or df["Close"].dropna().empty:
                        continue
                    result = df.dropna(subset=["Close"])
                    data[ticker] = result
                    self._cache_set(f"price:{ticker}:{period}", result)
                except (KeyError, TypeError):
                    continue

            if i + BATCH_SIZE < len(tickers):
                time.sleep(BATCH_SLEEP_SECONDS)

        logger.info("fetch_complete", fetched=len(data), requested=len(tickers))
        return data

    def fetch_info(self, ticker: str) -> dict[str, Any] | None:
        """Fetch stock info (market cap, sector, etc.) via yfinance.

        Returns:
            Dict of stock info fields, or None on failure.
        """
        cache_key = f"info:{ticker}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            info = yf.Ticker(ticker).info
            if not info:
                return None
            self._cache_set(cache_key, info)
            return info
        except Exception as exc:
            logger.warning("yfinance_info_failed", ticker=ticker, error=str(exc))
            return None
