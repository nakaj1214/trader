#!/usr/bin/env python3
"""
PostToolUse フック: 大量削除（20行以上）を検知してアプローチの見直しを促す。

Edit ツール実行後に edit-history.jsonl の最新エントリを読み取り、
lines_removed が 20 以上の場合にアプローチピボットの可能性を警告する。
box-shadow -> outline -> ::after のような手法切替による無駄な追加・削除を防ぐ。
"""

import json
import os
import sys
from pathlib import Path

# --- 定数 ---
LARGE_DELETE_THRESHOLD = 20

# プロジェクトルートの解決
_SCRIPT_DIR = Path(__file__).resolve().parent
# staging からの実行時と hooks/ からの実行時の両方に対応
_PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
LOG_FILE = str(_PROJECT_ROOT / ".claude" / "logs" / "edit-history.jsonl")


def read_last_entry() -> dict | None:
    """edit-history.jsonl の最終行を読み取る。"""
    try:
        if not os.path.exists(LOG_FILE):
            return None
        with open(LOG_FILE, "rb") as f:
            # ファイル末尾から最終行を効率的に読み取る
            f.seek(0, 2)
            file_size = f.tell()
            if file_size == 0:
                return None

            # 末尾から最大4KBを読み取って最終行を取得
            read_size = min(4096, file_size)
            f.seek(file_size - read_size)
            content = f.read().decode("utf-8", errors="replace")

            lines = content.strip().split("\n")
            if lines:
                return json.loads(lines[-1])
    except Exception:
        pass
    return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name != "Edit":
        sys.exit(0)

    # edit-history.jsonl から最新エントリを取得
    entry = read_last_entry()
    if entry is None:
        sys.exit(0)

    lines_removed = entry.get("lines_removed", 0)
    if lines_removed < LARGE_DELETE_THRESHOLD:
        sys.exit(0)

    file_path = entry.get("file", "unknown")
    lines_added = entry.get("lines_added", 0)

    context = (
        f"[large-delete-guard] {file_path} で {lines_removed} 行が削除されました"
    )

    # 削除のみ（追加なし）と書き直し（削除+追加）で異なるメッセージ
    if lines_added > 0:
        context += f"（{lines_added} 行追加）。\n"
        context += (
            f"  大規模な書き直しはアプローチのピボットを示している可能性があります。\n"
            f"  -> 現在のアプローチが正しいか、一度立ち止まって確認してください。\n"
            f"  -> /verify-before-fix で証拠を収集してから進めることを推奨します。"
        )
    else:
        context += "。\n"
        context += (
            f"  大量のコード削除が検出されました。\n"
            f"  -> 削除されたコードが本当に不要か確認してください。\n"
            f"  -> 方針転換の場合は plan.md を更新してから進めてください。"
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
