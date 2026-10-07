from __future__ import annotations

import hashlib
from unittest.mock import patch

import pandas as pd
import pytest

from src.screening.inflection_live import (
    FEATURE_DEFAULTS,
    LIVE_MEASURABLE_MAX_SCORE,
    REPORT_SCHEMA_VERSION,
    STRATEGY_VERSION,
    PriceDataRetryExhausted,
    _classify,
    _fundamental_features,
    _normalize_available_score,
    _pre_score,
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
    expected_date = str(prices["1111.T"].index[-1].date())
    with (
        patch("src.screening.inflection_live.fetch_price_data", return_value=prices) as fetch,
        patch(
            "src.screening.inflection_live.expected_tse_session_date",
            return_value=expected_date,
        ) as expected_session,
        patch.dict("os.environ", {"GITHUB_SHA": "abc123", "JQUANTS_PLAN": "free"}),
    ):
        report = scan_japan_inflection(
            client=FakeJQuantsClient(),
            deep_candidates=1,
            min_turnover_jpy=0,
        )

    fetch.assert_called_once_with(["1111.T"], 252)
    assert expected_session.call_args.args[0] == report["generated_at"]
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
    assert REPORT_SCHEMA_VERSION == 5
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
    current = _price_frame()
    short = current.tail(20)
    expected_date = str(current.index[-1].date())
    with (
        patch.object(
            client,
            "listed_issues",
            return_value=[
                {"Code": "11110", "Mkt": "0111", "MktNm": "プライム"},
                {"Code": "22220", "Mkt": "0112", "MktNm": "スタンダード"},
                {"Code": "33330", "Mkt": "0113", "MktNm": "グロース"},
                {"Code": "44440", "Mkt": "0113", "MktNm": "グロース"},
            ],
        ),
        patch(
            "src.screening.inflection_live.fetch_price_data",
            return_value={"1111.T": current, "2222.T": short, "3333.T": short},
        ),
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected_date),
    ):
        report = scan_japan_inflection(client=client, deep_candidates=0, control_sample_size=0)

    assert report["market_coverage"] == {
        "Prime": {"universe": 1, "price_data": 1, "technical_usable": 1, "latest_date_count": 1},
        "Standard": {"universe": 1, "price_data": 1, "technical_usable": 0, "latest_date_count": 1},
        "Growth": {"universe": 2, "price_data": 1, "technical_usable": 0, "latest_date_count": 1},
    }
    assert report["universe_count"] == 4
    assert report["price_data_count"] == 3
    assert report["technical_usable_count"] == 1
    assert report["latest_price_date_count"] == 3


def test_scan_retries_only_stale_tickers_and_recovers() -> None:
    current = _price_frame()
    stale = _price_frame().iloc[:-1]
    expected_date = str(current.index[-1].date())
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
            side_effect=[{"1111.T": current, "2222.T": stale}, {"2222.T": current}],
        ) as fetch,
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected_date),
        patch.dict(
            "os.environ",
            {"INFLECTION_PRICE_RETRY_COUNT": "1", "INFLECTION_PRICE_RETRY_WAIT_SECONDS": "0"},
        ),
    ):
        report = scan_japan_inflection(client=client, deep_candidates=0, control_sample_size=0)

    assert fetch.call_args_list[1].args == (["2222.T"], 252)
    assert report["latest_date_histogram"] == {expected_date: 2}
    assert report["stale_tickers_sample"] == []


def test_scan_retries_missing_tickers_when_price_coverage_is_low() -> None:
    current = _price_frame()
    expected_date = str(current.index[-1].date())
    client = FakeJQuantsClient()
    issues = [
        {"Code": f"{number}{number}{number}{number}0", "Mkt": "0111", "MktNm": "Prime"}
        for number in range(1, 5)
    ]
    with (
        patch.object(client, "listed_issues", return_value=issues),
        patch(
            "src.screening.inflection_live.fetch_price_data",
            side_effect=[
                {"1111.T": current, "2222.T": current},
                {"3333.T": current},
            ],
        ) as fetch,
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected_date),
        patch.dict(
            "os.environ",
            {"INFLECTION_PRICE_RETRY_COUNT": "1", "INFLECTION_PRICE_RETRY_WAIT_SECONDS": "0"},
        ),
    ):
        report = scan_japan_inflection(client=client, deep_candidates=0, control_sample_size=0)

    assert fetch.call_args_list[1].args == (["3333.T", "4444.T"], 252)
    assert report["price_data_count"] == 3
    assert report["latest_price_date_count"] == 3


