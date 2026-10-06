"""Minimal Slack incoming-webhook client."""

from __future__ import annotations

import requests

SLACK_TIMEOUT_SECONDS = 10


def post_text(webhook: str, text: str, *, timeout: float = SLACK_TIMEOUT_SECONDS) -> None:
    """Post ``text``; raises on a transport error or a non-2xx status."""
    response = requests.post(webhook, json={"text": text}, timeout=timeout)
    response.raise_for_status()


def escape(text: str) -> str:
    """Slack treats ``&``, ``<`` and ``>`` as control characters in message text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
