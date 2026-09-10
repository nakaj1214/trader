from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import requests

from scripts.run_position_monitor import is_in_session, run
from src.data.live_quote import SplitAdjustedHistory, TodayQuote

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 8, 12, 35, tzinfo=JST)
HOLDING = {
    "ticker": "1111.T",
    "entry_date": "2026-09-07",
    "entry_price": 100.0,
    "trailing_stop_pct": 10.0,
}
HISTORY = SplitAdjustedHistory(100.0, pd.Series(dtype=float), pd.Series(dtype=float))
BAR_INDEX = pd.DatetimeIndex([NOW - timedelta(minutes=2), NOW - timedelta(minutes=1)])
BARS = pd.DataFrame(
    {
        "Open": [100.0, 118.0],
        "High": [120.0, 119.0],
        "Low": [95.0, 107.0],
        "Close": [118.0, 109.0],
    },
    index=BAR_INDEX,
)
QUOTE = TodayQuote(100.0, 120.0, 95.0, 109.0, BAR_INDEX[-1].isoformat())
TRIGGERED_STATUS = {
    "ticker": "1111.T",
    "entry_date": "2026-09-07",
    "triggered": True,
    "exit_reason": "trailing_stop",
    "triggered_at": "2026-09-08T09:03:00+09:00",
    "last_notified_at": "2026-09-08T09:03:01+09:00",
}


@contextmanager
def _dependencies(
    holdings: list[dict[str, Any]],
    *,
    previous: list[dict[str, Any]] | None = None,
    bars: pd.DataFrame | None = BARS,
    quote: TodayQuote | None = QUOTE,
    session: bool = True,
    market_window: bool = True,
) -> Iterator[dict[str, Mock]]:
    calendar = Mock()
    calendar.is_session.return_value = session
    calendar.is_open_on_minute.return_value = market_window
    calendar.session_close.return_value = pd.Timestamp("2026-09-08 15:30", tz=JST)
    response = Mock()
    with (
        patch("scripts.run_position_monitor.read_status", return_value=previous or []) as read_status,
        patch("scripts.run_position_monitor.read_holdings", return_value=holdings),
        patch("scripts.run_position_monitor.write_status") as write,
        patch("scripts.run_position_monitor.fetch_split_adjusted_history", return_value=HISTORY) as fetch_history,
        patch("scripts.run_position_monitor.fetch_today_bars", return_value=bars) as fetch_bars,
        patch("scripts.run_position_monitor.build_today_quote", return_value=quote) as build_quote,
        patch("scripts.run_position_monitor.xcals.get_calendar", return_value=calendar),
        patch("scripts.run_position_monitor.requests.post", return_value=response) as post,
    ):
        yield {
            "read_status": read_status,
            "write": write,
            "fetch_history": fetch_history,
            "fetch_bars": fetch_bars,
            "build_quote": build_quote,
            "post": post,
            "response": response,
        }


def test_empty_holdings_exit_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([]) as deps:
        assert run(dry_run=False, evaluated_at=NOW) == 0

    deps["write"].assert_called_once_with([])
    deps["fetch_history"].assert_not_called()
    deps["fetch_bars"].assert_not_called()
    deps["post"].assert_not_called()


def test_non_session_skips_price_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], session=False) as deps:
        assert run(dry_run=False, evaluated_at=NOW) == 0

    deps["fetch_history"].assert_not_called()
    deps["fetch_bars"].assert_not_called()
    deps["post"].assert_not_called()


def test_dry_run_writes_triggered_status_without_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with _dependencies([HOLDING]) as deps:
        assert run(dry_run=True, evaluated_at=NOW) == 0

    row = deps["write"].call_args.args[0][0]
    assert row["status"] == "ok"
    assert row["triggered"] is True
    assert row["triggered_at"] == NOW.isoformat()
    assert row["last_notified_at"] == ""
    deps["post"].assert_not_called()
    deps["fetch_bars"].assert_called_once_with("1111.T")
    assert deps["build_quote"].call_args.args[0] is BARS


def test_trigger_and_partial_error_send_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([{"ticker": ""}, HOLDING]) as deps:
        assert run(dry_run=False, evaluated_at=NOW) == 0

    rows = deps["write"].call_args.args[0]
    assert [row["status"] for row in rows] == ["error", "ok"]
    assert rows[1]["last_notified_at"] == NOW.isoformat()
    assert deps["post"].call_count == 2
    assert "検証用アラート" in deps["post"].call_args_list[0].kwargs["json"]["text"]
    assert "一部銘柄" in deps["post"].call_args_list[1].kwargs["json"]["text"]
    assert deps["response"].raise_for_status.call_count == 2


def test_continuing_notified_trigger_is_not_sent_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], previous=[TRIGGERED_STATUS]) as deps:
        assert run(dry_run=False, evaluated_at=NOW) == 0

    row = deps["write"].call_args.args[0][0]
    assert row["triggered_at"] == TRIGGERED_STATUS["triggered_at"]
    assert row["last_notified_at"] == TRIGGERED_STATUS["last_notified_at"]
    deps["post"].assert_not_called()


def test_cleared_trigger_resets_notification_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    index = pd.DatetimeIndex([NOW - timedelta(minutes=1)])
    bars = pd.DataFrame(
        {"Open": [100.0], "High": [105.0], "Low": [95.0], "Close": [100.0]},
        index=index,
    )
    quote = TodayQuote(100.0, 105.0, 95.0, 100.0, index[-1].isoformat())
    with _dependencies([HOLDING], previous=[TRIGGERED_STATUS], bars=bars, quote=quote) as deps:
        assert run(dry_run=False, evaluated_at=NOW) == 0

    row = deps["write"].call_args.args[0][0]
    assert row["triggered"] is False
    assert row["triggered_at"] == ""
    assert row["last_notified_at"] == ""
    deps["post"].assert_not_called()