def test_scan_recovers_on_second_retry() -> None:
    current = _price_frame()
    stale = current.iloc[:-1]
    expected_date = str(current.index[-1].date())
    client = FakeJQuantsClient()
    with (
        patch.object(
            client,
            "listed_issues",
            return_value=[
                {"Code": "11110", "Mkt": "0111", "MktNm": "Prime"},
                {"Code": "22220", "Mkt": "0112", "MktNm": "Standard"},
            ],
        ),
        patch(
            "src.screening.inflection_live.fetch_price_data",
            side_effect=[
                {"1111.T": current, "2222.T": stale},
                {"2222.T": stale},
                {"2222.T": current},
            ],
        ) as fetch,
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected_date),
        patch.dict(
            "os.environ",
            {"INFLECTION_PRICE_RETRY_COUNT": "2", "INFLECTION_PRICE_RETRY_WAIT_SECONDS": "0,0"},
        ),
    ):
        report = scan_japan_inflection(client=client, deep_candidates=0, control_sample_size=0)

    assert fetch.call_count == 3
    assert report["latest_price_date_count"] == 2


def test_scan_raises_diagnostic_error_after_retries_are_exhausted() -> None:
    current = _price_frame()
    stale = current.iloc[:-1]
    expected_date = str(current.index[-1].date())
    client = FakeJQuantsClient()
    with (
        patch.object(
            client,
            "listed_issues",
            return_value=[
                {"Code": "11110", "Mkt": "0111", "MktNm": "Prime"},
                {"Code": "22220", "Mkt": "0112", "MktNm": "Standard"},
            ],
        ),
        patch(
            "src.screening.inflection_live.fetch_price_data",
            side_effect=[
                {"1111.T": current, "2222.T": stale},
                {"2222.T": stale},
                {"2222.T": stale},
            ],
        ),
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected_date),
        patch.dict(
            "os.environ",
            {"INFLECTION_PRICE_RETRY_COUNT": "2", "INFLECTION_PRICE_RETRY_WAIT_SECONDS": "0,0"},
        ),
        pytest.raises(PriceDataRetryExhausted) as raised,
    ):
        scan_japan_inflection(client=client, deep_candidates=0, control_sample_size=0)

    assert raised.value.details == {
        "retry_exhausted": "true",
        "expected_date": expected_date,
        "universe": "2",
        "missing": "0",
        "price_data": "2",
        "price_coverage": "100.0%",
        "latest_coverage": "50.0%",
        "failed_gate": "latest_coverage",
        "attempts": "3",
        "latest_dates": f"{expected_date}:1,{stale.index[-1].date()}:1",
        "dropped_future_bars": "0",
    }


@pytest.mark.parametrize(
    ("count", "waits"),
    [("-1", ""), ("invalid", ""), ("2", "0"), ("1", "nan")],
)
def test_scan_rejects_invalid_retry_configuration(count: str, waits: str) -> None:
    with (
        patch.dict(
            "os.environ",
            {
                "INFLECTION_PRICE_RETRY_COUNT": count,
                "INFLECTION_PRICE_RETRY_WAIT_SECONDS": waits,
            },
        ),
        pytest.raises(ValueError, match="retry configuration"),
    ):
        scan_japan_inflection(client=FakeJQuantsClient())


class MultiCodeFakeClient(FakeJQuantsClient):
    """Several listed names; counts financial_summary calls per code."""

    def __init__(self, count: int = 6, no_financials: frozenset[str] = frozenset()) -> None:
        self.codes = [f"{n}{n}{n}{n}0" for n in range(1, count + 1)]
        self.no_financials = no_financials
        self.calls: list[str] = []

    def listed_issues(self) -> list[dict[str, str]]:
        return [
            {"Code": code, "Mkt": "0111", "MktNm": "Prime", "CoName": f"Co {code}", "S33": "3650", "S33Nm": "電気機器"}
            for code in self.codes
        ] + [{"Code": "77770", "Mkt": "0111", "MktNm": "Prime", "S33": " ", "S33Nm": ""}]

    def financial_summary(self, code: str) -> list[dict[str, object]]:
        self.calls.append(code)
        if code in self.no_financials:
            return []
        return _FINANCIAL_ROWS


