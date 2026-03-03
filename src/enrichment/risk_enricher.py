"""Risk enricher: volatility, beta, max drawdown.

Migrated from src/enricher.py compute_risk_metrics().
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import structlog

from src.enrichment.base import Enricher

logger = structlog.get_logger(__name__)

TRADING_DAYS_PER_YEAR = 252


class RiskEnricher(Enricher):
    """Compute risk metrics: 20d/60d annualized vol, beta, max drawdown."""

    @property
    def name(self) -> str:
        return "risk"

    def enrich_ticker(
        self,
        ticker: str,
        stock_df: pd.DataFrame | None,
        info: dict[str, Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Compute risk metrics for a single ticker.

        Requires stock_df and spy_df (passed via kwargs).
        """
        if stock_df is None or stock_df.empty:
            return None

        spy_df = kwargs.get("spy_df")
        lookback_days = config.get("enrichment", {}).get("risk_lookback_days", 90)

        return compute_risk_metrics(stock_df, spy_df, lookback_days)


def compute_risk_metrics(
    df: pd.DataFrame,
    spy_df: pd.DataFrame | None,
    lookback_days: int = 90,
) -> dict[str, Any]:
    """Compute risk metrics for a stock.

    Args:
        df: Stock price DataFrame with 'Close' column.
        spy_df: SPY price DataFrame for beta calculation.
        lookback_days: Window for beta computation.

    Returns:
        Dict with vol_20d_ann, vol_60d_ann, beta, max_drawdown_1y.
    """
    close = df["Close"].squeeze()
    returns = close.pct_change().dropna()

    vol_20 = _annualized_vol(returns, 20)
    vol_60 = _annualized_vol(returns, 60)
    beta = _compute_beta(returns, spy_df, lookback_days)
    max_dd = _max_drawdown(close, TRADING_DAYS_PER_YEAR)

    return {
        "vol_20d_ann": round(vol_20, 4),
        "vol_60d_ann": round(vol_60, 4),
        "beta": round(beta, 2),
        "max_drawdown_1y": round(max_dd, 4),
    }


def _annualized_vol(returns: pd.Series, window: int) -> float:
    """Compute annualized volatility over the last N days."""
    if len(returns) >= window:
        std = float(returns.iloc[-window:].std())
    elif len(returns) > 1:
        std = float(returns.std())
    else:
        return 0.0
    return std * math.sqrt(TRADING_DAYS_PER_YEAR)


def _compute_beta(
    returns: pd.Series,
    spy_df: pd.DataFrame | None,
    lookback_days: int,
) -> float:
    """Compute beta against SPY."""
    if spy_df is None or spy_df.empty:
        return 1.0

    spy_close = spy_df["Close"].squeeze()
    spy_returns = spy_close.pct_change().dropna()

    common_idx = returns.index.intersection(spy_returns.index)
    if len(common_idx) < max(lookback_days, 20):
        r = returns.loc[common_idx]
        s = spy_returns.loc[common_idx]
    else:
        r = returns.loc[common_idx].iloc[-lookback_days:]
        s = spy_returns.loc[common_idx].iloc[-lookback_days:]

    if len(r) <= 1 or s.var() <= 0:
        return 1.0

    cov = np.cov(r.values, s.values)[0][1]
    return float(cov / s.var())


def _max_drawdown(close: pd.Series, window: int) -> float:
    """Compute maximum drawdown over the last N trading days."""
    dd_window = min(window, len(close))
    dd_close = close.iloc[-dd_window:]
    cummax = dd_close.cummax()
    drawdown = (dd_close - cummax) / cummax
    return float(drawdown.min()) if len(drawdown) > 0 else 0.0
