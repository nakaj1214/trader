#!/usr/bin/env python3
"""
fix-escalation-detector.py

Hook: Notification > user-prompt-submit
Detects failure patterns in user messages and injects fix-attempts context.
"""

import json
import os
import re
import sys

# Failure patterns to detect in user messages
FAILURE_PATTERNS = [
    r"改善されていない",
    r"直っていない",
    r"まだ動かない",
    r"前回と同じ",
    r"\d+回目",
    r"何度",
    r"また同じ",
    r"効かない",
    r"変わらない",
    r"治らない",
    r"直らない",
]

FIX_ATTEMPTS_PATH = "tasks/fix-attempts.md"


def detect_failure_pattern(message: str) -> bool:
    """Check if message contains failure patterns."""
    for pattern in FAILURE_PATTERNS:
        if re.search(pattern, message):
            return True
    return False


def count_attempts(content: str) -> int:
    """Count the number of Attempt sections in fix-attempts.md."""
    return len(re.findall(r"^### Attempt \d+", content, re.MULTILINE))


def get_latest_issue_attempts(content: str) -> int:
    """Get attempt count for the most recent (last) issue section."""
    # Split by Issue sections
    issues = re.split(r"^## Issue:", content, flags=re.MULTILINE)
    if len(issues) <= 1:
        return 0
    # Count attempts in the last issue
    last_issue = issues[-1]
    return len(re.findall(r"^### Attempt \d+", last_issue, re.MULTILINE))


def main() -> None:
    # Read user message from stdin (hook input)
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return

    # Extract user message
    message = hook_input.get("message", "")
    if not message:
        return

    # Check for failure patterns
    if not detect_failure_pattern(message):
        return

    # Check if fix-attempts.md exists
    if not os.path.exists(FIX_ATTEMPTS_PATH):
        # No history yet - just notify
        result = {
            "message": (
                "[fix-escalation] 失敗パターンを検知しました。"
                "fix-escalation スキルの手順に従い、"
                "tasks/fix-attempts.md に試行を記録してください。"
            )
        }
        print(json.dumps(result))
        return

    # Read fix-attempts.md
    with open(FIX_ATTEMPTS_PATH, encoding="utf-8") as f:
        content = f.read()

    attempt_count = get_latest_issue_attempts(content)

    if attempt_count >= 2:
        result = {
            "message": (
                f"[fix-escalation] この問題は{attempt_count}回失敗しています。"
                "fix-escalation スキルのエスカレーション手順（Step 3）を"
                "必ず実行してください。過去と同じアプローチでの修正は禁止です。"
                f"\n\n参照: {FIX_ATTEMPTS_PATH}"
            )
        }
    elif attempt_count == 1:
        result = {
            "message": (
                "[fix-escalation] 前回の修正が失敗しています。"
                f"{FIX_ATTEMPTS_PATH} に記録があります。"
                "次の試行で失敗した場合、エスカレーション調査が発動します。"
            )
        }
    else:
        result = {
            "message": (
                "[fix-escalation] 失敗パターンを検知しました。"
                "fix-escalation スキルの手順に従い、"
                "tasks/fix-attempts.md に試行を記録してください。"
            )
        }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
