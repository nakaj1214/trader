#!/usr/bin/env python3
"""
PreToolUse フック: Slack ベースの Bash コマンド承認。

Claude Code が Bash コマンドを実行しようとした際に Slack メッセージを送信し、
Block Kit ボタン（承認/拒否）+ Socket Mode daemon の IPC で許可/拒否を待つ。

daemon が未起動の場合はユーザーに起動を促す通知を送信し、コマンドをブロックする。

必須環境変数（.claude/.env で設定）:
  SLACK_BOT_TOKEN        - Slack Bot Token (xoxb-...)
  SLACK_CHANNEL_ID       - Slack Channel ID (C0XXXXXXX)
  SLACK_APPROVER_USER_ID - 承認者の Slack ユーザー ID (U0XXXXXXX, Bot ID ではない)

終了コード:
  0: 許可（ツール実行を継続）
  2: ブロック（ツール実行を阻止）
"""

import datetime
import json
import os
import re
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

# Shell metachar patterns that force require (evaluated before pattern matching)
SUBSHELL_PATTERN = re.compile(r"\$\(|`|<\(|>\(")

# Compound command splitters
COMPOUND_SPLIT_PATTERN = re.compile(r"&&|\|\||;|\|")

# --- Load env with settings.json fallback ---
_HOOKS_DIR = Path(__file__).resolve().parent.parent  # .claude/hooks/
sys.path.insert(0, str(_HOOKS_DIR))
from lib.env import get as _env

# Environment variables
BOT_TOKEN = _env("SLACK_BOT_TOKEN")
CHANNEL_ID = _env("SLACK_CHANNEL_ID")
APPROVER_USER_ID = _env("SLACK_APPROVER_USER_ID")

# File paths
PROJECT_DIR = _env("CLAUDE_PROJECT_DIR")
_BASE = Path(PROJECT_DIR) if PROJECT_DIR else _HOOKS_DIR.parent.parent
AUDIT_LOG_PATH = _BASE / ".claude/logs/approval_audit.jsonl"
PATTERNS_PATH = _HOOKS_DIR / "slack/approval_skip_patterns.txt"

# Socket Mode IPC paths and settings
IPC_DIR = _BASE / ".claude/hooks/ipc"
DAEMON_PID_FILE = IPC_DIR / "daemon.pid"
IPC_POLL_INTERVAL_SECONDS = 0.5
IPC_TIMEOUT_SECONDS = 300  # 5 minutes


def write_audit_log(
    command: str,
    decision: str,
    trigger: str,
    approver_user: Optional[str] = None,
    thread_ts: Optional[str] = None,
    message_ts: Optional[str] = None,
) -> None:
    """Append one record to the approval audit log."""
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.datetime.now(timezone.utc).isoformat(),
            "command": command,
            "decision": decision,
            "trigger": trigger,
            "approver_user": approver_user,
            "thread_ts": thread_ts,
            "message_ts": message_ts,
        }
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[slack_approval] Failed to write audit log: {e}", file=sys.stderr)


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
                    f"[slack_approval] Slack API {method} error: {result.get('error')}",
                    file=sys.stderr,
                )
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", RETRY_WAIT_SECONDS))
                time.sleep(retry_after)
                continue
            print(f"[slack_approval] HTTP error {e.code}: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[slack_approval] Request failed: {e}", file=sys.stderr)
            return None

    return None


def load_patterns() -> list:
    """Load list of (action, prefix) pairs from approval_skip_patterns.txt."""
    patterns = []
    try:
        with open(PATTERNS_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    action, _, prefix = line.partition(":")
                    patterns.append((action.strip(), prefix.strip()))
    except FileNotFoundError:
        print(
            f"[slack_approval] Pattern file not found: {PATTERNS_PATH}", file=sys.stderr
        )
    return patterns


def classify_token(token: str, patterns: list) -> str:
    """Return 'require', 'skip', or 'unknown' for a single command token."""
    token = token.strip()
    for action, prefix in patterns:
        if token.startswith(prefix):
            return action
    return "unknown"


def is_internal_hook_script(command: str) -> bool:
    """Return True if command calls an internal hook script in .claude/hooks/."""
    return ".claude/hooks/" in command and command.strip().startswith("python3 ")


def classify_command(command: str, patterns: list) -> str:
    """
    Classify full command as 'require' or 'skip'.

    Priority:
    0. Internal hook script auto-skip (prevents circular dependency)
    1. Subshell detection ($(...), `...`) → immediate require
    2. Compound command expansion (&&, ||, ;, |) + pattern prefix matching
    3. Default: require (fail-safe)
    """
    # Step 0: auto-skip internal hook scripts (prevents circular dependency)
    if is_internal_hook_script(command):
        return "skip"

    # Step 1: サブシェルのみ即 require
    if SUBSHELL_PATTERN.search(command):
        return "require"

    # Step 2: compound command expansion + pattern matching
    tokens = COMPOUND_SPLIT_PATTERN.split(command)
    classifications = [classify_token(t.strip(), patterns) for t in tokens]

    # 1つでも require → 全体が require
    if any(c == "require" for c in classifications):
        return "require"

    # 全トークンが skip → 全体が skip
    if all(c == "skip" for c in classifications):
        return "skip"

    # Default: require (fail-safe)
    return "require"


def is_daemon_running() -> bool:
    """Return True if the Socket Mode daemon pid file exists."""
    return DAEMON_PID_FILE.exists()


def send_daemon_start_notice(command: str, description: str = "") -> None:
    """Send a notification asking the user to start the Socket Mode daemon."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    desc_line = f"*{description}*\n" if description else ""
    text = (
        f"{mention}:warning: *Socket Mode daemon が未起動です*\n"
        f"{desc_line}"
        f"```{command}```\n"
        f"承認にはdaemonが必要です。以下のコマンドで起動してください:\n"
        f"```python3 .claude/hooks/slack/slack_socket_daemon.py &```"
    )
    slack_api_request(
        "chat.postMessage",
        {"channel": CHANNEL_ID, "text": text},
    )


def send_approval_request_blocks(command: str, description: str = "") -> Optional[dict]:
    """Send approval request with Block Kit buttons (Socket Mode IPC path)."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    desc_line = f"*{description}*\n" if description else ""
    text = (
        f"{mention}:bell: *Bash コマンド承認待ち*\n"
        f"{desc_line}"
        f"```{command}```"
    )
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        },
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
    """Wait for the Socket Mode daemon to write a decision via file-based IPC.

    Creates a .pending file to signal the daemon that approval is expected,
    then polls for the corresponding .decision file.

    Returns (decision, approver_user, message_ts) where decision is
    'allow', 'deny', or 'timeout'.
    """
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


