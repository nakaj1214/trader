"""notifier のテスト: NotificationResult、設定解決、Slack送信、notify統合。"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# --- _resolve_notification_config ---


def test_resolve_config_new_format():
    """新形式 (notifications セクション) で設定が解決されることを検証する。"""
    from src.notifier import _resolve_notification_config

    config = {
        "notifications": {
            "slack": {"enabled": False},
            "line": {"enabled": True},
        },
    }
    result = _resolve_notification_config(config)

    assert result["slack"]["enabled"] is False
    assert result["line"]["enabled"] is True


def test_resolve_config_legacy_format():
    """旧形式 (line.enabled) にフォールバックすることを検証する。"""
    from src.notifier import _resolve_notification_config

    config = {
        "line": {"enabled": True},
    }
    result = _resolve_notification_config(config)

    # notifications キーなし → Slack はデフォルト True
    assert result["slack"]["enabled"] is True
    # line.enabled から読み取り
    assert result["line"]["enabled"] is True


def test_resolve_config_empty():
    """設定が空の場合にデフォルト値が返ることを検証する。"""
    from src.notifier import _resolve_notification_config

    result = _resolve_notification_config({})

    assert result["slack"]["enabled"] is True
    assert result["line"]["enabled"] is False


def test_resolve_config_new_overrides_legacy():
    """新形式が旧形式より優先されることを検証する。"""
    from src.notifier import _resolve_notification_config

    config = {
        "line": {"enabled": True},
        "notifications": {
            "line": {"enabled": False},
        },
    }
    result = _resolve_notification_config(config)

    assert result["line"]["enabled"] is False


# --- send_to_slack ---


@patch("src.notifier.requests.post")
def test_send_to_slack_success(mock_post):
    """Slack 200 応答で NotificationResult.success=True が返ることを検証する。"""
    from src.notifier import send_to_slack

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"
    mock_post.return_value = mock_resp

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        result = send_to_slack("テスト")

    assert result.success is True
    assert result.channel == "slack"
    assert result.status_code == 200
    assert result.error_message is None


@patch("src.notifier.requests.post")
def test_send_to_slack_failure(mock_post):
    """Slack エラー応答で NotificationResult.success=False が返ることを検証する。"""
    from src.notifier import send_to_slack

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "server_error"
    mock_post.return_value = mock_resp

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        result = send_to_slack("テスト")

    assert result.success is False
    assert result.status_code == 500
    assert result.error_message == "server_error"


@patch("src.notifier.requests.post")
def test_send_to_slack_exception(mock_post):
    """ネットワークエラー時に status_code=None が返ることを検証する。"""
    import requests as req
    from src.notifier import send_to_slack

    mock_post.side_effect = req.ConnectionError("connection refused")

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        result = send_to_slack("テスト")

    assert result.success is False
    assert result.status_code is None
    assert "connection refused" in result.error_message


# --- notify ---


@patch("src.notifier.send_to_slack")
def test_notify_skips_slack_when_disabled(mock_slack):
    """Slack 無効時に send_to_slack が呼ばれないことを検証する。"""
    from src.notifier import notify

    config = {
        "display": {"beginner_mode": False},
        "google_sheets": {"spreadsheet_name": "Test"},
        "notifications": {
            "slack": {"enabled": False},
            "line": {"enabled": False},
        },
    }
    df = pd.DataFrame()

    result = notify(df, config=config)

    assert result is True  # 無効時は「意図的スキップ＝成功」
    mock_slack.assert_not_called()


@patch("src.notifier.send_to_slack")
@patch("src.line_notifier.send_to_line")
def test_notify_passes_slack_channel_to_line(mock_line, mock_slack):
    """notify が config の slack.channel を LINE に渡すことを検証する。"""
    from src.notifier import NotificationResult, notify

    mock_slack.return_value = NotificationResult(
        channel="slack", success=True, status_code=200
    )
    mock_line.return_value = NotificationResult(
        channel="line", success=True, status_code=200
    )

    config = {
        "display": {"beginner_mode": False},
        "google_sheets": {"spreadsheet_name": "Test"},
        "slack": {"channel": "#my-custom-channel"},
        "notifications": {
            "slack": {"enabled": True},
            "line": {"enabled": True},
        },
    }
    df = pd.DataFrame()

    notify(df, config=config)

    mock_line.assert_called_once()
    call_kwargs = mock_line.call_args
    assert call_kwargs.kwargs.get("slack_channel") == "#my-custom-channel" or \
        (len(call_kwargs.args) > 1 and call_kwargs.args[1] == "#my-custom-channel")


@patch("src.notifier.send_to_slack")
def test_notify_calls_slack_when_enabled(mock_slack):
    """Slack 有効時に send_to_slack が呼ばれることを検証する。"""
    from src.notifier import NotificationResult, notify

    mock_slack.return_value = NotificationResult(
        channel="slack", success=True, status_code=200
    )

    config = {
        "display": {"beginner_mode": False},
        "google_sheets": {"spreadsheet_name": "Test"},
        "notifications": {
            "slack": {"enabled": True},
            "line": {"enabled": False},
        },
    }
    df = pd.DataFrame()

    result = notify(df, config=config)

    assert result is True
    mock_slack.assert_called_once()
