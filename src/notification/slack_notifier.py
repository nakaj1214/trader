"""Slack notifier: Incoming Webhook and Bot Token notifications.

Migrated from src/notifier.py with plugin architecture.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests
import structlog

from src.notification.base import NotificationResult, Notifier

logger = structlog.get_logger(__name__)


class SlackNotifier(Notifier):
    """Slack notification via Incoming Webhook."""

    @property
    def name(self) -> str:
        return "slack"

    def send(self, text: str, **kwargs: Any) -> NotificationResult:
        """Send message to Slack via Incoming Webhook.

        Args:
            text: Message text.
            **kwargs: Not used.

        Returns:
            NotificationResult with send status.
        """
        webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            return NotificationResult(
                channel="slack",
                success=False,
                error_message="SLACK_WEBHOOK_URL not set",
            )

        try:
            resp = requests.post(
                webhook_url,
                json={"text": text},
                timeout=30,
            )
            success = resp.status_code == 200 and resp.text == "ok"
            return NotificationResult(
                channel="slack",
                success=success,
                status_code=resp.status_code,
                error_message=None if success else resp.text,
            )
        except requests.RequestException as e:
            return NotificationResult(
                channel="slack",
                success=False,
                error_message=str(e),
            )

    def is_enabled(self, config: dict[str, Any]) -> bool:
        """Check if Slack notifications are enabled."""
        notif_cfg = config.get("notification", {})
        return notif_cfg.get("slack", {}).get("enabled", True)


def build_report(
    predictions_df: Any,
    accuracy: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Build Slack notification report text.

    Args:
        predictions_df: Prediction DataFrame.
        accuracy: Accuracy stats dict.
        config: Application config.

    Returns:
        Formatted Slack message text.
    """
    import pandas as pd

    if config is None:
        config = {}

    today = datetime.now().strftime("%Y-%m-%d")
    beginner_mode = config.get("notification", {}).get("beginner_mode", False)

    lines = [
        f"*Weekly AI Stock Prediction Report ({today})*",
        "",
    ]

    if isinstance(predictions_df, pd.DataFrame) and predictions_df.empty:
        lines.append("No bullish predictions this week.")
    elif isinstance(predictions_df, pd.DataFrame):
        lines.append("*Bullish Predictions:*")
        for i, row in predictions_df.iterrows():
            lines.append(
                f"  {i + 1}. *{row['ticker']}*: "
                f"${row['current_price']:.2f} -> ${row['predicted_price']:.2f} "
                f"(+{row['predicted_change_pct']:.1f}%)"
            )

    if accuracy:
        lines.append("")
        lines.append("*Last Week Accuracy:*")
        lines.append(
            f"  Hit: {accuracy['hits']}/{accuracy['total']} "
            f"({accuracy['hit_rate_pct']:.1f}%)"
        )
        if accuracy.get("cumulative_total", 0) > 0:
            lines.append(
                f"  Cumulative: {accuracy['cumulative_hit_rate_pct']:.1f}% "
                f"({accuracy['cumulative_weeks']} weeks)"
            )

    if beginner_mode:
        try:
            from src.core.glossary import generate_beginner_notes

            notes = generate_beginner_notes()
            if notes:
                lines.append("")
                lines.append(f"_{notes}_")
        except ImportError:
            pass

    return "\n".join(lines)
