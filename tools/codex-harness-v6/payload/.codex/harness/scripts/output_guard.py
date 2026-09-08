#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Any

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ERROR_RE = re.compile(
    r"(?i)(?:\bfail(?:ed|ure)?\b|\berror\b|\bexception\b|\bfatal\b|\bpanic\b|"
    r"\bassert(?:ion|ing)?\b|\btraceback\b|\bexpected\b|\breceived\b|"
    r"\bundefined\b|\bnot found\b|\btimed? out\b|\btimeout\b|\bsyntax\b|"
    r"segmentation fault|permission denied|connection refused)"
)


def _clean(line: str) -> str:
    return ANSI_RE.sub("", line.rstrip("\r\n"))


def _tail_lines(path: Path, max_lines: int, scan_bytes: int) -> list[str]:
    if max_lines <= 0 or not path.exists():
        return []
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > scan_bytes:
            f.seek(size - scan_bytes)
            f.readline()  # discard partial line
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    lines = [_clean(x) for x in text.splitlines()]
    nonempty = [x for x in lines if x.strip()]
    return nonempty[-max_lines:]


def _failure_excerpt(path: Path, max_lines: int, scan_bytes: int, context: int = 3) -> list[str]:
    if max_lines <= 0 or not path.exists():
        return []
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > scan_bytes:
            f.seek(size - scan_bytes)
            f.readline()
        data = f.read()
    lines = [_clean(x) for x in data.decode("utf-8", errors="replace").splitlines()]
    if not lines:
        return []

    selected: set[int] = set()
    for i, line in enumerate(lines):
        if ERROR_RE.search(line):
            lo = max(0, i - context)
            hi = min(len(lines), i + context + 1)
            selected.update(range(lo, hi))

    # Always include the tail because PHPUnit/Pest/build tools often put the useful summary there.
    tail_count = min(40, max_lines // 3 if max_lines >= 12 else max_lines)
    selected.update(range(max(0, len(lines) - tail_count), len(lines)))

    ordered = sorted(selected)
    if not ordered:
        return [x for x in lines[-max_lines:] if x.strip()]

    out: list[str] = []
    previous = None
    for idx in ordered:
        if previous is not None and idx > previous + 1:
            out.append("...")
        line = lines[idx]
        if line.strip() or (out and out[-1] != ""):
            out.append(line)
        previous = idx
        if len(out) >= max_lines:
            break
    return out[:max_lines]


def _policy(item: dict[str, Any], token_cfg: dict[str, Any]) -> dict[str, Any]:
    verification = token_cfg.get("verification", {}) if isinstance(token_cfg, dict) else {}
    local = item.get("output", {}) if isinstance(item.get("output"), dict) else {}
    return {
        "success_lines": int(local.get("success_lines", verification.get("success_max_lines", 6))),
        "failure_lines": int(local.get("failure_lines", verification.get("failure_max_lines", 160))),
        "detail_lines": int(local.get("detail_lines", verification.get("detail_max_lines", 400))),
        "scan_bytes": int(local.get("scan_bytes", verification.get("tail_scan_bytes", 2 * 1024 * 1024))),
        "retain_success": bool(local.get("retain_success_log", verification.get("retain_success_logs", False))),
        "retain_failure": bool(local.get("retain_failure_log", verification.get("retain_failed_logs", True))),
    }


def run_guarded(
    *,
    name: str,
    command: str,
    cwd: Path,
    timeout: int,
    item: dict[str, Any],
    token_cfg: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    policy = _policy(item, token_cfg)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "command"
    log_path = run_dir / f"{safe_name}.log"
    run_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    timed_out = False
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            shell=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    pass
            code = 124

    elapsed = round(time.time() - started, 2)
    passed = code == 0
    excerpt = (
        _tail_lines(log_path, policy["success_lines"], policy["scan_bytes"])
        if passed
        else _failure_excerpt(log_path, policy["failure_lines"], policy["scan_bytes"])
    )

    retained = (passed and policy["retain_success"]) or ((not passed) and policy["retain_failure"])
    result = {
        "name": name,
        "command": command,
        "exit_code": code,
        "passed": passed,
        "timed_out": timed_out,
        "elapsed_seconds": elapsed,
        "excerpt": excerpt,
        "log_path": str(log_path.relative_to(run_dir.parents[1])) if retained else None,
        "detail_lines": policy["detail_lines"],
    }

    if not retained:
        try:
            log_path.unlink()
        except FileNotFoundError:
            pass

    return result


def read_detail(log_path: Path, max_lines: int, scan_bytes: int, raw: bool = False) -> list[str]:
    if raw:
        if not log_path.exists():
            return []
        return [_clean(x) for x in log_path.read_text(encoding="utf-8", errors="replace").splitlines()]
    return _failure_excerpt(log_path, max_lines, scan_bytes)


def prune_failed_logs(root: Path, keep_runs: int) -> None:
    if keep_runs <= 0 or not root.exists():
        return
    dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in dirs[keep_runs:]:
        try:
            for p in old.rglob("*"):
                if p.is_file():
                    p.unlink()
            for p in sorted((p for p in old.rglob("*") if p.is_dir()), reverse=True):
                p.rmdir()
            old.rmdir()
        except OSError:
            pass
