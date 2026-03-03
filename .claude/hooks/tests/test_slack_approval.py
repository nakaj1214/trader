#!/usr/bin/env python3
"""
Tests for slack_approval.py

Run:
  python3 -m pytest .claude/hooks/tests/test_slack_approval.py -v
"""

import contextlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import importlib.util

# Add hooks directory to path
HOOKS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOKS_DIR))
import slack_approval

# notify-slack.py has a hyphen, so use importlib
_spec = importlib.util.spec_from_file_location(
    "notify_slack", HOOKS_DIR / "notify-slack.py"
)
notify_slack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notify_slack)
sys.modules["notify_slack"] = notify_slack  # required for patch("notify_slack.xxx")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PATTERNS_PATH = Path(__file__).parent.parent / "approval_skip_patterns.txt"


def make_hook_input(command: str, tool_name: str = "Bash") -> str:
    return json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})


def run_main(stdin_text: str, env: dict) -> int:
    """Run slack_approval.main() with patched stdin/env; return exit code."""
    with patch("slack_approval.BOT_TOKEN", env.get("SLACK_BOT_TOKEN", "")), \
         patch("slack_approval.CHANNEL_ID", env.get("SLACK_CHANNEL_ID", "")), \
         patch("slack_approval.APPROVER_USER_ID", env.get("SLACK_APPROVER_USER_ID", "")), \
         patch("slack_approval.PATTERNS_PATH", PATTERNS_PATH), \
         patch("slack_approval.write_audit_log"), \
         patch("sys.stdin", StringIO(stdin_text)):
        try:
            slack_approval.main()
        except SystemExit as e:
            return int(e.code)
    return 0


DEFAULT_ENV = {
    "SLACK_BOT_TOKEN": "xoxb-test-token",
    "SLACK_CHANNEL_ID": "C0TEST",
    "SLACK_APPROVER_USER_ID": "U0APPROVER",
}


def make_post_message_response(ts: str = "1000.0") -> dict:
    return {"ok": True, "ts": ts, "channel": "C0TEST"}


def make_reactions_response(reactions: list) -> dict:
    """Simulate reactions.get API response."""
    return {"ok": True, "message": {"reactions": reactions}}


def make_reaction(name: str, users: list) -> dict:
    return {"name": name, "users": users, "count": len(users)}


def make_replies_response(reply_texts: list = None, user: str = "U0APPROVER") -> dict:
    """Simulate conversations.replies API response.

    reply_texts: list of reply text strings (from approver). None = no replies.
    """
    parent = {"type": "message", "user": "U0BOT", "text": "approval request", "ts": "1000.0"}
    replies = [
        {"type": "message", "user": user, "text": t}
        for t in (reply_texts or [])
    ]
    return {"ok": True, "messages": [parent] + replies}


# ---------------------------------------------------------------------------
# Tests: classify_command
# ---------------------------------------------------------------------------

class TestClassifyCommand(unittest.TestCase):
    """Unit tests for classify_command (no Slack calls)."""

    def setUp(self):
        self.patterns = slack_approval.load_patterns()

    def test_skip_ls(self):
        self.assertEqual(slack_approval.classify_command("ls -la", self.patterns), "skip")

    def test_skip_git_log(self):
        self.assertEqual(slack_approval.classify_command("git log --oneline", self.patterns), "skip")

    def test_require_rm_rf(self):
        self.assertEqual(slack_approval.classify_command("rm -rf /tmp/test", self.patterns), "require")

    def test_require_git_push(self):
        self.assertEqual(slack_approval.classify_command("git push origin main", self.patterns), "require")

    def test_compound_require_wins(self):
        self.assertEqual(
            slack_approval.classify_command("ls && rm -rf /tmp/x", self.patterns), "require"
        )

    def test_compound_all_skip(self):
        self.assertEqual(
            slack_approval.classify_command("ls | head", self.patterns), "skip"
        )

    def test_redirect_forces_require(self):
        self.assertEqual(
            slack_approval.classify_command("echo hi > /tmp/x", self.patterns), "require"
        )

    def test_subshell_forces_require(self):
        self.assertEqual(
            slack_approval.classify_command("ls $(rm -rf /tmp/x)", self.patterns), "require"
        )

    def test_unknown_command_defaults_to_require(self):
        self.assertEqual(
            slack_approval.classify_command("php artisan test", self.patterns), "require"
        )