FUNDAMENTAL_FEATURE_KEYS = (
    "revenue_growth_yoy_pct",
    "operating_profit_growth_yoy_pct",
    "operating_margin_change_pctpt",
    "turned_profitable",
    "upward_revision_pct",
    "negative_operating_cashflow",
    "latest_actual_disclosure_date",
    "latest_disclosure_date",
)
_FINANCIAL_ROWS = [
    {"DiscDate": "2025-08-01", "DiscTime": "15:00", "CurPerType": "Q1", "CurFYEn": "2026-03-31",
     "Sales": 100.0, "OP": 10.0, "FOP": 20.0, "CFO": 5.0},
    {"DiscDate": "2026-08-01", "DiscTime": "15:00", "CurPerType": "Q1", "CurFYEn": "2027-03-31",
     "Sales": 140.0, "OP": 25.0, "FOP": 25.0, "CFO": 8.0},
]


def _scan_multi(client: MultiCodeFakeClient, *, periods: int = 80, **kwargs: object) -> dict[str, object]:
    tickers = [f"{code[:4]}.T" for code in client.codes] + ["7777.T"]
    prices = {ticker: _price_frame(periods) for ticker in tickers}
    expected_date = str(prices[tickers[0]].index[-1].date())
    with (
        patch("src.screening.inflection_live.fetch_price_data", return_value=prices),
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected_date),
    ):
        return scan_japan_inflection(client=client, min_turnover_jpy=0, **kwargs)  # type: ignore[arg-type]


def test_candidate_persists_raw_features_score_details_and_sector() -> None:
    client = MultiCodeFakeClient()
    report = _scan_multi(client, deep_candidates=2, control_sample_size=0)
    candidate = report["candidates"][0]  # type: ignore[index]
    expected = _fundamental_features(_FINANCIAL_ROWS)

    assert set(candidate["features"]) == set(FEATURE_DEFAULTS)
    for key in FUNDAMENTAL_FEATURE_KEYS:  # the diagnostics added later are covered by their own tests
        assert candidate["features"][key] == expected.get(key, FEATURE_DEFAULTS[key])
    assert candidate["features"]["latest_actual_disclosure_date"] == "2026-08-01"
    details = candidate["score_details"]
    assert {"revenue_growth", "volume_ratio", "fundamental", "momentum", "risk_penalty"} <= set(details)
    # Live data has no catalyst points, so the subtotals add up to the raw score.
    assert details["fundamental"] + details["momentum"] + details["risk_penalty"] == pytest.approx(
        candidate["raw_inflection_score"]
    )
    assert candidate["pre_score"] == round(_pre_score(_technical_features(_price_frame())), 6)  # type: ignore[arg-type]
    assert (candidate["sector33_code"], candidate["sector33_name"]) == ("3650", "電気機器")


def test_candidate_features_keep_every_key_without_financials() -> None:
    client = MultiCodeFakeClient(no_financials=frozenset(f"{n}{n}{n}{n}0" for n in range(1, 7)))
    report = _scan_multi(client, deep_candidates=1, control_sample_size=0)

    features = report["candidates"][0]["features"]  # type: ignore[index]
    # No financials: every fundamental-derived value stays at its default, including the disclosure ages...
    for key in (*FUNDAMENTAL_FEATURE_KEYS, "forecast_disclosure_date", "disclosure_age_days", "forecast_age_days"):
        assert features[key] == FEATURE_DEFAULTS[key], key
    # ...while price-derived diagnostics exist because prices do.
    assert features["max_daily_return_20d_pct"] is not None and features["distance_from_period_high_pct"] is not None


def test_blank_sector_becomes_none() -> None:
    client = MultiCodeFakeClient(count=0)
    prices = {"7777.T": _price_frame()}
    with (
        patch("src.screening.inflection_live.fetch_price_data", return_value=prices),
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=str(prices["7777.T"].index[-1].date())),
    ):
        report = scan_japan_inflection(client=client, min_turnover_jpy=0, deep_candidates=1, control_sample_size=0)

    assert report["candidates"][0]["sector33_code"] is None
    assert report["candidates"][0]["sector33_name"] is None


