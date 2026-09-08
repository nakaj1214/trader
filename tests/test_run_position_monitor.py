from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import requests

from scripts.run_position_monitor import run
from src.data.live_quote import SplitAdjustedHistory, TodayQuote

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 8, 12, 35, tzinfo=JST)
HOLDING = {"ticker": "1111.T", "entry_date": "2026-09-07", "entry_price": 100.0, "trailing_stop_pct": 10.0}
HISTORY = SplitAdjustedHistory(
    100.0,
    pd.Series([120.0], index=pd.to_datetime(["2026-09-07"])),
    pd.Series([115.0], index=pd.to_datetime(["2026-09-07"])),
)
QUOTE = TodayQuote(110.0, 112.0, 107.0, 109.0, (NOW - timedelta(minutes=1)).isoformat())


@contextmanager
def _dependencies(holdings: list[dict], quote: TodayQuote | None = QUOTE, *, is_session: bool = True):
    calendar = Mock()
    calendar.is_session.return_value = is_session
    response = Mock()
    with patch("scripts.run_position_monitor.read_holdings", return_value=holdings), patch(
        "scripts.run_position_monitor.write_status"
    ) as write, patch(
        "scripts.run_position_monitor.fetch_split_adjusted_history", return_value=HISTORY
    ) as fetch_history, patch(
        "scripts.run_position_monitor.fetch_today_quote", return_value=quote
    ) as fetch_quote, patch(
        "scripts.run_position_monitor.xcals.get_calendar", return_value=calendar
    ), patch(
        "scripts.run_position_monitor.requests.post", return_value=response
    ) as post:
        yield write, fetch_history, fetch_quote, post, response


def test_empty_holdings_exit_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([]) as (write, fetch_history, fetch_quote, post, _):
        assert run(dry_run=False, evaluated_at=NOW) == 0

    write.assert_called_once_with([])
    fetch_history.assert_not_called()
    fetch_quote.assert_not_called()
    post.assert_not_called()


def test_non_session_skips_price_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], is_session=False) as (_, fetch_history, fetch_quote, post, _):
        assert run(dry_run=False, evaluated_at=NOW) == 0

    fetch_history.assert_not_called()
    fetch_quote.assert_not_called()
    post.assert_not_called()


def test_dry_run_writes_triggered_status_without_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with _dependencies([HOLDING]) as (write, _, _, post, _):
        assert run(dry_run=True, evaluated_at=NOW) == 0

    row = write.call_args.args[0][0]
    assert row["status"] == "ok"
    assert row["triggered"] is True
    post.assert_not_called()


def test_trigger_and_partial_error_send_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([{"ticker": ""}, HOLDING]) as (write, _, _, post, response):
        assert run(dry_run=False, evaluated_at=NOW) == 0

    rows = write.call_args.args[0]
    assert [row["status"] for row in rows] == ["error", "ok"]
    assert post.call_count == 2
    assert "検証用アラート" in post.call_args_list[0].kwargs["json"]["text"]
    assert "一部銘柄" in post.call_args_list[1].kwargs["json"]["text"]
    response.raise_for_status.assert_called()


def test_all_stale_rows_fail_after_status_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING], quote=None) as (write, _, _, post, _), pytest.raises(
        RuntimeError, match="no holdings"
    ):
        run(dry_run=False, evaluated_at=NOW)

    assert write.call_args.args[0][0]["status"] == "stale"
    post.assert_not_called()


def test_webhook_is_required_outside_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        run(dry_run=False, evaluated_at=NOW)


def test_status_write_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING]) as (write, _, _, _, _):
        write.side_effect = RuntimeError("sheet unavailable")
        with pytest.raises(RuntimeError, match="sheet unavailable"):
            run(dry_run=False, evaluated_at=NOW)


def test_slack_http_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/hook")
    with _dependencies([HOLDING]) as (_, _, _, _, response):
        response.raise_for_status.side_effect = requests.HTTPError("bad webhook")
        with pytest.raises(requests.HTTPError, match="bad webhook"):
            run(dry_run=False, evaluated_at=NOW)
