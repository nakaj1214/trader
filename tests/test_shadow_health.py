from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from scripts.run_inflection_shadow import (
    OUT_DIR,
    main,
    persist_report,
    snapshot_date,
    validate_report,
)
from src.data.snapshot_crypto import decrypt_json
from src.screening.inflection_live import PriceDataRetryExhausted

SECRET = "test-snapshot-secret"


def _retry_exhausted() -> PriceDataRetryExhausted:
    return PriceDataRetryExhausted(
        {
            "retry_exhausted": "true",
            "expected_date": "2026-09-28",
            "universe": "3704",
            "missing": "1200",
            "price_data": "2504",
            "price_coverage": "67.6%",
            "latest_coverage": "99.6%",
            "failed_gate": "price_coverage",
            "attempts": "3",
            "latest_dates": "2026-09-25:2504",
            "dropped_future_bars": "0",
        }
    )


def _healthy_report() -> dict:
    return {
        "strategy_version": "jp-inflection-shadow-v3",
        "report_schema_version": 4,
        "source_commit_sha": "abc123",
        "generated_at": "2026-09-07T08:00:00+00:00",
        "universe_count": 3700,
        "price_data_count": 3500,
        "technical_usable_count": 3300,
        "latest_price_date": "2026-09-07",
        "latest_price_date_count": 3400,
        "market_coverage": {
            "Prime": {
                "universe": 1800,
                "price_data": 1700,
                "technical_usable": 1600,
                "latest_date_count": 1650,
            },
            "Standard": {
                "universe": 1400,
                "price_data": 1350,
                "technical_usable": 1250,
                "latest_date_count": 1300,
            },
            "Growth": {
                "universe": 500,
                "price_data": 450,
                "technical_usable": 450,
                "latest_date_count": 450,
            },
        },
        "deep_candidate_count": 2,
        "runtime_versions": {"yfinance": "1.7.0", "pandas": "3.0.5"},
        "candidates": [{"ticker": "1111.T"}, {"ticker": "2222.T"}],
    }


def test_validate_report_accepts_healthy_scan() -> None:
    validate_report(_healthy_report())


def test_default_snapshot_directory_is_strategy_v3() -> None:
    assert OUT_DIR.as_posix().endswith("/dashboard/data/inflection/v3")


def test_validate_report_rejects_small_universe() -> None:
    report = _healthy_report()
    report["universe_count"] = 2000
    with pytest.raises(RuntimeError, match="universe too small"):
        validate_report(report)


def test_validate_report_rejects_low_price_coverage() -> None:
    report = _healthy_report()
    report["price_data_count"] = 1000
    with pytest.raises(RuntimeError, match="price coverage too low"):
        validate_report(report)


def test_validate_report_rejects_low_technical_coverage() -> None:
    report = _healthy_report()
    report["technical_usable_count"] = 1000
    with pytest.raises(RuntimeError, match="technical coverage too low"):
        validate_report(report)


def test_validate_report_rejects_split_market_date() -> None:
    report = _healthy_report()
    report["latest_price_date_count"] = 1000
    report["latest_date_histogram"] = {"2026-09-07": 1000, "2026-09-06": 2500}
    report["stale_tickers_sample"] = ["1111.T"]
    with pytest.raises(RuntimeError, match=r"histogram=.*2026-09-06.*stale_tickers_sample=.*1111\.T"):
        validate_report(report)


def test_validate_report_rejects_invalid_market_date() -> None:
    report = _healthy_report()
    report["latest_price_date"] = "not-a-date"
    with pytest.raises(RuntimeError, match="invalid latest market date"):
        validate_report(report)


def test_validate_report_rejects_stale_data_on_normal_tse_session() -> None:
    report = _healthy_report()
    report["latest_price_date"] = "2026-09-04"
    with pytest.raises(RuntimeError, match="market data is stale"):
        validate_report(report)


def test_validate_report_accepts_previous_session_on_weekend() -> None:
    report = _healthy_report()
    report["generated_at"] = "2026-09-12T08:00:00+00:00"
    report["latest_price_date"] = "2026-09-11"
    validate_report(report)


def test_validate_report_accepts_previous_session_before_tse_close() -> None:
    report = _healthy_report()
    report["generated_at"] = "2026-09-08T05:00:00+00:00"
    report["latest_price_date"] = "2026-09-07"

    validate_report(report)


