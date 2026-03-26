"""環境変数を読み込み、.claude/.env → .claude/settings.json の順でフォールバックする。"""

import json
import os
import re
from pathlib import Path

_dotenv_loaded: bool = False
_settings_env: dict | None = None


def _load_dotenv() -> None:
    """.claude/.env ファイルから環境変数を読み込む（未設定のもののみ）。"""
    candidates = [
        Path(os.environ.get("CLAUDE_PROJECT_DIR", "")) / ".claude/.env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for path in candidates:
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    # 既に設定済みの環境変数は上書きしない
                    if key and key not in os.environ:
                        os.environ[key] = value
            except Exception:
                continue
            return


def _strip_jsonc(text: str) -> str:
    """JSONC（コメント付き JSON）から // コメントと末尾カンマを除去する。"""
    # Remove // comments (but not inside strings)
    result = re.sub(r'(?<!["\w:])//.*', "", text)
    # Remove trailing commas before } or ]
    result = re.sub(r",\s*([}\]])", r"\1", result)
    return result


def _load_settings_env() -> dict:
    """未設定の環境変数のフォールバックとして .claude/settings.json の env セクションを読み込む。"""
    candidates = [
        Path(os.environ.get("CLAUDE_PROJECT_DIR", "")) / ".claude/settings.json",
        Path(__file__).resolve().parent.parent.parent / "settings.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                raw = path.read_text(encoding="utf-8")
                cleaned = _strip_jsonc(raw)
                data = json.loads(cleaned)
                return data.get("env", {})
            except Exception:
                continue
    return {}


def get(key: str) -> str:
    """os.environ → .claude/.env → settings.json の env セクションの順で取得する。"""
    global _dotenv_loaded, _settings_env
    if not _dotenv_loaded:
        _load_dotenv()
        _dotenv_loaded = True
    if _settings_env is None:
        _settings_env = _load_settings_env()
    return os.environ.get(key, "") or _settings_env.get(key, "")
