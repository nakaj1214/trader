"""Point-in-time helpers to prevent look-ahead bias."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def _as_aware_utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_available_at(disclosed_at: str | datetime, signal_at: str | datetime) -> bool:
    """Return True only if the information was public by signal time."""
    return _as_aware_utc(disclosed_at) <= _as_aware_utc(signal_at)


def filter_available_records(
    records: Iterable[dict[str, Any]],
    signal_at: str | datetime,
    disclosure_field: str = "disclosed_at",
) -> list[dict[str, Any]]:
    """Filter a dataset to information that existed at the decision timestamp."""
    available: list[dict[str, Any]] = []
    for record in records:
        disclosed_at = record.get(disclosure_field)
        if disclosed_at is None:
            continue
        if is_available_at(disclosed_at, signal_at):
            available.append(record)
    return available


def latest_available_record(
    records: Iterable[dict[str, Any]],
    signal_at: str | datetime,
    disclosure_field: str = "disclosed_at",
) -> dict[str, Any] | None:
    available = filter_available_records(records, signal_at, disclosure_field)
    if not available:
        return None
    return max(available, key=lambda row: _as_aware_utc(row[disclosure_field]))
