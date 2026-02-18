"""LINE Messaging API によるプッシュ通知

Slack 通知後にユーザへチェックを促す短いメッセージを LINE で送信する。
"""

import logging

import requests

from src.utils import get_env

logger = logging.getLogger(__name__)

LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def build_line_message(report_text: str) -> str:
    """Slack レポートの要約から LINE 用の通知メッセージを組み立てる。

    Slack に投稿されたレポート全文ではなく、チェックを促す短いメッセージを返す。

    Args:
        report_text: build_report() で生成された Slack 用テキスト。

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

    # 銘柄数をカウント（"  1." "  2." のようなパターン）
    stock_count = sum(
        1
        for line in report_text.splitlines()
        if len(line.strip()) >= 2 and line.strip()[:2].rstrip(".").isdigit()
    )

    parts = ["📊 Slack に株式予測レポートが届きました！"]
    if first_line:
        parts.append(f"\n{first_line}")
    if stock_count > 0:
        parts.append(f"\n今週の上昇予測: {stock_count}銘柄")
    parts.append("\nSlack の #stock-alerts を確認してください。")
    return "".join(parts)


def send_to_line(report_text: str) -> bool:
    """LINE Push Message API でチェック促進メッセージを送信する。

    Args:
        report_text: Slack 用レポートテキスト（LINE 用メッセージに変換される）。

    Returns:
        成功時 True、失敗時 False。
    """
    token = get_env("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = get_env("LINE_USER_ID")

    message_text = build_line_message(report_text)

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
        if resp.status_code == 200:
            logger.info("LINE通知送信成功")
            return True
        else:
            logger.error(
                "LINE通知失敗: status=%d, body=%s", resp.status_code, resp.text
            )
            return False
    except requests.RequestException:
        logger.exception("LINE通知送信エラー")
        return False
