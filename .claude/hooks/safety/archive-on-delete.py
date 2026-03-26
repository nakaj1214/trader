#!/usr/bin/env python3
"""
PreToolUse フック: Bash ツールで rm コマンド実行前にファイルを archive/ にバックアップする。

削除対象ファイルを archive/ フォルダにコピーしてから削除を許可する。
テスト用一時ファイル（__pycache__, .pytest_cache, /tmp/ 等）はスキップする。
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# archive/ をスキップするパターン
SKIP_PATTERNS = [
    r"__pycache__",
    r"\.pytest_cache",
    r"\.pyc$",
    r"node_modules",
    r"/tmp/",
    r"\\tmp\\",
    r"\.tmp$",
    r"/dist/",
    r"/build/",
    r"\.git/",
]


def should_skip(file_path: str) -> bool:
    """アーカイブをスキップすべきファイルかどうか判定する。"""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def extract_rm_targets(command: str) -> list[str]:
    """rm コマンドから削除対象のファイルパスを抽出する。"""
    # rm コマンドが含まれているか確認
    # rm, rm -f, rm -rf, rm -r 等のパターンをマッチ
    rm_pattern = r'\brm\s+'
    if not re.search(rm_pattern, command):
        return []

    # rm コマンド以降の引数を取得（パイプや && の前まで）
    # 複数のコマンドが連結されている場合は rm 部分のみ抽出
    rm_match = re.search(r'\brm\s+([^;&|]+)', command)
    if not rm_match:
        return []

    args_str = rm_match.group(1).strip()

    # オプション（-r, -f, -rf 等）を除去し、ファイルパスのみ抽出
    targets = []
    for token in args_str.split():
        if token.startswith("-"):
            continue
        # クォートを除去
        token = token.strip("'\"")
        if token:
            targets.append(token)

    return targets


def archive_file(file_path: str, project_dir: str) -> str | None:
    """ファイルを archive/ にコピーする。成功時はアーカイブパスを返す。"""
    src = Path(file_path)
    if not src.exists():
        return None

    archive_dir = Path(project_dir) / "archive"
    archive_dir.mkdir(exist_ok=True)

    # タイムスタンプ付きのファイル名で保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"{src.stem}_{timestamp}{src.suffix}"
    dest = archive_dir / dest_name

    try:
        if src.is_dir():
            shutil.copytree(str(src), str(dest))
        else:
            shutil.copy2(str(src), str(dest))
        return str(dest)
    except Exception:
        return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    # rm コマンドが含まれていない場合はスキップ
    targets = extract_rm_targets(command)
    if not targets:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    archived = []

    for target in targets:
        if should_skip(target):
            continue

        # 相対パスを絶対パスに変換
        if not os.path.isabs(target):
            target = os.path.join(project_dir, target)

        dest = archive_file(target, project_dir)
        if dest:
            archived.append(f"  {target} → {dest}")

    if archived:
        context = (
            "[archive-on-delete] ファイルを archive/ にバックアップしました:\n"
            + "\n".join(archived)
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": context,
            }
        }
        print(json.dumps(output, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    main()
