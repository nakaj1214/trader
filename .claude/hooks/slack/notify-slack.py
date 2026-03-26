#!/usr/bin/env python3
"""
PreToolUse フック: AskUserQuestion / ExitPlanMode の Slack 通知・承認。

Claude Code がユーザー確認を求める際に Slack へ通知を送信する。
- ExitPlanMode: Block Kit ボタンで承認/拒否（daemon IPC 経由）
- AskUserQuestion: 通知のみ（ブロックしない）

daemon が未起動の場合はユーザーに起動を促す通知を送信し、ブロックする。

必須環境変数（.claude/.env で設定）:
  SLACK_BOT_TOKEN        - Slack Bot Token (xoxb-...)
  SLACK_CHANNEL_ID       - Slack Channel ID (C0XXXXXXX)
  SLACK_APPROVER_USER_ID - 承認者の Slack ユーザー ID (U0XXXXXXX, Bot ID ではない)

オプション:
  SLACK_WEBHOOK_URL      - Incoming Webhook URL（CLI モードのフォールバック専用）

終了コード（フックモード）:
  0: 許可（ツール実行を継続）
  2: ブロック（ツール実行を阻止）

使い方（CLI モード — 通知のみ、承認なし）:
  python3 notify-slack.py --message "text" [--title "title"]
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

# --- Constants ---
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 2

# --- Load env with settings.json fallback ---
_HOOKS_DIR = Path(__file__).resolve().parent.parent  # .claude/hooks/
sys.path.insert(0, str(_HOOKS_DIR))
from lib.env import get as _env

# Environment variables
WEBHOOK_URL = _env("SLACK_WEBHOOK_URL")
BOT_TOKEN = _env("SLACK_BOT_TOKEN")
CHANNEL_ID = _env("SLACK_CHANNEL_ID")
APPROVER_USER_ID = _env("SLACK_APPROVER_USER_ID")

# File paths
PROJECT_DIR = _env("CLAUDE_PROJECT_DIR")
_BASE = Path(PROJECT_DIR) if PROJECT_DIR else _HOOKS_DIR.parent.parent

# Socket Mode IPC
IPC_DIR = _BASE / ".claude/hooks/ipc"
DAEMON_PID_FILE = IPC_DIR / "daemon.pid"
IPC_POLL_INTERVAL_SECONDS = 0.5
IPC_TIMEOUT_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Slack API helpers
# ---------------------------------------------------------------------------


def slack_api_request(method: str, payload: dict) -> Optional[dict]:
    """Call Slack Web API with retry on 429. Returns response dict or None."""
    url = f"https://slack.com/api/{method}"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {BOT_TOKEN}",
    }
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url, data=data, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return result
                print(
                    f"[notify-slack] Slack API {method} error: {result.get('error')}",
                    file=sys.stderr,
                )
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(
                    e.headers.get("Retry-After", RETRY_WAIT_SECONDS)
                )
                time.sleep(retry_after)
                continue
            print(
                f"[notify-slack] HTTP error {e.code}: {e}", file=sys.stderr
            )
            return None
        except Exception as e:
            print(f"[notify-slack] Request failed: {e}", file=sys.stderr)
            return None
    return None


def _send_via_webhook(text: str) -> bool:
    """Send message via Incoming Webhook (CLI fallback). Returns True on success."""
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


def send_slack_simple(message: str, title: str = "") -> bool:
    """Send a simple notification (no buttons). Used by CLI mode."""
    text = f"*{title}*\n{message}" if title else message
    if BOT_TOKEN and CHANNEL_ID:
        result = slack_api_request(
            "chat.postMessage", {"channel": CHANNEL_ID, "text": text}
        )
        return result is not None
    if WEBHOOK_URL:
        return _send_via_webhook(text)
    print("[notify-slack] No Slack credentials set, skipping.", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# Approval flow helpers (Button + daemon IPC only)
# ---------------------------------------------------------------------------


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


def update_message_status(
    message_ts: str, original_text: str, status_text: str
) -> None:
    """Update the original approval message to show final status."""
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": original_text},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": status_text}],
        },
    ]
    slack_api_request(
        "chat.update",
        {
            "channel": CHANNEL_ID,
            "ts": message_ts,
            "text": original_text,
            "blocks": blocks,
        },
    )


def run_approval_flow(notification_text: str) -> None:
    """Send button approval request to Slack, wait for daemon IPC response, exit 0 or 2."""
    # daemon 未起動: 起動を促す通知を送信しブロック
    if not is_daemon_running():
        send_daemon_start_notice(notification_text)
        print(
            "[notify-slack] Socket Mode daemon が未起動のためブロック。"
            "起動: python3 .claude/hooks/slack/slack_socket_daemon.py &",
            file=sys.stderr,
        )
        sys.exit(2)

    response = send_approval_request_blocks(notification_text)

    if not response:
        print(
            "[notify-slack] Slack API error: blocking (fail-closed)",
            file=sys.stderr,
        )
        sys.exit(2)

    thread_ts = response.get("ts", "")

    decision, approver_user, message_ts = wait_for_ipc_decision(thread_ts)

    if decision == "allow":
        update_message_status(
            thread_ts, notification_text, ":white_check_mark: 承認済み"
        )
        sys.exit(0)
    elif decision == "deny":
        update_message_status(
            thread_ts, notification_text, ":x: 拒否されました"
        )
        sys.exit(2)
    else:  # timeout
        update_message_status(
            thread_ts,
            notification_text,
            ":hourglass: タイムアウト（5分）: ブロックしました",
        )
        sys.exit(2)


# ---------------------------------------------------------------------------
# Notification text builders
# ---------------------------------------------------------------------------


def build_exit_plan_text() -> str:
    """Build Slack message for ExitPlanMode approval."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    now = datetime.now().strftime("%H:%M")
    return (
        f"{mention}:memo: *プラン承認待ち* ({now})\n"
        f"実装計画が完成しました。"
    )


