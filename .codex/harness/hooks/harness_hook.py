#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HARNESS_DIR = SCRIPT_DIR.parent
WORKSPACE_ROOT = HARNESS_DIR.parents[1]
sys.path.insert(0, str(HARNESS_DIR / "scripts"))
from common import config, load_json, repo_state_hash, diff_stats, changed_paths, RUNTIME_DIR, git_roots

CORRECTION_MARKERS = ("違う", "ではない", "そうではなく", "間違", "誤り", "訂正", "前にも", "以前も", "改善されていない", "not what i meant", "that's wrong", "that is wrong", "incorrect", "correction")
WORK_MARKERS = ("実装", "修正", "変更", "追加", "作成", "移行", "調査", "原因", "判断", "決定", "検証", "テスト", "未完了", "implemented", "fixed", "changed", "added", "created", "investigated", "root cause", "decision", "verified", "tested")
ARTIFACT_PATTERN = re.compile(r"(?:`[^`]*(?:/|\.(?:php|js|ts|tsx|vue|md|json|ya?ml|py))[^`]*`|\b(?:AGENTS\.md|git|docker|artisan|pytest|unittest)\b)", re.I)


def runtime_file(name):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR / name


def version() -> str:
    try:
        return (HARNESS_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"


def session_start(event, cfg):
    sid = event.get("session_id", "unknown")
    state = runtime_file(f"session-{sid}.json")
    if not state.exists():
        state.write_text(json.dumps({"baseline_state_hash": repo_state_hash(cfg), "created_at": time.time()}, indent=2), encoding="utf-8")
    layout = cfg.get("project_layout", {})
    roots = ", ".join(layout.get("git_roots", [])) or "auto-detect"
    app = layout.get("application_root", ".")
    knowledge = layout.get("knowledge_root", "docs")
    status = load_json(HARNESS_DIR / "commands.json", {}).get("status", "uninitialized")
    context = (
        f"Adaptive Codex Harness v{version()} active. Workspace `{WORKSPACE_ROOT}`; application root `{app}`; Git root(s): {roots}. "
        f"Read `{knowledge}/index.md` only as a map, then only task-relevant records. Verification commands: {status}. "
    )
    detected = git_roots(cfg)
    if detected and all(p != WORKSPACE_ROOT for p in detected):
        context += "Workspace and Git root differ; keep workspace-root Harness instructions/config in scope and avoid treating the application Git root as the whole workspace. "
    if status != "ready":
        context += "Before substantial edits, use `$harness-bootstrap` and confirm real project commands. "
    context += (
        "Use one Sol-high parent by default; at most two narrow independent subagents only when materially faster. "
        "Use bounded output, targeted checks during iteration, the final deterministic gate once, and bounded independent review only when required. "
        "Avoid scope creep, routine Knowledge writes, and bypassing safety rules."
    )
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}


def user_prompt(event):
    prompt = event.get("prompt") or ""
    normalized = prompt.casefold()
    if not any(m in normalized for m in CORRECTION_MARKERS):
        return {}
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "This prompt may contain a reusable correction. Verify it against current code/config/tests/runtime; if durable, use `$maintain-project-knowledge`. Keep one-off observations transient."}}


def subagent_stop(event, cfg):
    if event.get("agent_type") != "reviewer":
        return {"continue": True, "suppressOutput": True}
    message = event.get("last_assistant_message") or ""
    if "VERDICT: PASS" in message:
        runtime_file("review-stamp.json").write_text(json.dumps({"state_hash": repo_state_hash(cfg), "timestamp": time.time(), "agent_id": event.get("agent_id")}, indent=2), encoding="utf-8")
    return {"continue": True, "suppressOutput": True}


def is_substantive(message):
    normalized = (message or "").casefold().strip()
    return len(normalized) >= 160 and any(m in normalized for m in WORK_MARKERS) and bool(ARTIFACT_PATTERN.search(message or ""))


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def needs_verification(cfg) -> bool:
    paths = changed_paths(cfg)
    if not paths:
        return False
    gate = cfg.get("quality_gate", {})
    exempt = gate.get("verification_exempt_globs", ["docs/**", "memo/**", "**/*.md"])
    return any(not _matches_any(path, exempt) for path in paths)


def needs_review(cfg):
    gate = cfg.get("quality_gate", {})
    files, lines = diff_stats(cfg)
    threshold = gate.get("nontrivial", {})
    if files >= int(threshold.get("changed_files", 8)) or lines >= int(threshold.get("changed_lines", 200)):
        return True
    for path in changed_paths(cfg):
        for pat in gate.get("always_review_globs", []):
            if fnmatch.fnmatch(path, pat):
                return True
    return False


def stop(event, cfg):
    gate = cfg.get("quality_gate", {})
    sid = event.get("session_id", "unknown")
    session = load_json(runtime_file(f"session-{sid}.json"), {})
    baseline = session.get("baseline_state_hash")
    current = repo_state_hash(cfg)
    changed = bool(baseline and current != baseline)

    if gate.get("enabled", True) and changed:
        missing = []
        if gate.get("require_verification", True) and needs_verification(cfg):
            stamp = load_json(runtime_file("verify-stamp.json"), {})
            if stamp.get("state_hash") != current or not stamp.get("passed"):
                missing.append("run `python3 .codex/harness/scripts/verify.py` and resolve failures caused by the current task")
        if gate.get("require_independent_review", True) and needs_review(cfg):
            stamp = load_json(runtime_file("review-stamp.json"), {})
            if stamp.get("state_hash") != current:
                missing.append("use at most one bounded independent reviewer only when current-task risk justifies it")
        if missing:
            key = hashlib.sha256((sid + current).encode()).hexdigest()[:20]
            counter_path = runtime_file(f"stop-block-{key}.json")
            counter = load_json(counter_path, {"count": 0})
            count = int(counter.get("count", 0))
            max_blocks = int(gate.get("max_stop_blocks_per_diff", 1))
            if count < max_blocks:
                counter_path.write_text(json.dumps({"count": count + 1, "timestamp": time.time()}, indent=2), encoding="utf-8")
                return {"decision": "block", "reason": "Adaptive Harness v6.4 advisory quality policy: " + "; ".join(missing) + ". Later edits invalidate the relevant stamp."}
            return {"continue": True, "suppressOutput": True}

    knowledge_cfg = cfg.get("knowledge", {})
    if knowledge_cfg.get("stop_checkpoint", "advisory") == "blocking" and not event.get("stop_hook_active") and is_substantive(event.get("last_assistant_message") or ""):
        return {"decision": "block", "reason": "Perform one durable project-knowledge review. If nothing reusable was learned, finish without writing."}
    return {"continue": True, "suppressOutput": True}


def response_for(event):
    cfg = config(); name = event.get("hook_event_name")
    if name == "SessionStart": return session_start(event, cfg)
    if name == "UserPromptSubmit": return user_prompt(event)
    if name == "SubagentStop": return subagent_stop(event, cfg)
    if name == "Stop": return stop(event, cfg)
    return {}


def main():
    try:
        event = json.load(sys.stdin)
        response = response_for(event if isinstance(event, dict) else {})
    except Exception:
        response = {}
    json.dump(response, sys.stdout, ensure_ascii=False, separators=(",", ":")); sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
