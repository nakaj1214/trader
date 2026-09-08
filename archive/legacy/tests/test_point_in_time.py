from __future__ import annotations

from src.data.point_in_time import filter_available_records, is_available_at, latest_available_record


def test_information_after_signal_is_rejected() -> None:
    assert is_available_at("2026-05-14T06:30:00Z", "2026-05-14T06:29:59Z") is False
    assert is_available_at("2026-05-14T06:30:00Z", "2026-05-14T06:30:00Z") is True


def test_filter_available_records_uses_disclosure_time_not_period_end() -> None:
    records = [
        {
            "period_end": "2026-03-31",
            "disclosed_at": "2026-05-14T06:30:00Z",
            "operating_profit": 100,
        },
        {
            "period_end": "2025-12-31",
            "disclosed_at": "2026-02-10T06:30:00Z",
            "operating_profit": 80,
        },
    ]
    rows = filter_available_records(records, "2026-05-01T00:00:00Z")
    assert len(rows) == 1
    assert rows[0]["operating_profit"] == 80


def test_latest_available_record_returns_latest_public_information() -> None:
    records = [
        {"disclosed_at": "2026-02-10T06:30:00Z", "value": 1},
        {"disclosed_at": "2026-05-14T06:30:00Z", "value": 2},
    ]
    assert latest_available_record(records, "2026-04-01T00:00:00Z")["value"] == 1
    assert latest_available_record(records, "2026-06-01T00:00:00Z")["value"] == 2
