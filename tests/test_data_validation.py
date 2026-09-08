from __future__ import annotations

import pandas as pd

from src.data.validation import compare_close_series, validate_ohlcv


def test_validate_ohlcv_accepts_valid_data() -> None:
    df = pd.DataFrame(
        {
            "Open": [100, 105],
            "High": [110, 115],
            "Low": [95, 100],
            "Close": [108, 112],
            "Volume": [1000, 2000],
        },
        index=pd.to_datetime(["2026-01-05", "2026-01-06"]),
    )
    assert validate_ohlcv(df) == []


def test_validate_ohlcv_detects_structural_errors() -> None:
    df = pd.DataFrame(
        {
            "Open": [100, 105],
            "High": [90, 115],
            "Low": [95, 120],
            "Close": [108, 112],
            "Volume": [-1, 2000],
        },
        index=pd.to_datetime(["2026-01-05", "2026-01-05"]),
    )
    codes = {issue.code for issue in validate_ohlcv(df)}
    assert "DUPLICATE_INDEX" in codes
    assert "HIGH_INCONSISTENT" in codes
    assert "LOW_INCONSISTENT" in codes
    assert "NEGATIVE_VOLUME" in codes


def test_compare_close_series_reports_provider_agreement() -> None:
    idx = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    primary = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=idx)
    reference = pd.DataFrame({"Close": [100.0, 101.2, 101.9]}, index=idx)
    result = compare_close_series(primary, reference, tolerance_pct=0.5)
    assert result["overlap"] == 3
    assert result["match_rate_pct"] == 100.0
    assert result["max_abs_diff_pct"] is not None
