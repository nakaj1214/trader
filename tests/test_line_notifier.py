"""line_notifier のテスト: メッセージ生成、送信成功/失敗、notify 統合。"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# --- build_line_message ---

def test_build_line_message_contains_check_prompt():
    """LINE メッセージに Slack チェックを促す文言が含まれることを検証する。"""
    from src.line_notifier import build_line_message

    report = (
        "*週間AI株式予測レポート (2026-02-22)*\n"
        "\n"
        "*【今週の上昇予測銘柄】*\n"
        "  1. *AAPL*: $250.00 → $265.00 (予測 +6.0%, 信頼区間 ±3.2%)\n"
        "  2. *MSFT*: $420.00 → $438.00 (予測 +4.3%, 信頼区間 ±2.8%)\n"
    )
    result = build_line_message(report)

    assert "Slack" in result
    assert "#stock-alerts" in result
    assert "確認" in result


def test_build_line_message_includes_stock_count():
    """LINE メッセージに銘柄数が含まれることを検証する。"""
    from src.line_notifier import build_line_message

    report = (
        "*週間AI株式予測レポート (2026-02-22)*\n"
        "\n"
        "*【今週の上昇予測銘柄】*\n"
        "  1. *AAPL*: $250.00 → $265.00 (予測 +6.0%, 信頼区間 ±3.2%)\n"
        "  2. *MSFT*: $420.00 → $438.00 (予測 +4.3%, 信頼区間 ±2.8%)\n"
        "  3. *GOOGL*: $175.00 → $182.00 (予測 +4.0%, 信頼区間 ±2.5%)\n"
    )
    result = build_line_message(report)

    assert "3銘柄" in result


def test_build_line_message_single_stock():
    """1銘柄の場合も正しくカウントされることを検証する。"""
    from src.line_notifier import build_line_message

    report = (
        "*週間AI株式予測レポート (2026-02-22)*\n"
        "\n"
        "*【今週の上昇予測銘柄】*\n"
        "  1. *AAPL*: $250.00 → $265.00 (予測 +6.0%, 信頼区間 ±3.2%)\n"
    )
    result = build_line_message(report)

    assert "1銘柄" in result


def test_build_line_message_no_stocks():
    """予測銘柄がないレポートでも正常にメッセージが生成されることを検証する。"""
    from src.line_notifier import build_line_message

    report = (
        "*週間AI株式予測レポート (2026-02-22)*\n"
        "\n"
        "今週は上昇予測の銘柄がありませんでした。\n"
    )
    result = build_line_message(report)

    assert "Slack" in result
    # 銘柄数の記載がないこと
    assert "上昇予測:" not in result


def test_build_line_message_strips_slack_markdown():
    """LINE メッセージに Slack のマークダウン記号が含まれないことを検証する。"""
    from src.line_notifier import build_line_message

    report = "*週間AI株式予測レポート (2026-02-22)*\n"
    result = build_line_message(report)

    # タイトル行の内容が含まれ、*が除去されていること
    assert "週間AI株式予測レポート" in result
    assert "*" not in result


def test_build_line_message_uses_custom_channel():
    """slack_channel 引数で LINE 文面のチャンネル名が変わることを検証する。"""
    from src.line_notifier import build_line_message

    report = "*週間AI株式予測レポート (2026-02-22)*\n"
    result = build_line_message(report, slack_channel="#my-channel")

    assert "#my-channel" in result
    assert "#stock-alerts" not in result


# --- send_to_line ---

@patch("src.line_notifier.requests.post")
def test_send_to_line_success(mock_post):
    """LINE API 200 応答で NotificationResult.success=True が返ることを検証する。"""
    from src.line_notifier import send_to_line

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    with patch.dict("os.environ", {
        "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
        "LINE_USER_ID": "test-user-id",
    }):
        result = send_to_line("テストレポート")

    assert result.success is True
    assert result.channel == "line"
    assert result.status_code == 200
    mock_post.assert_called_once()

    # Authorization ヘッダーに Bearer トークンが設定されていること
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-token"

    # 送信先ユーザIDが正しいこと
    assert call_kwargs.kwargs["json"]["to"] == "test-user-id"


@patch("src.line_notifier.requests.post")
def test_send_to_line_failure(mock_post):
    """LINE API エラー応答で NotificationResult.success=False が返ることを検証する。"""
    from src.line_notifier import send_to_line

    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"
    mock_post.return_value = mock_resp

    with patch.dict("os.environ", {
        "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
        "LINE_USER_ID": "test-user-id",
    }):
        result = send_to_line("テストレポート")

    assert result.success is False
    assert result.status_code == 400
    assert result.error_message == "Bad Request"


@patch("src.line_notifier.requests.post")
def test_send_to_line_network_error(mock_post):
    """ネットワークエラー時に NotificationResult.success=False が返ることを検証する。"""
    import requests as req
    from src.line_notifier import send_to_line

    mock_post.side_effect = req.ConnectionError("connection refused")

    with patch.dict("os.environ", {
        "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
        "LINE_USER_ID": "test-user-id",
    }):
        result = send_to_line("テストレポート")

    assert result.success is False
    assert result.status_code is None
    assert "connection refused" in result.error_message


# --- notify 統合 ---

@patch("src.notifier.send_to_slack")
@patch("src.line_notifier.send_to_line")
def test_notify_calls_line_when_enabled(mock_line, mock_slack):
    """LINE が有効の場合、Slack 通知後に LINE 通知が呼ばれることを検証する。"""
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
        "notifications": {
            "slack": {"enabled": True},
            "line": {"enabled": True},
        },
    }
    df = pd.DataFrame()

    result = notify(df, config=config)

    assert result is True
    mock_slack.assert_called_once()
    mock_line.assert_called_once()


@patch("src.notifier.send_to_slack")
@patch("src.line_notifier.send_to_line")
def test_notify_skips_line_when_disabled(mock_line, mock_slack):
    """LINE が無効の場合、LINE 通知が呼ばれないことを検証する。"""
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
    mock_line.assert_not_called()


@patch("src.notifier.send_to_slack")
def test_notify_skips_line_when_no_config(mock_slack):
    """LINE 設定がない場合、LINE 通知がスキップされることを検証する。"""
    from src.notifier import NotificationResult, notify

    mock_slack.return_value = NotificationResult(
        channel="slack", success=True, status_code=200
    )

    config = {
        "display": {"beginner_mode": False},
        "google_sheets": {"spreadsheet_name": "Test"},
    }
    df = pd.DataFrame()

    result = notify(df, config=config)

    assert result is True


@patch("src.notifier.send_to_slack")
@patch("src.line_notifier.send_to_line")
def test_notify_returns_true_even_if_line_fails(mock_line, mock_slack):
    """LINE 通知が失敗しても Slack 成功なら True が返ることを検証する。"""
    from src.notifier import NotificationResult, notify

    mock_slack.return_value = NotificationResult(
        channel="slack", success=True, status_code=200
    )
    mock_line.return_value = NotificationResult(
        channel="line", success=False, status_code=400, error_message="Bad Request"
    )

    config = {
        "display": {"beginner_mode": False},
        "google_sheets": {"spreadsheet_name": "Test"},
        "notifications": {
            "slack": {"enabled": True},
            "line": {"enabled": True},
        },
    }
    df = pd.DataFrame()

    result = notify(df, config=config)

    assert result is True
    mock_slack.assert_called_once()
    mock_line.assert_called_once()
