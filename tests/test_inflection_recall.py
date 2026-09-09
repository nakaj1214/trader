from __future__ import annotations

import pandas as pd

from src.evaluation.inflection_recall import compute_tracked_pool_explosion_recall


def _history(values: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    return pd.DataFrame({"Close": values}, index=pd.bdate_range(start, periods=len(values)))


def test_tracked_pool_recall_counts_detection_and_exclusions() -> None:
    observations = [
        {"ticker": "A.T", "signal_date": "2026-01-02", "classification": "EARLY_CANDIDATE"},
        {"ticker": "B.T", "signal_date": "2026-01-02", "classification": "NONE"},
        {"ticker": "B.T", "signal_date": "2026-01-08", "classification": "WATCH"},
        {"ticker": "C.T", "signal_date": "2026-01-02", "classification": "NONE"},
        {"ticker": "D.T", "signal_date": "2026-01-02", "classification": "WATCH"},
        {"ticker": "E.T", "signal_date": "2026-01-02", "classification": "WATCH"},
    ]
    histories = {
        "A.T": _history([100.0, 100.0, 120.0, 151.0]),
        "B.T": _history([100.0, 100.0, 151.0, 151.0]),
        "C.T": _history([100.0, 100.0, 110.0, 120.0]),
        "D.T": _history([100.0, 100.0, 120.0, 151.0]),
        "E.T": _history([100.0], start="2026-01-05"),
    }

    result = compute_tracked_pool_explosion_recall(observations, histories)

    assert result["exploded_ticker_count"] == 3
    assert result["detected_ticker_count"] == 2
    assert result["tracked_pool_explosion_recall_pct"] == 66.667
    assert result["detection_lead_time_median_days"] == 4.0
    assert result["excluded_no_price_count"] == 1


def test_tracked_pool_recall_uses_latest_close_before_baseline() -> None:
    observations = [
        {"ticker": "A.T", "signal_date": "2026-01-05", "classification": "WATCH"},
    ]
    history = pd.DataFrame(
        {"Close": [100.0, 151.0]},
        index=pd.to_datetime(["2026-01-02", "2026-01-06"]),
    )

    result = compute_tracked_pool_explosion_recall(observations, {"A.T": history})

    assert result["exploded_ticker_count"] == 1
    assert result["detected_ticker_count"] == 1
    assert result["excluded_no_price_count"] == 0


def test_tracked_pool_recall_returns_stable_empty_schema() -> None:
    result = compute_tracked_pool_explosion_recall([], {})

    assert result["tracked_pool_explosion_recall_pct"] is None
    assert result["exploded_ticker_count"] == 0
    assert result["detected_ticker_count"] == 0
    assert result["detection_lead_time_median_days"] is None
    assert result["excluded_no_price_count"] == 0
