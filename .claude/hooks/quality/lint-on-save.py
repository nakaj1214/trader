#!/usr/bin/env python3
"""
PostToolUse フック: Edit/Write 後に Python ファイルのフォーマッターと型チェッカーを実行する。

Edit または Write ツールがファイルを変更した後にトリガーされる。
Python ファイルに対して ruff（フォーマット＋リント）と ty（型チェック）を実行する。
"""

import json
import os
import subprocess
import sys

# 入力バリデーション定数
MAX_PATH_LENGTH = 4096


def validate_path(file_path: str) -> bool:
    """セキュリティのためファイルパスをバリデーションする。"""
    if not file_path or len(file_path) > MAX_PATH_LENGTH:
        return False
    # Check for path traversal
    if ".." in file_path:
        return False
    return True


def get_file_path() -> str | None:
    """ツール入力からファイルパスを抽出する。"""
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not tool_input:
        return None

    try:
        data = json.loads(tool_input)
        return data.get("file_path")
    except json.JSONDecodeError:
        return None


def is_python_file(path: str) -> bool:
    """Python ファイルかどうかを判定する。"""
    return path.endswith(".py")


def run_command(cmd: list[str], cwd: str) -> tuple[int, str, str]:
    """コマンドを実行し (returncode, stdout, stderr) を返す。"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"


def main() -> None:
    file_path = get_file_path()
    if not file_path:
        return

    # Validate input
    if not validate_path(file_path):
        return

    if not is_python_file(file_path):
        return

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Determine relative path for display
    if file_path.startswith(project_dir):
        rel_path = os.path.relpath(file_path, project_dir)
    else:
        rel_path = file_path

    issues: list[str] = []

    # Run ruff format
    ret, stdout, stderr = run_command(
        ["uv", "run", "ruff", "format", file_path],
        cwd=project_dir,
    )
    if ret != 0:
        issues.append(f"ruff format failed:\n{stderr or stdout}")

    # Run ruff check with auto-fix
    ret, stdout, stderr = run_command(
        ["uv", "run", "ruff", "check", "--fix", file_path],
        cwd=project_dir,
    )
    if ret != 0:
        # Show remaining issues that couldn't be auto-fixed
        output = stdout or stderr
        if output.strip():
            issues.append(f"ruff check issues:\n{output}")

    # Run ty type check
    ret, stdout, stderr = run_command(
        ["uv", "run", "ty", "check", file_path],
        cwd=project_dir,
    )
    if ret != 0:
        output = stdout or stderr
        if output.strip():
            issues.append(f"ty check issues:\n{output}")

    # Report results
    if issues:
        print(f"[lint-on-save] Issues found in {rel_path}:", file=sys.stderr)
        for issue in issues:
            print(issue, file=sys.stderr)
        print(
            "\nPlease review and fix these issues.",
            file=sys.stderr,
        )
    else:
        print(f"[lint-on-save] OK: {rel_path} passed all checks")


if __name__ == "__main__":
    main()
