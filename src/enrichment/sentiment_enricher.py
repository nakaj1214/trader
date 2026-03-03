"""Sentiment enricher: news sentiment, short interest, institutional holders.

Migrated from src/enricher.py: _enrich_news_sentiment, enrich_short_interest,
enrich_institutional_holders, enrich_52w_high.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from src.enrichment.base import Enricher, is_jp_ticker

logger = structlog.get_logger(__name__)


class SentimentEnricher(Enricher):
    """Aggregate sentiment signals: news, short interest, institutional, 52w high."""

    @property
    def name(self) -> str:
        return "sentiment"

    def enrich_ticker(
        self,
        ticker: str,
        stock_df: pd.DataFrame | None,
        info: dict[str, Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Collect all sentiment-related signals for a ticker."""
        result: dict[str, Any] = {}

        news = _fetch_news_sentiment(ticker, config)
        if news is not None:
            result["news_sentiment"] = news

        short_int = _enrich_short_interest(ticker, info)
        if short_int is not None:
            result["short_interest"] = short_int

        w52 = _enrich_52w_high(ticker, info)
        if w52 is not None:
            result["fifty2w_score"] = w52["fifty2w_score"]
            result["fifty2w_pct_from_high"] = w52["fifty2w_pct_from_high"]

        return result if result else None


def _fetch_news_sentiment(
    ticker: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Fetch news sentiment from Finnhub for US stocks.

    Returns None for JP stocks, disabled config, or API failures.
    """
    finnhub_cfg = config.get("providers", {}).get("finnhub", {})
    if not finnhub_cfg.get("enabled", True):
        return None
    if is_jp_ticker(ticker):
        return None

    try:
        from src.data.providers.finnhub_provider import FinnhubProvider

        provider = FinnhubProvider()
        if not provider.is_available():
            return None
        return provider.fetch_info(ticker)
    except Exception:
        logger.warning("news_sentiment_fetch_failed", ticker=ticker)
        return None


def _enrich_short_interest(
    ticker: str,
    info: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract short interest data as supplemental info.

    Not used in scoring. Monthly data from yfinance.
    """
    try:
        short_ratio = info.get("shortRatio")
        short_pct = info.get("shortPercentOfFloat")

        if short_pct is not None:
            pct = float(short_pct)
            if pct > 0.20:
                signal = "high_short"
            elif pct > 0.10:
                signal = "moderate_short"
            else:
                signal = "neutral"
        else:
            signal = "neutral"

        return {
            "short_ratio": round(float(short_ratio), 2) if short_ratio is not None else None,
            "short_pct_float": round(float(short_pct), 4) if short_pct is not None else None,
            "signal": signal,
            "data_note": "Monthly data, reference only (yfinance)",
        }
    except Exception:
        logger.warning("short_interest_fetch_failed", ticker=ticker)
        return None


def _enrich_52w_high(
    ticker: str,
    info: dict[str, Any],
) -> dict[str, Any] | None:
    """Compute 52-week high momentum indicator.

    Returns:
        Dict with fifty2w_score and fifty2w_pct_from_high, or None.
    """
    try:
        current = info.get("currentPrice") or info.get("regularMarketPrice")
        high52 = info.get("fiftyTwoWeekHigh")

        if current is None or high52 is None:
            return None

        current_f = float(current)
        high52_f = float(high52)
        if high52_f <= 0:
            return None

        ratio = current_f / high52_f
        return {
            "fifty2w_score": round(min(ratio, 1.0), 4),
            "fifty2w_pct_from_high": round(ratio - 1.0, 4),
        }
    except Exception:
        logger.warning("52w_high_fetch_failed", ticker=ticker)
        return None
