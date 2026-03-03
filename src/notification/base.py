"""Notifier ABC: common interface for notification channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class NotificationResult:
    """Structured notification result."""

    channel: str
    success: bool
    status_code: int | None = None
    error_message: str | None = None


class Notifier(ABC):
    """Abstract base class for notification channels."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name (e.g. 'slack', 'line')."""

    @abstractmethod
    def send(self, text: str, **kwargs: Any) -> NotificationResult:
        """Send a notification message.

        Args:
            text: Message text to send.
            **kwargs: Channel-specific options.

        Returns:
            NotificationResult with success status.
        """

    def is_enabled(self, config: dict[str, Any]) -> bool:
        """Check if this notifier is enabled in config.

        Args:
            config: Application config dict.

        Returns:
            True if this channel is enabled.
        """
        notif_cfg = config.get("notification", {})
        return notif_cfg.get(self.name, {}).get("enabled", False)
