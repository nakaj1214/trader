#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import re
from pathlib import Path

from common import WORKSPACE_ROOT, HARNESS_DIR, changed_paths, load_json

RULES_PATH = HARNESS_DIR / "architecture_rules.json"


def _matches(path: str, globs: list[str]) -> bool:
    return not globs or any(fnmatch.fnmatch(path, pat) for pat in globs)


def run(all_files: bool = False) -> tuple[str, list[dict]]:
    cfg = load_json(RULES_PATH, {"mode": "advisory", "rules": []})
    mode = str(cfg.get("mode", "advisory"))
    rules = cfg.get("rules", []) if isinstance(cfg.get("rules"), list) else []
    if not rules:
        return mode, []

    if all_files:
        candidates = []
        for p in WORKSPACE_ROOT.rglob("*"):
            if p.is_file() and ".git" not in p.parts and ".harness/runtime" not in p.as_posix():
                candidates.append(p.relative_to(WORKSPACE_ROOT).as_posix())
    else:
        candidates = changed_paths()

    findings: list[dict] = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("enabled", True) is False:
            continue
        if rule.get("type") != "forbid_regex":
            continue
        pattern = str(rule.get("pattern", ""))
        if not pattern:
            continue
        try:
            rx = re.compile(pattern, re.MULTILINE)
        except re.error as e:
            findings.append({"rule": rule.get("id", "invalid"), "path": str(RULES_PATH.relative_to(WORKSPACE_ROOT)), "message": f"invalid regex: {e}"})
            continue
        include = [str(x) for x in rule.get("include_globs", []) if x]
        exclude = [str(x) for x in rule.get("exclude_globs", []) if x]
        for rel in candidates:
            if not _matches(rel, include) or (exclude and _matches(rel, exclude)):
                continue
            p = WORKSPACE_ROOT / rel
            try:
                if not p.is_file() or p.stat().st_size > int(rule.get("max_file_bytes", 2_000_000)):
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = rx.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                findings.append({
                    "rule": str(rule.get("id", "unnamed")),
                    "path": rel,
                    "line": line,
                    "message": str(rule.get("message", "architecture rule violated")),
                })
    return mode, findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Changed-file architecture ratchet")
    ap.add_argument("--all", action="store_true", help="Scan all workspace files instead of changed files")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    mode, findings = run(args.all)
    if args.json:
        print(json.dumps({"mode": mode, "findings": findings}, ensure_ascii=False, separators=(",", ":")))
    else:
        print(f"Architecture check: {len(findings)} finding(s), mode={mode}")
        for f in findings[:30]:
            loc = f"{f['path']}:{f.get('line', '?')}"
            print(f"- [{f['rule']}] {loc} {f['message']}")
        if len(findings) > 30:
            print(f"... {len(findings)-30} more")
    return 1 if findings and mode == "enforce" else 0


if __name__ == "__main__":
    raise SystemExit(main())