def test_validate_report_rejects_duplicate_candidates() -> None:
    report = _healthy_report()
    report["candidates"] = [{"ticker": "1111.T"}, {"ticker": "1111.T"}]
    with pytest.raises(RuntimeError, match="duplicate candidate"):
        validate_report(report)


def test_validate_report_rejects_market_coverage_total_mismatch() -> None:
    report = _healthy_report()
    report["market_coverage"]["Growth"]["universe"] -= 1

    with pytest.raises(RuntimeError, match="market coverage totals mismatch"):
        validate_report(report)


def test_validate_report_allows_low_coverage_in_one_market() -> None:
    report = _healthy_report()
    report.update(
        price_data_count=3250,
        technical_usable_count=3000,
        latest_price_date_count=3150,
    )
    report["market_coverage"] = {
        "Prime": {
            "universe": 1800,
            "price_data": 1800,
            "technical_usable": 1700,
            "latest_date_count": 1750,
        },
        "Standard": {
            "universe": 1400,
            "price_data": 1300,
            "technical_usable": 1200,
            "latest_date_count": 1250,
        },
        "Growth": {
            "universe": 500,
            "price_data": 150,
            "technical_usable": 100,
            "latest_date_count": 150,
        },
    }

    validate_report(report)


def test_validate_report_rejects_missing_reproducibility_metadata() -> None:
    report = _healthy_report()
    report.pop("source_commit_sha")
    with pytest.raises(RuntimeError, match="source commit"):
        validate_report(report)


def test_validate_report_rejects_missing_runtime_versions() -> None:
    report = _healthy_report()
    report.pop("runtime_versions")
    with pytest.raises(RuntimeError, match="runtime dependency"):
        validate_report(report)


def test_snapshot_date_uses_japan_calendar_date() -> None:
    now = datetime(2026, 9, 7, 15, 30, tzinfo=UTC)
    assert snapshot_date(now) == "2026-09-08"


def test_persist_report_uses_market_data_date_not_execution_date(tmp_path) -> None:
    out_dir = tmp_path / "inflection"
    latest = tmp_path / "latest.enc"
    snapshot, created = persist_report(
        _healthy_report(), encryption_secret=SECRET, out_dir=out_dir, latest_path=latest
    )
    assert created is True
    assert snapshot.name == "2026-09-07.enc"
    stored = decrypt_json(snapshot.read_text(encoding="utf-8"), SECRET)
    assert stored["latest_price_date"] == "2026-09-07"
    assert stored["storage"]["snapshot_date_basis"] == "latest_price_date"


def test_persist_report_does_not_overwrite_same_market_day_snapshot(tmp_path) -> None:
    out_dir = tmp_path / "inflection"
    latest = tmp_path / "latest.enc"
    first = _healthy_report()
    second = _healthy_report()
    second["source_commit_sha"] = "newer456"

    snapshot, created = persist_report(first, encryption_secret=SECRET, out_dir=out_dir, latest_path=latest)
    assert created is True
    original_snapshot = snapshot.read_text(encoding="utf-8")

    same_snapshot, created = persist_report(second, encryption_secret=SECRET, out_dir=out_dir, latest_path=latest)
    assert same_snapshot == snapshot
    assert created is False
    assert snapshot.read_text(encoding="utf-8") == original_snapshot
    assert decrypt_json(latest.read_text(encoding="utf-8"), SECRET)["source_commit_sha"] == "newer456"


def test_persist_report_rejects_filename_date_that_differs_from_market_date(tmp_path) -> None:
    with pytest.raises(ValueError, match="must match latest_price_date"):
        persist_report(
            _healthy_report(),
            encryption_secret=SECRET,
            out_dir=tmp_path / "inflection",
            latest_path=tmp_path / "latest.enc",
            date="2026-09-08",
        )


