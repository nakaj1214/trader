from __future__ import annotations

import pandas as pd

from src.data.validation import validate_ohlcv


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