def test_stale_row_preserves_previous_trigger_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with (
        _dependencies([HOLDING], previous=[TRIGGERED_STATUS], bars=None) as deps,
        pytest.raises(RuntimeError, match="no holdings"),
    ):
        run(dry_run=False, evaluated_at=NOW)

    row = deps["write"].call_args.args[0][0]
    assert row["status"] == "stale"
    assert row["triggered"] is True
    assert row["exit_reason"] == TRIGGERED_STATUS["exit_reason"]
    assert row["triggered_at"] == TRIGGERED_STATUS["triggered_at"]
    assert row["last_notified_at"] == TRIGGERED_STATUS["last_notified_at"]
    deps["post"].assert_not_called()


def test_error_row_preserves_previous_trigger_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with (
        _dependencies([HOLDING], previous=[TRIGGERED_STATUS]) as deps,
        pytest.raises(RuntimeError, match="no holdings"),
    ):
        deps["fetch_history"].side_effect = ValueError("bad daily history")
        run(dry_run=False, evaluated_at=NOW)

    row = deps["write"].call_args.args[0][0]
    assert row["status"] == "error"
    assert row["triggered"] is True
    assert row["triggered_at"] == TRIGGERED_STATUS["triggered_at"]
    assert row["last_notified_at"] == TRIGGERED_STATUS["last_notified_at"]


def test_all_stale_rows_fail_after_status_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], bars=None) as deps, pytest.raises(RuntimeError, match="no holdings"):
        run(dry_run=False, evaluated_at=NOW)

    assert deps["write"].call_args.args[0][0]["status"] == "stale"
    deps["post"].assert_not_called()


@pytest.mark.parametrize(
    ("holdings", "previous", "source"),
    [
        ([HOLDING, HOLDING], [], "holdings"),
        ([HOLDING], [TRIGGERED_STATUS, TRIGGERED_STATUS], "status"),
    ],
)
def test_duplicate_position_keys_fail_before_write(
    monkeypatch: pytest.MonkeyPatch,
    holdings: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    source: str,
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies(holdings, previous=previous) as deps, pytest.raises(ValueError, match=f"in {source}"):
        run(dry_run=False, evaluated_at=NOW)

    deps["write"].assert_not_called()


def test_webhook_is_required_outside_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        run(dry_run=False, evaluated_at=NOW)


def test_status_write_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING]) as deps:
        deps["write"].side_effect = RuntimeError("sheet unavailable")
        with pytest.raises(RuntimeError, match="sheet unavailable"):
            run(dry_run=False, evaluated_at=NOW)


def test_slack_http_failure_saves_retryable_state_then_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING]) as deps:
        deps["response"].raise_for_status.side_effect = requests.HTTPError("bad webhook")
        with pytest.raises(requests.HTTPError, match="bad webhook"):
            run(dry_run=False, evaluated_at=NOW)

    saved = deps["write"].call_args.args[0][0]
    assert saved["triggered"] is True
    assert saved["last_notified_at"] == ""
    deps["write"].assert_called_once()

    with _dependencies([HOLDING], previous=[saved]) as retry:
        assert run(dry_run=False, evaluated_at=NOW) == 0

    retried = retry["write"].call_args.args[0][0]
    assert retried["triggered_at"] == saved["triggered_at"]
    assert retried["last_notified_at"] == NOW.isoformat()
    retry["post"].assert_called_once()


@pytest.mark.parametrize(
    ("quote_time", "expected_status"),
    [
        (datetime(2026, 9, 8, 14, 40, tzinfo=JST), "stale"),
        (datetime(2026, 9, 8, 15, 30, tzinfo=JST), "ok"),
    ],
)
def test_run_uses_ten_minute_threshold_during_close_grace(
    monkeypatch: pytest.MonkeyPatch,
    quote_time: datetime,
    expected_status: str,
) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    evaluated_at = datetime(2026, 9, 8, 15, 35, tzinfo=JST)
    bars = pd.DataFrame(
        {"Open": [100.0], "High": [105.0], "Low": [95.0], "Close": [100.0]},
        index=pd.DatetimeIndex([quote_time]),
    )
    quote = TodayQuote(100.0, 105.0, 95.0, 100.0, quote_time.isoformat())
    with _dependencies([HOLDING], bars=bars, quote=quote, market_window=False) as deps:
        if expected_status == "stale":
            with pytest.raises(RuntimeError, match="no holdings"):
                run(dry_run=True, evaluated_at=evaluated_at)
        else:
            assert run(dry_run=True, evaluated_at=evaluated_at) == 0

    assert deps["write"].call_args.args[0][0]["status"] == expected_status


@pytest.mark.parametrize(
    ("when", "open_now", "expected"),
    [
        (datetime(2026, 9, 8, 9, 3, tzinfo=JST), True, True),
        (datetime(2026, 9, 8, 12, 0, tzinfo=JST), False, False),
        (datetime(2026, 9, 8, 15, 35, tzinfo=JST), False, True),
        (datetime(2026, 9, 8, 16, 5, tzinfo=JST), False, False),
    ],
)
def test_market_window_includes_thirty_minutes_after_close(
    when: datetime,
    open_now: bool,
    expected: bool,
) -> None:
    calendar = Mock()
    calendar.is_open_on_minute.return_value = open_now
    calendar.is_session.return_value = True
    calendar.session_close.return_value = pd.Timestamp("2026-09-08 15:30", tz=JST)

    assert is_in_session(calendar, when) is expected
