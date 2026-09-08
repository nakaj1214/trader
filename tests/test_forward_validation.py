from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.evaluation.forward_validation import (
    GitSnapshot,
    MarketDataFetchError,
    SnapshotLoadError,
    evaluate_prediction,
    fetch_histories_yfinance,
    iter_prediction_snapshots,
    reconstruct_predictions,
    summarize_evaluations,
)


def _history(values: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(values))
    return pd.DataFrame({"Close": values}, index=idx)


def test_reconstruct_keeps_earliest_committed_prediction() -> None:
    old = GitSnapshot("a" * 40, "2026-01-01T00:00:00Z", {"predictions": [
        {"date": "2026-01-01", "ticker": "7203.T", "predicted_price": 110.0}
    ]})
    newer = GitSnapshot("b" * 40, "2026-01-08T00:00:00Z", {"predictions": [
        {"date": "2026-01-01", "ticker": "7203.T", "predicted_price": 999.0}
    ]})
    rows = reconstruct_predictions([old, newer])
    assert len(rows) == 1
    assert rows[0]["predicted_price"] == 110.0
    assert rows[0]["source_commit"] == "a" * 40


def test_evaluate_prediction_exact_horizon_math() -> None:
    history = _history([100, 102, 104, 106, 108, 110, 120, 130])
    prediction = {"date": "2026-01-01", "ticker": "7203.T", "current_price": 100.0, "predicted_price": 110.0}
    row = evaluate_prediction(prediction, history, horizons=(5,))
    assert row["reference_close"] == 100.0
    assert row["reference_price_match"] is True
    assert row["h5_close"] == 110.0
    assert row["h5_return_pct"] == 10.0
    assert row["h5_direction_hit"] is True
    assert row["h5_forecast_abs_error_pct"] == 0.0
    assert row["h5_max_return_pct"] == 10.0
    assert row["h5_min_return_pct"] == 2.0
    assert row["h5_max_drawdown_pct"] == 0.0


def test_true_drawdown_uses_intermediate_peak() -> None:
    history = _history([100, 120, 150, 105, 130, 140])
    prediction = {"date": "2026-01-01", "ticker": "7203.T", "current_price": 100.0, "predicted_price": 110.0}
    row = evaluate_prediction(prediction, history, horizons=(5,))
    assert row["h5_min_return_pct"] == 5.0
    assert row["h5_max_drawdown_pct"] == -30.0


def test_reference_price_mismatch_is_detected() -> None:
    history = _history([100, 101, 102, 103, 104, 105])
    prediction = {"date": "2026-01-01", "ticker": "7203.T", "current_price": 90.0, "predicted_price": 110.0}
    row = evaluate_prediction(prediction, history, horizons=(5,), reference_tolerance_pct=1.0)
    assert row["reference_price_match"] is False
    assert round(row["reference_price_diff_pct"], 3) == 11.111


def test_retrospective_ten_for_one_split_is_normalized() -> None:
    history = _history([3580, 3600, 3650, 3700, 3750, 3800])
    prediction = {"date": "2026-01-01", "ticker": "5801.T", "current_price": 35800.0, "predicted_price": 39000.0}
    row = evaluate_prediction(prediction, history, horizons=(5,))
    assert row["corporate_action_scale"] == 10.0
    assert row["raw_reference_close"] == 3580.0
    assert row["reference_close"] == 35800.0
    assert row["reference_price_match"] is True
    assert round(row["h5_return_pct"], 3) == round((38000 / 35800 - 1) * 100, 3)


def test_split_during_forward_window_uses_adjusted_close() -> None:
    index = pd.bdate_range("2026-01-01", periods=6)
    history = pd.DataFrame({
        "Close": [100, 102, 52, 53, 54, 55],
        "Adj Close": [50, 51, 52, 53, 54, 55],
    }, index=index)
    prediction = {"date": "2026-01-01", "ticker": "7203.T",
                  "current_price": 100.0, "predicted_price": 110.0}
    row = evaluate_prediction(prediction, history, horizons=(5,))
    assert row["corporate_action_scale"] == 2.0
    assert row["reference_close"] == 100.0
    assert row["h5_close"] == 110.0
    assert row["h5_return_pct"] == 10.0


