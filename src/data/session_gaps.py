"""Find trading sessions for which no daily snapshot exists.

A missed scan leaves nothing behind but a missing file, so gaps are derived by comparing the TSE
calendar with the snapshot file names (nothing is decrypted). Holidays and weekends are never gaps.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

from src.data.forward_prices import snapshot_dates
from src.data.market_calendar import TSE_CALENDAR, expected_tse_session_date


def _sessions(start: date, end: date) -> list[date]:
    if start > end:
        return []
    calendar = xcals.get_calendar(TSE_CALENDAR)
    return [timestamp.date() for timestamp in calendar.sessions_in_range(start.isoformat(), end.isoformat())]


def latest_settled_session(now: datetime) -> date:
    """The newest session whose snapshot should exist at ``now`` (tz-aware).

    Handles weekends, holidays and a session that has not closed yet (its data is not final).
    """
    return date.fromisoformat(expected_tse_session_date(now))


def missing_sessions(snapshot_dir: Path, through: date) -> list[str]:
    """Sessions from the first snapshot up to and including ``through`` that have no snapshot."""
    present = set(snapshot_dates([snapshot_dir]))
    if not present:
        return []
    return [str(day) for day in _sessions(min(present), through) if day not in present]


def previous_session_missing(snapshot_dir: Path, market_date: date) -> str | None:
    """The session before ``market_date`` if it has no snapshot (days before the first snapshot never count)."""
    present = set(snapshot_dates([snapshot_dir]))
    if not present:
        return None
    earlier = _sessions(market_date - timedelta(days=14), market_date - timedelta(days=1))
    if not earlier:
        return None
    previous = earlier[-1]
    return str(previous) if previous >= min(present) and previous not in present else None


def session_coverage(snapshot_dir: Path, through: date) -> dict[str, Any]:
    """How many sessions were expected, how many snapshots exist, and which sessions are missing."""
    present = sorted(snapshot_dates([snapshot_dir]))
    if not present:
        return {
            "first_snapshot_date": None,
            "last_snapshot_date": None,
            "expected_sessions": 0,
            "snapshots": 0,
            "missing_sessions": [],
        }
    expected = _sessions(present[0], through)
    missing = [str(day) for day in expected if day not in set(present)]
    return {
        "first_snapshot_date": str(present[0]),
        "last_snapshot_date": str(present[-1]),
        "expected_sessions": len(expected),
        "snapshots": len(expected) - len(missing),
        "missing_sessions": missing,
    }
