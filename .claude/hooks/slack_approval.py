#!/usr/bin/env python3
"""
PreToolUse hook: Slack-based Bash command approval.

Sends a Slack message when Claude Code wants to run a Bash command,
then polls the message for allow/deny via:
  - Emoji reaction: :white_check_mark: (allow) or :x: (deny)
  - Thread reply: keywords like "allow" / "deny" (and Japanese equivalents)

Required environment variables (set in .claude/settings.json env section):
  SLACK_BOT_TOKEN        - Slack Bot Token (xoxb-...)
  SLACK_CHANNEL_ID       - Slack Channel ID (C0XXXXXXX)
  SLACK_APPROVER_USER_ID - Approver's Slack user ID (U0XXXXXXX, NOT Bot ID)

Exit codes:
  0: Allow (tool execution continues)
  2: Block (tool execution is blocked)
"""

import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# --- Constants ---
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 2  # Default wait on 429 (Retry-After header takes priority)
POLL_INTERVAL_SECONDS = 5
POLL_MAX_COUNT = 60  # 5s * 60 = max 5 minutes

# Shell metachar patterns that force require (evaluated before pattern matching)
REDIRECT_PATTERN = re.compile(r"(?:>>?|<(?!\()|2>>?|&>|\|&)")
SUBSHELL_PATTERN = re.compile(r"\$\(|`|<\(|>\(")

# Compound command splitters
COMPOUND_SPLIT_PATTERN = re.compile(r"&&|\|\||;|\|")

# Environment variables
BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")
APPROVER_USER_ID = os.environ.get("SLACK_APPROVER_USER_ID", "")

# File paths
PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", "")
_BASE = Path(PROJECT_DIR) if PROJECT_DIR else Path(".")
AUDIT_LOG_PATH = _BASE / ".claude/logs/approval_audit.jsonl"
PATTERNS_PATH = _BASE / ".claude/hooks/approval_skip_patterns.txt"

# Socket Mode IPC paths and settings
IPC_DIR = _BASE / ".claude/hooks/ipc"
DAEMON_PID_FILE = IPC_DIR / "daemon.pid"
IPC_POLL_INTERVAL_SECONDS = 0.5
IPC_TIMEOUT_SECONDS = 300  # 5 minutes (same as polling timeout)


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
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
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


def has_shell_metachar(command: str) -> bool:
    """Return True if command contains redirect or subshell metacharacters."""
    return bool(REDIRECT_PATTERN.search(command) or SUBSHELL_PATTERN.search(command))


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


def classify_command(command: str, patterns: list) -> str:
    """
    Classify full command as 'require' or 'skip'.

    Priority:
    1. Shell metachar / redirect detection → immediate require
    2. Compound command expansion (&&, ||, ;, |)
    3. Pattern prefix matching
    4. Default: require (fail-safe)
    """
    # Step 1: shell metachar detection (highest priority)
    if has_shell_metachar(command):
        return "require"

    # Step 2: compound command expansion
    tokens = COMPOUND_SPLIT_PATTERN.split(command)
    classifications = [classify_token(t, patterns) for t in tokens]

    # If any token matches require → entire command is require
    if any(c == "require" for c in classifications):
        return "require"

    # If all tokens match skip → entire command is skip
    if all(c == "skip" for c in classifications):
        return "skip"

    # Default: require (fail-safe)
    return "require"


def is_daemon_running() -> bool:
    """Return True if the Socket Mode daemon pid file exists.

    Note: os.kill(pid, 0) is intentionally not used because the daemon may
    run inside a Docker container where the PID namespace differs from the host.
    The daemon removes daemon.pid on clean shutdown (SIGTERM/SIGINT), so file
    existence is a reliable indicator in normal operation. A crashed daemon
    leaves a stale file, which causes a 5-minute IPC timeout (fail-closed).
    """
    return DAEMON_PID_FILE.exists()


def send_approval_request(command: str, extra_text: str = "") -> Optional[dict]:
    """Send approval request as plain text (polling mode). Returns API response or None."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    text = (
        f"{mention}:bell: Bash コマンド承認待ち\n```{command}```\n"
        f":white_check_mark: で承認 / :x: で拒否"
        f"（リアクション or スレッド返信: allow/deny）"
    )
    if extra_text:
        text += f"\n{extra_text}"

    return slack_api_request(
        "chat.postMessage",
        {"channel": CHANNEL_ID, "text": text},
    )


def send_approval_request_blocks(command: str) -> Optional[dict]:
    """Send approval request with Block Kit buttons (Socket Mode IPC path).

    Returns API response or None. The daemon handles button interactions and
    writes the decision to an IPC file for wait_for_ipc_decision() to read.
    """
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    text = f"{mention}:bell: Bash コマンド承認待ち\n```{command}```"
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


def update_message_status(message_ts: str, command: str, status_text: str) -> None:
    """Update the original approval message to show the final status (no buttons)."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    text = f"{mention}:bell: Bash コマンド承認待ち\n```{command}```"
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


