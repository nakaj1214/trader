from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = HARNESS_DIR.parents[1]
CONFIG_PATH = HARNESS_DIR / "config.json"
COMMANDS_PATH = HARNESS_DIR / "commands.json"
RUNTIME_DIR = HARNESS_DIR / "runtime"


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def config():
    return load_json(CONFIG_PATH, {})


def resolve_workspace_path(value: str | None) -> Path:
    if not value or value == ".":
        return WORKSPACE_ROOT
    return (WORKSPACE_ROOT / value).resolve()


def git_roots(cfg=None):
    cfg = cfg or config()
    roots = []
    for value in cfg.get("project_layout", {}).get("git_roots", []):
        p = resolve_workspace_path(value)
        if (p / ".git").exists():
            roots.append(p)
    if not roots and (WORKSPACE_ROOT / ".git").exists():
        roots.append(WORKSPACE_ROOT)
    return roots


def _run_bytes(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except Exception:
        return b""


def _hash_command(hasher, cmd) -> None:
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert p.stdout is not None
        while True:
            chunk = p.stdout.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
        p.wait(timeout=60)
    except Exception:
        hasher.update(b"<command-error>")


def repo_state_hash(cfg=None) -> str:
    cfg = cfg or config()
    h = hashlib.sha256()
    for root in git_roots(cfg):
        try:
            rel = root.relative_to(WORKSPACE_ROOT).as_posix()
        except Exception:
            rel = str(root)
        h.update(rel.encode())
        h.update(b"\0worktree\0")
        _hash_command(h, ["git", "-C", str(root), "diff", "--binary", "HEAD"])
        h.update(b"\0cached\0")
        _hash_command(h, ["git", "-C", str(root), "diff", "--binary", "--cached", "HEAD"])
        names = _run_bytes(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"]).decode(errors="replace").splitlines()
        for name in sorted(names):
            p = root / name
            h.update(b"\0untracked\0" + name.encode(errors="replace"))
            try:
                if p.is_file():
                    with p.open("rb") as f:
                        while True:
                            chunk = f.read(1024 * 1024)
                            if not chunk:
                                break
                            h.update(chunk)
            except Exception:
                h.update(b"<read-error>")
    return h.hexdigest()


def changed_paths(cfg=None):
    cfg = cfg or config()
    result = []
    for root in git_roots(cfg):
        prefix = root.relative_to(WORKSPACE_ROOT)
        names = set()
        for args in (["diff", "--name-only", "HEAD"], ["diff", "--cached", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]):
            out = _run_bytes(["git", "-C", str(root), *args]).decode(errors="replace")
            names.update(x for x in out.splitlines() if x)
        result.extend((prefix / n).as_posix() if str(prefix) != "." else n for n in sorted(names))
    return result


def diff_stats(cfg=None):
    cfg = cfg or config()
    files = 0
    lines = 0
    for root in git_roots(cfg):
        out = _run_bytes(["git", "-C", str(root), "diff", "--numstat", "HEAD"]).decode(errors="replace")
        seen = set()
        for row in out.splitlines():
            parts = row.split("\t")
            if len(parts) >= 3:
                seen.add(parts[2]); files += 1
                try:
                    lines += int(parts[0]) + int(parts[1])
                except ValueError:
                    lines += 1000
        untracked = _run_bytes(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"]).decode(errors="replace").splitlines()
        for n in untracked:
            if n in seen:
                continue
            files += 1
            try:
                p = root / n
                lines += sum(1 for _ in p.open("rb")) if p.is_file() else 0
            except Exception:
                lines += 1
    return files, lines
