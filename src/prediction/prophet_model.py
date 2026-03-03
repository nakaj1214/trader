"""Prophet prediction model: time-series forecasting with uncertainty.

Migrated from src/predictor.py with plugin architecture integration.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import structlog

from src.prediction.base import PredictionModel

logger = structlog.get_logger(__name__)

MIN_HISTORY_ROWS = 30


def compute_prob_up(predicted_change_pct: float, ci_pct: float) -> float:
    """Compute probability of positive return via normal approximation.

    Prophet fits with interval_width=0.95, so ci_pct is the half-width
    of the 95% CI. We back out sigma = ci_pct / 1.96 and compute
    P(X > 0) = Phi(mu / sigma).

    Args:
        predicted_change_pct: Predicted return (%).
        ci_pct: Half-width of 95% confidence interval (%).

    Returns:
        Probability of positive return [0.0, 1.0].
    """
    if ci_pct <= 0:
        return 1.0 if predicted_change_pct > 0 else 0.0
    sigma = ci_pct / 1.96
    z = predicted_change_pct / sigma
    return round(0.5 * (1 + math.erf(z / math.sqrt(2))), 4)


def fetch_history(ticker: str, days: int) -> pd.DataFrame:
    """Fetch closing prices from yfinance in Prophet format (ds, y).

    Args:
        ticker: Stock ticker symbol.
        days: Number of calendar days of history.

    Returns:
        DataFrame with 'ds' and 'y' columns, or empty DataFrame.
    """
    import yfinance as yf

    end = datetime.now()
    start = end - timedelta(days=days)
    df = yf.download(ticker, start=start, end=end, progress=False)
    if df.empty:
        return pd.DataFrame()

    close = df["Close"].squeeze()
    prophet_df = pd.DataFrame({
        "ds": close.index.tz_localize(None),
        "y": close.values,
    })
    return prophet_df.dropna().reset_index(drop=True)


class ProphetModel(PredictionModel):
    """Prophet-based time series prediction model."""

    @property
    def name(self) -> str:
        return "prophet"

    def predict_stock(
        self,
        ticker: str,
        history: pd.DataFrame,
        forecast_days: int,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Generate Prophet forecast for a single ticker.

        Args:
            ticker: Stock ticker symbol.
            history: DataFrame with 'ds' and 'y' columns.
            forecast_days: Business days to forecast ahead.
            config: Prophet config (changepoint_prior_scale, interval_width, etc).

        Returns:
            Prediction dict or None on failure.
        """
        if history.empty or len(history) < MIN_HISTORY_ROWS:
            logger.warning(
                "insufficient_history",
                ticker=ticker,
                rows=len(history),
                min_required=MIN_HISTORY_ROWS,
            )
            return None

        current_price = float(history["y"].iloc[-1])

        try:
            from prophet import Prophet

            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=True,
                changepoint_prior_scale=config.get("changepoint_prior_scale", 0.05),
                interval_width=config.get("interval_width", 0.95),
                uncertainty_samples=int(config.get("uncertainty_samples", 1000)),
            )
            model.fit(history)

            future = model.make_future_dataframe(periods=forecast_days, freq="B")
            forecast = model.predict(future)

            last_row = forecast.iloc[-1]
            predicted_price = float(last_row["yhat"])
            ci_lower = float(last_row["yhat_lower"])
            ci_upper = float(last_row["yhat_upper"])

            predicted_change_pct = (predicted_price - current_price) / current_price * 100
            ci_pct = (ci_upper - ci_lower) / 2 / current_price * 100

            return {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "predicted_price": round(predicted_price, 2),
                "predicted_change_pct": round(predicted_change_pct, 2),
                "ci_lower": round(ci_lower, 2),
                "ci_upper": round(ci_upper, 2),
                "ci_pct": round(ci_pct, 2),
                "prob_up": compute_prob_up(predicted_change_pct, ci_pct),
                "prob_up_calibrated": None,
                "model": self.name,
            }
        except Exception:
            logger.exception("prophet_prediction_error", ticker=ticker)
            return None
