#!/usr/bin/env python3
"""
PreToolUse フック: Slack ベースの Edit/Write 承認（バックグラウンドエージェント用）。

Claude Code がファイルを編集または書き込もうとした際に Slack メッセージを送信し、
Block Kit ボタン（承認/拒否）+ Socket Mode daemon の IPC で許可/拒否を待つ。

daemon が未起動の場合はユーザーに起動を促す通知を送信し、ブロックする。

必須環境変数（.claude/.env で設定）:
  SLACK_BOT_TOKEN        - Slack Bot Token (xoxb-...)
  SLACK_CHANNEL_ID       - Slack Channel ID (C0XXXXXXX)
  SLACK_APPROVER_USER_ID - 承認者の Slack ユーザー ID (U0XXXXXXX, Bot ID ではない)

オプション:
  EDIT_APPROVAL_ENABLED  - "1" に設定して有効化（デフォルト: 無効）

終了コード:
  0: 許可（ツール実行を継続）
  2: ブロック（ツール実行を阻止）
"""

import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import timezone
from pathlib import Path
from typing import Optional

# --- Constants ---
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 2
PREVIEW_CHARS = 300  # Max chars for content preview in Slack message

# --- Load env with settings.json fallback ---
_HOOKS_DIR = Path(__file__).resolve().parent.parent  # .claude/hooks/
sys.path.insert(0, str(_HOOKS_DIR))
from lib.env import get as _env

# Environment variables
BOT_TOKEN = _env("SLACK_BOT_TOKEN")
CHANNEL_ID = _env("SLACK_CHANNEL_ID")
APPROVER_USER_ID = _env("SLACK_APPROVER_USER_ID")
EDIT_APPROVAL_ENABLED = _env("EDIT_APPROVAL_ENABLED") or "0"

# File paths
PROJECT_DIR = _env("CLAUDE_PROJECT_DIR")
_BASE = Path(PROJECT_DIR) if PROJECT_DIR else _HOOKS_DIR.parent.parent
AUDIT_LOG_PATH = _BASE / ".claude/logs/edit_approval_audit.jsonl"

# Socket Mode IPC
IPC_DIR = _BASE / ".claude/hooks/ipc"
DAEMON_PID_FILE = IPC_DIR / "daemon.pid"
IPC_POLL_INTERVAL_SECONDS = 0.5
IPC_TIMEOUT_SECONDS = 300  # 5 minutes


def write_audit_log(
    file_path: str,
    tool_name: str,
    decision: str,
    trigger: str,
    approver_user: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> None:
    """Append one record to the edit approval audit log."""
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.datetime.now(timezone.utc).isoformat(),
            "file_path": file_path,
            "tool_name": tool_name,
            "decision": decision,
            "trigger": trigger,
            "approver_user": approver_user,
            "thread_ts": thread_ts,
        }
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[edit_approval] Failed to write audit log: {e}", file=sys.stderr)


def slack_api_request(method: str, payload: dict) -> Optional[dict]:
    """Call Slack Web API with retry on 429. Returns response dict or None on failure."""
    url = f"https://slack.com/api/{method}"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {BOT_TOKEN}",
    }
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return result
                print(
                    f"[edit_approval] Slack API {method} error: {result.get('error')}",
                    file=sys.stderr,
                )
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", RETRY_WAIT_SECONDS))
                time.sleep(retry_after)
                continue
            print(f"[edit_approval] HTTP error {e.code}: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[edit_approval] Request failed: {e}", file=sys.stderr)
            return None
    return None


def truncate(text: str, max_chars: int = PREVIEW_CHARS) -> str:
    """Truncate text and append ellipsis if too long."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def build_edit_diff(old_str: str, new_str: str, context_lines: int = 3) -> str:
    """Build a compact diff showing only changed lines with context."""
    old_lines = old_str.splitlines()
    new_lines = new_str.splitlines()

    import difflib

    diff = list(difflib.unified_diff(
        old_lines, new_lines, lineterm="", n=context_lines
    ))

    if not diff:
        return "(変更なし)"

    # Skip the --- / +++ header lines, show only hunks
    result_lines = []
    for line in diff[2:]:  # skip --- and +++ headers
        if len("\n".join(result_lines)) > PREVIEW_CHARS:
            result_lines.append("…")
            break
        result_lines.append(line)

    return "\n".join(result_lines) if result_lines else "(変更なし)"


def build_notification_text(tool_name: str, file_path: str, tool_input: dict) -> str:
    """Build Slack notification text showing file path and change preview."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    icon = ":pencil2:" if tool_name == "Edit" else ":page_facing_up:"

    lines = [f"{mention}{icon} *ファイル編集承認待ち* (`{tool_name}`)", f"`{file_path}`"]

    if tool_name == "Edit":
        old_str = tool_input.get("old_string", "")
        new_str = tool_input.get("new_string", "")
        diff_text = build_edit_diff(old_str, new_str)
        lines.append(f"*差分:*\n```{diff_text}```")
    elif tool_name in ("Write", "NotebookEdit"):
        content = tool_input.get("content", tool_input.get("new_source", ""))
        total_lines = content.count("\n") + 1
        lines.append(f"*新規ファイル ({total_lines}行):*\n```{truncate(content)}```")

    return "\n".join(lines)