# ---------------------------------------------------------------------------
# Tests: poll_for_decision (unit)
# ---------------------------------------------------------------------------

class TestPollForDecision(unittest.TestCase):
    """Unit tests for poll_for_decision (reactions + thread replies)."""

    def _run_poll(
        self,
        reactions_seq: list,
        replies_seq: list = None,
    ) -> tuple:
        """Run poll_for_decision() with separate response sequences per API method."""
        reactions_iter = iter(reactions_seq)
        replies_iter = iter(replies_seq or [make_replies_response()] * len(reactions_seq))

        def side_effect(method, payload):
            if method == "reactions.get":
                return next(reactions_iter, None)
            elif method == "conversations.replies":
                return next(replies_iter, None)
            return None

        with patch("slack_approval.slack_api_request", side_effect=side_effect), \
             patch("slack_approval.time.sleep"), \
             patch("slack_approval.APPROVER_USER_ID", "U0APPROVER"), \
             patch("slack_approval.CHANNEL_ID", "C0TEST"), \
             patch("slack_approval.POLL_MAX_COUNT", len(reactions_seq)):
            return slack_approval.poll_for_decision("1000.0")

    # --- Reaction tests ---

    def test_allow_reaction_returns_allow(self):
        decision, user, _ = self._run_poll([
            make_reactions_response([make_reaction("white_check_mark", ["U0APPROVER"])]),
        ])
        self.assertEqual(decision, "allow")
        self.assertEqual(user, "U0APPROVER")

    def test_deny_reaction_returns_deny(self):
        decision, user, _ = self._run_poll([
            make_reactions_response([make_reaction("x", ["U0APPROVER"])]),
        ])
        self.assertEqual(decision, "deny")
        self.assertEqual(user, "U0APPROVER")

    def test_other_user_reaction_ignored(self):
        # Reaction from a different user → no match from replies either → timeout
        decision, user, _ = self._run_poll(
            [make_reactions_response([make_reaction("white_check_mark", ["U0SOMEONE_ELSE"])])],
            [make_replies_response()],
        )
        self.assertEqual(decision, "timeout")
        self.assertIsNone(user)

    def test_unrelated_reaction_ignored(self):
        decision, _, _ = self._run_poll(
            [make_reactions_response([make_reaction("thumbsup", ["U0APPROVER"])])],
            [make_replies_response()],
        )
        self.assertEqual(decision, "timeout")

    def test_deny_wins_over_allow_when_deny_first(self):
        # Both reactions present; deny listed first → deny
        decision, _, _ = self._run_poll([
            make_reactions_response([
                make_reaction("x", ["U0APPROVER"]),
                make_reaction("white_check_mark", ["U0APPROVER"]),
            ]),
        ])
        self.assertEqual(decision, "deny")

    # --- Thread reply tests ---

    def test_allow_reply_returns_allow(self):
        decision, user, _ = self._run_poll(
            [make_reactions_response([])],       # no reaction
            [make_replies_response(["allow"])],  # reply: "allow"
        )
        self.assertEqual(decision, "allow")
        self.assertEqual(user, "U0APPROVER")

    def test_deny_reply_returns_deny(self):
        decision, user, _ = self._run_poll(
            [make_reactions_response([])],
            [make_replies_response(["deny"])],
        )
        self.assertEqual(decision, "deny")

    def test_japanese_allow_reply(self):
        decision, _, _ = self._run_poll(
            [make_reactions_response([])],
            [make_replies_response(["承認"])],
        )
        self.assertEqual(decision, "allow")

    def test_japanese_deny_reply(self):
        decision, _, _ = self._run_poll(
            [make_reactions_response([])],
            [make_replies_response(["拒否"])],
        )
        self.assertEqual(decision, "deny")

    def test_reply_from_other_user_ignored(self):
        decision, _, _ = self._run_poll(
            [make_reactions_response([])],
            [make_replies_response(["allow"], user="U0SOMEONE_ELSE")],
        )
        self.assertEqual(decision, "timeout")

    def test_no_reaction_no_reply_times_out(self):
        decision, user, _ = self._run_poll(
            [make_reactions_response([])],
            [make_replies_response()],
        )
        self.assertEqual(decision, "timeout")
        self.assertIsNone(user)

    def test_reaction_api_error_falls_through_to_reply(self):
        # reactions.get fails (None) → check replies → allow
        decision, _, _ = self._run_poll(
            [None],
            [make_replies_response(["allow"])],
        )
        self.assertEqual(decision, "allow")


