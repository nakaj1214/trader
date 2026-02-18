"""predictor のテスト: 営業日基準で予測日が進むこと。"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def test_make_future_dataframe_uses_business_days():
    """make_future_dataframe に freq='B' が渡されることを検証する。"""
    # Prophet をモック化
    mock_model = MagicMock()
    mock_model.make_future_dataframe.return_value = pd.DataFrame({"ds": []})
    mock_model.predict.return_value = pd.DataFrame({
        "ds": ["2026-02-20"],
        "yhat": [100.0],
        "yhat_lower": [95.0],
        "yhat_upper": [105.0],
    })

    history_df = pd.DataFrame({
        "ds": pd.bdate_range("2025-11-01", periods=60),
        "y": range(100, 160),
    })

    with (
        patch("src.predictor.fetch_history", return_value=history_df),
        patch("src.predictor.Prophet", return_value=mock_model),
    ):
        from src.predictor import predict_stock
        predict_stock("TEST", history_days=90, forecast_days=5)

    # freq="B" が渡されていることを確認
    mock_model.make_future_dataframe.assert_called_once_with(periods=5, freq="B")


def test_predict_filters_bullish_only():
    """上昇予測のみがフィルタリングされることを検証する。"""
    from src.predictor import predict

    mock_results = [
        {"ticker": "UP1", "current_price": 100, "predicted_price": 110,
         "predicted_change_pct": 10.0, "ci_lower": 105, "ci_upper": 115, "ci_pct": 5.0},
        {"ticker": "DOWN1", "current_price": 100, "predicted_price": 90,
         "predicted_change_pct": -10.0, "ci_lower": 85, "ci_upper": 95, "ci_pct": 5.0},
        {"ticker": "UP2", "current_price": 200, "predicted_price": 210,
         "predicted_change_pct": 5.0, "ci_lower": 205, "ci_upper": 215, "ci_pct": 2.5},
    ]

    screened_df = pd.DataFrame({"ticker": ["UP1", "DOWN1", "UP2"]})

    with patch("src.predictor.predict_stock", side_effect=mock_results):
        result = predict(screened_df, config={"prediction": {"history_days": 90, "forecast_days": 5}})

    assert len(result) == 2
    assert list(result["ticker"]) == ["UP1", "UP2"]
    assert all(result["predicted_change_pct"] > 0)
