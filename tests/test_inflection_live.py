from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from src.screening.inflection_live import (
    LIVE_MEASURABLE_MAX_SCORE,
    REPORT_SCHEMA_VERSION,
    STRATEGY_VERSION,
    _classify,
    _fundamental_features,
    _normalize_available_score,
    _technical_features,
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
            {
                "DiscDate": "2026-08-15",
                "DiscTime": "15:00",
                "DocType": "EarnForecastRevision",
                "CurPerType": "FY",
                "CurFYEn": "2027-03-31",
                "Sales": None,
                "OP": None,
                "FOP": 30.0,
            },
        ]


def _price_frame(periods: int = 80) -> pd.DataFrame:
    index = pd.date_range("2026-05-01", periods=periods, freq="B")
    close = pd.Series([100.0 + i * 0.8 for i in range(periods)], index=index)
    old_volume_days = max(0, periods - 20)
    volume = pd.Series(
        [1_000_000.0] * old_volume_days + [2_000_000.0] * (periods - old_volume_days),
        index=index,
    )
    return pd.DataFrame({"Close": close, "Volume": volume})


def test_live_score_normalizes_actual_measurable_maximum() -> None:
    assert LIVE_MEASURABLE_MAX_SCORE == 58.0
    assert _normalize_available_score(33.0, 25.0, 0.0) == pytest.approx(100.0)
    assert _normalize_available_score(33.0, 25.0, -3.0) < 100.0


def test_classify_marks_overextended_before_candidate_thresholds() -> None:
    assert _classify(100.0, {"return_20d_pct": 55.0, "return_60d_pct": 60.0}) == "OVEREXTENDED"


def test_technical_features_use_raw_turnover_separately_from_adjusted_close() -> None:
    prices = _price_frame()
    prices["Turnover"] = 123_000_000.0

    result = _technical_features(prices)

    assert result is not None
    assert result["avg_turnover_20d_jpy"] == 123_000_000.0


@pytest.mark.parametrize("periods", [19, 20])
def test_technical_features_require_21_closes(periods: int) -> None:
    assert _technical_features(_price_frame(periods)) is None


@pytest.mark.parametrize(
    ("periods", "near_52w_high", "near_listing_high"),
    [(21, False, True), (100, False, True), (251, False, True), (252, True, False)],
)
def test_technical_features_distinguish_listing_and_52w_highs(
    periods: int,
    near_52w_high: bool,
    near_listing_high: bool,
) -> None:
    result = _technical_features(_price_frame(periods))

    assert result is not None
    assert result["return_20d_pct"] is not None
    assert result["near_52w_high"] is near_52w_high
    assert result["near_listing_high"] is near_listing_high


def test_fundamentals_ignore_forecast_only_row_for_latest_actual() -> None:
    rows = FakeJQuantsClient().financial_summary("11110")
    result = _fundamental_features(rows)

    assert result["revenue_growth_yoy_pct"] == pytest.approx(40.0)
    assert result["operating_profit_growth_yoy_pct"] == pytest.approx(150.0)
    assert result["latest_actual_disclosure_date"] == "2026-08-01"
    assert result["latest_disclosure_date"] == "2026-08-15"
    assert result["upward_revision_pct"] == pytest.approx(20.0)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [(-100.0, -200.0, -100.0), (-100.0, -50.0, 50.0), (-100.0, 50.0, 150.0), (100.0, -50.0, -150.0)],
)
def test_forecast_revision_preserves_improvement_direction(old: float, new: float, expected: float) -> None:
    rows = [
        {"DiscDate": "2026-08-01", "CurPerType": "Q1", "CurFYEn": "2027-03-31", "Sales": 1, "FOP": old},
        {"DiscDate": "2026-08-02", "CurPerType": "Q1", "CurFYEn": "2027-03-31", "Sales": 1, "FOP": new},
    ]

    assert _fundamental_features(rows)["upward_revision_pct"] == pytest.approx(expected)


def test_fundamentals_use_prior_fiscal_year_instead_of_same_year_correction() -> None:
    rows = [
        {
            "DiscDate": "2025-08-01",
            "DiscTime": "15:00",
            "CurPerType": "Q1",
            "CurFYEn": "2026-03-31",
            "Sales": 100.0,
            "OP": 10.0,
        },
        {
            "DiscDate": "2026-08-01",
            "DiscTime": "15:00",
            "CurPerType": "Q1",
            "CurFYEn": "2027-03-31",
            "Sales": 140.0,
            "OP": 20.0,
        },
        {
            "DiscDate": "2026-08-02",
            "DiscTime": "15:00",
            "CurPerType": "Q1",
            "CurFYEn": "2027-03-31",
            "Sales": 150.0,
            "OP": 25.0,
        },
    ]
    result = _fundamental_features(rows)
    assert result["revenue_growth_yoy_pct"] == pytest.approx(50.0)
    assert result["operating_profit_growth_yoy_pct"] == pytest.approx(150.0)


