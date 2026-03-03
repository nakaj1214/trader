"""LightGBM prediction model stub.

Placeholder for future LightGBM-based ensemble member.
Currently returns None for all predictions (model not yet trained).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from src.prediction.base import PredictionModel

logger = structlog.get_logger(__name__)


class LightGBMModel(PredictionModel):
    """LightGBM gradient boosting prediction model (stub).

    This model will be implemented when sufficient training data
    is available. Currently acts as a no-op ensemble member.
    """

    @property
    def name(self) -> str:
        return "lightgbm"

    def predict_stock(
        self,
        ticker: str,
        history: pd.DataFrame,
        forecast_days: int,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Placeholder: returns None until model is trained.

        Args:
            ticker: Stock ticker symbol.
            history: Historical price DataFrame.
            forecast_days: Business days to forecast ahead.
            config: Model-specific configuration.

        Returns:
            None (model not yet implemented).
        """
        logger.debug("lightgbm_not_implemented", ticker=ticker)
        return None
