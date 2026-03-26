#!/usr/bin/env python3
"""
PostToolUse フック: plan.md / proposal.md の頻繁な書き直しを検知して警告する。

docs/implement/plan.md または docs/implement/proposal.md が Write ツールで
3回以上上書きされた場合、計画を安定させてから実装に進むよう警告する。
「研究と実装分離」原則の違反を早期に検知するためのフック。
"""

import json
import os
import sys
import tempfile

# --- 定数 ---
WARN_THRESHOLD = 3
STATE_FILE = os.path.join(tempfile.gettempdir(), "claude-plan-rewrite-counts.json")

# 監視対象ファイル（プロジェクトルートからの相対パス末尾で判定）
WATCHED_SUFFIXES = (
    "docs/implement/plan.md",
    "docs/implement/proposal.md",
)


def load_counts() -> dict:
    """一時ファイルから Write カウントを読み込む。"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_counts(counts: dict) -> None:
    """Write カウントを一時ファイルに保存する。"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(counts, f)
    except Exception:
        pass


def normalize_path(file_path: str) -> str:
    """プロジェクトルートからの相対パスに正規化する。"""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    if file_path.startswith(project_dir):
        return os.path.relpath(file_path, project_dir)
    return file_path


def is_watched_file(rel_path: str) -> bool:
    """監視対象ファイルかどうか判定する。"""
    normalized = rel_path.replace("\\", "/")
    return any(normalized.endswith(suffix) for suffix in WATCHED_SUFFIXES)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name != "Write":
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    rel_path = normalize_path(file_path)

    if not is_watched_file(rel_path):
        sys.exit(0)

    # カウント更新
    counts = load_counts()
    counts[rel_path] = counts.get(rel_path, 0) + 1
    save_counts(counts)

    write_count = counts[rel_path]

    # 閾値到達で警告
    if write_count >= WARN_THRESHOLD:
        basename = os.path.basename(rel_path)
        context = (
            f"[plan-rewrite-alert] {basename} がセッション内で {write_count} 回上書きされました。\n"
            f"  計画が安定していない状態で実装を進めると、手戻りが増加します。\n"
            f"  -> 計画を確定してから実装に進んでください（研究と実装分離の原則）。\n"
            f"  -> proposal/plan の変更履歴を残すため、Write ではなく Edit の使用を検討してください。"
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
