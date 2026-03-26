#!/usr/bin/env python3
"""
PostToolUse フック: 同一ファイルが3回以上編集されたら警告する。

同じセッション内で同一ファイルへの Edit/Write が3回に達した場合、
/verify-before-fix の使用を推奨する additionalContext を出力する。
edit-tracker.py の JSONL ログではなく、軽量な一時ファイルで追跡する。
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# --- 定数 ---
WARN_THRESHOLD = 3
STATE_FILE = os.path.join(tempfile.gettempdir(), "claude-same-file-edit-counts.json")


def load_counts() -> dict:
    """一時ファイルから編集カウントを読み込む。"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_counts(counts: dict) -> None:
    """編集カウントを一時ファイルに保存する。"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(counts, f)
    except Exception:
        pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # プロジェクトルートからの相対パスに正規化
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    if file_path.startswith(project_dir):
        rel_path = os.path.relpath(file_path, project_dir)
    else:
        rel_path = file_path

    # カウント更新
    counts = load_counts()
    counts[rel_path] = counts.get(rel_path, 0) + 1
    save_counts(counts)

    edit_count = counts[rel_path]

    # 3回目の編集で警告（4回目以降は毎回）
    if edit_count >= WARN_THRESHOLD:
        context = (
            f"[same-file-edit-warn] ⚠ {rel_path} がセッション内で {edit_count} 回編集されました。\n"
            f"  同じファイルを繰り返し修正しているなら、推測ベースの修正に陥っている可能性があります。\n"
            f"  → /verify-before-fix で証拠を収集してから修正してください。"
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": context,
            }
        }
        print(json.dumps(output, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    main()
