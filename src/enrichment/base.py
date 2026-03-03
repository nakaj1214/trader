"""Enricher ABC: common interface for all enrichment processors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


def is_jp_ticker(ticker: str) -> bool:
    """Check if a ticker is a Japanese stock (yfinance format: e.g. 7203.T)."""
    return str(ticker).upper().endswith(".T")


class Enricher(ABC):
    """Abstract base class for enrichment processors.

    Each enricher adds a specific type of supplemental data
    (risk metrics, events, sentiment, etc.) to prediction records.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Enricher identifier (e.g. 'risk', 'events', 'sentiment')."""

    @abstractmethod
    def enrich_ticker(
        self,
        ticker: str,
        stock_df: pd.DataFrame | None,
        info: dict[str, Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Enrich a single ticker with supplemental data.

        Args:
            ticker: Stock ticker symbol.
            stock_df: Historical price DataFrame (may be None).
            info: Ticker info dict (from yfinance or providers).
            config: Application config dict.
            **kwargs: Additional context (peer_data, spy_df, etc).

        Returns:
            Enrichment data dict, or None if enrichment is not available.
        """


def enrich_all(
    tickers: list[str],
    date: str,
    stock_data: dict[str, pd.DataFrame],
    spy_df: pd.DataFrame | None,
    info_cache: dict[str, dict[str, Any]],
    config: dict[str, Any],
    enrichers: list[Enricher] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Run all enrichers on the given tickers.

    Args:
        tickers: List of ticker symbols to enrich.
        date: Prediction date string.
        stock_data: Mapping of ticker -> price DataFrame.
        spy_df: SPY benchmark DataFrame.
        info_cache: Mapping of ticker -> info dict.
        config: Application configuration.
        enrichers: List of enricher instances. If None, uses defaults.

    Returns:
        Mapping of (date, ticker) -> combined enrichment dict.
    """
    if enrichers is None:
        enrichers = _default_enrichers()

    enrichment: dict[tuple[str, str], dict[str, Any]] = {}

    for ticker in tickers:
        key = (date, ticker)
        combined: dict[str, Any] = {}
        stock_df = stock_data.get(ticker)
        info = info_cache.get(ticker, {})

        for enricher in enrichers:
            try:
                result = enricher.enrich_ticker(
                    ticker=ticker,
                    stock_df=stock_df,
                    info=info,
                    config=config,
                    spy_df=spy_df,
                    peer_data=_build_peer_data(tickers, stock_data, info_cache),
                )
                if result is not None:
                    combined[enricher.name] = result
            except Exception:
                logger.warning(
                    "enricher_failed",
                    enricher=enricher.name,
                    ticker=ticker,
                )

        if combined:
            enrichment[key] = combined

    return enrichment


def _build_peer_data(
    tickers: list[str],
    stock_data: dict[str, pd.DataFrame],
    info_cache: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build peer data list for evidence signal z-score computation."""
    return [
        {
            "ticker": t,
            "info": info_cache.get(t, {}),
            "df": stock_data.get(t),
        }
        for t in tickers
    ]


def _default_enrichers() -> list[Enricher]:
    """Import and instantiate the default set of enrichers."""
    from src.enrichment.event_enricher import EventEnricher
    from src.enrichment.evidence_enricher import EvidenceEnricher
    from src.enrichment.risk_enricher import RiskEnricher
    from src.enrichment.sentiment_enricher import SentimentEnricher
    from src.enrichment.sizing_enricher import SizingEnricher

    return [
        RiskEnricher(),
        EventEnricher(),
        EvidenceEnricher(),
        SentimentEnricher(),
        SizingEnricher(),
    ]
