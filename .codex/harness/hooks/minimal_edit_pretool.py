#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

MIN_EXISTING_LINES = 40
PROTECTED = (
    ".codex/harness/scripts/minimal_diff_guard.py",
    ".codex/harness/hooks/minimal_edit_pretool.py",
    ".codex/harness/minimal_edit_policy.json",
)


def deny(reason: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    return 0


def git_root(cwd: Path) -> Path | None:
    cp = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return Path(cp.stdout.strip()).resolve() if cp.returncode == 0 else None


def all_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            out.extend(all_strings(value))
    elif isinstance(obj, list):
        for value in obj:
            out.extend(all_strings(value))
    return out


def extract_path(tool_input: dict[str, Any]) -> str | None:
    for key in ("file_path", "path", "filename", "file"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve(root: Path, raw: str) -> Path:
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def tracked(root: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    cp = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{rel}"], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return cp.returncode == 0


def line_count(path: Path) -> int:
    try:
        raw = path.read_bytes()
        if b"\x00" in raw[:8192]:
            return 0
        return len(raw.decode("utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def patch_text(tool_input: dict[str, Any]) -> str:
    joined = "\n".join(all_strings(tool_input))
    return joined if ("*** Update File:" in joined or "@@" in joined) else ""


def rewrite_like_patch(text: str, root: Path) -> str | None:
    blocks = re.split(r"(?=^\*\*\* Update File: )", text, flags=re.M)
    for block in blocks:
        m = re.match(r"^\*\*\* Update File:\s*(.+?)\s*$", block, flags=re.M)
        if not m:
            continue
        raw = m.group(1).strip()
        path = resolve(root, raw)
        if not path.exists() or not tracked(root, path):
            continue
        original = line_count(path)
        if original < MIN_EXISTING_LINES:
            continue
        deleted = sum(1 for line in block.splitlines() if line.startswith("-") and not line.startswith("---"))
        added = sum(1 for line in block.splitlines() if line.startswith("+") and not line.startswith("+++"))
        if deleted >= max(30, int(original * 0.60)) and added >= 15:
            return (
                f"{raw}: patch removes {deleted}/{original} existing lines and adds {added}. "
                "Preserve unchanged content and patch only the required lines/blocks."
            )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    joined = "\n".join(all_strings(tool_input)).lower()
    if tool_name in {"Write", "Edit", "apply_patch"} and any(p.lower() in joined for p in PROTECTED):
        return deny(
            "Adaptive Harness v6.10 blocked editing the minimal-diff guard/policy. "
            "Update guard infrastructure through the installer/maintainer path."
        )

    root = git_root(Path(payload.get("cwd") or Path.cwd()).resolve())
    if root is None:
        return 0

    if tool_name == "Write":
        raw = extract_path(tool_input)
        if raw:
            path = resolve(root, raw)
            if path.exists() and tracked(root, path):
                lines = line_count(path)
                if lines >= MIN_EXISTING_LINES:
                    return deny(
                        f"Adaptive Harness v6.10 blocked whole-file Write for existing tracked file "
                        f"{raw} ({lines} lines). Use Edit/apply_patch and modify only the necessary lines/blocks."
                    )
        return 0

    if tool_name == "apply_patch":
        text = patch_text(tool_input)
        if text:
            reason = rewrite_like_patch(text, root)
            if reason:
                return deny("Adaptive Harness v6.10 blocked rewrite-like apply_patch. " + reason)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
