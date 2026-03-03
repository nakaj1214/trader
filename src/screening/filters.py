"""Filter chain for stock screening: market cap, liquidity, golden cross.

Each filter operates on a pandas DataFrame and returns a filtered copy.
Stocks with unknown/missing data are retained by default to avoid
incorrectly discarding valid tickers.
"""

from __future__ import annotations

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class MarketCapFilter:
    """Removes stocks below a minimum market cap threshold."""

    def apply(self, stocks: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Filter by minimum market cap."""
        min_cap = _get_nested(config, ["filters", "market_cap", "min"],
                              fallback=config.get("min_market_cap", 0))
        if min_cap <= 0:
            return stocks
        if "market_cap" not in stocks.columns:
            return stocks

        before = len(stocks)
        mask = stocks["market_cap"].isna() | (stocks["market_cap"] >= min_cap)
        result = stocks[mask].copy()
        logger.info("market_cap_filter", before=before, after=len(result), min_cap=min_cap)
        return result


class LiquidityFilter:
    """Removes stocks with insufficient average daily dollar volume."""

    def apply(self, stocks: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Filter by average daily dollar volume (separate US/JP thresholds)."""
        min_us = _get_nested(config, ["filters", "liquidity", "min_dollar_volume_us"],
                             fallback=config.get("min_avg_dollar_volume_us", 0))
        min_jp = _get_nested(config, ["filters", "liquidity", "min_dollar_volume_jp"],
                             fallback=config.get("min_avg_dollar_volume_jp", 0))

        if min_us <= 0 and min_jp <= 0:
            return stocks
        if "avg_dollar_volume" not in stocks.columns or "ticker" not in stocks.columns:
            return stocks

        before = len(stocks)

        def _passes(row: pd.Series) -> bool:
            ticker: str = str(row["ticker"])
            addv = row.get("avg_dollar_volume")
            if addv is None or pd.isna(addv):
                return True
            is_jp = ticker.endswith(".T")
            threshold = min_jp if is_jp else min_us
            return threshold <= 0 or float(addv) >= threshold

        mask = stocks.apply(_passes, axis=1)
        result = stocks[mask].copy()
        logger.info("liquidity_filter", before=before, after=len(result))
        return result


class GoldenCrossFilter:
    """Removes stocks where SMA50 <= SMA200 (death cross)."""

    def apply(self, stocks: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Filter by golden cross condition."""
        enabled = _get_nested(config, ["filters", "golden_cross", "enabled"],
                              fallback=config.get("use_golden_cross_filter", True))
        if not enabled:
            return stocks
        if "golden_cross" not in stocks.columns:
            return stocks

        before = len(stocks)
        mask = stocks["golden_cross"].isna() | (stocks["golden_cross"] != 0.0)
        result = stocks[mask].copy()
        logger.info("golden_cross_filter", before=before, after=len(result))
        return result


class FilterChain:
    """Applies a sequence of filters to a stocks DataFrame."""

    def __init__(
        self,
        filters: list[MarketCapFilter | LiquidityFilter | GoldenCrossFilter] | None = None,
    ) -> None:
        self._filters = filters or [
            MarketCapFilter(),
            LiquidityFilter(),
            GoldenCrossFilter(),
        ]

    def apply(self, stocks: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Apply all filters in sequence."""
        result = stocks
        for flt in self._filters:
            result = flt.apply(result, config)
        return result


def _get_nested(mapping: dict, keys: list[str], fallback: object = 0) -> object:
    """Traverse nested dict by key path, returning fallback on any miss."""
    node: object = mapping
    for key in keys:
        if not isinstance(node, dict):
            return fallback
        node = node.get(key)
        if node is None:
            return fallback
    return node