def test_control_sample_is_deterministic_liquid_and_separate() -> None:
    first = _scan_multi(MultiCodeFakeClient(), deep_candidates=2, control_sample_size=3)
    second = _scan_multi(MultiCodeFakeClient(), deep_candidates=2, control_sample_size=3)
    baseline = _scan_multi(MultiCodeFakeClient(), deep_candidates=2, control_sample_size=0)

    tickers = [row["ticker"] for row in first["control_sample"]]  # type: ignore[attr-defined]
    assert tickers == [row["ticker"] for row in second["control_sample"]]  # type: ignore[attr-defined]
    assert tickers == sorted(tickers) and len(tickers) == len(set(tickers)) == 3
    assert first["control_sample_size"] == 3 and first["control_sample_seed"] == second["control_sample_seed"]
    assert first["scan_parameters"]["control_sample_size"] == 3  # type: ignore[index]
    for key in ("candidates", "deep_candidate_count", "classification_counts"):
        assert first[key] == baseline[key]
    assert baseline["control_sample"] == [] and baseline["control_sample_size"] == 0


def test_control_sample_seed_is_derived_from_market_date() -> None:
    first = _scan_multi(MultiCodeFakeClient(), periods=80, deep_candidates=1, control_sample_size=3)
    next_day = _scan_multi(MultiCodeFakeClient(), periods=81, deep_candidates=1, control_sample_size=3)

    assert first["latest_price_date"] != next_day["latest_price_date"]
    for report in (first, next_day):
        digest = hashlib.sha256(str(report["latest_price_date"]).encode()).digest()
        assert report["control_sample_seed"] == int.from_bytes(digest[:8], "big")
    assert first["control_sample_seed"] != next_day["control_sample_seed"]


def test_control_sample_reuses_deep_financials_and_respects_size() -> None:
    client = MultiCodeFakeClient()
    report = _scan_multi(client, deep_candidates=2, control_sample_size=4)

    assert len(client.calls) == len(set(client.calls))  # no ticker fetched twice
    assert len(report["control_sample"]) == 4  # type: ignore[arg-type]
    assert len(client.calls) <= 2 + 4

    zero = MultiCodeFakeClient()
    _scan_multi(zero, deep_candidates=2, control_sample_size=0)
    assert len(zero.calls) == 2

    everyone = MultiCodeFakeClient()
    report = _scan_multi(everyone, deep_candidates=2, control_sample_size=50)
    assert len(report["control_sample"]) == 7  # type: ignore[arg-type]


def test_negative_control_sample_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="control_sample_size"):
        scan_japan_inflection(client=MultiCodeFakeClient(), control_sample_size=-1)


@pytest.mark.parametrize("include_new_features", [True, False])
def test_scan_output_satisfies_validator_and_both_loaders(tmp_path, include_new_features: bool) -> None:  # type: ignore[no-untyped-def]
    from scripts.run_inflection_shadow import _validate_schema5_row
    from src.data.snapshot_crypto import encrypt_json
    from src.evaluation.inflection_forward import load_inflection_signals
    from src.evaluation.inflection_learning import load_inflection_learning_observations

    report = _scan_multi(MultiCodeFakeClient(), deep_candidates=3, control_sample_size=3)
    if not include_new_features:
        for row in report["candidates"] + report["control_sample"]:  # type: ignore[operator]
            for key in NEW_DIAGNOSTIC_KEYS[:8]:
                row["features"].pop(key)
    for row in report["candidates"] + report["control_sample"]:  # type: ignore[operator]
        _validate_schema5_row(row, "scan row")

    stored = report | {"storage": {"encrypted": True, "snapshot_date_basis": "latest_price_date"}}
    (tmp_path / f"{report['latest_price_date']}.enc").write_text(encrypt_json(stored, "secret"), encoding="utf-8")
    observations = load_inflection_learning_observations(tmp_path, encryption_secret="secret")
    signals = load_inflection_signals(
        tmp_path, encryption_secret="secret", classifications=("EARLY_CANDIDATE", "WATCH", "NONE", "OVEREXTENDED")
    )

    assert len(observations) == len(signals) == 3  # control_sample is not mixed into evaluation inputs
    assert all(row["features"] is not None and row["sector33_code"] == "3650" for row in observations)


# --- REQ-050: diagnostics recorded for later study -----------------------------------------------------

NEW_DIAGNOSTIC_KEYS = (
    "quarterly_sales_growth_yoy_pct",
    "quarterly_op_growth_yoy_pct",
    "quarterly_sales_growth_accel_pctpt",
    "quarterly_op_growth_accel_pctpt",
    "sector33_return_20d_pct",
    "sector33_return_60d_pct",
    "relative_return_20d_vs_sector_pct",
    "relative_return_60d_vs_sector_pct",
    "forecast_disclosure_date",
    "disclosure_age_days",
    "forecast_age_days",
    "max_daily_return_20d_pct",
    "up_day_ratio_20d",
    "up_day_ratio_60d",
    "daily_volatility_20d_pct",
    "distance_from_period_high_pct",
)
# Taken from the code BEFORE the diagnostics existed: scoring, classification and selection must not move.
PRE_DIAGNOSTICS_FINGERPRINT = "f8583efe1192924eece3dddcdd8a4188be4be65e04032d6996a4a74e0aee48fc"


