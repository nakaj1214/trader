#!/usr/bin/env python3
"""
PostToolUse フック: 大規模な実装後に Codex レビューを提案する。

ファイル変更を追跡し、大量のコードが書かれた際にコードレビューを提案する。
"""

import json
import os
import sys
import tempfile

# 入力バリデーション定数
MAX_PATH_LENGTH = 4096
MAX_CONTENT_LENGTH = 1_000_000


def validate_input(file_path: str, content: str) -> bool:
    """セキュリティのため入力をバリデーションする。"""
    if not file_path or len(file_path) > MAX_PATH_LENGTH:
        return False
    if len(content) > MAX_CONTENT_LENGTH:
        return False
    # Check for path traversal
    if ".." in file_path:
        return False
    return True


# セッション内の変更を追跡する状態ファイル（クロスプラットフォーム一時ディレクトリ）
STATE_FILE = os.path.join(tempfile.gettempdir(), "claude-code-implementation-state.json")

# レビュー提案のしきい値
MIN_FILES_FOR_REVIEW = 3
MIN_LINES_FOR_REVIEW = 100


def load_state() -> dict:
    """セッション状態を読み込む。"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"files_changed": [], "total_lines": 0, "review_suggested": False}


def save_state(state: dict):
    """セッション状態を保存する。"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def count_lines(content: str) -> int:
    """コンテンツ内の意味のある行数をカウントする。"""
    lines = content.split("\n")
    # Count non-empty, non-comment lines
    meaningful = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    return len(meaningful)


def should_suggest_review(state: dict) -> tuple[bool, str]:
    """コードレビューを提案すべきか判定する。"""
    if state.get("review_suggested"):
        return False, ""

    files_count = len(state.get("files_changed", []))
    total_lines = state.get("total_lines", 0)

    if files_count >= MIN_FILES_FOR_REVIEW:
        return True, f"{files_count} files modified"

    if total_lines >= MIN_LINES_FOR_REVIEW:
        return True, f"{total_lines}+ lines written"

    return False, ""


def main():
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")

        # Only process Write/Edit tools
        if tool_name not in ["Write", "Edit"]:
            sys.exit(0)

        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "") or tool_input.get("new_string", "")

        # Validate input
        if not validate_input(file_path, content):
            sys.exit(0)

        # Skip non-source files
        if not any(file_path.endswith(ext) for ext in [".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs"]):
            sys.exit(0)

        # Load and update state
        state = load_state()
        if file_path not in state["files_changed"]:
            state["files_changed"].append(file_path)
        state["total_lines"] += count_lines(content)
        save_state(state)

        # Check if review should be suggested
        should_review, reason = should_suggest_review(state)

        if should_review:
            state["review_suggested"] = True
            save_state(state)

            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"[Code Review Suggestion] {reason} in this session. "
                        "Consider having Codex review the implementation. "
                        "**Recommended**: Use Task tool with subagent_type='general-purpose' "
                        "to consult Codex with git diff and preserve main context."
                    )
                }
            }
            print(json.dumps(output))

        sys.exit(0)

    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
