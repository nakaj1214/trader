"""Shared test fixtures for the trader test suite."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Minimal test configuration dict."""
    return {
        "screening": {
            "markets": ["sp500"],
            "top_n": 3,
            "lookback_days": 252,
            "filters": {
                "market_cap": {"min": 0},
                "liquidity": {"min_dollar_volume_us": 0, "min_dollar_volume_jp": 0},
                "golden_cross": {"enabled": False},
                "earnings_exclusion": {"days": 5},
            },
            "scoring": {
                "weights": {
                    "price_change_1m": 0.20,
                    "volume_trend": 0.15,
                    "rsi_score": 0.15,
                    "macd_signal": 0.15,
                    "fifty2w_score": 0.15,
                    "bb_position": 0.10,
                    "adx_score": 0.10,
                }
            },
        },
        "prediction": {
            "model": "prophet",
            "history_days": 30,
            "forecast_days": 5,
            "prophet": {
                "interval_width": 0.95,
                "changepoint_prior_scale": 0.05,
                "uncertainty_samples": 100,
            },
            "guardrail": {"clip_pct": 30.0, "warn_pct": 20.0},
            "ensemble": {"weights": {"prophet": 0.4, "lightgbm": 0.6}},
        },
        "providers": {
            "jquants": {"enabled": False},
            "finnhub": {"enabled": False},
            "fmp": {"enabled": False},
            "fred": {"enabled": False},
            "perplexity": {"enabled": False},
        },
        "export": {
            "google_sheets": {
                "spreadsheet_name": "trade",
                "worksheet_name": "predictions",
            }
        },
        "notification": {
            "slack": {"enabled": False, "channel": "#test", "chart_enabled": False, "channel_id": ""},
            "line": {"enabled": False},
            "beginner_mode": False,
            "chart": {"lookback_days": 60},
        },
        "enrichment": {
            "sizing": {
                "vol_target_ann": 0.10,
                "max_weight_cap": 0.20,
                "stop_loss_multiplier": 1.0,
            }
        },
        "evaluation": {
            "backtest": {
                "num_rules_tested": 1,
                "num_parameters_tuned": 4,
                "oos_start": "2025-01-01",
                "min_rules_for_pbo": 2,
            },
            "walkforward": {
                "train_weeks": 52,
                "test_weeks": 13,
                "min_train_weeks": 26,
            },
        },
        "data": {"price_column": "Close"},
    }


@pytest.fixture
def sample_screened_df() -> pd.DataFrame:
    """Sample screened stocks DataFrame."""
    return pd.DataFrame({
        "ticker": ["AAPL", "MSFT", "GOOGL"],
        "current_price": [150.0, 300.0, 120.0],
        "score": [0.85, 0.80, 0.75],
        "price_change_1m": [0.05, 0.03, 0.04],
        "rsi": [55.0, 48.0, 52.0],
        "macd_bullish": [1.0, 1.0, 0.0],
    })


@pytest.fixture
def sample_predictions_df() -> pd.DataFrame:
    """Sample predictions DataFrame."""
    return pd.DataFrame({
        "ticker": ["AAPL", "MSFT"],
        "current_price": [150.0, 300.0],
        "predicted_price": [158.0, 312.0],
        "predicted_change_pct": [5.33, 4.0],
        "ci_pct": [8.0, 7.5],
        "prob_up": [0.75, 0.70],
        "prob_up_calibrated": [None, None],
        "model": ["prophet", "prophet"],
    })


@pytest.fixture
def sample_prediction_records() -> list[dict[str, Any]]:
    """Sample prediction records in DB format."""
    return [
        {
            "date": "2025-01-06",
            "ticker": "AAPL",
            "current_price": 150.0,
            "predicted_price": 158.0,
            "predicted_change_pct": 5.33,
            "confidence_interval_pct": 8.0,
            "prob_up": 0.75,
            "prob_up_calibrated": None,
            "actual_price": 155.0,
            "is_hit": True,
            "status": "confirmed",
        },
        {
            "date": "2025-01-06",
            "ticker": "MSFT",
            "current_price": 300.0,
            "predicted_price": 312.0,
            "predicted_change_pct": 4.0,
            "confidence_interval_pct": 7.5,
            "prob_up": 0.70,
            "prob_up_calibrated": None,
            "actual_price": 295.0,
            "is_hit": False,
            "status": "confirmed",
        },
        {
            "date": "2025-01-13",
            "ticker": "GOOGL",
            "current_price": 120.0,
            "predicted_price": 126.0,
            "predicted_change_pct": 5.0,
            "confidence_interval_pct": 9.0,
            "prob_up": 0.68,
            "prob_up_calibrated": None,
            "actual_price": None,
            "is_hit": None,
            "status": "predicted",
        },
    ]


@pytest.fixture
def mock_yf_download(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock yfinance.download to return dummy price data."""
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    mock_df = pd.DataFrame(
        {
            "Open": [100.0 + i * 0.5 for i in range(60)],
            "High": [101.0 + i * 0.5 for i in range(60)],
            "Low": [99.0 + i * 0.5 for i in range(60)],
            "Close": [100.0 + i * 0.5 for i in range(60)],
            "Volume": [1000000] * 60,
        },
        index=dates,
    )
    mock = MagicMock(return_value=mock_df)
    monkeypatch.setattr("yfinance.download", mock)
    return mock