def _frame_from_returns(returns: list[float], base: float = 100.0) -> pd.DataFrame:
    closes = [base]
    for value in returns:
        closes.append(closes[-1] * (1.0 + value))
    index = pd.bdate_range("2026-01-05", periods=len(closes))
    return pd.DataFrame({"Close": closes, "Volume": [1_000_000.0] * len(closes)}, index=index)


def test_diagnostics_do_not_change_scores_classifications_or_selection() -> None:
    import hashlib
    import json

    report = _scan_multi(MultiCodeFakeClient(), deep_candidates=3, control_sample_size=3)

    def stripped(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {**row, "features": {k: v for k, v in row["features"].items() if k not in NEW_DIAGNOSTIC_KEYS}}  # type: ignore[attr-defined]
            for row in rows
        ]

    payload = {
        "candidates": stripped(report["candidates"]),  # type: ignore[arg-type]
        "control_sample": stripped(report["control_sample"]),  # type: ignore[arg-type]
        "classification_counts": report["classification_counts"],
    }
    blob = json.dumps(payload, sort_keys=True, default=str)

    assert hashlib.sha256(blob.encode()).hexdigest() == PRE_DIAGNOSTICS_FINGERPRINT
    assert set(NEW_DIAGNOSTIC_KEYS) <= set(report["candidates"][0]["features"])  # type: ignore[index]


def test_price_diagnostics_match_a_hand_calculation() -> None:
    import statistics

    # 61 closes: a spike first (the period high), 39 calm +0.5% days, then 20 days alternating +2% / -1%.
    returns = [0.50] + [-0.30] + [0.005] * 38 + [0.02, -0.01] * 10
    frame = _frame_from_returns(returns)
    last20 = returns[-20:]

    tech = _technical_features(frame)

    assert tech is not None
    assert tech["max_daily_return_20d_pct"] == pytest.approx(2.0)
    assert tech["up_day_ratio_20d"] == pytest.approx(0.5)
    last60 = returns[-60:]
    assert tech["up_day_ratio_60d"] == pytest.approx(sum(value > 0 for value in last60) / 60)
    assert tech["daily_volatility_20d_pct"] == pytest.approx(statistics.stdev(last20) * 100, rel=1e-9)
    closes = frame["Close"]
    assert tech["distance_from_period_high_pct"] == pytest.approx((closes.iloc[-1] / closes.max() - 1) * 100)
    assert tech["distance_from_period_high_pct"] < 0


def test_price_diagnostics_need_enough_history_and_never_raise() -> None:
    twenty_returns = _technical_features(_frame_from_returns([0.01] * 20))  # 21 closes: the minimum
    forty_returns = _technical_features(_frame_from_returns([0.01] * 40))

    assert twenty_returns is not None and forty_returns is not None
    for tech in (twenty_returns, forty_returns):
        assert tech["max_daily_return_20d_pct"] == pytest.approx(1.0) and tech["up_day_ratio_20d"] == 1.0
        assert tech["up_day_ratio_60d"] is None  # fewer than 60 returns
        assert tech["daily_volatility_20d_pct"] == pytest.approx(0.0, abs=1e-9)
        assert tech["distance_from_period_high_pct"] == pytest.approx(0.0)  # at its high


def test_price_diagnostics_ignore_a_zero_price_instead_of_failing() -> None:
    frame = _frame_from_returns([0.01] * 40)
    frame.iloc[10, frame.columns.get_loc("Close")] = 0.0  # a bad print makes one return infinite

    tech = _technical_features(frame)

    assert tech is not None and tech["max_daily_return_20d_pct"] == pytest.approx(1.0)  # last 20 days are clean


