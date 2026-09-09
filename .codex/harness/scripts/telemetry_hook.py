#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HARNESS_DIR = SCRIPT_DIR.parent
RUNTIME_DIR = ROOT / ".harness" / "runtime"
TELEMETRY_DIR = RUNTIME_DIR / "telemetry"


def _safe_id(value: object) -> str:
    raw = str(value or "unknown").encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:12]


def _json_len(value: object) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return 0


def _bash_family(command: str) -> str:
    command = (command or "").strip()
    if not command:
        return "empty"
    # Do not retain command text: only a coarse family is stored.
    first = command.split(None, 1)[0]
    if first in {"bash", "sh", "zsh"}:
        return "shell-wrapper"
    return first[:40]


def build_record(event: dict) -> dict:
    name = str(event.get("hook_event_name") or "unknown")
    record = {
        "ts": round(time.time(), 3),
        "event": name,
        "session": _safe_id(event.get("session_id")),
        "turn": _safe_id(event.get("turn_id")) if event.get("turn_id") else None,
        "model": str(event.get("model") or "")[:80],
    }
    if name in {"SubagentStart", "SubagentStop"}:
        record["agent_type"] = str(event.get("agent_type") or "unknown")[:80]
        record["agent"] = _safe_id(event.get("agent_id"))
    if name in {"PreToolUse", "PostToolUse"}:
        tool = str(event.get("tool_name") or "unknown")
        record["tool"] = tool[:100]
        tool_input = event.get("tool_input")
        record["input_chars"] = _json_len(tool_input)
        if tool == "Bash" and isinstance(tool_input, dict):
            cmd = str(tool_input.get("command") or "")
            record["command_family"] = _bash_family(cmd)
            record["command_chars"] = len(cmd)
        if name == "PostToolUse":
            record["response_chars"] = _json_len(event.get("tool_response"))
    return {k: v for k, v in record.items() if v is not None}


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d")
        path = TELEMETRY_DIR / f"{day}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(build_record(event), ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        # Observability must never block development work.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
