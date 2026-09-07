from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.run_inflection_shadow import snapshot_date, validate_report


def _healthy_report() -> dict:
    return {
        "universe_count": 3700,
        "price_data_count": 3600,
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


def test_validate_report_rejects_duplicate_candidates() -> None:
    report = _healthy_report()
    report["candidates"] = [{"ticker": "1111.T"}, {"ticker": "1111.T"}]
    with pytest.raises(RuntimeError, match="duplicate candidate"):
        validate_report(report)


def test_snapshot_date_uses_japan_calendar_date() -> None:
    # 15:30 UTC is already the next calendar day in Japan.
    now = datetime(2026, 9, 7, 15, 30, tzinfo=UTC)
    assert snapshot_date(now) == "2026-09-08"