# ---------------------------------------------------------------------------
# Tests: main() integration
# ---------------------------------------------------------------------------

class TestSlackApprovalIntegration(unittest.TestCase):
    """Integration tests for main() with mocked Slack API."""

    def _patch_main(self, mock_api_responses: list, command: str, extra_patches: dict = None):
        """Helper to run main() with reaction-based mock responses."""
        patch_specs = [
            ("slack_approval.slack_api_request", None),
            ("slack_approval.time.sleep", MagicMock()),
            ("slack_approval.time.time", MagicMock(return_value=1000.0)),
            ("slack_approval.write_audit_log", MagicMock()),
            ("slack_approval.PATTERNS_PATH", PATTERNS_PATH),
            ("slack_approval.BOT_TOKEN", DEFAULT_ENV["SLACK_BOT_TOKEN"]),
            ("slack_approval.CHANNEL_ID", DEFAULT_ENV["SLACK_CHANNEL_ID"]),
            ("slack_approval.APPROVER_USER_ID", DEFAULT_ENV["SLACK_APPROVER_USER_ID"]),
            ("sys.stdin", StringIO(make_hook_input(command))),
        ]
        if extra_patches:
            patch_specs.extend(extra_patches.items())

        with contextlib.ExitStack() as stack:
            mocks = {}
            for target, value in patch_specs:
                if value is None:
                    mocks[target] = stack.enter_context(patch(target))
                else:
                    stack.enter_context(patch(target, value))
            mock_api = mocks["slack_approval.slack_api_request"]
            mock_api.side_effect = mock_api_responses
            with self.assertRaises(SystemExit) as ctx:
                slack_approval.main()
        return ctx.exception.code

    # --- Skip cases ---

    def test_skip_read_only_ls(self):
        code = run_main(make_hook_input("ls -la"), DEFAULT_ENV)
        self.assertEqual(code, 0)

    def test_skip_git_log(self):
        code = run_main(make_hook_input("git log --oneline"), DEFAULT_ENV)
        self.assertEqual(code, 0)

    # --- Token/Channel not set: hook disabled ---

    def test_token_not_set_exits_0(self):
        env = {**DEFAULT_ENV, "SLACK_BOT_TOKEN": ""}
        code = run_main(make_hook_input("php artisan test"), env)
        self.assertEqual(code, 0)

    def test_channel_not_set_exits_0(self):
        env = {**DEFAULT_ENV, "SLACK_CHANNEL_ID": ""}
        code = run_main(make_hook_input("php artisan test"), env)
        self.assertEqual(code, 0)

    # --- Approver not set: fail-closed ---

    def test_approver_not_set_exits_2(self):
        env = {**DEFAULT_ENV, "SLACK_APPROVER_USER_ID": ""}
        code = run_main(make_hook_input("php artisan test"), env)
        self.assertEqual(code, 2)

    # --- Allow via reaction ---

    def test_allow_reaction_exits_0(self):
        post_response = make_post_message_response(ts="1000.0")
        allow_response = make_reactions_response([
            make_reaction("white_check_mark", ["U0APPROVER"]),
        ])
        code = self._patch_main(
            [post_response, allow_response, post_response],  # post + poll + thread notification
            "php artisan test",
        )
        self.assertEqual(code, 0)

    # --- Deny via reaction ---

    def test_deny_reaction_exits_2(self):
        post_response = make_post_message_response(ts="1000.0")
        deny_response = make_reactions_response([
            make_reaction("x", ["U0APPROVER"]),
        ])
        code = self._patch_main(
            [post_response, deny_response, post_response],
            "php artisan test",
        )
        self.assertEqual(code, 2)

    # --- Timeout ---

    def test_timeout_exits_2(self):
        post_response = make_post_message_response(ts="1000.0")
        # poll: reactions.get (empty) + conversations.replies (no replies) + thread notification
        with patch("slack_approval.slack_api_request") as mock_api, \
             patch("slack_approval.time.sleep"), \
             patch("slack_approval.time.time", return_value=1000.0), \
             patch("slack_approval.write_audit_log"), \
             patch("slack_approval.PATTERNS_PATH", PATTERNS_PATH), \
             patch("slack_approval.BOT_TOKEN", DEFAULT_ENV["SLACK_BOT_TOKEN"]), \
             patch("slack_approval.CHANNEL_ID", DEFAULT_ENV["SLACK_CHANNEL_ID"]), \
             patch("slack_approval.APPROVER_USER_ID", DEFAULT_ENV["SLACK_APPROVER_USER_ID"]), \
             patch("slack_approval.POLL_MAX_COUNT", 1), \
             patch("sys.stdin", StringIO(make_hook_input("php artisan test"))):

            mock_api.side_effect = [
                post_response,           # chat.postMessage
                make_reactions_response([]),   # reactions.get → empty
                make_replies_response(),       # conversations.replies → no replies
                post_response,           # thread notification
            ]
            with self.assertRaises(SystemExit) as ctx:
                slack_approval.main()
            self.assertEqual(ctx.exception.code, 2)

    # --- API error: fail-closed ---

    def test_api_error_exits_2(self):
        with patch("slack_approval.slack_api_request", return_value=None), \
             patch("slack_approval.write_audit_log"), \
             patch("slack_approval.PATTERNS_PATH", PATTERNS_PATH), \
             patch("slack_approval.BOT_TOKEN", DEFAULT_ENV["SLACK_BOT_TOKEN"]), \
             patch("slack_approval.CHANNEL_ID", DEFAULT_ENV["SLACK_CHANNEL_ID"]), \
             patch("slack_approval.APPROVER_USER_ID", DEFAULT_ENV["SLACK_APPROVER_USER_ID"]), \
             patch("sys.stdin", StringIO(make_hook_input("git push origin main"))):

            with self.assertRaises(SystemExit) as ctx:
                slack_approval.main()
            self.assertEqual(ctx.exception.code, 2)

    # --- Reaction from other user is ignored ---

    def test_other_user_reaction_ignored_then_timeout(self):
        post_response = make_post_message_response(ts="1000.0")
        with patch("slack_approval.slack_api_request") as mock_api, \
             patch("slack_approval.time.sleep"), \
             patch("slack_approval.time.time", return_value=1000.0), \
             patch("slack_approval.write_audit_log"), \
             patch("slack_approval.PATTERNS_PATH", PATTERNS_PATH), \
             patch("slack_approval.BOT_TOKEN", DEFAULT_ENV["SLACK_BOT_TOKEN"]), \
             patch("slack_approval.CHANNEL_ID", DEFAULT_ENV["SLACK_CHANNEL_ID"]), \
             patch("slack_approval.APPROVER_USER_ID", DEFAULT_ENV["SLACK_APPROVER_USER_ID"]), \
             patch("slack_approval.POLL_MAX_COUNT", 1), \
             patch("sys.stdin", StringIO(make_hook_input("php artisan test"))):

            mock_api.side_effect = [
                post_response,  # chat.postMessage
                make_reactions_response([make_reaction("white_check_mark", ["U0SOMEONE_ELSE"])]),
                make_replies_response(),  # no reply from approver
                post_response,  # thread notification
            ]
            with self.assertRaises(SystemExit) as ctx:
                slack_approval.main()
            self.assertEqual(ctx.exception.code, 2)

    # --- Redirect and subshell require approval ---

    def test_redirect_requires_approval_and_allow(self):
        post_response = make_post_message_response(ts="1000.0")
        allow_response = make_reactions_response([
            make_reaction("white_check_mark", ["U0APPROVER"]),
        ])
        code = self._patch_main(
            [post_response, allow_response, post_response],
            "echo hi > /tmp/x",
        )
        self.assertEqual(code, 0)

    def test_subshell_requires_approval_and_deny(self):
        post_response = make_post_message_response(ts="1000.0")
        deny_response = make_reactions_response([
            make_reaction("x", ["U0APPROVER"]),
        ])
        code = self._patch_main(
            [post_response, deny_response, post_response],
            "ls $(rm -rf /tmp/x)",
        )
        self.assertEqual(code, 2)