def send_thread_notification(thread_ts: str, message: str) -> None:
    """Post a notification message to an existing Slack thread."""
    slack_api_request(
        "chat.postMessage",
        {"channel": CHANNEL_ID, "thread_ts": thread_ts, "text": message},
    )


ALLOW_REACTION = "white_check_mark"
DENY_REACTION = "x"

ALLOW_KEYWORDS: frozenset = frozenset({"allow", "ok", "yes", "y", "承認", "許可"})
DENY_KEYWORDS: frozenset = frozenset({"deny", "no", "ng", "n", "拒否", "却下", "block"})


def poll_for_decision(message_ts: str) -> tuple:
    """
    Poll for allow/deny via emoji reaction OR thread reply from the approver.

    Checks per poll interval:
      1. Emoji reactions: :white_check_mark: (allow), :x: (deny)
      2. Thread replies: keywords like "allow"/"deny" (and Japanese equivalents)

    Returns (decision, approver_user, message_ts) where decision is
    'allow', 'deny', or 'timeout'.
    """
    for _ in range(POLL_MAX_COUNT):
        time.sleep(POLL_INTERVAL_SECONDS)

        # --- Check reactions ---
        reaction_result = slack_api_request(
            "reactions.get",
            {
                "channel": CHANNEL_ID,
                "timestamp": message_ts,
                "full": True,
            },
        )
        if reaction_result:
            reactions = reaction_result.get("message", {}).get("reactions", [])
            for reaction in reactions:
                name = reaction.get("name", "")
                users = reaction.get("users", [])
                if APPROVER_USER_ID not in users:
                    continue
                if name == ALLOW_REACTION:
                    return "allow", APPROVER_USER_ID, message_ts
                elif name == DENY_REACTION:
                    return "deny", APPROVER_USER_ID, message_ts

        # --- Check thread replies ---
        replies_result = slack_api_request(
            "conversations.replies",
            {"channel": CHANNEL_ID, "ts": message_ts},
        )
        if replies_result:
            messages = replies_result.get("messages", [])
            for msg in messages[1:]:  # skip parent message
                if msg.get("user") != APPROVER_USER_ID:
                    continue
                text = msg.get("text", "").strip().lower()
                if text in ALLOW_KEYWORDS:
                    return "allow", APPROVER_USER_ID, message_ts
                elif text in DENY_KEYWORDS:
                    return "deny", APPROVER_USER_ID, message_ts

    return "timeout", None, None


def main() -> None:
    """Main entry point: read PreToolUse hook input and decide allow/block."""
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    patterns = load_patterns()
    classification = classify_command(command, patterns)

    # Skip: exit 0 immediately (no Slack notification)
    if classification == "skip":
        write_audit_log(command, "skip", "pattern")
        sys.exit(0)

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

    # Choose mode: Socket Mode IPC (if daemon running) or polling (fallback)
    daemon_running = is_daemon_running()

    if daemon_running:
        response = send_approval_request_blocks(command)
    else:
        response = send_approval_request(command)

    if not response:
        # API error: fail-closed (block command)
        write_audit_log(command, "deny", "error")
        print(
            "[slack_approval] Slack API error: blocking command (fail-closed)",
            file=sys.stderr,
        )
        sys.exit(2)

    thread_ts = response.get("ts", "")

    # Wait for decision via IPC (Socket Mode) or polling (fallback)
    if daemon_running:
        decision, approver_user, message_ts = wait_for_ipc_decision(thread_ts)
    else:
        decision, approver_user, message_ts = poll_for_decision(thread_ts)

    if decision == "allow":
        update_message_status(thread_ts, command, ":white_check_mark: 承認済み")
        write_audit_log(command, "allow", "slack", approver_user, thread_ts, message_ts)
        sys.exit(0)
    elif decision == "deny":
        update_message_status(thread_ts, command, ":x: 拒否されました")
        write_audit_log(command, "deny", "slack", approver_user, thread_ts, message_ts)
        sys.exit(2)
    else:  # timeout
        update_message_status(
            thread_ts, command, ":hourglass: タイムアウト（5分）: コマンドをブロックしました"
        )
        write_audit_log(command, "timeout", "timeout", None, thread_ts, None)
        sys.exit(2)


if __name__ == "__main__":
    main()
