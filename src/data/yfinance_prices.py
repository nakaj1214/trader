"""Resilient yfinance OHLCV fetcher for the JP inflection production path."""
from __future__ import annotations

import time
from collections.abc import Callable

import pandas as pd
import yfinance as yf

BATCH_SIZE = 50
CALENDAR_DAY_FACTOR = 1.5
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0


def _extract_batch(raw: pd.DataFrame, batch: list[str]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for ticker in batch:
        try:
            frame = raw.copy() if len(batch) == 1 else raw[ticker].copy()
            if frame.empty or "Close" not in frame.columns or frame["Close"].dropna().empty:
                continue
            result[ticker] = frame.dropna(subset=["Close"])
        except (KeyError, TypeError):
            continue
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
    """Fetch OHLCV with explicit adjustment semantics and retry missing batches.

    A retry is attempted not only on provider exceptions but also when yfinance
    returns a partial batch. Retries are limited to the missing symbols so a
    transient per-symbol failure does not discard an otherwise healthy batch.
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
            except Exception:
                raw = pd.DataFrame()

            found = _extract_batch(raw, pending) if not raw.empty else {}
            data.update(found)
            pending = [ticker for ticker in pending if ticker not in found]

            if pending and attempt < max_retries:
                sleep(retry_backoff_seconds * (2**attempt))

        if start + batch_size < len(tickers):
            sleep(1.0)

    return data