def test_disclosure_ages_are_counted_from_the_scan_market_date() -> None:
    prices = {"1111.T": _price_frame()}
    expected_date = str(prices["1111.T"].index[-1].date())
    with (
        patch("src.screening.inflection_live.fetch_price_data", return_value=prices),
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected_date),
    ):
        report = scan_japan_inflection(client=FakeJQuantsClient(), deep_candidates=1, min_turnover_jpy=0)

    features = report["candidates"][0]["features"]
    market_date = pd.Timestamp(expected_date)
    assert features["latest_actual_disclosure_date"] == "2026-08-01"
    assert features["disclosure_age_days"] == (market_date - pd.Timestamp("2026-08-01")).days
    assert features["forecast_disclosure_date"] == "2026-08-15"  # the revision filing used for the upward revision
    assert features["forecast_age_days"] == (market_date - pd.Timestamp("2026-08-15")).days
    assert features["upward_revision_pct"] == pytest.approx(20.0)


def test_forecast_disclosure_is_none_with_fewer_than_two_forecasts() -> None:
    rows = _fundamental_features(_FINANCIAL_ROWS)  # only one forecast for the latest fiscal year

    assert rows["forecast_disclosure_date"] is None and rows["upward_revision_pct"] is None


@pytest.mark.parametrize("disclosed", [None, "", "not-a-date", "2026/08/01", "2026-13-40"])
def test_age_is_none_for_a_missing_or_malformed_disclosure_date(disclosed: object) -> None:
    from src.screening.inflection_live import _age_days

    assert _age_days("2026-08-20", disclosed) is None


def test_age_accepts_the_iso_basic_date_form_too() -> None:
    from src.screening.inflection_live import _age_days

    assert _age_days("2026-08-20", "20260801") == 19  # YYYYMMDD is valid ISO 8601 and parsed as such


def test_age_counts_days_including_same_day_disclosures() -> None:
    from src.screening.inflection_live import _age_days

    assert _age_days("2026-08-20", "2026-08-20") == 0
    assert _age_days("2026-08-20", "2026-05-22") == 90
    assert _age_days("2026-08-20", "2026-08-21") == -1  # a future-dated filing is reported, not hidden


def test_no_financials_means_no_disclosure_ages() -> None:
    client = MultiCodeFakeClient(no_financials=frozenset(f"{n}{n}{n}{n}0" for n in range(1, 7)))
    features = _scan_multi(client, deep_candidates=1, control_sample_size=0)["candidates"][0]["features"]  # type: ignore[index]

    assert features["disclosure_age_days"] is None and features["forecast_age_days"] is None


def test_scan_discards_future_bars_on_initial_fetch_and_retry() -> None:
    current = _price_frame()
    expected = str(current.index[-1].date())
    future = pd.concat([current, current.tail(1).set_axis([current.index[-1] + pd.offsets.BDay()])])
    future.iloc[-1, 0] = 10_000_000.0
    client = FakeJQuantsClient()
    for initial in (future, current.iloc[:-1]):
        with (
            patch("src.screening.inflection_live.fetch_price_data", side_effect=[{"1111.T": initial}, {"1111.T": future}]),
            patch("src.screening.inflection_live.expected_tse_session_date", return_value=expected),
            patch.dict("os.environ", {"INFLECTION_PRICE_RETRY_COUNT": "1", "INFLECTION_PRICE_RETRY_WAIT_SECONDS": "0"}),
        ):
            report = scan_japan_inflection(client=client, deep_candidates=1, min_turnover_jpy=0)
        assert report["latest_price_date_count"] == 1
        assert report["candidates"][0]["current_price"] == float(current["Close"].iloc[-1])
        assert report["latest_date_histogram"] == {expected: 1}
    pd.testing.assert_frame_equal(future.iloc[:-1], current, check_freq=False)


def test_drop_future_bars_preserves_timezone_and_handles_unparseable_index() -> None:
    from src.screening.inflection_live import _drop_future_bars

    frame = _price_frame(22)
    frame.index = frame.index.tz_localize("Asia/Tokyo")
    prices = {"A.T": frame, "invalid": frame.set_axis(["bad"] * len(frame))}
    assert _drop_future_bars(prices, str(frame.index[-2].date())) == {"A.T"}
    pd.testing.assert_frame_equal(prices["A.T"], frame.iloc[:-1])
    assert len(prices["invalid"]) == len(frame)


def test_failure_histogram_is_redacted_and_counts_unique_trimmed_tickers(capsys: pytest.CaptureFixture[str]) -> None:
    current = _price_frame()
    future_only = current.tail(1).set_axis([current.index[-1] + pd.offsets.BDay()])
    with (
        patch("src.screening.inflection_live.fetch_price_data", return_value={"1111.T": future_only}),
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=str(current.index[-1].date())),
        patch.dict("os.environ", {"INFLECTION_PRICE_RETRY_COUNT": "1", "INFLECTION_PRICE_RETRY_WAIT_SECONDS": "0"}),
        pytest.raises(PriceDataRetryExhausted) as raised,
    ):
        scan_japan_inflection(client=FakeJQuantsClient())
    assert raised.value.details["latest_dates"] == ""
    assert raised.value.details["dropped_future_bars"] == "1"
    captured = capsys.readouterr()
    assert "latest_dates=" in captured.out
    assert "1111.T" not in captured.out + captured.err + str(raised.value)


