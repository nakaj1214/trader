from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.data.session_gaps import (
    latest_settled_session,
    missing_sessions,
    previous_session_missing,
    session_coverage,
)

SEPTEMBER = [
    "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18",  # one full week
    "2026-09-24", "2026-09-25",  # 9/21-9/23 are exchange holidays
    "2026-09-29", "2026-09-30",  # 9/28 (Monday) is missing
]


def make_dir(tmp_path: Path, dates: list[str], name: str = "v3") -> Path:
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    for day in dates:
        (directory / f"{day}.enc").write_text("x", encoding="utf-8")
    return directory


def test_only_real_missing_sessions_are_gaps_not_weekends_or_holidays(tmp_path: Path) -> None:
    directory = make_dir(tmp_path, SEPTEMBER)

    assert missing_sessions(directory, date(2026, 9, 30)) == ["2026-09-28"]


def test_a_session_after_the_last_snapshot_counts_when_the_end_is_later(tmp_path: Path) -> None:
    directory = make_dir(tmp_path, SEPTEMBER)

    assert missing_sessions(directory, date(2026, 10, 2)) == ["2026-09-28", "2026-10-01", "2026-10-02"]


def test_no_snapshots_or_an_end_before_the_first_snapshot_means_no_gaps(tmp_path: Path) -> None:
    assert missing_sessions(tmp_path / "does-not-exist", date(2026, 9, 30)) == []
    assert missing_sessions(make_dir(tmp_path, ["2026-09-24"], "late"), date(2026, 9, 1)) == []


def test_non_snapshot_files_are_ignored(tmp_path: Path) -> None:
    directory = make_dir(tmp_path, ["2026-09-14", "2026-09-16"])
    (directory / "notes.txt").write_text("x", encoding="utf-8")
    (directory / "2026-09-15.json").write_text("x", encoding="utf-8")

    assert missing_sessions(directory, date(2026, 9, 16)) == ["2026-09-15"]


def test_previous_session_missing_reports_the_skipped_day(tmp_path: Path) -> None:
    directory = make_dir(tmp_path, SEPTEMBER)

    assert previous_session_missing(directory, date(2026, 9, 29)) == "2026-09-28"
    assert previous_session_missing(directory, date(2026, 9, 30)) is None  # 9/29 exists
    assert previous_session_missing(directory, date(2026, 9, 28)) is None  # the previous session is Friday 9/25
    assert previous_session_missing(directory, date(2026, 9, 24)) is None  # 9/18 exists across the holidays


def test_days_before_the_first_snapshot_never_count_as_missing(tmp_path: Path) -> None:
    directory = make_dir(tmp_path, ["2026-09-24", "2026-09-25"])

    assert previous_session_missing(directory, date(2026, 9, 24)) is None  # 9/18 predates the first snapshot
    assert previous_session_missing(tmp_path / "empty", date(2026, 9, 24)) is None


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 2, 7, 40, tzinfo=UTC), date(2026, 10, 2)),  # Fri 16:40 JST, after the close
        (datetime(2026, 10, 2, 5, 0, tzinfo=UTC), date(2026, 10, 1)),  # Fri 14:00 JST, before the close
        (datetime(2026, 10, 4, 0, 30, tzinfo=UTC), date(2026, 10, 2)),  # Sunday 09:30 JST
        (datetime(2026, 9, 22, 1, 0, tzinfo=UTC), date(2026, 9, 18)),  # holiday Tuesday: back over the long weekend
    ],
)
def test_latest_settled_session_handles_close_weekends_and_holidays(now: datetime, expected: date) -> None:
    assert latest_settled_session(now) == expected


def test_latest_settled_session_requires_a_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        latest_settled_session(datetime(2026, 10, 2, 7, 40))  # noqa: DTZ001 - a naive time is the point of this test


def test_consecutive_failures_after_the_last_snapshot_are_visible_at_the_next_weekly_run(tmp_path: Path) -> None:
    """Review: scans fail Mon-Fri; the Sunday run must still report all five sessions."""
    directory = make_dir(tmp_path, ["2026-09-24", "2026-09-25"])
    sunday = datetime(2026, 10, 4, 0, 30, tzinfo=UTC)

    coverage = session_coverage(directory, latest_settled_session(sunday))

    assert coverage["missing_sessions"] == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]
    assert coverage["last_snapshot_date"] == "2026-09-25" and coverage["expected_sessions"] == 7


def test_session_coverage_counts_and_the_empty_case(tmp_path: Path) -> None:
    directory = make_dir(tmp_path, SEPTEMBER)

    assert session_coverage(directory, date(2026, 9, 30)) == {
        "first_snapshot_date": "2026-09-14",
        "last_snapshot_date": "2026-09-30",
        "expected_sessions": 10,
        "snapshots": 9,
        "missing_sessions": ["2026-09-28"],
    }
    assert session_coverage(tmp_path / "none", date(2026, 9, 30)) == {
        "first_snapshot_date": None,
        "last_snapshot_date": None,
        "expected_sessions": 0,
        "snapshots": 0,
        "missing_sessions": [],
    }
