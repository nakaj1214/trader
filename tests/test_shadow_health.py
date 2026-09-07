from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.run_inflection_shadow import persist_report, snapshot_date, validate_report
from src.data.snapshot_crypto import decrypt_json

SECRET = "test-snapshot-secret"


def _healthy_report() -> dict:
    return {
        "strategy_version": "jp-inflection-shadow-v1",
        "report_schema_version": 3,
        "source_commit_sha": "abc123",
        "universe_count": 3700,
        "price_data_count": 3500,
        "technical_usable_count": 3300,
        "latest_price_date": "2026-09-07",
        "latest_price_date_count": 3400,
        "deep_candidate_count": 2,
        "runtime_versions": {"yfinance": "1.7.0", "pandas": "3.0.5"},
        "candidates": [{"ticker": "1111.T"}, {"ticker": "2222.T"}],
    }


def test_validate_report_accepts_healthy_scan() -> None:
    validate_report(_healthy_report())


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
    with pytest.raises(RuntimeError, match="market-date coverage too low"):
        validate_report(report)


def test_validate_report_rejects_invalid_market_date() -> None:
    report = _healthy_report()
    report["latest_price_date"] = "not-a-date"
    with pytest.raises(RuntimeError, match="invalid latest market date"):
        validate_report(report)


def test_validate_report_rejects_duplicate_candidates() -> None:
    report = _healthy_report()
    report["candidates"] = [{"ticker": "1111.T"}, {"ticker": "1111.T"}]
    with pytest.raises(RuntimeError, match="duplicate candidate"):
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
