#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HARNESS_DIR = SCRIPT_DIR.parent
RUNTIME_DIR = HARNESS_DIR / "runtime"
LOG_DIR = RUNTIME_DIR / "quiet-exec"

ERROR_MARKERS = ("error", "exception", "failed", "failure", "fatal", "traceback", "warning", "assert")


def bounded_failure(lines: list[str], limit: int) -> list[str]:
    if len(lines) <= limit:
        return lines
    picked: list[str] = []
    seen: set[int] = set()
    # Keep a few lines around likely errors first.
    radius = 2
    for i, line in enumerate(lines):
        if any(marker in line.casefold() for marker in ERROR_MARKERS):
            for j in range(max(0, i - radius), min(len(lines), i + radius + 1)):
                if j not in seen:
                    picked.append(lines[j])
                    seen.add(j)
                    if len(picked) >= limit:
                        return picked
    # Fill remaining budget from the tail.
    for j in range(max(0, len(lines) - limit), len(lines)):
        if j not in seen:
            picked.append(lines[j])
            seen.add(j)
            if len(picked) >= limit:
                break
    return picked


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture verbose local command output and expose only a bounded excerpt")
    ap.add_argument("--name", default="command")
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--success-lines", type=int, default=3)
    ap.add_argument("--failure-lines", type=int, default=80)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--keep-success", action="store_true")
    ap.add_argument("--shell", help="Shell command string. Use this for pipes/redirection/compound commands.")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="Command after --, e.g. -- rg -n Foo src")
    args = ap.parse_args()

    if args.shell:
        command = args.shell
        shell = True
    else:
        command = list(args.command)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            ap.error("provide --shell '...' or a command after --")
        shell = False

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in args.name)[:60] or "command"
    log_path = LOG_DIR / f"{stamp}-{safe}.log"

    started = time.monotonic()
    try:
        cp = subprocess.run(
            command,
            cwd=Path(args.cwd),
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=args.timeout,
        )
        code = cp.returncode
        output = cp.stdout or ""
    except subprocess.TimeoutExpired as exc:
        code = 124
        out = exc.stdout or ""
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        output = out + f"\nTIMEOUT after {args.timeout}s\n"

    elapsed = time.monotonic() - started
    lines = output.splitlines()
    passed = code == 0

    if (not passed) or args.keep_success:
        log_path.write_text(output, encoding="utf-8")

    state = "PASS" if passed else "FAIL"
    print(f"[{state}] {args.name} ({elapsed:.2f}s, exit={code}, captured={len(lines)} lines)")
    if passed:
        excerpt = lines[-max(0, args.success_lines):] if args.success_lines else []
    else:
        excerpt = bounded_failure(lines, max(1, args.failure_lines))
    for line in excerpt:
        print(f"  {line}")

    if not passed:
        print(f"  retained log: {log_path}")
        print("  inspect only a bounded range first; avoid catting the whole log")
    elif args.keep_success:
        print(f"  retained log: {log_path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
