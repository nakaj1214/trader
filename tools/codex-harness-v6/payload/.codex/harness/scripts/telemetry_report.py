#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent / "runtime" / "telemetry"


def load_records(days: int) -> list[dict]:
    if not ROOT.exists():
        return []
    cutoff = time.time() - max(days, 1) * 86400
    rows: list[dict] = []
    for path in sorted(ROOT.glob("*.jsonl")):
        try:
            if path.stat().st_mtime < cutoff:
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    v = json.loads(line)
                    if isinstance(v, dict):
                        rows.append(v)
                except Exception:
                    pass
        except OSError:
            pass
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Compact local Harness observability report")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    rows = load_records(args.days)
    if not rows:
        print("No telemetry records yet.")
        return 0

    events = Counter(str(r.get("event", "unknown")) for r in rows)
    tools = Counter(str(r.get("tool", "")) for r in rows if r.get("tool"))
    families = Counter(str(r.get("command_family", "")) for r in rows if r.get("command_family"))
    agents = Counter(str(r.get("agent_type", "unknown")) for r in rows if r.get("event") == "SubagentStart")
    sessions = len({r.get("session") for r in rows if r.get("session")})

    print(f"Harness telemetry ({args.days}d): {len(rows)} events / {sessions} sessions")
    print("Events: " + ", ".join(f"{k}={v}" for k, v in events.most_common(8)))
    if tools:
        print("Tools : " + ", ".join(f"{k}={v}" for k, v in tools.most_common(8)))
    if families:
        print("Bash  : " + ", ".join(f"{k}={v}" for k, v in families.most_common(8)))
    if agents:
        print("Agents: " + ", ".join(f"{k}={v}" for k, v in agents.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
