"""アトミックな JSONL 追記と、破損行を隔離する安全な読み取り。"""

import json
import os
import sys
from pathlib import Path

# fcntl は Unix 専用。Windows ではファイルロックに msvcrt を使用する
if sys.platform == "win32":
    import msvcrt

    def _lock(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock(fd: int) -> None:
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def append_jsonl(filepath: str, json_line: str) -> None:
    """排他ファイルロック付きで JSONL ファイルに1行追記する。

    fcntl.flock (Unix) または msvcrt.locking (Windows) を使用して
    並行書き込みによるデータ破損を防止する。ロック解除前にデータを
    ディスクにフラッシュ・同期する。

    Parameters
    ----------
    filepath : str
        JSONL ファイルのパス。親ディレクトリは必要に応じて作成される。
    json_line : str
        追記する JSON 文字列（改行は自動付与）。
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        _lock(fd)
        line = json_line.rstrip("\n") + "\n"
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        _unlock(fd)
        os.close(fd)


def read_jsonl_safe(filepath: str) -> list[dict]:
    """JSONL ファイルを読み込み、破損行を .corrupt ファイルに隔離する。

    有効な JSON 行は dict のリストとして返される。
    破損行（空行含む）は {filepath}.corrupt に書き出される。

    Parameters
    ----------
    filepath : str
        読み込む JSONL ファイルのパス。

    Returns
    -------
    list[dict]
        有効行からパースされた JSON オブジェクトのリスト。
    """
    path = Path(filepath)
    if not path.is_file():
        return []

    entries: list[dict] = []
    corrupt_lines: list[str] = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
                entries.append(obj)
            except (json.JSONDecodeError, ValueError):
                corrupt_lines.append(line)

    if corrupt_lines:
        corrupt_path = str(filepath) + ".corrupt"
        with open(corrupt_path, "a", encoding="utf-8") as cf:
            for cl in corrupt_lines:
                cf.write(cl if cl.endswith("\n") else cl + "\n")

    return entries
