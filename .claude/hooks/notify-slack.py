#!/usr/bin/env python3
"""
PreToolUse hook: Send Slack notification when user input is required.

Triggers on AskUserQuestion to notify that Claude/Codex needs user attention.

Environment variables (set in .claude/settings.json env section):
  SLACK_BOT_TOKEN   - Slack Bot Token (xoxb-...) [preferred]
  SLACK_CHANNEL_ID  - Slack Channel ID (required when using Bot Token)
  SLACK_WEBHOOK_URL - Slack Incoming Webhook URL [fallback]

Send priority:
  1. SLACK_BOT_TOKEN + SLACK_CHANNEL_ID → chat.postMessage API
  2. SLACK_WEBHOOK_URL only → Incoming Webhook (legacy)
  3. Neither set → skip silently

Usage (direct):
  python3 notify-slack.py --message "text" [--title "title"]
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")


def _send_via_bot_token(text: str) -> bool:
    """Send message via Slack Web API (chat.postMessage). Returns True on success."""
    payload = json.dumps({"channel": CHANNEL_ID, "text": text}).encode("utf-8")
    try:
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {BOT_TOKEN}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return bool(result.get("ok"))
    except Exception as e:
        print(f"[notify-slack] Bot Token send failed: {e}", file=sys.stderr)
        return False


def _send_via_webhook(text: str) -> bool:
    """Send message via Incoming Webhook. Returns True on success."""
    payload = json.dumps({"text": text}).encode("utf-8")
    try:
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        print(f"[notify-slack] Webhook send failed: {e}", file=sys.stderr)
        return False


def send_slack(message: str, title: str = "") -> bool:
    """Send a message to Slack. Uses Bot Token API if available, else Webhook."""
    text = f"*{title}*\n{message}" if title else message

    if BOT_TOKEN and CHANNEL_ID:
        return _send_via_bot_token(text)

    if WEBHOOK_URL:
        return _send_via_webhook(text)

    print("[notify-slack] No Slack credentials set, skipping.", file=sys.stderr)
    return False


def handle_hook() -> None:
    """Handle PreToolUse hook input from Claude Code."""
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name != "AskUserQuestion":
        sys.exit(0)

    questions = tool_input.get("questions", [])
    if not questions:
        sys.exit(0)

    message_lines = []
    for q in questions:
        question_text = q.get("question", "")
        if not question_text:
            continue
        message_lines.append(f"• {question_text}")
        options = q.get("options", [])
        for opt in options:
            label = opt.get("label", "")
            description = opt.get("description", "")
            if label and description:
                message_lines.append(f"    - *{label}*: {description}")
            elif label:
                message_lines.append(f"    - *{label}*")
        # Always ensure "Other" appears as the last choice
        has_other = any(
            opt.get("label", "").lower() in ("other", "その他")
            for opt in options
        )
        if options and not has_other:
            message_lines.append("    - *Other*: この中にない場合は自由に記入")
    message = "\n".join(message_lines)

    now = datetime.now().strftime("%H:%M")
    send_slack(
        message=message,
        title=f":bell: Claude Code が確認を求めています ({now})",
    )
    sys.exit(0)


def handle_cli() -> None:
    """Handle direct CLI invocation: --message TEXT [--title TITLE]"""
    args = sys.argv[1:]
    message = ""
    title = ""

    i = 0
    while i < len(args):
        if args[i] == "--message" and i + 1 < len(args):
            message = args[i + 1]
            i += 2
        elif args[i] == "--title" and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        else:
            i += 1

    if not message:
        print("Usage: notify-slack.py --message TEXT [--title TITLE]", file=sys.stderr)
        sys.exit(1)

    message = message.replace("\\n", "\n")
    title = title.replace("\\n", "\n")
    success = send_slack(message=message, title=title)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # If stdin has data and no CLI args → hook mode
    if len(sys.argv) == 1 and not sys.stdin.isatty():
        handle_hook()
    else:
        handle_cli()