# ---------------------------------------------------------------------------
# Tests: notify-slack.py (AskUserQuestion with choices)
# ---------------------------------------------------------------------------


class TestNotifySlackHook(unittest.TestCase):
    """Tests for notify-slack.py handle_hook with AskUserQuestion."""

    def _run_hook(self, tool_input: dict) -> bool:
        """Run handle_hook() and return whether send_slack was called."""
        hook_data = json.dumps({
            "tool_name": "AskUserQuestion",
            "tool_input": tool_input,
        })
        with patch("notify_slack.send_slack") as mock_send, \
             patch("sys.stdin", StringIO(hook_data)):
            try:
                notify_slack.handle_hook()
            except SystemExit:
                pass
            return mock_send.called, mock_send.call_args

    def test_single_question_no_options(self):
        """Simple question without options."""
        called, call_args = self._run_hook({
            "questions": [{"question": "続行しますか？", "header": "確認", "options": []}]
        })
        self.assertTrue(called)
        message = call_args.kwargs.get("message", call_args[1].get("message", ""))
        self.assertIn("続行しますか？", message)

    def test_question_with_options_shows_choices(self):
        """Question with options should include choices in the message."""
        called, call_args = self._run_hook({
            "questions": [{
                "question": "どちらを使用しますか？",
                "header": "選択",
                "options": [
                    {"label": "Option A", "description": "最初の選択肢"},
                    {"label": "Option B", "description": "2番目の選択肢"},
                ]
            }]
        })
        self.assertTrue(called)
        message = call_args.kwargs.get("message", call_args[1].get("message", ""))
        self.assertIn("どちらを使用しますか？", message)
        self.assertIn("Option A", message)
        self.assertIn("Option B", message)

    def test_multiple_questions_all_shown(self):
        """Multiple questions should all appear in the message."""
        called, call_args = self._run_hook({
            "questions": [
                {"question": "質問1", "header": "Q1", "options": []},
                {"question": "質問2", "header": "Q2", "options": [
                    {"label": "はい", "description": ""},
                    {"label": "いいえ", "description": ""},
                ]},
            ]
        })
        self.assertTrue(called)
        message = call_args.kwargs.get("message", call_args[1].get("message", ""))
        self.assertIn("質問1", message)
        self.assertIn("質問2", message)
        self.assertIn("はい", message)
        self.assertIn("いいえ", message)

    def test_empty_questions_skips_send(self):
        """No questions → send_slack should not be called."""
        called, _ = self._run_hook({"questions": []})
        self.assertFalse(called)

    def test_non_askuserquestion_tool_skips(self):
        """Non-AskUserQuestion tool → send_slack should not be called."""
        hook_data = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        })
        with patch("notify_slack.send_slack") as mock_send, \
             patch("sys.stdin", StringIO(hook_data)):
            try:
                notify_slack.handle_hook()
            except SystemExit:
                pass
            self.assertFalse(mock_send.called)

    def test_other_option_auto_appended(self):
        """When options exist but none is 'Other', it should be appended."""
        called, call_args = self._run_hook({
            "questions": [{
                "question": "どちらにしますか？",
                "header": "選択",
                "options": [
                    {"label": "Option A", "description": "説明A"},
                    {"label": "Option B", "description": "説明B"},
                ]
            }]
        })
        self.assertTrue(called)
        message = call_args.kwargs.get("message", call_args[1].get("message", ""))
        self.assertIn("Other", message)

    def test_other_option_not_duplicated(self):
        """When 'Other' already exists in options, it should not be added again."""
        called, call_args = self._run_hook({
            "questions": [{
                "question": "選んでください",
                "header": "選択",
                "options": [
                    {"label": "Option A", "description": "説明A"},
                    {"label": "Other", "description": "自由記入"},
                ]
            }]
        })
        self.assertTrue(called)
        message = call_args.kwargs.get("message", call_args[1].get("message", ""))
        # "Other" should appear exactly once
        self.assertEqual(message.count("Other"), 1)

    def test_no_options_no_other_appended(self):
        """When question has no options, 'Other' should not be appended."""
        called, call_args = self._run_hook({
            "questions": [{"question": "続行しますか？", "header": "確認", "options": []}]
        })
        self.assertTrue(called)
        message = call_args.kwargs.get("message", call_args[1].get("message", ""))
        self.assertNotIn("Other", message)


