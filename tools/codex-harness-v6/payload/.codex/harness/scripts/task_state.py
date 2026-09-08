#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "runtime" / "task-state"
LATEST = ROOT / "latest.json"


def load() -> dict:
    try:
        v = json.loads(LATEST.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def save(v: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Optional compact state for genuinely long/multi-session tasks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("title")
    c = sub.add_parser("checkpoint"); c.add_argument("summary")
    sub.add_parser("show")
    sub.add_parser("finish")
    args = ap.parse_args()
    if args.cmd == "start":
        save({"title": args.title, "status": "active", "created_at": time.time(), "checkpoints": []})
    elif args.cmd == "checkpoint":
        v = load()
        if not v:
            raise SystemExit("No active task state. Use start first.")
        cps = v.setdefault("checkpoints", [])
        cps.append({"ts": time.time(), "summary": args.summary[:1200]})
        v["checkpoints"] = cps[-8:]
        save(v)
    elif args.cmd == "show":
        v = load(); print(json.dumps(v, ensure_ascii=False, indent=2) if v else "No task state.")
    elif args.cmd == "finish":
        v = load()
        if v:
            v["status"] = "finished"; v["finished_at"] = time.time(); save(v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