def test_fundamentals_return_none_when_only_same_year_correction_exists() -> None:
    rows = [
        {
            "DiscDate": "2026-08-01",
            "DiscTime": "15:00",
            "CurPerType": "Q1",
            "CurFYEn": "2027-03-31",
            "Sales": 140.0,
            "OP": 20.0,
        },
        {
            "DiscDate": "2026-08-02",
            "DiscTime": "15:00",
            "CurPerType": "Q1",
            "CurFYEn": "2027-03-31",
            "Sales": 150.0,
            "OP": 25.0,
        },
    ]
    result = _fundamental_features(rows)
    assert result["revenue_growth_yoy_pct"] is None
    assert result["operating_profit_growth_yoy_pct"] is None
    assert result["operating_margin_change_pctpt"] is None


def test_fundamentals_do_not_treat_a_two_year_gap_as_yoy() -> None:
    rows = [
        {"DiscDate": "2024-08-01", "CurPerType": "Q1", "CurFYEn": "2025-03-31", "Sales": 100},
        {"DiscDate": "2026-08-01", "CurPerType": "Q1", "CurFYEn": "2027-03-31", "Sales": 150},
    ]

    result = _fundamental_features(rows)

    assert result["revenue_growth_yoy_pct"] is None


def test_scan_japan_inflection_filters_market_and_builds_candidate() -> None:
    prices = {"1111.T": _price_frame()}
    with (
        patch("src.screening.inflection_live.fetch_price_data", return_value=prices) as fetch,
        patch.dict("os.environ", {"GITHUB_SHA": "abc123", "JQUANTS_PLAN": "free"}),
    ):
        report = scan_japan_inflection(
            client=FakeJQuantsClient(),
            deep_candidates=1,
            min_turnover_jpy=0,
        )

    fetch.assert_called_once_with(["1111.T"], 252)
    assert report["universe_count"] == 1
    assert report["price_data_count"] == 1
    assert report["technical_usable_count"] == 1
    assert report["latest_price_date_count"] == 1
    assert report["latest_date_histogram"] == {str(prices["1111.T"].index[-1].date()): 1}
    assert report["stale_tickers_sample"] == []
    assert report["deep_candidate_count"] == 1
    assert report["strategy_version"] == STRATEGY_VERSION
    assert report["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert STRATEGY_VERSION == "jp-inflection-shadow-v3"
    assert REPORT_SCHEMA_VERSION == 4
    assert report["source_commit_sha"] == "abc123"
    assert report["data_policy"]["jquants_plan"] == "free"
    assert report["data_policy"]["jquants_data_delay_weeks"] == 12
    assert report["runtime_versions"]["yfinance"]
    assert report["runtime_versions"]["pandas"]
    assert len(report["candidates"]) == 1
    candidate = report["candidates"][0]
    assert candidate["ticker"] == "1111.T"
    assert candidate["company_name"] == "Test Corp"
    assert 0.0 <= candidate["score"] <= 100.0
    assert candidate["live_normalized_score"] == candidate["score"]
    assert candidate["raw_inflection_score"] != candidate["live_normalized_score"]
    assert candidate["classification"] in {"EARLY_CANDIDATE", "WATCH", "OVEREXTENDED", "NONE"}


def test_scan_reports_market_coverage_by_stable_market_code() -> None:
    client = FakeJQuantsClient()
    with (
        patch.object(
            client,
            "listed_issues",
            return_value=[
                {"Code": "11110", "Mkt": "0111", "MktNm": "プライム"},
                {"Code": "22220", "Mkt": "0112", "MktNm": "スタンダード"},
                {"Code": "33330", "Mkt": "0113", "MktNm": "グロース"},
            ],
        ),
        patch(
            "src.screening.inflection_live.fetch_price_data",
            return_value={"1111.T": _price_frame(), "2222.T": _price_frame(20)},
        ),
    ):
        report = scan_japan_inflection(client=client, deep_candidates=0)

    assert report["market_coverage"] == {
        "Prime": {"universe": 1, "price_data": 1, "technical_usable": 1, "latest_date_count": 1},
        "Standard": {"universe": 1, "price_data": 1, "technical_usable": 0, "latest_date_count": 0},
        "Growth": {"universe": 1, "price_data": 0, "technical_usable": 0, "latest_date_count": 0},
    }
    assert report["universe_count"] == 3
    assert report["price_data_count"] == 2
    assert report["technical_usable_count"] == 1
    assert report["latest_price_date_count"] == 1


def test_scan_reports_latest_date_distribution_and_stale_tickers() -> None:
    current = _price_frame()
    stale = _price_frame().iloc[:-1]
    client = FakeJQuantsClient()
    with (
        patch.object(
            client,
            "listed_issues",
            return_value=[
                {"Code": "11110", "Mkt": "0111", "MktNm": "Prime", "CoName": "Current"},
                {"Code": "22220", "Mkt": "0112", "MktNm": "Standard", "CoName": "Stale"},
            ],
        ),
        patch(
            "src.screening.inflection_live.fetch_price_data",
            return_value={"1111.T": current, "2222.T": stale},
        ),
    ):
        report = scan_japan_inflection(client=client, deep_candidates=0)

    assert report["latest_date_histogram"] == {
        str(current.index[-1].date()): 1,
        str(stale.index[-1].date()): 1,
    }
    assert report["stale_tickers_sample"] == ["2222.T"]