def update_message_status(message_ts: str, command: str, status_text: str, description: str = "") -> None:
    """Update the original approval message to show the final status (no buttons)."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    desc_line = f"*{description}*\n" if description else ""
    text = (
        f"{mention}:bell: *Bash コマンド承認待ち*\n"
        f"{desc_line}"
        f"```{command}```"
    )
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": status_text}],
        },
    ]
    slack_api_request(
        "chat.update",
        {"channel": CHANNEL_ID, "ts": message_ts, "text": text, "blocks": blocks},
    )


def main() -> None:
    """Main entry point: read PreToolUse hook input and decide allow/block."""
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # MCP Codex ツール: 常に承認リクエスト（パターン分類なし）
    if tool_name == "mcp__codex__codex":
        prompt = tool_input.get("prompt", "")
        if not prompt:
            sys.exit(0)
        model = tool_input.get("model", "default")
        description = f"Codex MCP ({model})"
        command = prompt
        from lib.work_hours import is_work_hours
        if not is_work_hours():
            write_audit_log(command, "skip", "off_hours")
            sys.exit(0)
        _run_approval_flow(command, description)
        return

    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    description = tool_input.get("description", "")

    patterns = load_patterns()
    classification = classify_command(command, patterns)

    # Skip: exit 0 immediately (no Slack notification)
    if classification == "skip":
        write_audit_log(command, "skip", "pattern")
        sys.exit(0)

    # 勤務時間外はスキップ
    from lib.work_hours import is_work_hours
    if not is_work_hours():
        write_audit_log(command, "skip", "off_hours")
        sys.exit(0)

    _run_approval_flow(command, description)


def _run_approval_flow(command: str, description: str = "") -> None:
    """承認フロー: Slack にボタン付きリクエストを送信し、daemon IPC で結果を待つ。"""
    # Token/Channel not set: hook is disabled, delegate to permissions.allow
    if not BOT_TOKEN or not CHANNEL_ID:
        write_audit_log(command, "skip", "token_not_set")
        sys.exit(0)

    # APPROVER_USER_ID is required: fail-closed if not set
    if not APPROVER_USER_ID:
        write_audit_log(command, "deny", "approver_not_set")
        print(
            "[slack_approval] SLACK_APPROVER_USER_ID が未設定のため承認をブロック",
            file=sys.stderr,
        )
        sys.exit(2)

    # daemon 未起動: 起動を促す通知を送信しブロック
    if not is_daemon_running():
        send_daemon_start_notice(command, description)
        write_audit_log(command, "deny", "daemon_not_running")
        print(
            "[slack_approval] Socket Mode daemon が未起動のためブロック。"
            "起動: python3 .claude/hooks/slack/slack_socket_daemon.py &",
            file=sys.stderr,
        )
        sys.exit(2)

    # ボタン付き承認リクエストを送信
    response = send_approval_request_blocks(command, description)

    if not response:
        write_audit_log(command, "deny", "error")
        print(
            "[slack_approval] Slack API error: blocking command (fail-closed)",
            file=sys.stderr,
        )
        sys.exit(2)

    thread_ts = response.get("ts", "")

    # daemon IPC で決定を待つ
    decision, approver_user, message_ts = wait_for_ipc_decision(thread_ts)

    if decision == "allow":
        update_message_status(thread_ts, command, ":white_check_mark: 承認済み", description)
        write_audit_log(command, "allow", "slack", approver_user, thread_ts, message_ts)
        sys.exit(0)
    elif decision == "deny":
        update_message_status(thread_ts, command, ":x: 拒否されました", description)
        write_audit_log(command, "deny", "slack", approver_user, thread_ts, message_ts)
        sys.exit(2)
    else:  # timeout
        update_message_status(
            thread_ts, command, ":hourglass: タイムアウト（5分）: コマンドをブロックしました", description
        )
        write_audit_log(command, "timeout", "timeout", None, thread_ts, None)
        sys.exit(2)


if __name__ == "__main__":
    main()
