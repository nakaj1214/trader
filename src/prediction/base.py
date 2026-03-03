"""Prediction model ABC: common interface for all forecasting models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class PredictionModel(ABC):
    """Abstract base class for stock price prediction models.

    Subclasses implement `predict_stock` for single-ticker forecasting
    and optionally override `predict_batch` for batch processing.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable model name (e.g. 'prophet', 'lightgbm')."""

    @abstractmethod
    def predict_stock(
        self,
        ticker: str,
        history: pd.DataFrame,
        forecast_days: int,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Generate a prediction for a single ticker.

        Args:
            ticker: Stock ticker symbol.
            history: Historical price DataFrame with 'ds' and 'y' columns
                     (Prophet format) or OHLCV columns depending on model.
            forecast_days: Number of business days to forecast ahead.
            config: Model-specific configuration dict.

        Returns:
            Dict with keys: ticker, current_price, predicted_price,
            predicted_change_pct, ci_lower, ci_upper, ci_pct, prob_up.
            None if prediction fails.
        """

    def predict_batch(
        self,
        tickers: list[str],
        history_map: dict[str, pd.DataFrame],
        forecast_days: int,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate predictions for multiple tickers.

        Default implementation calls predict_stock in a loop.
        Override for models that support batch inference.

        Returns:
            List of prediction dicts (failures are excluded).
        """
        results: list[dict[str, Any]] = []
        for ticker in tickers:
            history = history_map.get(ticker)
            if history is None or history.empty:
                logger.warning("no_history_for_ticker", ticker=ticker, model=self.name)
                continue
            result = self.predict_stock(ticker, history, forecast_days, config)
            if result is not None:
                results.append(result)
        return results
