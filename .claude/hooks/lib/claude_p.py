"""
hooks/lib/claude_p.py

claude -p（非対話モード）を呼び出すユーティリティ。
タイムアウト・エラーハンドリングを統一する。

使い方:
    from lib.claude_p import run

    result = run("Summarize this: " + text, timeout=120)
"""

import os
import shutil
import subprocess
import sys


def _find_claude() -> str:
    """claude CLI 実行ファイルのパスを解決する。

    検索順序:
    1. shutil.which("claude") — 標準 PATH 検索
    2. ~/.local/bin/claude(.exe) — 一般的なインストール先
    3. フォールバック: 素の "claude"（subprocess が FileNotFoundError を発生させる）
    """
    found = shutil.which("claude")
    if found:
        return found

    home = os.path.expanduser("~")
    ext = ".exe" if sys.platform == "win32" else ""
    local_bin = os.path.join(home, ".local", "bin", f"claude{ext}")
    if os.path.isfile(local_bin):
        return local_bin

    return "claude"


# インポート時に1回だけ解決する
_CLAUDE_BIN = _find_claude()


def run(prompt: str, timeout: int = 120) -> str:
    """
    claude -p でプロンプトを実行してテキストを返す。

    Parameters
    ----------
    prompt : str
        claude -p に渡すプロンプト（トランスクリプト含む全文）
    timeout : int
        タイムアウト秒数（デフォルト 120）

    Returns
    -------
    str
        生成されたテキスト。エラー時は "(エラーメッセージ)" を返す。
    """
    try:
        # Remove CLAUDECODE env var to allow nested claude -p invocation
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        # Pass prompt via stdin to avoid Windows 32KB command-line limit
        result = subprocess.run(
            [_CLAUDE_BIN, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return f"(生成に失敗しました: returncode={result.returncode})\n```\n{result.stderr[:500]}\n```"

    except subprocess.TimeoutExpired:
        return f"(生成がタイムアウトしました: {timeout}秒)"
    except FileNotFoundError:
        return f"(claude CLI が見つかりません: {_CLAUDE_BIN})"
    except OSError as e:
        return f"(OS エラー: {e})"
    except Exception as e:
        return f"(予期しないエラー: {e})"
