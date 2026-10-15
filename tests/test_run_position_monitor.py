from __future__ import annotations

import logging
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import pytest
import requests

from scripts.run_position_monitor import is_in_session, run
from src.data.live_quote import SplitAdjustedHistory, TodayQuote
from src.data.live_quote import fetch_session_bars as live_fetch_session_bars
from src.data.live_quote import fetch_today_bars as live_fetch_today_bars

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


@pytest.fixture(autouse=True)
def _production_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")


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
    if bars is not None and not bars.attrs:
        bars = bars.copy()
        bars["Volume"] = 1.0
        bars.attrs = {"requested_date": bars.index[-1].date().isoformat(), "daily_bar": {
            "Open": float(bars["Open"].iloc[0]), "High": float(bars["High"].max()),
            "Low": float(bars["Low"].min()), "Close": float(bars["Close"].iloc[-1]), "Volume": float(len(bars)),
        }}
    calendar = Mock(wraps=xcals.get_calendar("XTKS"))
    calendar.is_session.return_value = session
    calendar.is_open_on_minute.return_value = market_window
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
    pd.testing.assert_frame_equal(deps["build_quote"].call_args.args[0].drop(columns="Volume"), BARS)


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


def test_recovered_price_preserves_the_record_of_a_notified_touch(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert row["triggered"] is True
    assert row["triggered_at"] == TRIGGERED_STATUS["triggered_at"]
    assert row["last_notified_at"] == TRIGGERED_STATUS["last_notified_at"]
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
def test_run_uses_twenty_minute_threshold_during_close_grace(
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


# --- REQ-047: stop-proximity warning --------------------------------------------------------------------

NEAR_BARS = pd.DataFrame(
    {"Open": [100.0, 118.0], "High": [120.0, 119.0], "Low": [99.0, 109.0], "Close": [118.0, 110.0]},
    index=BAR_INDEX,
)  # stop = 120 * 0.9 = 108, last = 110: 1.85% above it and not touched
NEAR_QUOTE = TodayQuote(100.0, 120.0, 99.0, 110.0, BAR_INDEX[-1].isoformat())
FAR_BARS = pd.DataFrame(
    {"Open": [100.0, 118.0], "High": [120.0, 126.0], "Low": [99.0, 117.0], "Close": [118.0, 125.0]},
    index=BAR_INDEX,
)  # stop = 126 * 0.9 = 113.4, last = 125: about 10% above it
FAR_QUOTE = TodayQuote(100.0, 126.0, 99.0, 125.0, BAR_INDEX[-1].isoformat())
OTHER_ENTRY = {**HOLDING, "entry_date": "2026-09-04"}


def _warned_row(entry_date: str = "2026-09-07", when: datetime = NOW, ticker: str = "1111.T") -> dict[str, Any]:
    return {"ticker": ticker, "entry_date": entry_date, "triggered": False, "last_warned_at": when.isoformat()}


def _warning_posts(deps: dict[str, Mock]) -> list[str]:
    return [call.kwargs["json"]["text"] for call in deps["post"].call_args_list if "残り" in call.kwargs["json"]["text"]]


def _written(deps: dict[str, Mock]) -> list[dict[str, Any]]:
    return list(deps["write"].call_args.args[0])


def test_a_stock_close_to_its_stop_is_warned_once_and_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        assert run(dry_run=False, evaluated_at=NOW) == 0

    (text,) = _warning_posts(deps)
    assert "検証用アラート" in text and "確定した売買判断ではありません" in text and "1111.T" in text
    assert "3%以内" in text and "残り1.9%" in text
    (row,) = _written(deps)
    assert row["triggered"] is False and row["last_warned_at"] == NOW.isoformat()


def test_the_same_ticker_is_not_warned_again_the_same_day_but_is_the_next_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    later = NOW + timedelta(minutes=5)
    with _dependencies([HOLDING], previous=[_warned_row()], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        run(dry_run=False, evaluated_at=later)
    assert _warning_posts(deps) == []
    assert _written(deps)[0]["last_warned_at"] == NOW.isoformat()  # the original time is kept

    yesterday = _warned_row(when=NOW - timedelta(days=1))
    with _dependencies([HOLDING], previous=[yesterday], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        run(dry_run=False, evaluated_at=later)
    assert len(_warning_posts(deps)) == 1
    assert _written(deps)[0]["last_warned_at"] == later.isoformat()


def test_no_warning_when_far_from_the_stop_or_already_triggered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], bars=FAR_BARS, quote=FAR_QUOTE) as deps:
        run(dry_run=False, evaluated_at=NOW)
    assert _warning_posts(deps) == [] and _written(deps)[0]["last_warned_at"] == ""

    with _dependencies([HOLDING]) as deps:  # the default bars trigger the stop: that is a different alert
        run(dry_run=False, evaluated_at=NOW)
    assert _warning_posts(deps) == [] and _written(deps)[0]["triggered"] is True


def test_dry_run_neither_sends_nor_marks_anything_warned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with _dependencies([HOLDING], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        run(dry_run=True, evaluated_at=NOW)

    deps["post"].assert_not_called()
    assert _written(deps)[0]["last_warned_at"] == ""


def test_a_failed_send_does_not_mark_the_warning_so_the_next_run_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        deps["response"].raise_for_status.side_effect = requests.HTTPError("slack down")
        with pytest.raises(requests.HTTPError):
            run(dry_run=False, evaluated_at=NOW)

    assert _written(deps)[0]["last_warned_at"] == ""  # state is still persisted, without a success time


def test_two_positions_of_one_ticker_close_to_the_stop_are_warned_as_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING, OTHER_ENTRY], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        run(dry_run=False, evaluated_at=NOW)

    (text,) = _warning_posts(deps)
    assert text.count("1111.T") == 1  # listed once in the message
    assert [row["last_warned_at"] for row in _written(deps)] == [NOW.isoformat()] * 2
    deps["fetch_bars"].assert_called_once_with("1111.T")


def test_shared_today_bars_are_copied_for_each_position() -> None:
    contaminated: list[bool] = []

    def build_quote(bars: pd.DataFrame) -> TodayQuote:
        contaminated.append("position_marker" in bars.attrs)
        bars.attrs["position_marker"] = True
        return QUOTE

    with _dependencies([HOLDING, OTHER_ENTRY]) as deps:
        deps["build_quote"].side_effect = build_quote
        run(dry_run=True, evaluated_at=NOW)

    assert contaminated == [False, False]
    deps["fetch_bars"].assert_called_once_with("1111.T")


def test_shared_today_bar_failure_is_ticker_scoped() -> None:
    holdings = [HOLDING, OTHER_ENTRY, {**HOLDING, "ticker": "2222.T"}]
    good_bars = BARS.copy()
    good_bars["Volume"] = 1.0
    good_bars.attrs = {
        "requested_date": NOW.date().isoformat(),
        "daily_bar": {"Open": 100.0, "High": 120.0, "Low": 95.0, "Close": 109.0, "Volume": 2.0},
    }

    def fetch_bars(ticker: str) -> pd.DataFrame:
        if ticker == "1111.T":
            raise TypeError("provider bug")
        return good_bars

    with _dependencies(holdings) as deps:
        deps["fetch_bars"].side_effect = fetch_bars
        run(dry_run=True, evaluated_at=NOW)

    assert [row["status"] for row in _written(deps)] == ["error", "error", "ok"]
    assert [call.args[0] for call in deps["fetch_bars"].call_args_list] == ["1111.T", "2222.T"]


def test_replacing_a_warned_position_the_same_day_keeps_the_ticker_warned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review: warn -> swap the position for another entry date -> run again must stay at one warning."""
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:  # run 1: warns
        run(dry_run=False, evaluated_at=NOW)
    assert len(_warning_posts(deps)) == 1
    after_first = _written(deps)

    with _dependencies([OTHER_ENTRY], previous=after_first, bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:  # run 2: swapped
        run(dry_run=False, evaluated_at=NOW + timedelta(minutes=5))
    assert _warning_posts(deps) == []
    after_second = _written(deps)
    assert [row["entry_date"] for row in after_second] == ["2026-09-04"]  # the old row is gone...
    assert after_second[0]["last_warned_at"] == NOW.isoformat()  # ...but the new row carries the warning time

    with _dependencies([OTHER_ENTRY], previous=after_second, bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:  # run 3
        run(dry_run=False, evaluated_at=NOW + timedelta(minutes=10))
    assert _warning_posts(deps) == []

    next_day = [{**row, "last_warned_at": (NOW - timedelta(days=1)).isoformat()} for row in after_second]
    with _dependencies([OTHER_ENTRY], previous=next_day, bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        run(dry_run=False, evaluated_at=NOW + timedelta(minutes=15))
    assert len(_warning_posts(deps)) == 1  # the next day it can warn again


def test_stale_rows_keep_the_warning_time_even_when_every_quote_is_unusable() -> None:
    previous = [_warned_row()]
    with (
        _dependencies([OTHER_ENTRY], previous=previous, bars=None, quote=None) as deps,
        pytest.raises(RuntimeError, match="no holdings had a usable current quote"),
    ):
        run(dry_run=True, evaluated_at=NOW)

    (row,) = _written(deps)
    assert row["status"] == "stale" and row["last_warned_at"] == NOW.isoformat()  # carried by ticker


def test_a_ticker_warned_earlier_today_is_not_repeated_while_another_one_is_warned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING, {**HOLDING, "ticker": "2222.T"}], previous=[_warned_row(ticker="2222.T")], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        run(dry_run=False, evaluated_at=NOW)

    by_ticker = {row["ticker"]: row for row in _written(deps)}
    assert by_ticker["1111.T"]["last_warned_at"] == NOW.isoformat()  # warned now
    assert by_ticker["2222.T"]["last_warned_at"] == NOW.isoformat()  # already warned today: not repeated, time kept
    assert len(_warning_posts(deps)) == 1 and "2222.T" not in _warning_posts(deps)[0]


def test_unreadable_or_non_numeric_warning_state_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    junk = [{"ticker": "1111.T", "entry_date": "2026-09-07", "last_warned_at": "not a time"}, {"ticker": "", "last_warned_at": NOW.isoformat()}]
    with _dependencies([HOLDING], previous=junk, bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        run(dry_run=False, evaluated_at=NOW)

    assert len(_warning_posts(deps)) == 1  # junk does not suppress the warning


@pytest.mark.parametrize(("count", "reference", "warn"), [(20, 80.0, True), (20, 84.0, False), (19, 80.0, False)])
def test_overheating_warning_boundaries_and_deduplication(
    monkeypatch: pytest.MonkeyPatch, count: int, reference: float, warn: bool
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    closes = pd.Series([reference] * count, index=pd.bdate_range(end="2026-09-07", periods=count))
    history = SplitAdjustedHistory(100.0, pd.Series(dtype=float), closes)
    with _dependencies([HOLDING], bars=FAR_BARS, quote=FAR_QUOTE) as deps:
        deps["fetch_history"].return_value = history
        run(dry_run=False, evaluated_at=NOW)
        rows = _written(deps)
    texts = [call.kwargs["json"]["text"] for call in deps["post"].call_args_list]
    assert bool(texts) is warn
    if warn:
        assert len(texts) == 1 and "1111.T: 過熱: 20日で +56.2%" in texts[0]
        assert rows[0]["last_warned_at"] == NOW.isoformat()
        with _dependencies([HOLDING], previous=rows, bars=FAR_BARS, quote=FAR_QUOTE) as second:
            second["fetch_history"].return_value = history
            run(dry_run=False, evaluated_at=NOW)
        second["post"].assert_not_called()


def test_overheating_and_stop_proximity_share_one_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    # The same ticker can have different stop distances across purchase dates.
    closes = pd.Series([70.0] * 20, index=pd.bdate_range(end="2026-09-07", periods=20))
    with _dependencies([HOLDING, OTHER_ENTRY], bars=NEAR_BARS, quote=NEAR_QUOTE) as deps:
        deps["fetch_history"].return_value = SplitAdjustedHistory(100.0, pd.Series(dtype=float), closes)
        run(dry_run=False, evaluated_at=NOW)
    (text,) = _warning_posts(deps)
    assert text.count("1111.T") == 1 and "残り" in text and "過熱: 20日で" in text
    assert [row["last_warned_at"] for row in _written(deps)] == [NOW.isoformat()] * 2


def test_exactly_fifty_percent_is_an_overheating_candidate() -> None:
    from scripts.run_position_monitor import _warning_candidates

    row = {"ticker": "1111.T", "triggered": False, "distance_to_stop_pct": 10.0, "return_20d_pct": 50.0}
    assert len(_warning_candidates([row], {})) == 1
    assert _warning_candidates([{**row, "return_20d_pct": 49.999}], {}) == []
    assert _warning_candidates([row], {"1111.T": NOW}) == []
    assert _warning_candidates([{**row, "triggered": True}], {}) == []


def _close_bars(day: str, *, touched: bool) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"Open": [100.0, 100.0, 100.0], "High": [100.0, 100.0, 100.0],
         "Low": [100.0, 85.0 if touched else 100.0, 100.0], "Close": [100.0, 100.0, 100.0],
         "Volume": [10.0, 10.0, 10.0]},
        index=pd.DatetimeIndex([f"{day} 09:00", f"{day} 15:25", f"{day} 15:30"], tz=JST),
    )
    frame.attrs = {"requested_date": day, "daily_bar": {
        "Open": 100.0, "High": 100.0, "Low": 85.0 if touched else 100.0,
        "Close": 100.0, "Volume": 30.0,
    }}
    return frame


def test_unpublished_close_remains_pending_with_an_evaluation_checkpoint() -> None:
    at = datetime(2026, 9, 8, 15, 35, tzinfo=JST)
    bars = _close_bars("2026-09-08", touched=False).iloc[:1].copy()
    bars.index = pd.DatetimeIndex(["2026-09-08 15:20"], tz=JST)
    bars.attrs["daily_bar"]["Volume"] = 10.0
    quote = TodayQuote(100.0, 100.0, 100.0, 100.0, bars.index[-1].isoformat())
    with _dependencies([HOLDING], bars=bars, quote=quote) as deps:
        try:
            run(dry_run=True, evaluated_at=at)
        except RuntimeError:
            pass
    row = _written(deps)[0]
    assert row["status"] == "incomplete"
    assert row["as_of_at"] == quote.as_of_at
    assert "session end" in row["error"]


@pytest.mark.parametrize("final_failed", [False, True])
@pytest.mark.parametrize("checkpoint_time", ["15:20", "15:30"])
def test_next_day_recovers_1525_touch_and_does_not_repeat_the_notification(
    monkeypatch: pytest.MonkeyPatch, final_failed: bool, checkpoint_time: str
) -> None:
    from src.data.live_quote import build_today_quote

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    yesterday = "2026-09-08"
    today = datetime(2026, 9, 9, 9, 20, tzinfo=JST)
    historical = _close_bars(yesterday, touched=True)
    current_bars = _close_bars("2026-09-09", touched=False).iloc[:1]
    history = SplitAdjustedHistory(
        100.0, pd.Series([100.0], index=pd.DatetimeIndex([yesterday], tz=JST)),
        pd.Series([100.0], index=pd.DatetimeIndex([yesterday], tz=JST)),
    )
    previous = [{**HOLDING, "triggered": False, "as_of_at": f"{yesterday}T{checkpoint_time}:00+09:00",
                 "status": "stale" if final_failed else "ok"}]
    with (
        _dependencies([HOLDING], previous=previous, bars=current_bars) as deps,
        patch("scripts.run_position_monitor.fetch_session_bars", return_value=historical, create=True) as recovery,
    ):
        deps["fetch_history"].return_value = history
        deps["build_quote"].side_effect = build_today_quote
        assert run(dry_run=False, evaluated_at=today) == 0
        saved = _written(deps)
    assert saved[0]["triggered"] is True
    assert saved[0]["exit_reason"] == "recovered_trailing_stop"
    assert saved[0]["triggered_at"] == "2026-09-08T15:25:00+09:00"
    recovery.assert_called_once_with("1111.T", yesterday)
    texts = [call.kwargs["json"]["text"] for call in deps["post"].call_args_list]
    assert len(texts) == 1 and "過去の未評価区間" in texts[0]
    with (
        _dependencies([HOLDING], previous=saved, bars=current_bars) as retry,
        patch("scripts.run_position_monitor.fetch_session_bars", return_value=historical, create=True),
    ):
        retry["fetch_history"].return_value = history
        retry["build_quote"].side_effect = build_today_quote
        assert run(dry_run=False, evaluated_at=today) == 0
    assert _written(retry)[0]["triggered"] is True
    retry["post"].assert_not_called()


def test_failed_final_monitor_keeps_the_last_evaluated_timestamp() -> None:
    previous = [{**HOLDING, "triggered": False, "as_of_at": "2026-09-08T12:35:00+09:00"}]
    with _dependencies([HOLDING], previous=previous, bars=None) as deps, pytest.raises(RuntimeError, match="no holdings"):
        run(dry_run=True, evaluated_at=NOW)
    assert _written(deps)[0]["as_of_at"] == previous[0]["as_of_at"]


def test_recovery_does_not_advance_past_a_missing_historical_session() -> None:
    today = datetime(2026, 9, 9, 9, 20, tzinfo=JST)
    previous = [{**HOLDING, "triggered": False, "as_of_at": "2026-09-08T15:20:00+09:00"}]
    index = pd.DatetimeIndex(["2026-09-08"], tz=JST)
    with (
        _dependencies([HOLDING], previous=previous) as deps,
        patch("scripts.run_position_monitor.fetch_session_bars", return_value=None, create=True),
        pytest.raises(RuntimeError, match="no holdings"),
    ):
        deps["fetch_history"].return_value = SplitAdjustedHistory(
            100.0, pd.Series([100.0], index=index), pd.Series([100.0], index=index)
        )
        run(dry_run=True, evaluated_at=today)
    row = _written(deps)[0]
    assert row["status"] == "incomplete"
    assert row["as_of_at"] == previous[0]["as_of_at"]


def test_incomplete_current_path_keeps_the_checkpoint_for_next_run() -> None:
    previous = [{**HOLDING, "triggered": False, "as_of_at": "2026-09-08T09:00:00+09:00"}]
    bars = _close_bars("2026-09-08", touched=True).iloc[[0, 2]].copy()
    at = datetime(2026, 9, 8, 15, 45, tzinfo=JST)
    quote = TodayQuote(100.0, 100.0, 100.0, 100.0, bars.index[-1].isoformat())
    with (_dependencies([HOLDING], previous=previous, bars=bars, quote=quote) as deps,
          pytest.raises(RuntimeError, match="no holdings")):
        run(dry_run=True, evaluated_at=at)
    row = _written(deps)[0]
    assert row["status"] == "incomplete"
    assert row["as_of_at"] == previous[0]["as_of_at"]
    assert row["last_notified_at"] == ""


def test_missed_whole_day_is_replayed_when_the_final_monitor_never_started(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.data.live_quote import build_today_quote

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    today = datetime(2026, 9, 9, 9, 20, tzinfo=JST)
    index = pd.DatetimeIndex(["2026-09-08"], tz=JST)
    historical = _close_bars("2026-09-08", touched=True)
    with (
        _dependencies([HOLDING], previous=[{**HOLDING, "triggered": False}]) as deps,
        patch("scripts.run_position_monitor.fetch_session_bars", return_value=historical) as fetch,
    ):
        deps["fetch_history"].return_value = SplitAdjustedHistory(
            100.0, pd.Series([100.0], index=index), pd.Series([100.0], index=index)
        )
        deps["build_quote"].side_effect = build_today_quote
        assert run(dry_run=False, evaluated_at=today) == 0
    fetch.assert_called_once_with("1111.T", "2026-09-08")
    assert _written(deps)[0]["exit_reason"] == "recovered_trailing_stop"


@pytest.mark.parametrize("branch", ["refs/heads/feature", "refs/tags/release", ""])
def test_nonproduction_branch_cannot_read_notify_or_write_shared_state(
    monkeypatch: pytest.MonkeyPatch, branch: str
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", branch)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING]) as deps, pytest.raises(RuntimeError, match="production writer"):
        run(dry_run=False, evaluated_at=NOW)
    deps["read_status"].assert_not_called()
    deps["post"].assert_not_called()
    deps["write"].assert_not_called()


@pytest.mark.parametrize("dry_run", [False, True])
def test_local_execution_cannot_bypass_the_production_state_lock(
    monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING]) as deps, pytest.raises(RuntimeError, match="production writer"):
        run(dry_run=dry_run, evaluated_at=NOW)
    deps["read_status"].assert_not_called()
    deps["post"].assert_not_called()
    deps["write"].assert_not_called()


def test_notified_stop_cannot_roll_back_when_the_current_price_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], previous=[TRIGGERED_STATUS], bars=FAR_BARS, quote=FAR_QUOTE) as deps:
        assert run(dry_run=False, evaluated_at=NOW) == 0
    row = _written(deps)[0]
    assert row["triggered"] is True
    assert row["triggered_at"] == TRIGGERED_STATUS["triggered_at"]
    assert row["last_notified_at"] == TRIGGERED_STATUS["last_notified_at"]
    deps["post"].assert_not_called()


@pytest.mark.parametrize("provider", ["read_status", "read_holdings", "fetch_split_adjusted_history",
                                     "fetch_today_bars", "write_status", "requests.post"])
def test_monitor_public_boundary_does_not_leak_a_fake_providers_holdings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, caplog: pytest.LogCaptureFixture, provider: str
) -> None:
    from scripts.run_position_monitor import main

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/private-webhook")
    hidden = "9999.T entry_date=2026-08-04 holdings=[secret] private-token"
    reached = []
    def fail(*args, **kwargs):
        reached.append(provider)
        print(hidden)
        logging.getLogger("fake.sheets.provider").exception(hidden)
        raise RuntimeError(hidden)
    public_traceback = ""
    with (
        _dependencies([HOLDING]),
        patch("scripts.run_position_monitor.run", side_effect=lambda **kwargs: run(evaluated_at=NOW, **kwargs)),
        patch(f"scripts.run_position_monitor.{provider}", side_effect=fail),
    ):
        try:
            result = main([])
        except Exception as error:  # noqa: BLE001 - include the old public traceback in the red-phase leak assertion
            result = 1
            public_traceback = "".join(traceback.format_exception(error))
    assert result == 1
    assert reached
    captured = capsys.readouterr()
    public = captured.out + captured.err + caplog.text + public_traceback
    for value in ("9999.T", "2026-08-04", "holdings=[secret]", "private-token", "private-webhook"):
        assert value not in public
    assert "RuntimeError" in public


def test_duplicate_position_failure_contains_row_numbers_without_the_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    holding = {**HOLDING, "ticker": "9999.T", "entry_date": "2026-08-04"}
    with _dependencies([holding, holding]), pytest.raises(ValueError) as error:
        run(dry_run=False, evaluated_at=NOW)
    message = str(error.value)
    assert "9999.T" not in message and "2026-08-04" not in message
    assert "rows 2 and 3" in message


# --- sessions older than the provider's 1-minute retention are judged on the daily bar (ISSUE-04) ----------------


def _old_history(
    sessions: list[str], today: str, *, low_by_session: dict[str, float] | None = None, with_daily: bool = True,
) -> SplitAdjustedHistory:
    """Flat 100/100/100/100 days (volume 30) unless a session's low is lowered; today's bar is flat too."""
    low_by_session = low_by_session or {}
    index = pd.DatetimeIndex([*sessions, today], tz=JST)
    daily = pd.DataFrame(
        {"Open": 100.0, "High": 100.0, "Low": [low_by_session.get(s, 100.0) for s in [*sessions, today]],
         "Close": 100.0, "Volume": 30.0},
        index=index,
    )
    prior = daily.iloc[:-1]
    return SplitAdjustedHistory(
        100.0, prior["High"], prior["Close"], daily if with_daily else pd.DataFrame(),
    )


def _flat_today(at: datetime) -> tuple[pd.DataFrame, TodayQuote]:
    day = at.date().isoformat()
    frame = _close_bars(day, touched=False)
    frame.index = pd.DatetimeIndex([f"{day} 09:00", f"{day} 11:00", f"{day} 12:30"], tz=JST)  # inside TSE hours
    return frame, TodayQuote(100.0, 100.0, 100.0, 100.0, frame.index[-1].isoformat())


def _run_old_sessions(
    sessions: list[str], at: datetime, *, previous: list[dict[str, Any]] | None = None,
    low_by_session: dict[str, float] | None = None, with_daily: bool = True,
) -> tuple[dict[str, Mock], Mock, list[dict[str, Any]] | None]:
    """Run once with 1-minute bars unavailable for every pending session; return deps, the recovery mock, rows."""
    from src.data.live_quote import build_today_quote

    today = at.date().isoformat()
    history = _old_history(sessions, today, low_by_session=low_by_session, with_daily=with_daily)
    bars, quote = _flat_today(at)
    holding = {**HOLDING, "entry_date": "2026-06-01"}
    with (
        patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://example.test/hook"}),
        _dependencies([holding], previous=previous, bars=bars, quote=quote) as deps,
        patch("scripts.run_position_monitor.fetch_session_bars", return_value=None) as recovery,
    ):
        deps["fetch_history"].return_value = history
        deps["build_quote"].side_effect = build_today_quote
        try:
            run(dry_run=False, evaluated_at=at)
        except RuntimeError:
            pass
        rows = list(deps["write"].call_args.args[0]) if deps["write"].called else None
    return deps, recovery, rows


OLD_SESSIONS = ["2026-06-02", "2026-07-15", "2026-08-03"]  # all more than 30 days before NOW (2026-09-08)


def test_old_sessions_without_one_minute_bars_no_longer_block_the_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    deps, recovery, rows = _run_old_sessions(OLD_SESSIONS, NOW)

    assert rows is not None and rows[0]["status"] == "ok" and rows[0]["triggered"] is False
    assert rows[0]["as_of_at"]  # the checkpoint advanced to the current quote
    deps["post"].assert_not_called()
    assert recovery.call_count == len(OLD_SESSIONS)

    # The second run starts from the checkpoint: the old sessions are not replayed again.
    _, second_recovery, second_rows = _run_old_sessions(OLD_SESSIONS, NOW, previous=rows)
    assert second_rows is not None and second_rows[0]["status"] == "ok"
    second_recovery.assert_not_called()


def test_an_old_session_whose_daily_low_could_have_touched_the_stop_is_reported_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    deps, _, rows = _run_old_sessions(OLD_SESSIONS, NOW, low_by_session={"2026-07-15": 85.0})  # stop is 90

    assert rows is not None
    assert (rows[0]["status"], rows[0]["triggered"]) == ("recovered", True)
    assert rows[0]["exit_reason"] == "recovered_daily_possible_touch"
    assert rows[0]["triggered_at"].startswith("2026-07-15")
    assert rows[0]["quote_source"] == "daily_bar_conservative"
    texts = [call.kwargs["json"]["text"] for call in deps["post"].call_args_list]
    assert len(texts) == 1 and "recovered_daily_possible_touch" in texts[0]

    again, _, _ = _run_old_sessions(OLD_SESSIONS, NOW, previous=rows, low_by_session={"2026-07-15": 85.0})
    again["post"].assert_not_called()  # the notified, latched recovery is not announced again


@pytest.mark.parametrize(("evaluated_day", "age", "judged_on_daily"), [("2026-09-09", 30, False), ("2026-09-10", 31, True)])
def test_the_retention_boundary_is_thirty_days(evaluated_day: str, age: int, judged_on_daily: bool) -> None:
    at = datetime.fromisoformat(f"{evaluated_day}T12:35:00+09:00")
    _, _, rows = _run_old_sessions(["2026-08-10"], at)  # 30 / 31 days before the evaluation

    assert (at.date() - datetime.fromisoformat("2026-08-10").date()).days == age
    assert rows is not None
    assert (rows[0]["status"] == "ok") is judged_on_daily
    if not judged_on_daily:  # within the retention a missing minute path stays incomplete (C02)
        assert rows[0]["status"] == "incomplete"


def test_an_old_session_without_any_daily_bar_stays_incomplete() -> None:
    _, _, rows = _run_old_sessions(OLD_SESSIONS, NOW, with_daily=False)

    assert rows is not None and rows[0]["status"] == "incomplete"


def test_the_daily_test_never_misses_a_touch_the_minute_path_would_report() -> None:
    import random

    from scripts.run_position_monitor import _daily_could_touch

    rng = random.Random(20261014)
    possible = impossible = 0
    for _ in range(400):
        stop_pct = rng.choice([5.0, 10.0, 15.0, 20.0])
        prior_high_water = 100.0 + rng.uniform(0.0, 30.0)
        price, minutes = prior_high_water * rng.uniform(0.85, 1.0), []
        for _ in range(rng.randint(2, 40)):
            opened = price * (1.0 + rng.uniform(-0.01, 0.01))
            closed = opened * (1.0 + rng.uniform(-0.02, 0.02))
            high = max(opened, closed) * (1.0 + rng.uniform(0.0, 0.015))
            low = min(opened, closed) * (1.0 - rng.uniform(0.0, 0.015))
            minutes.append((opened, high, low, closed))
            price = closed
        high_water, touched = prior_high_water, False
        for opened, high, low, _ in minutes:  # the monitor's rule, minute by minute
            stop = high_water * (1.0 - stop_pct / 100.0)
            if opened <= stop or low <= stop:
                touched = True
                break
            high_water = max(high_water, high)
        daily = {"High": max(m[1] for m in minutes), "Low": min(m[2] for m in minutes)}
        could = _daily_could_touch(prior_high_water, daily, stop_pct)
        assert could or not touched  # a real touch always implies the daily test is true
        possible += could
        impossible += not could
    assert possible > 0 and impossible > 0  # the check is not trivially always true or always false


# --- the failure category reaches the status row, safely (ISSUE-09) -----------------------------------------------


class _Status:
    def __init__(self, code: int) -> None:
        self.status_code = code


def _http_error(code: int) -> requests.HTTPError:
    return requests.HTTPError("boom", response=_Status(code))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (requests.Timeout("t"), "timeout"),
        (_http_error(429), "rate_limit"),
        (_http_error(401), "auth"),
        (_http_error(500), "server_error"),
    ],
    ids=["timeout", "http_429", "http_401", "http_500"],
)
def test_the_provider_failure_category_is_in_the_status_row_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, category: str
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    ticker = Mock()
    ticker.history.side_effect = failure
    with _dependencies([HOLDING]) as deps, patch("src.data.live_quote.yf.Ticker", return_value=ticker):
        deps["fetch_bars"].side_effect = live_fetch_today_bars  # the real fetcher, on a failing provider
        with pytest.raises(RuntimeError):
            run(dry_run=False, evaluated_at=NOW)
    row = _written(deps)[0]

    assert row["status"] == "stale"
    assert row["error"] == f"current quote is missing or invalid ({category})"
    assert "1111.T" not in row["error"] and "boom" not in row["error"]


def test_one_ticker_failure_category_is_shared_by_all_its_positions_and_not_by_other_tickers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    holdings = [HOLDING, {**HOLDING, "entry_date": "2026-09-04"}, {**HOLDING, "ticker": "2222.T"}]

    def provider(symbol: str) -> Mock:
        ticker = Mock()
        ticker.history.side_effect = requests.Timeout("t") if symbol == "1111.T" else _http_error(429)
        return ticker

    with _dependencies(holdings) as deps, patch("src.data.live_quote.yf.Ticker", side_effect=provider):
        deps["fetch_bars"].side_effect = live_fetch_today_bars
        with pytest.raises(RuntimeError):
            run(dry_run=False, evaluated_at=NOW)

    assert [row["error"] for row in _written(deps)] == [
        "current quote is missing or invalid (timeout)",
        "current quote is missing or invalid (timeout)",
        "current quote is missing or invalid (rate_limit)",
    ]


def test_a_pending_session_failure_names_its_category_in_the_incomplete_row() -> None:
    today = datetime(2026, 9, 9, 9, 20, tzinfo=JST)
    previous = [{**HOLDING, "triggered": False, "as_of_at": "2026-09-08T15:20:00+09:00"}]
    index = pd.DatetimeIndex(["2026-09-08"], tz=JST)
    ticker = Mock()
    ticker.history.side_effect = requests.Timeout("t")
    with (
        _dependencies([HOLDING], previous=previous) as deps,
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("scripts.run_position_monitor.fetch_session_bars", live_fetch_session_bars),
        pytest.raises(RuntimeError, match="no holdings"),
    ):
        deps["fetch_history"].return_value = SplitAdjustedHistory(
            100.0, pd.Series([100.0], index=index), pd.Series([100.0], index=index)
        )
        run(dry_run=True, evaluated_at=today)
    row = _written(deps)[0]

    assert row["status"] == "incomplete"
    assert row["error"] == "pending historical session data is unavailable (timeout)"
