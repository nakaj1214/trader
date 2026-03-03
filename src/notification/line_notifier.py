"""LINE notifier: push notification via LINE Messaging API.

Migrated from src/line_notifier.py.
Sends a short check-prompt message after Slack report is posted.
"""

from __future__ import annotations

import os
from typing import Any

import requests
import structlog

from src.notification.base import NotificationResult, Notifier

logger = structlog.get_logger(__name__)

LINE_API_URL = "https://api.line.me/v2/bot/message/push"


class LineNotifier(Notifier):
    """LINE push notification channel."""

    @property
    def name(self) -> str:
        return "line"

    def send(self, text: str, **kwargs: Any) -> NotificationResult:
        """Send LINE push message.

        Args:
            text: Message text to send.
            **kwargs: Optional 'slack_channel' for message formatting.

        Returns:
            NotificationResult with send status.
        """
        token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
        user_id = os.environ.get("LINE_USER_ID", "")

        if not token or not user_id:
            return NotificationResult(
                channel="line",
                success=False,
                error_message="LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID not set",
            )

        slack_channel = kwargs.get("slack_channel", "#stock-alerts")
        message_text = build_line_message(text, slack_channel=slack_channel)

        try:
            resp = requests.post(
                LINE_API_URL,
                json={
                    "to": user_id,
                    "messages": [{"type": "text", "text": message_text}],
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                timeout=30,
            )
            success = resp.status_code == 200
            return NotificationResult(
                channel="line",
                success=success,
                status_code=resp.status_code,
                error_message=None if success else resp.text,
            )
        except requests.RequestException as e:
            return NotificationResult(
                channel="line",
                success=False,
                error_message=str(e),
            )

    def is_enabled(self, config: dict[str, Any]) -> bool:
        """Check if LINE notifications are enabled."""
        notif_cfg = config.get("notification", {})
        return notif_cfg.get("line", {}).get("enabled", False)


def build_line_message(
    report_text: str,
    slack_channel: str = "#stock-alerts",
) -> str:
    """Build a short LINE message summarizing the Slack report.

    Args:
        report_text: Full Slack report text.
        slack_channel: Slack channel name for reference.

    Returns:
        Short LINE notification text.
    """
    first_line = ""
    for line in report_text.splitlines():
        stripped = line.replace("*", "").replace("_", "").strip()
        if stripped:
            first_line = stripped
            break

    stock_count = sum(
        1
        for line in report_text.splitlines()
        if line.strip()[:1].isdigit() and ". *" in line and "*:" in line
    )

    parts = ["Slack に株式予測レポートが届きました！"]
    if first_line:
        parts.append(f"\n{first_line}")
    if stock_count > 0:
        parts.append(f"\nBullish predictions: {stock_count} stocks")
    parts.append(f"\nCheck Slack {slack_channel}")
    return "".join(parts)
