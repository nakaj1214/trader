#!/usr/bin/env python3
"""
Slack Socket Mode デーモン: リアルタイム Bash コマンド承認用。

WebSocket（Socket Mode）で Slack に接続し、各フックからの
Block Kit ボタン操作を処理し、ファイルベース IPC で判定結果を書き込む。

必須環境変数:
  SLACK_APP_TOKEN        - App-Level Token (xapp-...)
  SLACK_BOT_TOKEN        - Bot Token (xoxb-...)
  SLACK_APPROVER_USER_ID - 承認者の Slack ユーザー ID (U0XXXXXXX)

オプション:
  CLAUDE_PROJECT_DIR     - プロジェクトルート（デフォルト: カレントディレクトリ）

セットアップ:
  1. Slack App 設定で Socket Mode を有効にする
  2. connections:write スコープ付きの App-Level Token (xapp-...) を生成する
  3. .claude/.env に SLACK_APP_TOKEN を設定する

使い方:
  python3 .claude/hooks/slack/slack_socket_daemon.py

  # バックグラウンド実行（systemd / launchd / screen 等）:
  nohup python3 .claude/hooks/slack/slack_socket_daemon.py &

終了コード:
  0: 正常終了（SIGTERM / SIGINT）
  1: 必須環境変数の不足または slack_sdk 未インストール
"""

import os
import signal
import sys
import time
from pathlib import Path

try:
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web import WebClient
except ImportError:
    print(
        "[socket_daemon] slack_sdk not installed. Run: pip install slack_sdk",
        file=sys.stderr,
    )
    sys.exit(1)

# --- Load env with settings.json fallback ---
_HOOKS_DIR = Path(__file__).resolve().parent.parent  # .claude/hooks/
sys.path.insert(0, str(_HOOKS_DIR))
from lib.env import get as _env

# --- Environment variables ---
APP_TOKEN = _env("SLACK_APP_TOKEN")
BOT_TOKEN = _env("SLACK_BOT_TOKEN")
APPROVER_USER_ID = _env("SLACK_APPROVER_USER_ID")

# --- File paths ---
PROJECT_DIR = _env("CLAUDE_PROJECT_DIR")
_BASE = Path(PROJECT_DIR) if PROJECT_DIR else _HOOKS_DIR.parent.parent
IPC_DIR = _BASE / ".claude/hooks/ipc"
DAEMON_PID_FILE = IPC_DIR / "daemon.pid"


def handle_decision(message_ts: str, decision: str) -> None:
    """Write decision to IPC file if a matching pending request exists.

    slack_approval.py creates a .pending file when waiting for approval.
    This daemon writes the .decision file in response to a button click.
    """
    pending_file = IPC_DIR / f"{message_ts}.pending"
    decision_file = IPC_DIR / f"{message_ts}.decision"

    if pending_file.exists():
        decision_file.write_text(decision)
        print(
            f"[socket_daemon] Decision '{decision}' written for ts={message_ts}",
            flush=True,
        )
    else:
        print(
            f"[socket_daemon] No pending request for ts={message_ts}, ignoring.",
            flush=True,
        )


def process_interactive(client: SocketModeClient, req: SocketModeRequest) -> None:
    """Handle Block Kit button interactions from approval messages."""
    # Acknowledge immediately (Slack requires response within 3 seconds)
    client.send_socket_mode_response(
        SocketModeResponse(envelope_id=req.envelope_id)
    )

    payload = req.payload
    user_id = payload.get("user", {}).get("id", "")

    if user_id != APPROVER_USER_ID:
        print(
            f"[socket_daemon] Ignoring action from non-approver: {user_id}",
            flush=True,
        )
        return

    # container.message_ts is the original message timestamp
    message_ts = payload.get("container", {}).get("message_ts", "")
    if not message_ts:
        message_ts = payload.get("message", {}).get("ts", "")

    actions = payload.get("actions", [])
    for action in actions:
        action_id = action.get("action_id", "")
        if action_id == "approve":
            handle_decision(message_ts, "allow")
        elif action_id == "deny":
            handle_decision(message_ts, "deny")


def make_event_handler(client: SocketModeClient):
    """Return a socket_mode_request_listener that dispatches events."""

    def handler(cli: SocketModeClient, req: SocketModeRequest) -> None:
        if req.type == "interactive":
            process_interactive(cli, req)
        else:
            # Acknowledge all other events to prevent Slack retries
            cli.send_socket_mode_response(
                SocketModeResponse(envelope_id=req.envelope_id)
            )

    return handler


def main() -> None:
    """Start the Socket Mode daemon."""
    if not APP_TOKEN:
        print(
            "[socket_daemon] SLACK_APP_TOKEN not set (requires xapp-... token). Exiting.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not BOT_TOKEN:
        print("[socket_daemon] SLACK_BOT_TOKEN not set. Exiting.", file=sys.stderr)
        sys.exit(1)

    if not APPROVER_USER_ID:
        print(
            "[socket_daemon] SLACK_APPROVER_USER_ID not set. Exiting.", file=sys.stderr
        )
        sys.exit(1)

    IPC_DIR.mkdir(parents=True, exist_ok=True)
    DAEMON_PID_FILE.write_text(str(os.getpid()))

    def cleanup(signum=None, frame=None) -> None:
        DAEMON_PID_FILE.unlink(missing_ok=True)
        print("[socket_daemon] Stopped.", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    web_client = WebClient(token=BOT_TOKEN)
    socket_client = SocketModeClient(app_token=APP_TOKEN, web_client=web_client)
    socket_client.socket_mode_request_listeners.append(
        make_event_handler(socket_client)
    )

    socket_client.connect()
    print(
        f"[socket_daemon] Connected to Slack Socket Mode. PID={os.getpid()}",
        flush=True,
    )

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        cleanup()


if __name__ == "__main__":
    main()
