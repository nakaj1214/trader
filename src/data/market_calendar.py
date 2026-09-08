"""Tokyo Stock Exchange session-date helpers."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

JST = ZoneInfo("Asia/Tokyo")
TSE_CALENDAR = "XTKS"


def expected_tse_session_date(generated_at: str | datetime) -> str:
    """Return the latest TSE session that should exist when the scan was generated.

    Production scans run after the TSE close. On exchange holidays the expected
    session is the immediately preceding TSE session, preventing holidays from
    being mistaken for stale provider data while still detecting normal-day lag.
    """
    timestamp = pd.Timestamp(generated_at)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    japan_date = str(timestamp.tz_convert(JST).date().isoformat())
    calendar = xcals.get_calendar(TSE_CALENDAR)
    if bool(calendar.is_session(japan_date)):
        session = pd.Timestamp(japan_date)
        if timestamp >= calendar.session_close(session):
            return japan_date
        return str(calendar.previous_session(session).date().isoformat())
    previous_session = calendar.date_to_session(japan_date, direction="previous")
    return str(previous_session.date().isoformat())