def test_main_writes_retry_diagnostics_to_github_output_without_persisting(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "github-output"
    error = _retry_exhausted()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    with (
        patch("scripts.run_inflection_shadow.snapshot_encryption_secret", return_value=SECRET),
        patch("scripts.run_inflection_shadow.scan_japan_inflection", side_effect=error),
        patch("scripts.run_inflection_shadow.persist_report") as persist,
        pytest.raises(PriceDataRetryExhausted) as raised,
    ):
        main()

    assert raised.value is error
    persist.assert_not_called()
    assert output.read_text(encoding="utf-8").splitlines() == [
        f"{key}={value}" for key, value in error.details.items()
    ]


def test_main_preserves_retry_error_without_github_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _retry_exhausted()
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    with (
        patch("scripts.run_inflection_shadow.snapshot_encryption_secret", return_value=SECRET),
        patch("scripts.run_inflection_shadow.scan_japan_inflection", side_effect=error),
        pytest.raises(PriceDataRetryExhausted) as raised,
    ):
        main()

    assert raised.value is error


def _v5_row(ticker: str, **overrides: object) -> dict:
    return {"ticker": ticker, "features": {}, "score_details": {}, "pre_score": 12.0} | overrides


def _healthy_report_v5() -> dict:
    return _healthy_report() | {
        "report_schema_version": 5,
        "liquid_candidate_count": 2500,
        "candidates": [_v5_row("1111.T"), _v5_row("2222.T")],
        "control_sample_size": 2,
        "control_sample": [_v5_row("3333.T"), _v5_row("4444.T")],
    }


def test_validate_report_accepts_healthy_schema5_scan() -> None:
    validate_report(_healthy_report_v5())


def test_validate_report_accepts_schema5_with_empty_control_sample() -> None:
    validate_report(_healthy_report_v5() | {"control_sample_size": 0, "control_sample": []})


def test_validate_report_accepts_control_sample_capped_by_liquid_count() -> None:
    validate_report(_healthy_report_v5() | {"control_sample_size": 25, "liquid_candidate_count": 2})


@pytest.mark.parametrize(
    "overrides",
    [
        {"features": None},
        {"score_details": None},
        {"pre_score": float("nan")},
        {"pre_score": float("inf")},
        {"pre_score": True},
        {"pre_score": None},
    ],
)
@pytest.mark.parametrize("section", ["candidates", "control_sample"])
def test_validate_report_rejects_invalid_schema5_rows(section: str, overrides: dict) -> None:
    report = _healthy_report_v5()
    report[section] = [_v5_row("1111.T" if section == "candidates" else "3333.T") | overrides, report[section][1]]
    with pytest.raises(RuntimeError, match="DATA_HEALTH"):
        validate_report(report)


def test_validate_report_rejects_empty_control_sample_ticker() -> None:
    report = _healthy_report_v5()
    report["control_sample"] = [_v5_row("") , _v5_row("4444.T")]
    with pytest.raises(RuntimeError, match="control sample ticker missing"):
        validate_report(report)


def test_validate_report_rejects_candidate_missing_schema5_field() -> None:
    report = _healthy_report_v5()
    del report["candidates"][0]["features"]
    with pytest.raises(RuntimeError, match="features/score_details missing"):
        validate_report(report)


def test_validate_report_rejects_control_sample_size_mismatch() -> None:
    report = _healthy_report_v5()
    report["control_sample"] = report["control_sample"][:1]
    with pytest.raises(RuntimeError, match="control sample size mismatch"):
        validate_report(report)


def test_validate_report_rejects_duplicate_control_tickers() -> None:
    report = _healthy_report_v5()
    report["control_sample"] = [_v5_row("3333.T"), _v5_row("3333.T")]
    with pytest.raises(RuntimeError, match="duplicate control sample tickers"):
        validate_report(report)


@pytest.mark.parametrize("override", [{"control_sample": None}, {"control_sample_size": None}, {"control_sample_size": True}])
def test_validate_report_rejects_missing_control_metadata(override: dict) -> None:
    with pytest.raises(RuntimeError, match="control sample metadata"):
        validate_report(_healthy_report_v5() | override)


def test_validate_report_accepts_rows_carrying_the_diagnostic_features() -> None:
    features = {"disclosure_age_days": 19, "up_day_ratio_60d": None, "max_daily_return_20d_pct": 4.2,
                "major_holder_filings_60d": 2, "major_holder_new_filings_60d": 1, "days_since_major_holder_filing": None}
    report = _healthy_report_v5()
    report["candidates"] = [_v5_row("1111.T", features=features), _v5_row("2222.T")]
    report["control_sample"] = [_v5_row("3333.T", features=features), _v5_row("4444.T")]

    validate_report(report)