def _quarter_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for year, sales, profits in ((2024, [100, 200, 300, 400], [10, 20, 30, 40]),
                                (2025, [110, 240, 390, 560], [12, 26, 42, 60])):
        start = pd.Timestamp(f"{year - 1}-04-01")
        for q, period in enumerate(("1Q", "2Q", "3Q", "FY"), start=1):
            end = start + pd.DateOffset(months=3 * q) - pd.Timedelta(days=1)
            rows.append({
                "Code": "11110", "DiscDate": str((end + pd.Timedelta(days=30)).date()), "DiscTime": "15:00",
                "CurPerType": period, "CurFYEn": f"{year}-03-31",
                "CurPerSt": str(start.date()), "CurPerEn": str(end.date()),
                "DocType": f"{period}FinancialStatements_Consolidated_JP",
                "Sales": sum(sales[:q]), "OP": sum(profits[:q]),
            })
    return rows


@pytest.mark.parametrize(("period", "sales_growth", "op_growth", "accel"), [
    ("1Q", 10.0, 20.0, None), ("2Q", 20.0, 30.0, 10.0),
    ("3Q", 30.0, 40.0, 10.0), ("FY", 40.0, 50.0, 10.0),
])
def test_quarterly_growth_uses_standalone_values(period: str, sales_growth: float, op_growth: float,
                                                accel: float | None) -> None:
    rows = _quarter_rows()
    cutoff = next(str(r["DiscDate"]) for r in rows if r["CurFYEn"] == "2025-03-31" and r["CurPerType"] == period)
    features = _fundamental_features([r for r in rows if str(r["DiscDate"]) <= cutoff])
    assert features["quarterly_sales_growth_yoy_pct"] == pytest.approx(sales_growth)
    assert features["quarterly_op_growth_yoy_pct"] == pytest.approx(op_growth)
    for label in ("sales", "op"):
        value = features[f"quarterly_{label}_growth_accel_pctpt"]
        assert value is None if accel is None else value == pytest.approx(accel)


@pytest.mark.parametrize("missing_period", ["1Q", "2Q", "3Q"])
def test_quarterly_missing_previous_cumulative_is_not_zero(missing_period: str) -> None:
    rows = _quarter_rows()
    periods = ["1Q", "2Q", "3Q", "FY"]
    target = periods[periods.index(missing_period) + 1]
    cutoff = next(str(r["DiscDate"]) for r in rows if r["CurFYEn"] == "2025-03-31" and r["CurPerType"] == target)
    rows = [r for r in rows if str(r["DiscDate"]) <= cutoff and
            not (r["CurFYEn"] == "2025-03-31" and r["CurPerType"] == missing_period)]
    features = _fundamental_features(rows)
    assert features["quarterly_sales_growth_yoy_pct"] is None
    assert features["quarterly_sales_growth_accel_pctpt"] is None


@pytest.mark.parametrize("profit", [0, -5])
def test_quarterly_nonpositive_prior_profit_is_missing(profit: int) -> None:
    rows = _quarter_rows()
    previous = next(r for r in rows if r["CurFYEn"] == "2024-03-31" and r["CurPerType"] == "FY")
    previous["OP"] = 60 + profit  # Previous 3Q's cumulative profit is 60.
    features = _fundamental_features(rows)
    assert features["quarterly_op_growth_yoy_pct"] is None
    assert features["quarterly_op_growth_accel_pctpt"] is None


def test_quarterly_first_quarter_acceleration_crosses_fiscal_year() -> None:
    rows = _quarter_rows()
    rows.append({"Code": "11110", "DiscDate": "2025-07-30", "DiscTime": "15:00", "CurPerType": "1Q",
                 "CurFYEn": "2026-03-31", "DocType": "1QFinancialStatements_Consolidated_JP",
                 "Sales": 180, "OP": 24})
    features = _fundamental_features(rows)
    assert features["quarterly_sales_growth_accel_pctpt"] == pytest.approx((180 / 110 - 1) * 100 - 40)
    assert features["quarterly_op_growth_accel_pctpt"] == pytest.approx(50)