def build_ask_user_question_text(tool_input: dict) -> str:
    """Build Slack message for AskUserQuestion notification."""
    mention = f"<@{APPROVER_USER_ID}> " if APPROVER_USER_ID else ""
    now = datetime.now().strftime("%H:%M")

    questions = tool_input.get("questions", [])
    lines = [f"{mention}:bell: *Claude Code が確認を求めています* ({now})"]

    for q in questions:
        question_text = q.get("question", "")
        if not question_text:
            continue
        lines.append(f"\n• {question_text}")
        options = q.get("options", [])
        for opt in options:
            label = opt.get("label", "")
            description = opt.get("description", "")
            if label and description:
                lines.append(f"    - *{label}*: {description}")
            elif label:
                lines.append(f"    - *{label}*")
        has_other = any(
            opt.get("label", "").lower() in ("other", "その他")
            for opt in options
        )
        if options and not has_other:
            lines.append("    - *Other*: この中にない場合は自由に記入")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hook mode entry point
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    """Write debug log to stderr and log file."""
    log_line = f"[notify-slack] {msg}"
    print(log_line, file=sys.stderr)
    try:
        log_path = _BASE / ".claude/logs/notify-slack-debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def handle_hook() -> None:
    """Handle PreToolUse hook input from Claude Code."""
    _log("hook started")
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        _log("JSON decode error, exiting")
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    _log(f"tool_name={tool_name}")

    if tool_name not in ("ExitPlanMode", "AskUserQuestion"):
        _log(f"skipping: tool_name={tool_name} not in target list")
        sys.exit(0)

    # 勤務時間外はスキップ
    from lib.work_hours import is_work_hours
    if not is_work_hours():
        _log("skip: off work hours")
        sys.exit(0)

    # Credentials check: no BOT_TOKEN/CHANNEL_ID → skip (exit 0)
    if not BOT_TOKEN or not CHANNEL_ID:
        _log(f"no credentials: BOT_TOKEN={bool(BOT_TOKEN)}, CHANNEL_ID={bool(CHANNEL_ID)}")
        sys.exit(0)

    # APPROVER_USER_ID required: fail-closed if not set
    if not APPROVER_USER_ID:
        _log("APPROVER_USER_ID not set, blocking")
        sys.exit(2)

    _log(f"credentials OK, building notification for {tool_name}")

    if tool_name == "ExitPlanMode":
        notification_text = build_exit_plan_text()
        _log(f"starting approval flow, daemon_running={is_daemon_running()}")
        run_approval_flow(notification_text)
    else:
        # AskUserQuestion: 通知のみ送信（ブロックしない）
        questions = tool_input.get("questions", [])
        if not questions:
            _log("no questions in AskUserQuestion, skipping")
            sys.exit(0)
        notification_text = build_ask_user_question_text(tool_input)
        _log("AskUserQuestion: sending notification only (no approval)")
        send_slack_simple(notification_text)
        sys.exit(0)


# ---------------------------------------------------------------------------
# CLI mode entry point (notification only, no approval)
# ---------------------------------------------------------------------------


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
        print(
            "Usage: notify-slack.py --message TEXT [--title TITLE]",
            file=sys.stderr,
        )
        sys.exit(1)

    message = message.replace("\\n", "\n")
    title = title.replace("\\n", "\n")
    success = send_slack_simple(message=message, title=title)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # If stdin has data and no CLI args → hook mode
    if len(sys.argv) == 1 and not sys.stdin.isatty():
        handle_hook()
    else:
        handle_cli()
