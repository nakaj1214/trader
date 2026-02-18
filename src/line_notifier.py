"""LINE Messaging API によるプッシュ通知

Slack 通知後にユーザへチェックを促す短いメッセージを LINE で送信する。
"""

import logging

import requests

from src.notifier import NotificationResult
from src.utils import get_env

logger = logging.getLogger(__name__)

LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def build_line_message(
    report_text: str, slack_channel: str = "#stock-alerts"
) -> str:
    """Slack レポートの要約から LINE 用の通知メッセージを組み立てる。

    Slack に投稿されたレポート全文ではなく、チェックを促す短いメッセージを返す。

    Args:
        report_text: build_report() で生成された Slack 用テキスト。
        slack_channel: Slack チャンネル名。LINE 文面に使用。

    Returns:
        LINE 送信用のプレーンテキスト。
    """
    # Slack マークダウン記法を除去して最初の行（タイトル）を取得
    first_line = ""
    for line in report_text.splitlines():
        stripped = line.replace("*", "").replace("_", "").strip()
        if stripped:
            first_line = stripped
            break

    # 銘柄数をカウント（レポートの "  1. *TICKER*:" パターンにマッチ）
    stock_count = sum(
        1
        for line in report_text.splitlines()
        if line.strip()[:1].isdigit() and ". *" in line and "*:" in line
    )

    parts = ["\U0001f4ca Slack に株式予測レポートが届きました！"]
    if first_line:
        parts.append(f"\n{first_line}")
    if stock_count > 0:
        parts.append(f"\n今週の上昇予測: {stock_count}銘柄")
    parts.append(f"\nSlack の {slack_channel} を確認してください。")
    return "".join(parts)


def _log_result(result: NotificationResult) -> None:
    """LINE 通知結果をログ出力する。"""
    if result.success:
        logger.info(
            "notification_sent channel=%s status_code=%s",
            result.channel,
            result.status_code,
        )
    else:
        logger.error(
            "notification_failed channel=%s status_code=%s error=%s",
            result.channel,
            result.status_code,
            result.error_message,
        )


def send_to_line(
    report_text: str, slack_channel: str = "#stock-alerts"
) -> NotificationResult:
    """LINE Push Message API でチェック促進メッセージを送信する。

    Args:
        report_text: Slack 用レポートテキスト（LINE 用メッセージに変換される）。
        slack_channel: Slack チャンネル名。LINE 文面に使用。

    Returns:
        NotificationResult: 送信結果。
    """
    token = get_env("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = get_env("LINE_USER_ID")

    message_text = build_line_message(report_text, slack_channel=slack_channel)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message_text}],
    }

    try:
        resp = requests.post(LINE_API_URL, json=payload, headers=headers, timeout=30)
        success = resp.status_code == 200
        result = NotificationResult(
            channel="line",
            success=success,
            status_code=resp.status_code,
            error_message=None if success else resp.text,
        )
    except requests.RequestException as e:
        result = NotificationResult(
            channel="line",
            success=False,
            status_code=None,
            error_message=str(e),
        )

    _log_result(result)
    return result