def is_daemon_running() -> bool:
    """Return True if the Socket Mode daemon pid file exists."""
    return DAEMON_PID_FILE.exists()


def send_daemon_start_notice(context: str) -> None:
    """Send a notification asking the user to start the Socket Mode daemon."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    text = (
        f"{mention}:warning: *Socket Mode daemon が未起動です*\n"
        f"{context}\n"
        f"承認にはdaemonが必要です。以下のコマンドで起動してください:\n"
        f"```python3 .claude/hooks/slack/slack_socket_daemon.py &```"
    )
    slack_api_request(
        "chat.postMessage",
        {"channel": CHANNEL_ID, "text": text},
    )


def send_approval_request_blocks(text: str) -> Optional[dict]:
    """Send Block Kit approval request (Socket Mode IPC path)."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "承認"},
                    "style": "primary",
                    "action_id": "approve",
                    "value": "approve",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "拒否"},
                    "style": "danger",
                    "action_id": "deny",
                    "value": "deny",
                },
            ],
        },
    ]
    return slack_api_request(
        "chat.postMessage",
        {"channel": CHANNEL_ID, "text": text, "blocks": blocks},
    )


def wait_for_ipc_decision(message_ts: str) -> tuple:
    """Wait for Socket Mode daemon to write a decision via file-based IPC."""
    IPC_DIR.mkdir(parents=True, exist_ok=True)
    pending_file = IPC_DIR / f"{message_ts}.pending"
    decision_file = IPC_DIR / f"{message_ts}.decision"
    pending_file.write_text(message_ts)
    deadline = time.time() + IPC_TIMEOUT_SECONDS
    try:
        while time.time() < deadline:
            if decision_file.exists():
                decision = decision_file.read_text().strip()
                if decision in ("allow", "deny"):
                    return decision, "daemon", message_ts
            time.sleep(IPC_POLL_INTERVAL_SECONDS)
        return "timeout", None, None
    finally:
        pending_file.unlink(missing_ok=True)
        decision_file.unlink(missing_ok=True)


def update_message_status(message_ts: str, original_text: str, status_text: str) -> None:
    """Update the original approval message to show final status."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": original_text}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": status_text}]},
    ]
    slack_api_request(
        "chat.update",
        {"channel": CHANNEL_ID, "ts": message_ts, "text": original_text, "blocks": blocks},
    )


def main() -> None:
    """Main entry point: read PreToolUse hook input and decide allow/block."""
    # EDIT_APPROVAL_ENABLED=1 で有効化（デフォルト無効）
    if EDIT_APPROVAL_ENABLED != "1":
        sys.exit(0)

    # 勤務時間外はスキップ
    from lib.work_hours import is_work_hours
    if not is_work_hours():
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", tool_input.get("notebook_path", ""))
    if not file_path:
        sys.exit(0)

    # Slack credentials not set: skip
    if not BOT_TOKEN or not CHANNEL_ID:
        write_audit_log(file_path, tool_name, "skip", "token_not_set")
        sys.exit(0)

    if not APPROVER_USER_ID:
        write_audit_log(file_path, tool_name, "deny", "approver_not_set")
        print("[edit_approval] SLACK_APPROVER_USER_ID が未設定のため承認をブロック", file=sys.stderr)
        sys.exit(2)

    notification_text = build_notification_text(tool_name, file_path, tool_input)

    # daemon 未起動: 起動を促す通知を送信しブロック
    if not is_daemon_running():
        send_daemon_start_notice(notification_text)
        write_audit_log(file_path, tool_name, "deny", "daemon_not_running")
        print(
            "[edit_approval] Socket Mode daemon が未起動のためブロック。"
            "起動: python3 .claude/hooks/slack/slack_socket_daemon.py &",
            file=sys.stderr,
        )
        sys.exit(2)

    # ボタン付き承認リクエストを送信
    response = send_approval_request_blocks(notification_text)

    if not response:
        write_audit_log(file_path, tool_name, "deny", "error")
        print("[edit_approval] Slack API error: blocking (fail-closed)", file=sys.stderr)
        sys.exit(2)

    thread_ts = response.get("ts", "")

    # daemon IPC で決定を待つ
    decision, approver_user, message_ts = wait_for_ipc_decision(thread_ts)

    if decision == "allow":
        update_message_status(thread_ts, notification_text, ":white_check_mark: 承認済み")
        write_audit_log(file_path, tool_name, "allow", "slack", approver_user, thread_ts)
        sys.exit(0)
    elif decision == "deny":
        update_message_status(thread_ts, notification_text, ":x: 拒否されました")
        write_audit_log(file_path, tool_name, "deny", "slack", approver_user, thread_ts)
        sys.exit(2)
    else:  # timeout
        update_message_status(
            thread_ts, notification_text,
            ":hourglass: タイムアウト（5分）: 編集をブロックしました"
        )
        write_audit_log(file_path, tool_name, "timeout", "timeout", None, thread_ts)
        sys.exit(2)


if __name__ == "__main__":
    main()
