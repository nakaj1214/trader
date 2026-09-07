from __future__ import annotations

import pandas as pd

from src.evaluation.forward_validation import (
    evaluate_prediction,
    reconstruct_predictions,
    summarize_evaluations,
    GitSnapshot,
)


def _history(values: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(values))
    return pd.DataFrame({"Close": values}, index=idx)


def test_reconstruct_keeps_earliest_committed_prediction() -> None:
    old = GitSnapshot(
        sha="a" * 40,
        committed_at="2026-01-01T00:00:00Z",
        payload={"predictions": [{"date": "2026-01-01", "ticker": "7203.T", "predicted_price": 110.0}]},
    )
    newer = GitSnapshot(
        sha="b" * 40,
        committed_at="2026-01-08T00:00:00Z",
        payload={"predictions": [{"date": "2026-01-01", "ticker": "7203.T", "predicted_price": 999.0}]},
    )
    rows = reconstruct_predictions([old, newer])
    assert len(rows) == 1
    assert rows[0]["predicted_price"] == 110.0
    assert rows[0]["source_commit"] == "a" * 40


def test_evaluate_prediction_exact_horizon_math() -> None:
    history = _history([100, 102, 104, 106, 108, 110, 120, 130])
    prediction = {
        "date": "2026-01-01",
        "ticker": "7203.T",
        "current_price": 100.0,
        "predicted_price": 110.0,
    }
    row = evaluate_prediction(prediction, history, horizons=(5,))
    assert row["reference_close"] == 100.0
    assert row["reference_price_match"] is True
    assert row["h5_close"] == 110.0
    assert row["h5_return_pct"] == 10.0
    assert row["h5_direction_hit"] is True
    assert row["h5_forecast_abs_error_pct"] == 0.0
    assert row["h5_max_return_pct"] == 10.0
    assert row["h5_max_drawdown_pct"] == 2.0


def test_reference_price_mismatch_is_detected() -> None:
    history = _history([100, 101, 102, 103, 104, 105])
    prediction = {
        "date": "2026-01-01",
        "ticker": "7203.T",
        "current_price": 90.0,
        "predicted_price": 110.0,
    }
    row = evaluate_prediction(prediction, history, horizons=(5,), reference_tolerance_pct=1.0)
    assert row["reference_price_match"] is False
    assert round(row["reference_price_diff_pct"], 3) == 11.111


def test_direction_hit_can_be_false_even_when_forecast_is_high() -> None:
    history = _history([100, 99, 98, 97, 96, 95])
    prediction = {
        "date": "2026-01-01",
        "ticker": "7203.T",
        "current_price": 100.0,
        "predicted_price": 120.0,
    }
    row = evaluate_prediction(prediction, history, horizons=(5,))
    assert row["h5_close"] == 95.0
    assert row["h5_return_pct"] == -5.0
    assert row["h5_direction_hit"] is False
    assert row["h5_max_drawdown_pct"] == -5.0


def test_summary_separates_data_quality_and_performance() -> None:
    rows = [
        {
            "date": "2026-01-01",
            "ticker": "A.T",
            "reference_price_match": True,
            "reference_price_diff_pct": 0.1,
            "h5_return_pct": 10.0,
            "h5_direction_hit": True,
            "h5_forecast_abs_error_pct": 2.0,
            "h5_max_return_pct": 12.0,
            "h5_max_drawdown_pct": -1.0,
        },
        {
            "date": "2026-01-08",
            "ticker": "B.T",
            "reference_price_match": False,
            "reference_price_diff_pct": 2.0,
            "h5_return_pct": -4.0,
            "h5_direction_hit": False,
            "h5_forecast_abs_error_pct": 8.0,
            "h5_max_return_pct": 1.0,
            "h5_max_drawdown_pct": -7.0,
        },
    ]
    summary = summarize_evaluations(rows, horizons=(5,))
    assert summary["data_quality"]["reference_price_match_rate_pct"] == 50.0
    assert summary["performance"]["h5"]["direction_hit_rate_pct"] == 50.0
    assert summary["performance"]["h5"]["mean_return_pct"] == 3.0