def test_three_for_one_split_scale_is_recognized() -> None:
    prediction = {"date": "2026-01-01", "ticker": "7203.T",
                  "current_price": 300.0, "predicted_price": 330.0}
    row = evaluate_prediction(prediction, _history([100, 101, 102, 103, 104, 105]), horizons=(5,))
    assert row["corporate_action_scale"] == 3.0
    assert row["h5_return_pct"] == 5.0


def test_direction_hit_can_be_false_even_when_forecast_is_high() -> None:
    history = _history([100, 99, 98, 97, 96, 95])
    prediction = {"date": "2026-01-01", "ticker": "7203.T", "current_price": 100.0, "predicted_price": 120.0}
    row = evaluate_prediction(prediction, history, horizons=(5,))
    assert row["h5_close"] == 95.0
    assert row["h5_return_pct"] == -5.0
    assert row["h5_direction_hit"] is False
    assert row["h5_max_drawdown_pct"] == -5.0


def test_longer_horizons_are_not_scored_as_forecast_accuracy() -> None:
    history = _history(list(range(100, 131)))
    prediction = {"date": "2026-01-01", "ticker": "7203.T", "current_price": 100.0, "predicted_price": 110.0}
    row = evaluate_prediction(prediction, history, horizons=(5, 20), forecast_horizon=5)
    assert row["h5_direction_hit"] is not None
    assert row["h20_direction_hit"] is None
    assert row["h20_forecast_abs_error_pct"] is None


def test_summary_separates_data_quality_and_performance() -> None:
    rows = [
        {"date": "2026-01-01", "ticker": "A.T", "reference_price_match": True,
         "reference_price_diff_pct": 0.1, "corporate_action_scale": 1.0,
         "h5_return_pct": 10.0, "h5_direction_hit": True, "h5_forecast_abs_error_pct": 2.0,
         "h5_max_return_pct": 12.0, "h5_max_drawdown_pct": -1.0},
        {"date": "2026-01-08", "ticker": "B.T", "reference_price_match": False,
         "reference_price_diff_pct": 2.0, "corporate_action_scale": 1.0,
         "h5_return_pct": -4.0, "h5_direction_hit": False, "h5_forecast_abs_error_pct": 8.0,
         "h5_max_return_pct": 1.0, "h5_max_drawdown_pct": -7.0},
    ]
    summary = summarize_evaluations(rows, horizons=(5,))
    assert summary["data_quality"]["reference_price_match_rate_pct"] == 50.0
    assert summary["performance"]["h5"]["direction_hit_rate_pct"] == 50.0
    assert summary["performance"]["h5"]["mean_return_pct"] == 3.0


def test_snapshot_decode_failure_is_not_silently_skipped() -> None:
    log = "a" * 40 + "\t2026-01-01T00:00:00Z\n"
    with patch("src.evaluation.forward_validation._git", side_effect=[log, "not-json"]), \
            pytest.raises(SnapshotLoadError, match="Could not decode"):
        iter_prediction_snapshots(Path("."))


@pytest.mark.parametrize("history", [pd.DataFrame(), pd.DataFrame({"Volume": [1]})])
def test_forward_price_fetch_failure_is_not_silently_excluded(history: pd.DataFrame) -> None:
    ticker = Mock()
    ticker.history.return_value = history
    predictions = [{"date": "2026-01-01", "ticker": "7203.T"}]
    with patch("yfinance.Ticker", return_value=ticker), \
            pytest.raises(MarketDataFetchError, match="7203.T"):
        fetch_histories_yfinance(predictions)
