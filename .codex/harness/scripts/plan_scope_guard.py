#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

# Heuristic linter only. Human/agent policy remains authoritative.
PATTERNS = [
    ("embedded-code", re.compile(r"```(?:php|sql|python|js|javascript|bash|sh|toml|json)\b", re.I), "Plan contains implementation code; keep only when acceptance-critical."),
    ("driver-branch", re.compile(r"DB::getDriverName|sqlite.*mysql|mysql.*sqlite", re.I), "DB-driver implementation branching is usually implementation-time detail."),
    ("sentinel", re.compile(r"1970-01-01|sentinel|epoch", re.I), "Sentinel constants usually belong in implementation notes, not the plan."),
    ("future-detail", re.compile(r"(?:Phase\s*[3-9]|将来|スコープ外).*?(?:Controller|Service|Repository|Model|migration|テスト|algorithm|アルゴリズム)", re.I | re.S), "Out-of-scope/future work appears to contain detailed design."),
    ("generated-column", re.compile(r"generated\s+column|GENERATED\s+ALWAYS|default_guard", re.I), "A concrete DB enforcement mechanism may be over-specified unless requirement-critical."),
]

READY_TERMS = [
    ("requirements", ("REQ-", "要件")),
    ("scope", ("スコープ", "scope")),
    ("files", ("対象ファイル", "影響範囲", "ファイル")),
    ("acceptance", ("受入条件", "完了条件", "acceptance")),
    ("verification", ("テスト", "検証")),
]

def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6.8 plan-scope heuristic guard")
    ap.add_argument("plan")
    ap.add_argument("--proposal")
    ap.add_argument("--strict", action="store_true", help="Return non-zero if scope warnings exist")
    args = ap.parse_args()

    plan = Path(args.plan)
    if not plan.is_file():
        print(f"FAIL plan not found: {plan}")
        return 2
    text = plan.read_text(encoding="utf-8", errors="replace")

    warnings = []
    for code, rx, msg in PATTERNS:
        if rx.search(text):
            warnings.append((code, msg))

    missing = []
    low = text.lower()
    for key, terms in READY_TERMS:
        if not any(t.lower() in low for t in terms):
            missing.append(key)

    print("Adaptive Codex Harness v6.8 Plan Scope Guard")
    print(f"Plan: {plan}")
    if args.proposal:
        p = Path(args.proposal)
        print(f"Proposal: {p} ({'found' if p.is_file() else 'missing'})")
    print()

    if missing:
        print("READY-GATE: INCOMPLETE")
        print("  Missing planning signals: " + ", ".join(missing))
    else:
        print("READY-GATE: structurally sufficient")

    if warnings:
        print(f"SCOPE-WARN: {len(warnings)}")
        for code, msg in warnings:
            print(f"  - [{code}] {msg}")
    else:
        print("SCOPE-WARN: 0")

    print("\nNote: warnings are advisory. Only the v6.8 Blocking definition may block planning.")
    if args.strict and warnings:
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
