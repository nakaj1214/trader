#!/usr/bin/env python3
"""
Stop hook: Claude が作業を完了した際に Slack へ完了通知を送信する。

Filters:
  - hook_event_name must be "Stop" (SubagentStop is ignored)
  - stop_hook_active must be false (recursion guard)
  - last_assistant_message must be >= MIN_MESSAGE_LENGTH chars (skip short responses)

Environment variables (set in .claude/settings.json env section):
  SLACK_BOT_TOKEN   - Slack Bot Token (xoxb-...) [preferred]
  SLACK_CHANNEL_ID  - Slack Channel ID (required when using Bot Token)
  SLACK_WEBHOOK_URL - Slack Incoming Webhook URL [fallback]

Usage (hook mode — called by Claude Code Stop event):
  echo '{"hook_event_name":"Stop","last_assistant_message":"..."}' | python3 stop-notify.py

Usage (direct — called from skills):
  python3 stop-notify.py --message "text" [--title "title"]
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent  # .claude/hooks/
sys.path.insert(0, str(_HOOKS_DIR))
from lib.env import get as _env

# Minimum message length to trigger notification (skip greetings / short Q&A)
MIN_MESSAGE_LENGTH = 200

WEBHOOK_URL = _env("SLACK_WEBHOOK_URL")
BOT_TOKEN = _env("SLACK_BOT_TOKEN")
CHANNEL_ID = _env("SLACK_CHANNEL_ID")


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
        print(f"[stop-notify] Bot Token send failed: {e}", file=sys.stderr)
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
        print(f"[stop-notify] Webhook send failed: {e}", file=sys.stderr)
        return False


def _is_handover_response(text: str) -> bool:
    """Handover レスポンスかどうかを判定する。

    handover スキルや pre-compact-handover の出力パターンを検出する。
    """
    if not text:
        return False
    # 典型的な handover パターン: "Handover —" または "ハンドオーバー" を含み、
    # "Session Summary" / "セッション概要" / "Next Steps" / "次のステップ" がある
    has_handover_title = "Handover —" in text or "ハンドオーバー" in text
    has_handover_section = any(
        kw in text
        for kw in ("Session Summary", "セッション概要", "Next Steps", "次のステップ", "Completed Work", "完了した作業")
    )
    return has_handover_title and has_handover_section


SUMMARY_MAX_CHARS = 400


def extract_summary(text: str) -> str:
    """last_assistant_message から Slack 通知用の要約を抽出する。

    Markdown 記号やツール呼び出しタグを除去し、先頭 400 文字以内で
    文境界（改行位置）に合わせて切り出す。
    """
    if not text:
        return ""

    # ツール呼び出し情報を除去（<function_calls>...</function_calls> 等）
    cleaned = re.sub(r"<[^>]+>", "", text)
    # Markdown 見出し記号を除去
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    # Markdown 水平線を除去
    cleaned = re.sub(r"^---+\s*$", "", cleaned, flags=re.MULTILINE)
    # Markdown 太字記号を除去
    cleaned = re.sub(r"\*\*([^*]*)\*\*", r"\1", cleaned)
    # 連続する空行を1つに
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return ""

    if len(cleaned) <= SUMMARY_MAX_CHARS:
        return cleaned

    # 400 文字で切り出し、最後の改行位置で切る
    truncated = cleaned[:SUMMARY_MAX_CHARS]
    last_newline = truncated.rfind("\n")
    if last_newline > SUMMARY_MAX_CHARS // 2:
        truncated = truncated[:last_newline]

    return truncated.rstrip() + "…"


def send_slack(message: str, title: str = "") -> bool:
    """Send a message to Slack. Uses Bot Token API if available, else Webhook."""
    text = f"*{title}*\n{message}" if title else message

    if BOT_TOKEN and CHANNEL_ID:
        return _send_via_bot_token(text)

    if WEBHOOK_URL:
        return _send_via_webhook(text)

    print("[stop-notify] No Slack credentials set, skipping.", file=sys.stderr)
    return False


def handle_hook() -> None:
    """Handle Stop hook input from Claude Code.

    Filters applied (REQ-001, REQ-002):
    1. hook_event_name must be "Stop" — SubagentStop is ignored
    2. stop_hook_active must be false — prevents recursion
    3. last_assistant_message length >= MIN_MESSAGE_LENGTH — skips short responses
    """
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Filter 1: Only fire on main session Stop (not SubagentStop)
    event_name = data.get("hook_event_name", "")
    if event_name != "Stop":
        print(f"[stop-notify] skip: event={event_name} (not Stop)", file=sys.stderr)
        sys.exit(0)

    # 勤務時間外はスキップ
    from lib.work_hours import is_work_hours
    if not is_work_hours():
        print("[stop-notify] skip: off work hours", file=sys.stderr)
        sys.exit(0)

    # Filter 2: Recursion guard
    if data.get("stop_hook_active"):
        print("[stop-notify] skip: stop_hook_active=true", file=sys.stderr)
        sys.exit(0)

    # Filter 3: Short response filter (greetings, simple Q&A)
    assistant_message = data.get("last_assistant_message", "")
    if len(assistant_message) < MIN_MESSAGE_LENGTH:
        print(
            f"[stop-notify] skip: message too short ({len(assistant_message)}<{MIN_MESSAGE_LENGTH})",
            file=sys.stderr,
        )
        sys.exit(0)

    now = datetime.now().strftime("%H:%M")

    # Handover レスポンスの検出: 内容は既にファイルに保存されているため短い通知のみ
    if _is_handover_response(assistant_message):
        send_slack(
            message="ハンドオーバードキュメントを保存しました。",
            title=f":memo: Handover 完了 ({now})",
        )
        sys.exit(0)

    try:
        summary = extract_summary(assistant_message)
    except Exception:
        summary = ""

    message = summary if summary else "作業が完了しました。結果を確認してください。"

    send_slack(
        message=message,
        title=f":white_check_mark: Claude Code 応答完了 ({now})",
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
        print("Usage: stop-notify.py --message TEXT [--title TITLE]", file=sys.stderr)
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
