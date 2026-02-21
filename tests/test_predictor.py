"""predictor のテスト: 営業日基準で予測日が進むこと。"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# --- compute_prob_up ---


def test_compute_prob_up_center():
    """予測変化 = 0 のとき prob_up = 0.5 になること。"""
    from src.predictor import compute_prob_up
    assert abs(compute_prob_up(0.0, 5.0) - 0.5) < 1e-4


def test_compute_prob_up_positive():
    """正の予測変化のとき prob_up > 0.5 になること。"""
    from src.predictor import compute_prob_up
    assert compute_prob_up(5.0, 5.0) > 0.5


def test_compute_prob_up_negative():
    """負の予測変化のとき prob_up < 0.5 になること。"""
    from src.predictor import compute_prob_up
    assert compute_prob_up(-5.0, 5.0) < 0.5


def test_compute_prob_up_zero_ci():
    """ci_pct = 0 のとき、prob_up は 1.0 (正) または 0.0 (負) になること。"""
    from src.predictor import compute_prob_up
    assert compute_prob_up(5.0, 0.0) == 1.0
    assert compute_prob_up(-5.0, 0.0) == 0.0


def test_compute_prob_up_symmetry():
    """prob_up(+x) + prob_up(-x) = 1.0 になること（正規分布の対称性）。"""
    from src.predictor import compute_prob_up
    p_pos = compute_prob_up(3.0, 6.0)
    p_neg = compute_prob_up(-3.0, 6.0)
    assert abs(p_pos + p_neg - 1.0) < 1e-4


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


# ---------------------------------------------------------------------------
# Phase 25: Prophet config 読み込みテスト
# ---------------------------------------------------------------------------

def test_predict_stock_uses_prophet_cfg():
    """predict_stock() が prophet_cfg のパラメータを Prophet に渡すこと。"""
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

    prophet_cfg = {
        "interval_width": 0.95,
        "changepoint_prior_scale": 0.1,
        "uncertainty_samples": 500,
    }

    with (
        patch("src.predictor.fetch_history", return_value=history_df),
        patch("src.predictor.Prophet", return_value=mock_model) as mock_prophet,
    ):
        from src.predictor import predict_stock
        predict_stock("TEST", history_days=90, forecast_days=5, prophet_cfg=prophet_cfg)

    init_kwargs = mock_prophet.call_args[1]
    assert init_kwargs["changepoint_prior_scale"] == pytest.approx(0.1)
    assert init_kwargs["interval_width"] == pytest.approx(0.95)
    assert init_kwargs["uncertainty_samples"] == 500


def test_predict_passes_prophet_cfg_to_predict_stock():
    """predict() が config["prophet"] を predict_stock() に渡すこと。"""
    from src.predictor import predict

    mock_results = [
        {"ticker": "AAPL", "current_price": 100, "predicted_price": 110,
         "predicted_change_pct": 10.0, "ci_lower": 105, "ci_upper": 115, "ci_pct": 5.0},
    ]
    screened_df = pd.DataFrame({"ticker": ["AAPL"]})
    prophet_cfg = {"interval_width": 0.95, "changepoint_prior_scale": 0.1}

    with patch("src.predictor.predict_stock", side_effect=mock_results) as mock_ps:
        predict(
            screened_df,
            config={
                "prediction": {"history_days": 90, "forecast_days": 5},
                "prophet": prophet_cfg,
            },
        )

    # predict_stock に prophet_cfg が渡されていること（4番目の positional arg）
    call_args = mock_ps.call_args[0]
    assert call_args[3] == prophet_cfg


def test_predict_stock_defaults_when_no_prophet_cfg():
    """prophet_cfg=None の場合、デフォルト値（interval_width=0.95）で動作すること。"""
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
        patch("src.predictor.Prophet", return_value=mock_model) as mock_prophet,
    ):
        from src.predictor import predict_stock
        predict_stock("TEST", history_days=90, forecast_days=5, prophet_cfg=None)

    init_kwargs = mock_prophet.call_args[1]
    assert init_kwargs["interval_width"] == pytest.approx(0.95)
    assert init_kwargs["changepoint_prior_scale"] == pytest.approx(0.05)
    assert init_kwargs["uncertainty_samples"] == 1000