def test_quarterly_corrections_basis_and_point_in_time() -> None:
    from src.evaluation.inflection_historical import FinancialsStore

    rows = _quarter_rows()
    latest = rows[-1]
    revised = {**latest, "DiscDate": "2025-05-01", "Sales": 1400}
    foreign = {**rows[-2], "DiscDate": "2025-04-30", "DocType": "3QFinancialStatements_NonConsolidated_JP",
               "Sales": 9999}
    source = FinancialsStore([*rows, revised, foreign])
    before = _fundamental_features(source.view("2025-04-30", "disclosure").financial_summary("11110"))
    after = _fundamental_features(source.view("2025-05-01", "disclosure").financial_summary("11110"))
    # On 4/30 the latest actual is the non-consolidated 3Q, which has no comparable history.
    assert before["quarterly_sales_growth_yoy_pct"] is None
    assert after["quarterly_sales_growth_yoy_pct"] == pytest.approx(65)
    live_bounded = _fundamental_features([*rows, revised], as_of="2025-04-30")
    assert live_bounded["quarterly_sales_growth_yoy_pct"] == pytest.approx(40)
    assert live_bounded["revenue_growth_yoy_pct"] == pytest.approx(40)  # legacy uses the latest revision (1400/1000).


def test_quarterly_irregular_period_and_invalid_values_stay_missing() -> None:
    rows = _quarter_rows()
    rows[-1]["CurPerSt"] = "2024-07-01"  # A short fiscal year is not a normal 4Q.
    assert _fundamental_features(rows)["quarterly_sales_growth_yoy_pct"] is None
    rows[-1].pop("CurPerSt")
    rows[-1]["Sales"] = float("nan")
    assert _fundamental_features(rows)["quarterly_sales_growth_yoy_pct"] is None


def test_quarterly_accepts_fourth_quarter_alias() -> None:
    rows = _quarter_rows()
    rows[-1]["CurPerType"] = "4Q"
    assert _fundamental_features(rows)["quarterly_sales_growth_yoy_pct"] == pytest.approx(40)


def test_sector_median_includes_illiquid_names_and_both_candidate_pools() -> None:
    from src.screening.inflection_live import select_and_evaluate

    prices = {f"{n}.T": _frame_from_returns([0.0] * 40 + [value / 20] * 20)
              for n, value in enumerate((0.0, 0.1, 0.2, 0.3, 9.0))}
    meta = {ticker: {"Code": "11110", "S33": "3650"} for ticker in prices}
    prices["4.T"]["Volume"] = 0  # The outlier is illiquid but belongs to the sector sample.
    prices["B.T"] = _frame_from_returns([0.0] * 60)
    meta["B.T"] = {"Code": "11110", "S33": "9999"}
    prices["C.T"] = _frame_from_returns([0.0] * 60)
    meta["C.T"] = {"Code": "11110"}
    selected = select_and_evaluate(prices, meta, FakeJQuantsClient(), seed_date="2026-04-01", deep_candidates=2,
                                   min_turnover_jpy=1, control_sample_size=20, fundamental_limitation="test")
    median_return = ((1 + 0.2 / 20) ** 20 - 1) * 100
    for candidate in [*selected.candidates, *selected.control_sample]:
        if meta[candidate.ticker].get("S33") == "3650":
            assert candidate.features["sector33_return_20d_pct"] == pytest.approx(median_return)
            assert candidate.features["relative_return_20d_vs_sector_pct"] == pytest.approx(
                candidate.return_20d_pct - median_return)
            assert candidate.features["sector33_return_60d_pct"] == pytest.approx(median_return)
        else:
            assert candidate.features["sector33_return_20d_pct"] is None
            assert candidate.features["relative_return_60d_vs_sector_pct"] is None


@pytest.mark.parametrize("count", [4, 5])
def test_sector_threshold_and_missing_long_history(count: int) -> None:
    client = MultiCodeFakeClient(count=count)
    report = _scan_multi(client, periods=21, deep_candidates=2, control_sample_size=10)
    for row in report["candidates"] + report["control_sample"]:  # type: ignore[operator]
        features = row["features"]
        if row["sector33_code"] == "3650" and count == 5:
            assert features["sector33_return_20d_pct"] is not None
        else:
            assert features["sector33_return_20d_pct"] is None
        assert features["sector33_return_60d_pct"] is None
        assert features["relative_return_60d_vs_sector_pct"] is None