# ---------------------------------------------------------------------------
# Tests: IPC mode (Socket Mode daemon integration)
# ---------------------------------------------------------------------------


class TestIPCMode(unittest.TestCase):
    """Tests for Socket Mode IPC path in slack_approval.py."""

    # --- is_daemon_running ---

    def test_no_pid_file_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_path = Path(tmpdir) / "daemon.pid"
            with patch.object(slack_approval, "DAEMON_PID_FILE", pid_path):
                self.assertFalse(slack_approval.is_daemon_running())

    def test_stale_pid_returns_false(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pid", delete=False) as f:
            f.write("999999999")  # almost certainly no such PID
            pid_path = Path(f.name)
        try:
            with patch.object(slack_approval, "DAEMON_PID_FILE", pid_path):
                self.assertFalse(slack_approval.is_daemon_running())
        finally:
            pid_path.unlink(missing_ok=True)

    def test_own_pid_returns_true(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pid", delete=False) as f:
            f.write(str(os.getpid()))
            pid_path = Path(f.name)
        try:
            with patch.object(slack_approval, "DAEMON_PID_FILE", pid_path):
                self.assertTrue(slack_approval.is_daemon_running())
        finally:
            pid_path.unlink(missing_ok=True)

    def test_invalid_pid_content_returns_false(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pid", delete=False) as f:
            f.write("not-a-number")
            pid_path = Path(f.name)
        try:
            with patch.object(slack_approval, "DAEMON_PID_FILE", pid_path):
                self.assertFalse(slack_approval.is_daemon_running())
        finally:
            pid_path.unlink(missing_ok=True)

    # --- wait_for_ipc_decision ---

    def test_ipc_allow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ipc_dir = Path(tmpdir)
            ts = "1000.0"
            decision_file = ipc_dir / f"{ts}.decision"

            def _write():
                time.sleep(0.05)
                decision_file.write_text("allow")

            t = threading.Thread(target=_write)
            t.start()
            with patch.object(slack_approval, "IPC_DIR", ipc_dir), \
                 patch.object(slack_approval, "IPC_TIMEOUT_SECONDS", 5):
                decision, user, msg_ts = slack_approval.wait_for_ipc_decision(ts)
            t.join()

        self.assertEqual(decision, "allow")
        self.assertEqual(user, "daemon")
        self.assertEqual(msg_ts, ts)

    def test_ipc_deny(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ipc_dir = Path(tmpdir)
            ts = "2000.0"
            decision_file = ipc_dir / f"{ts}.decision"

            def _write():
                time.sleep(0.05)
                decision_file.write_text("deny")

            t = threading.Thread(target=_write)
            t.start()
            with patch.object(slack_approval, "IPC_DIR", ipc_dir), \
                 patch.object(slack_approval, "IPC_TIMEOUT_SECONDS", 5):
                decision, user, _ = slack_approval.wait_for_ipc_decision(ts)
            t.join()

        self.assertEqual(decision, "deny")
        self.assertEqual(user, "daemon")

    def test_ipc_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ipc_dir = Path(tmpdir)
            with patch.object(slack_approval, "IPC_DIR", ipc_dir), \
                 patch.object(slack_approval, "IPC_TIMEOUT_SECONDS", 0.1):
                decision, user, _ = slack_approval.wait_for_ipc_decision("3000.0")
        self.assertEqual(decision, "timeout")
        self.assertIsNone(user)

    def test_ipc_cleans_up_pending_file_on_allow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ipc_dir = Path(tmpdir)
            ts = "4000.0"
            (ipc_dir / f"{ts}.decision").write_text("allow")
            with patch.object(slack_approval, "IPC_DIR", ipc_dir), \
                 patch.object(slack_approval, "IPC_TIMEOUT_SECONDS", 5):
                slack_approval.wait_for_ipc_decision(ts)
            self.assertFalse((ipc_dir / f"{ts}.pending").exists())
            self.assertFalse((ipc_dir / f"{ts}.decision").exists())

    def test_ipc_cleans_up_on_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ipc_dir = Path(tmpdir)
            ts = "5000.0"
            with patch.object(slack_approval, "IPC_DIR", ipc_dir), \
                 patch.object(slack_approval, "IPC_TIMEOUT_SECONDS", 0.05):
                slack_approval.wait_for_ipc_decision(ts)
            self.assertFalse((ipc_dir / f"{ts}.pending").exists())

    # --- main() with daemon running: uses Block Kit ---

    def test_main_uses_blocks_when_daemon_running(self):
        """When daemon is running, main() calls send_approval_request_blocks()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ipc_dir = Path(tmpdir)
            pid_path = ipc_dir / "daemon.pid"
            pid_path.write_text(str(os.getpid()))

            post_response = make_post_message_response(ts="9000.0")

            def _write_allow():
                time.sleep(0.1)
                (ipc_dir / "9000.0.decision").write_text("allow")

            t = threading.Thread(target=_write_allow)
            t.start()

            with patch("slack_approval.slack_api_request", return_value=post_response) as mock_api, \
                 patch("slack_approval.write_audit_log"), \
                 patch("slack_approval.PATTERNS_PATH", PATTERNS_PATH), \
                 patch("slack_approval.BOT_TOKEN", DEFAULT_ENV["SLACK_BOT_TOKEN"]), \
                 patch("slack_approval.CHANNEL_ID", DEFAULT_ENV["SLACK_CHANNEL_ID"]), \
                 patch("slack_approval.APPROVER_USER_ID", DEFAULT_ENV["SLACK_APPROVER_USER_ID"]), \
                 patch("slack_approval.IPC_DIR", ipc_dir), \
                 patch("slack_approval.DAEMON_PID_FILE", pid_path), \
                 patch("slack_approval.IPC_TIMEOUT_SECONDS", 5), \
                 patch("sys.stdin", StringIO(make_hook_input("php artisan test"))):

                with self.assertRaises(SystemExit) as ctx:
                    slack_approval.main()
                t.join()

            self.assertEqual(ctx.exception.code, 0)
            # First API call must include Block Kit blocks
            first_call_payload = mock_api.call_args_list[0][0][1]
            self.assertIn("blocks", first_call_payload)

    def test_main_uses_polling_when_daemon_not_running(self):
        """When daemon is not running, main() falls back to reaction/reply polling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_path = Path(tmpdir) / "daemon.pid"
            # No PID file → daemon not running

            post_response = make_post_message_response(ts="1000.0")
            allow_reactions = make_reactions_response(
                [make_reaction("white_check_mark", ["U0APPROVER"])]
            )
            with patch("slack_approval.slack_api_request") as mock_api, \
                 patch("slack_approval.time.sleep"), \
                 patch("slack_approval.write_audit_log"), \
                 patch("slack_approval.PATTERNS_PATH", PATTERNS_PATH), \
                 patch("slack_approval.BOT_TOKEN", DEFAULT_ENV["SLACK_BOT_TOKEN"]), \
                 patch("slack_approval.CHANNEL_ID", DEFAULT_ENV["SLACK_CHANNEL_ID"]), \
                 patch("slack_approval.APPROVER_USER_ID", DEFAULT_ENV["SLACK_APPROVER_USER_ID"]), \
                 patch("slack_approval.DAEMON_PID_FILE", pid_path), \
                 patch("sys.stdin", StringIO(make_hook_input("php artisan test"))):

                mock_api.side_effect = [
                    post_response,    # chat.postMessage
                    allow_reactions,  # reactions.get → allow
                    post_response,    # thread notification
                ]
                with self.assertRaises(SystemExit) as ctx:
                    slack_approval.main()

            self.assertEqual(ctx.exception.code, 0)
            # First API call must NOT include blocks (plain text polling mode)
            first_call_payload = mock_api.call_args_list[0][0][1]
            self.assertNotIn("blocks", first_call_payload)


if __name__ == "__main__":
    unittest.main()
