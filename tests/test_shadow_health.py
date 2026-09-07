from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from scripts.run_inflection_shadow import persist_report, snapshot_date, validate_report


def _healthy_report() -> dict:
    return {
        "strategy_version": "jp-inflection-shadow-v1",
        "report_schema_version": 2,
        "source_commit_sha": "abc123",
        "universe_count": 3700,
        "price_data_count": 3500,
        "technical_usable_count": 3300,
        "latest_price_date": "2026-09-07",
        "latest_price_date_count": 3400,
        "deep_candidate_count": 2,
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


def test_validate_report_rejects_stale_or_split_market_date() -> None:
    report = _healthy_report()
    report["latest_price_date_count"] = 1000
    with pytest.raises(RuntimeError, match="market-date coverage too low"):
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


def test_snapshot_date_uses_japan_calendar_date() -> None:
    now = datetime(2026, 9, 7, 15, 30, tzinfo=UTC)
    assert snapshot_date(now) == "2026-09-08"


def test_persist_report_does_not_overwrite_same_day_snapshot(tmp_path) -> None:
    out_dir = tmp_path / "inflection"
    latest = tmp_path / "latest.json"
    first = _healthy_report()
    second = _healthy_report()
    second["source_commit_sha"] = "newer456"

    snapshot, created = persist_report(first, out_dir=out_dir, latest_path=latest, date="2026-09-08")
    assert created is True
    original_snapshot = json.loads(snapshot.read_text(encoding="utf-8"))

    same_snapshot, created = persist_report(second, out_dir=out_dir, latest_path=latest, date="2026-09-08")
    assert same_snapshot == snapshot
    assert created is False
    assert json.loads(snapshot.read_text(encoding="utf-8")) == original_snapshot
    assert json.loads(latest.read_text(encoding="utf-8"))["source_commit_sha"] == "newer456"
