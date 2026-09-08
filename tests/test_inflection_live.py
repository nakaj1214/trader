from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from src.screening.inflection_live import (
    LIVE_MEASURABLE_MAX_SCORE,
    _classify,
    _fundamental_features,
    _normalize_available_score,
    scan_japan_inflection,
)


class FakeJQuantsClient:
    def is_available(self) -> bool:
        return True

    def listed_issues(self) -> list[dict[str, str]]:
        return [
            {"Code": "11110", "Mkt": "0111", "MktNm": "Prime", "CoName": "Test Corp"},
            {"Code": "99990", "Mkt": "0105", "MktNm": "Other", "CoName": "Excluded"},
        ]

    def financial_summary(self, code: str) -> list[dict[str, object]]:
        assert code == "11110"
        return [
            {
                "DiscDate": "2025-08-01",
                "DiscTime": "15:00",
                "CurPerType": "Q1",
                "CurFYEn": "2026-03-31",
                "Sales": 100.0,
                "OP": 10.0,
                "FOP": 20.0,
                "CFO": 5.0,
            },
            {
                "DiscDate": "2026-08-01",
                "DiscTime": "15:00",
                "CurPerType": "Q1",
                "CurFYEn": "2027-03-31",
                "Sales": 140.0,
                "OP": 25.0,
                "FOP": 25.0,
                "CFO": 8.0,
            },
        ]


def _price_frame() -> pd.DataFrame:
    index = pd.date_range("2026-05-01", periods=80, freq="B")
    close = pd.Series([100.0 + i * 0.8 for i in range(80)], index=index)
    volume = pd.Series([1_000_000.0] * 60 + [2_000_000.0] * 20, index=index)
    return pd.DataFrame({"Close": close, "Volume": volume})


def test_live_score_normalizes_actual_measurable_maximum() -> None:
    assert LIVE_MEASURABLE_MAX_SCORE == 58.0
    assert _normalize_available_score(33.0, 25.0, 0.0) == pytest.approx(100.0)
    assert _normalize_available_score(33.0, 25.0, -3.0) < 100.0


def test_classify_marks_overextended_before_candidate_thresholds() -> None:
    assert _classify(100.0, {"return_20d_pct": 55.0, "return_60d_pct": 60.0}) == "OVEREXTENDED"


def test_fundamentals_use_prior_fiscal_year_for_yoy_and_revision_for_forecast() -> None:
    rows = [
        {"DiscDate": "2025-08-01", "CurPerType": "Q1", "CurFYEn": "2026-03-31", "Sales": 100, "OP": 10},
        {"DiscDate": "2026-05-01", "CurPerType": "Q1", "CurFYEn": "2027-03-31", "Sales": 120, "OP": 15, "FOP": 20},
        {"DiscDate": "2026-08-01", "CurPerType": "Q1", "CurFYEn": "2027-03-31", "Sales": 140, "OP": 25, "FOP": 25},
    ]

    features = _fundamental_features(rows)

    assert features["revenue_growth_yoy_pct"] == pytest.approx(40.0)
    assert features["operating_profit_growth_yoy_pct"] == pytest.approx(150.0)
    assert features["upward_revision_pct"] == pytest.approx(25.0)


def test_scan_japan_inflection_filters_market_and_builds_candidate() -> None:
    prices = {"1111.T": _price_frame()}
    with patch("src.screening.inflection_live._fetch_price_data", return_value=prices) as fetch:
        report = scan_japan_inflection(
            client=FakeJQuantsClient(),
            deep_candidates=1,
            min_turnover_jpy=0,
        )

    fetch.assert_called_once_with(["1111.T"], 252, auto_adjust=True)
    assert report["universe_count"] == 1
    assert report["price_data_count"] == 1
    assert report["deep_candidate_count"] == 1
    assert len(report["candidates"]) == 1
    candidate = report["candidates"][0]
    assert candidate["ticker"] == "1111.T"
    assert candidate["company_name"] == "Test Corp"
    assert 0.0 <= candidate["score"] <= 100.0
    assert candidate["classification"] in {"EARLY_CANDIDATE", "WATCH", "OVEREXTENDED", "NONE"}
