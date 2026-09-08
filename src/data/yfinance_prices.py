"""Resilient yfinance OHLCV fetcher for the JP inflection production path."""
from __future__ import annotations

import time
from collections.abc import Callable

import pandas as pd
import yfinance as yf

from src.data.validation import validate_ohlcv

BATCH_SIZE = 50
CALENDAR_DAY_FACTOR = 1.5
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0


def _extract_ticker_frame(raw: pd.DataFrame, ticker: str, batch_size: int) -> pd.DataFrame:
    """Extract one ticker from flat or singleton/multi-ticker MultiIndex data."""
    if raw.empty:
        return pd.DataFrame()
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw.copy() if batch_size == 1 else pd.DataFrame()
    for level in range(raw.columns.nlevels):
        if ticker in raw.columns.get_level_values(level):
            frame = raw.xs(ticker, axis=1, level=level, drop_level=True).copy()
            if isinstance(frame.columns, pd.MultiIndex) and frame.columns.nlevels == 1:
                frame.columns = frame.columns.get_level_values(0)
            return frame
    return pd.DataFrame()


def _extract_batch(raw: pd.DataFrame, batch: list[str]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for ticker in batch:
        frame = _extract_ticker_frame(raw, ticker, len(batch))
        if frame.empty or "Close" not in frame.columns or frame["Close"].dropna().empty:
            continue
        frame = frame.dropna(subset=["Close"])
        if validate_ohlcv(frame):
            continue
        result[ticker] = frame
    return result


def fetch_price_data(
    tickers: list[str],
    lookback_days: int,
    *,
    batch_size: int = BATCH_SIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, pd.DataFrame]:
    """Fetch raw OHLCV plus ``Adj Close`` and retry missing/invalid symbols.

    ``auto_adjust=False`` is deliberate: raw Close/Volume are needed for turnover,
    while the scanner uses Adj Close for split-aware momentum and breakout.
    """
    if not tickers:
        return {}

    period = f"{int(lookback_days * CALENDAR_DAY_FACTOR)}d"
    data: dict[str, pd.DataFrame] = {}

    for start in range(0, len(tickers), batch_size):
        original_batch = tickers[start : start + batch_size]
        pending = list(original_batch)

        for attempt in range(max_retries + 1):
            if not pending:
                break
            try:
                raw = yf.download(
                    " ".join(pending),
                    period=period,
                    group_by="ticker",
                    progress=False,
                    auto_adjust=False,
                    actions=False,
                    threads=True,
                )
            except Exception:  # noqa: BLE001 - third-party provider failures are retried uniformly
                raw = pd.DataFrame()

            found = _extract_batch(raw, pending) if not raw.empty else {}
            data.update(found)
            pending = [ticker for ticker in pending if ticker not in found]

            if pending and attempt < max_retries:
                sleep(retry_backoff_seconds * (2**attempt))

        if start + batch_size < len(tickers):
            sleep(1.0)

    return data
