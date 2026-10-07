#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Any

VERSION = "6.12.0"
SUPPORTED_FROM = {(6, 10, 0), (6, 11, 0), (6, 12, 0)}
REVIEWED_V610_CORE = {'.codex/harness/bin/codex-project': '208f843039364152649fe789f140fa07f75a4c1bad7ade2b5e4d2aff8404568b',
 '.codex/harness/hooks/harness_hook.py': 'b2f05dd88cff52449ec0c49d765293f1d3e616f33977960f3ad48ecc423b21c8',
 '.codex/harness/hooks/minimal_edit_pretool.py': '28b578a235da7f97a0b7982dce4bbeef18297091964c4cc47a1a00502fdb71ee',
 '.codex/harness/hooks/pre_tool_safety.py': '5f970a6a4fba4dbcf94b1fcb096a87c3a9ada55aa660aa48aba65077c45fcc6a',
 '.codex/harness/scripts/architecture_check.py': 'ef0e1bd493e0650185aa29d7dab16a4fb5c26131cddd902b4ac216923581e53e',
 '.codex/harness/scripts/minimal_diff_guard.py': '9f77da05986b622bec2341c43ce05a54d06ee10e25152d792d6133afbb3b635f',
 '.codex/harness/scripts/selftest.py': '07c80c120ab28a5524f7a132fdf6ff5d84dab5b9dc59ef9b6cc4d46607da1498',
 '.codex/harness/scripts/task_scope.py': '00cee1e89d98555b4072ce1e7d376f1e8e8a4b5ff278448d5d7d76ff21054290',
 '.codex/harness/scripts/task_state.py': '3892d4c9a206e177e5a985235acea158a91afc68f78d6d0fac0ef6830fced819',
 '.codex/harness/scripts/telemetry_report.py': '22760e124856d3fa1a066fea5604b444b9a2339de096e3b3ea66a1efc3586f2a',
 '.codex/harness/scripts/verify.py': '7620cd8e1c7da76f8559341fc36a967696a4b9e42b1540c20ac5c74d2b939315'}
LEGACY_HOOK_HASHES = {'.agents/hooks/knowledge_lifecycle.py': '13669a6960b345b2a2f2e726fa52962965aab09f657916d831cb037c4d374d53',
 '.agents/hooks/tests/test_knowledge_lifecycle.py': '22167d29b1577c3d8102733b8b83a7cec797955630ee0d7602ff92d737cb1648'}
ONEOFF_RUNTIME_HASHES = {'.harness/runtime/analyze_approval_snapshots.php': '56f6dfe4c411ef5024e1c6c6028b5e42458c5026e1fbef0d938d65006bad3afa',
 '.harness/runtime/analyze_approval_snapshots.py': 'd5b49c01528d5defd5523777c08dfd134cc0f6b60fd89f9c66dc80b090a73b1d',
 '.harness/runtime/analyze_overtime_backup.php': 'd31f99d3d071e1beeadb1e96897a48837fd6a0687ac189ea84dd1a3aa8393f9c',
 '.harness/runtime/compare_dump_table_hashes.py': 'eb661b71c9982e6ae6f6e704701b903ed87ef3f889cf42ec06abf94fd878c831',
 '.harness/runtime/inspect_dev_db.php': 'd14ac2e2db67acce710f19556982a69638a6d7094124fcd3ec06cc41bb73c039',
 '.harness/runtime/restore_20260922_to_ams.sh': ('364c111ba67109fe88b70f14bd59efe2744388e692caaa73448b32cfdc1f570d',
                                                 'b34a54cf82486ddadf00cc4b18ea2ccdb5b6bd04705ac2140f9138e3920e4620')}
DESIRED_SOURCES = {'architecture_check.py': '#!/usr/bin/env python3\n'
                          'from __future__ import annotations\n'
                          '\n'
                          'import argparse\n'
                          'import fnmatch\n'
                          'import json\n'
                          'import re\n'
                          'from pathlib import Path\n'
                          '\n'
                          'from common import WORKSPACE_ROOT, HARNESS_DIR, changed_paths, git_roots, load_json\n'
                          '\n'
                          'RULES_PATH = HARNESS_DIR / "architecture_rules.json"\n'
                          '\n'
                          '\n'
                          'def _matches(path: str, globs: list[str]) -> bool:\n'
                          '    return not globs or any(fnmatch.fnmatch(path, pat) for pat in globs)\n'
                          '\n'
                          '\n'
                          'def run(all_files: bool = False) -> tuple[str, list[dict]]:\n'
                          '    cfg = load_json(RULES_PATH, {"mode": "advisory", "rules": []})\n'
                          '    mode = str(cfg.get("mode", "advisory"))\n'
                          '    rules = cfg.get("rules", []) if isinstance(cfg.get("rules"), list) else []\n'
                          '    if not rules:\n'
                          '        return mode, []\n'
                          '\n'
                          '    if all_files:\n'
                          '        candidates = []\n'
                          '        for root in git_roots():\n'
                          '            for p in root.rglob("*"):\n'
                          '                if not p.is_file() or ".git" in p.parts:\n'
                          '                    continue\n'
                          '                candidates.append(p.relative_to(WORKSPACE_ROOT).as_posix())\n'
                          '    else:\n'
                          '        candidates = changed_paths()\n'
                          '\n'
                          '    findings: list[dict] = []\n'
                          '    for rule in rules:\n'
                          '        if not isinstance(rule, dict) or rule.get("enabled", True) is False:\n'
                          '            continue\n'
                          '        if rule.get("type") != "forbid_regex":\n'
                          '            continue\n'
                          '        pattern = str(rule.get("pattern", ""))\n'
                          '        if not pattern:\n'
                          '            continue\n'
                          '        try:\n'
                          '            rx = re.compile(pattern, re.MULTILINE)\n'
                          '        except re.error as e:\n'
                          '            findings.append({"rule": rule.get("id", "invalid"), "path": '
                          'str(RULES_PATH.relative_to(WORKSPACE_ROOT)), "message": f"invalid regex: {e}"})\n'
                          '            continue\n'
                          '        include = [str(x) for x in rule.get("include_globs", []) if x]\n'
                          '        exclude = [str(x) for x in rule.get("exclude_globs", []) if x]\n'
                          '        for rel in candidates:\n'
                          '            if not _matches(rel, include) or (exclude and _matches(rel, exclude)):\n'
                          '                continue\n'
                          '            p = WORKSPACE_ROOT / rel\n'
                          '            try:\n'
                          '                if not p.is_file() or p.stat().st_size > int(rule.get("max_file_bytes", 2_000_000)):\n'
                          '                    continue\n'
                          '                text = p.read_text(encoding="utf-8", errors="replace")\n'
                          '            except OSError:\n'
                          '                continue\n'
                          '            m = rx.search(text)\n'
                          '            if m:\n'
                          '                line = text.count("\\n", 0, m.start()) + 1\n'
                          '                findings.append({\n'
                          '                    "rule": str(rule.get("id", "unnamed")),\n'
                          '                    "path": rel,\n'
                          '                    "line": line,\n'
                          '                    "message": str(rule.get("message", "architecture rule violated")),\n'
                          '                })\n'
                          '    return mode, findings\n'
                          '\n'
                          '\n'
                          'def main() -> int:\n'
                          '    ap = argparse.ArgumentParser(description="Changed-file architecture ratchet")\n'
                          '    ap.add_argument("--all", action="store_true", help="Scan all workspace files instead of changed files")\n'
                          '    ap.add_argument("--json", action="store_true")\n'
                          '    args = ap.parse_args()\n'
                          '    mode, findings = run(args.all)\n'
                          '    if args.json:\n'
                          '        print(json.dumps({"mode": mode, "findings": findings}, ensure_ascii=False, separators=(",", ":")))\n'
                          '    else:\n'
                          '        print(f"Architecture check: {len(findings)} finding(s), mode={mode}")\n'
                          '        for f in findings[:30]:\n'
                          '            loc = f"{f[\'path\']}:{f.get(\'line\', \'?\')}"\n'
                          '            print(f"- [{f[\'rule\']}] {loc} {f[\'message\']}")\n'
                          '        if len(findings) > 30:\n'
                          '            print(f"... {len(findings)-30} more")\n'
                          '    return 1 if findings and mode == "enforce" else 0\n'
                          '\n'
                          '\n'
                          'if __name__ == "__main__":\n'
                          '    raise SystemExit(main())\n',
 'codex-project': '#!/usr/bin/env sh\n'
                  'set -eu\n'
                  'export PYTHONDONTWRITEBYTECODE=1\n'
                  'ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)\n'
                  'cd "$ROOT"\n'
                  'exec codex "$@"\n',
 'harness_hook.py': '#!/usr/bin/env python3\n'
                    'from __future__ import annotations\n'
                    '\n'
                    'import fnmatch\n'
                    'import hashlib\n'
                    'import json\n'
                    'import re\n'
                    'import sys\n'
                    'import time\n'
                    'from pathlib import Path\n'
                    '\n'
                    'SCRIPT_DIR = Path(__file__).resolve().parent\n'
                    'HARNESS_DIR = SCRIPT_DIR.parent\n'
                    'WORKSPACE_ROOT = HARNESS_DIR.parents[1]\n'
                    'sys.path.insert(0, str(HARNESS_DIR / "scripts"))\n'
                    'from common import config, load_json, repo_state_hash, diff_stats, changed_paths, RUNTIME_DIR, git_roots\n'
                    '\n'
                    'CORRECTION_MARKERS = ("違う", "ではない", "そうではなく", "間違", "誤り", "訂正", "前にも", "以前も", "改善されていない", "not what i meant", '
                    '"that\'s wrong", "that is wrong", "incorrect", "correction")\n'
                    'WORK_MARKERS = ("実装", "修正", "変更", "追加", "作成", "移行", "調査", "原因", "判断", "決定", "検証", "テスト", "未完了", "implemented", '
                    '"fixed", "changed", "added", "created", "investigated", "root cause", "decision", "verified", "tested")\n'
                    'ARTIFACT_PATTERN = '
                    're.compile(r"(?:`[^`]*(?:/|\\.(?:php|js|ts|tsx|vue|md|json|ya?ml|py))[^`]*`|\\b(?:AGENTS\\.md|git|docker|artisan|pytest|unittest)\\b)", '
                    're.I)\n'
                    '\n'
                    '\n'
                    'def runtime_file(name):\n'
                    '    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)\n'
                    '    return RUNTIME_DIR / name\n'
                    '\n'
                    '\n'
                    'def version() -> str:\n'
                    '    try:\n'
                    '        return (HARNESS_DIR / "VERSION").read_text(encoding="utf-8").strip()\n'
                    '    except Exception:\n'
                    '        return "unknown"\n'
                    '\n'
                    '\n'
                    'def session_start(event, cfg):\n'
                    '    sid = event.get("session_id", "unknown")\n'
                    '    state = runtime_file(f"session-{sid}.json")\n'
                    '    if not state.exists():\n'
                    '        state.write_text(json.dumps({"baseline_state_hash": repo_state_hash(cfg), "created_at": time.time()}, '
                    'indent=2), encoding="utf-8")\n'
                    '    layout = cfg.get("project_layout", {})\n'
                    '    roots = ", ".join(layout.get("git_roots", [])) or "auto-detect"\n'
                    '    app = layout.get("application_root", ".")\n'
                    '    knowledge = layout.get("knowledge_root", "docs")\n'
                    '    status = load_json(HARNESS_DIR / "commands.json", {}).get("status", "uninitialized")\n'
                    '    context = (\n'
                    '        f"Adaptive Codex Harness v{version()} active. Workspace `{WORKSPACE_ROOT}`; application root `{app}`; Git '
                    'root(s): {roots}. "\n'
                    '        f"Read `{knowledge}/index.md` only as a map, then only task-relevant records. Verification commands: '
                    '{status}. "\n'
                    '    )\n'
                    '    detected = git_roots(cfg)\n'
                    '    if detected and all(p != WORKSPACE_ROOT for p in detected):\n'
                    '        context += "Workspace and Git root differ; keep workspace-root Harness instructions/config in scope and avoid '
                    'treating the application Git root as the whole workspace. "\n'
                    '    if status != "ready":\n'
                    '        context += "Before substantial edits, use `$harness-bootstrap` and confirm real project commands. "\n'
                    '    context += (\n'
                    '        "Use one Sol-high parent by default; at most two narrow independent subagents only when materially faster. "\n'
                    '        "Use bounded output, targeted checks during iteration, the final deterministic gate once, and bounded '
                    'independent review only when required. "\n'
                    '        "Avoid scope creep, routine Knowledge writes, and bypassing safety rules."\n'
                    '    )\n'
                    '    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}\n'
                    '\n'
                    '\n'
                    'def user_prompt(event):\n'
                    '    prompt = event.get("prompt") or ""\n'
                    '    normalized = prompt.casefold()\n'
                    '    if not any(m in normalized for m in CORRECTION_MARKERS):\n'
                    '        return {}\n'
                    '    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "This prompt may contain '
                    'a reusable correction. Verify it against current code/config/tests/runtime; if durable, use '
                    '`$maintain-project-knowledge`. Keep one-off observations transient."}}\n'
                    '\n'
                    '\n'
                    'def subagent_stop(event, cfg):\n'
                    '    if event.get("agent_type") != "reviewer":\n'
                    '        return {"continue": True, "suppressOutput": True}\n'
                    '    message = event.get("last_assistant_message") or ""\n'
                    '    if "VERDICT: PASS" in message:\n'
                    '        runtime_file("review-stamp.json").write_text(json.dumps({"state_hash": repo_state_hash(cfg), "timestamp": '
                    'time.time(), "agent_id": event.get("agent_id")}, indent=2), encoding="utf-8")\n'
                    '    return {"continue": True, "suppressOutput": True}\n'
                    '\n'
                    '\n'
                    'def is_substantive(message):\n'
                    '    normalized = (message or "").casefold().strip()\n'
                    '    return len(normalized) >= 160 and any(m in normalized for m in WORK_MARKERS) and '
                    'bool(ARTIFACT_PATTERN.search(message or ""))\n'
                    '\n'
                    '\n'
                    'def _matches_any(path: str, patterns: list[str]) -> bool:\n'
                    '    return any(fnmatch.fnmatch(path, p) for p in patterns)\n'
                    '\n'
                    '\n'
                    'def needs_verification(cfg) -> bool:\n'
                    '    paths = changed_paths(cfg)\n'
                    '    if not paths:\n'
                    '        return False\n'
                    '    gate = cfg.get("quality_gate", {})\n'
                    '    exempt = gate.get("verification_exempt_globs", ["docs/**", "memo/**", "**/*.md"])\n'
                    '    return any(not _matches_any(path, exempt) for path in paths)\n'
                    '\n'
                    '\n'
                    'def needs_review(cfg):\n'
                    '    gate = cfg.get("quality_gate", {})\n'
                    '    files, lines = diff_stats(cfg)\n'
                    '    threshold = gate.get("nontrivial", {})\n'
                    '    if files >= int(threshold.get("changed_files", 8)) or lines >= int(threshold.get("changed_lines", 200)):\n'
                    '        return True\n'
                    '    for path in changed_paths(cfg):\n'
                    '        for pat in gate.get("always_review_globs", []):\n'
                    '            if fnmatch.fnmatch(path, pat):\n'
                    '                return True\n'
                    '    return False\n'
                    '\n'
                    '\n'
                    'def stop(event, cfg):\n'
                    '    gate = cfg.get("quality_gate", {})\n'
                    '    sid = event.get("session_id", "unknown")\n'
                    '    session = load_json(runtime_file(f"session-{sid}.json"), {})\n'
                    '    baseline = session.get("baseline_state_hash")\n'
                    '    current = repo_state_hash(cfg)\n'
                    '    changed = bool(baseline and current != baseline)\n'
                    '\n'
                    '    if gate.get("enabled", True) and changed:\n'
                    '        missing = []\n'
                    '        if gate.get("require_verification", True) and needs_verification(cfg):\n'
                    '            stamp = load_json(runtime_file("verify-stamp.json"), {})\n'
                    '            if stamp.get("state_hash") != current or not stamp.get("passed"):\n'
                    '                missing.append("run `python3 .codex/harness/scripts/verify.py` and resolve failures caused by the '
                    'current task")\n'
                    '        if gate.get("require_independent_review", True) and needs_review(cfg):\n'
                    '            stamp = load_json(runtime_file("review-stamp.json"), {})\n'
                    '            if stamp.get("state_hash") != current:\n'
                    '                missing.append("use at most one bounded independent reviewer only when current-task risk justifies '
                    'it")\n'
                    '        if missing:\n'
                    '            key = hashlib.sha256((sid + current).encode()).hexdigest()[:20]\n'
                    '            counter_path = runtime_file(f"stop-block-{key}.json")\n'
                    '            counter = load_json(counter_path, {"count": 0})\n'
                    '            count = int(counter.get("count", 0))\n'
                    '            max_blocks = int(gate.get("max_stop_blocks_per_diff", 1))\n'
                    '            if count < max_blocks:\n'
                    '                counter_path.write_text(json.dumps({"count": count + 1, "timestamp": time.time()}, indent=2), '
                    'encoding="utf-8")\n'
                    '                return {"decision": "block", "reason": "Adaptive Harness advisory quality policy: validate the '
                    'current task first. Resolve only failures caused by the current task. Do not modify unrelated pre-existing '
                    'dirty-worktree changes or failures; report them as non-blocking instead. Use targeted verification for small/low-risk '
                    'changes. Run full verification only when the current task is broad/high-risk or targeted verification is '
                    'insufficient. Spawn one bounded independent `reviewer` only for broad/high-risk changes (for example: >=5 '
                    'task-touched files, >=200 task diff lines, auth/permission/security, migration/schema, cross-service/repository '
                    'behavior, or an explicit review request). A reviewer is not required for a small low-risk fix with adequate targeted '
                    'verification. Later edits invalidate only the verification/review evidence relevant to those edits."}\n'
                    '            return {"continue": True, "suppressOutput": True}\n'
                    '\n'
                    '    knowledge_cfg = cfg.get("knowledge", {})\n'
                    '    if knowledge_cfg.get("stop_checkpoint", "advisory") == "blocking" and not event.get("stop_hook_active") and '
                    'is_substantive(event.get("last_assistant_message") or ""):\n'
                    '        return {"decision": "block", "reason": "Perform one durable project-knowledge review. If nothing reusable was '
                    'learned, finish without writing."}\n'
                    '    return {"continue": True, "suppressOutput": True}\n'
                    '\n'
                    '\n'
                    'def response_for(event):\n'
                    '    cfg = config(); name = event.get("hook_event_name")\n'
                    '    if name == "SessionStart": return session_start(event, cfg)\n'
                    '    if name == "UserPromptSubmit": return user_prompt(event)\n'
                    '    if name == "SubagentStop": return subagent_stop(event, cfg)\n'
                    '    if name == "Stop": return stop(event, cfg)\n'
                    '    return {}\n'
                    '\n'
                    '\n'
                    'def main():\n'
                    '    try:\n'
                    '        event = json.load(sys.stdin)\n'
                    '        response = response_for(event if isinstance(event, dict) else {})\n'
                    '    except Exception:\n'
                    '        response = {}\n'
                    '    json.dump(response, sys.stdout, ensure_ascii=False, separators=(",", ":")); sys.stdout.write("\\n")\n'
                    '    return 0\n'
                    '\n'
                    '\n'
                    'if __name__ == "__main__":\n'
                    '    raise SystemExit(main())\n',
 'minimal_diff_guard.py': '#!/usr/bin/env python3\n'
                          'from __future__ import annotations\n'
                          '\n'
                          'import argparse\n'
                          'import difflib\n'
                          'import fnmatch\n'
                          'import hashlib\n'
                          'import json\n'
                          'import subprocess\n'
                          'import sys\n'
                          'from dataclasses import dataclass\n'
                          'from pathlib import Path\n'
                          'from typing import Any\n'
                          '\n'
                          'ROOT = Path(__file__).resolve().parents[3]\n'
                          'POLICY_PATH = ROOT / ".codex" / "harness" / "minimal_edit_policy.json"\n'
                          'CONFIG_PATH = ROOT / ".codex" / "harness" / "config.json"\n'
                          'TASK_SCOPE = ROOT / ".harness" / "runtime" / "task_scope" / "current.json"\n'
                          '\n'
                          'DEFAULT = {\n'
                          '    "min_original_lines": 40,\n'
                          '    "min_deleted_lines": 30,\n'
                          '    "min_added_lines": 15,\n'
                          '    "major_delete_ratio": 0.60,\n'
                          '    "rewrite_churn_ratio": 0.90,\n'
                          '    "low_similarity_ratio": 0.55,\n'
                          '    "mode": "fail",\n'
                          '    "task_scope_aware": True,\n'
                          '    "allowlist_globs": [\n'
                          '        "*.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "composer.lock",\n'
                          '        "*.min.js", "*.min.css", "*.map", "dist/**", "build/**", "coverage/**", ".harness/**",\n'
                          '    ],\n'
                          '}\n'
                          '\n'
                          'TEXT_SUFFIXES = {\n'
                          '    ".php", ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".md", ".txt",\n'
                          '    ".json", ".toml", ".yaml", ".yml", ".xml", ".ini", ".conf", ".css",\n'
                          '    ".scss", ".html", ".htm", ".sql", ".sh", ".bash", ".zsh", ".rules",\n'
                          '}\n'
                          '\n'
                          '\n'
                          '@dataclass(frozen=True)\n'
                          'class Candidate:\n'
                          '    root: Path\n'
                          '    repo_path: str\n'
                          '    display_path: str\n'
                          '\n'
                          '\n'
                          'def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:\n'
                          '    return subprocess.run(args, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n'
                          '\n'
                          '\n'
                          'def load_json(path: Path) -> dict[str, Any]:\n'
                          '    try:\n'
                          '        raw = json.loads(path.read_text(encoding="utf-8"))\n'
                          '        return raw if isinstance(raw, dict) else {}\n'
                          '    except Exception:\n'
                          '        return {}\n'
                          '\n'
                          '\n'
                          'def load_policy() -> dict[str, Any]:\n'
                          '    cfg = dict(DEFAULT)\n'
                          '    raw = load_json(POLICY_PATH)\n'
                          '    guard = raw.get("guard", raw)\n'
                          '    if isinstance(guard, dict):\n'
                          '        for key in DEFAULT:\n'
                          '            if key in guard:\n'
                          '                cfg[key] = guard[key]\n'
                          '    return cfg\n'
                          '\n'
                          '\n'
                          'def norm(path: str) -> str:\n'
                          '    value = path.replace("\\\\", "/")\n'
                          '    while value.startswith("./"):\n'
                          '        value = value[2:]\n'
                          '    return value\n'
                          '\n'
                          '\n'
                          'def root_key(root: Path) -> str:\n'
                          '    try:\n'
                          '        rel = root.relative_to(ROOT).as_posix()\n'
                          '        return "." if rel == "." else rel\n'
                          '    except ValueError:\n'
                          '        return str(root)\n'
                          '\n'
                          '\n'
                          'def display_path(root: Path, repo_path: str) -> str:\n'
                          '    key = root_key(root)\n'
                          '    return norm(repo_path) if key == "." else f"{key}/{norm(repo_path)}"\n'
                          '\n'
                          '\n'
                          'def git_roots() -> list[Path]:\n'
                          '    roots: list[Path] = []\n'
                          '    cfg = load_json(CONFIG_PATH)\n'
                          '    values = cfg.get("project_layout", {}).get("git_roots", [])\n'
                          '    if isinstance(values, list):\n'
                          '        for value in values:\n'
                          '            if not isinstance(value, str) or not value.strip():\n'
                          '                continue\n'
                          '            root = ROOT if value == "." else (ROOT / value).resolve()\n'
                          '            if (root / ".git").exists() and root not in roots:\n'
                          '                roots.append(root)\n'
                          '    if (ROOT / ".git").exists() and ROOT not in roots:\n'
                          '        roots.append(ROOT)\n'
                          '    if not roots:\n'
                          '        for child in ROOT.iterdir():\n'
                          '            if child.is_dir() and (child / ".git").exists():\n'
                          '                roots.append(child.resolve())\n'
                          '    return roots\n'
                          '\n'
                          '\n'
                          'def matches_any(path: str, patterns: list[str]) -> bool:\n'
                          '    p = norm(path)\n'
                          '    return any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(Path(p).name, pat) for pat in patterns)\n'
                          '\n'
                          '\n'
                          'def digest(path: Path) -> str:\n'
                          '    if not path.exists() or not path.is_file():\n'
                          '        return "<missing>"\n'
                          '    h = hashlib.sha256()\n'
                          '    try:\n'
                          '        with path.open("rb") as f:\n'
                          '            for block in iter(lambda: f.read(1024 * 1024), b""):\n'
                          '                h.update(block)\n'
                          '        return h.hexdigest()\n'
                          '    except OSError:\n'
                          '        return "<unreadable>"\n'
                          '\n'
                          '\n'
                          'def status_paths(root: Path) -> set[str]:\n'
                          '    cp = run(root, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all")\n'
                          '    if cp.returncode != 0:\n'
                          '        return set()\n'
                          '    chunks = cp.stdout.split("\\0")\n'
                          '    out: set[str] = set()\n'
                          '    i = 0\n'
                          '    while i < len(chunks):\n'
                          '        item = chunks[i]\n'
                          '        if not item:\n'
                          '            i += 1\n'
                          '            continue\n'
                          '        if len(item) >= 4:\n'
                          '            code, path = item[:2], item[3:]\n'
                          '            out.add(norm(path))\n'
                          '            if (code.startswith("R") or code.startswith("C")) and i + 1 < len(chunks) and chunks[i + 1]:\n'
                          '                out.add(norm(chunks[i + 1]))\n'
                          '                i += 1\n'
                          '        i += 1\n'
                          '    return out\n'
                          '\n'
                          '\n'
                          'def baseline_dirty(root: Path) -> dict[str, str]:\n'
                          '    data = load_json(TASK_SCOPE)\n'
                          '    roots = data.get("roots", {})\n'
                          '    if not isinstance(roots, dict):\n'
                          '        return {}\n'
                          '    entry = roots.get(root_key(root), {})\n'
                          '    dirty = entry.get("dirty", {}) if isinstance(entry, dict) else {}\n'
                          '    return {norm(k): str(v) for k, v in dirty.items()} if isinstance(dirty, dict) else {}\n'
                          '\n'
                          '\n'
                          'def task_touched_candidates(cfg: dict[str, Any]) -> list[Candidate]:\n'
                          '    out: dict[str, Candidate] = {}\n'
                          '    for root in git_roots():\n'
                          '        now = status_paths(root)\n'
                          '        base = baseline_dirty(root) if cfg.get("task_scope_aware", True) else {}\n'
                          '        if not base:\n'
                          '            touched = now\n'
                          '        else:\n'
                          '            touched = set()\n'
                          '            for p in now | set(base):\n'
                          '                current = digest(root / p) if p in now else "<clean>"\n'
                          '                before = base.get(p, "<clean>")\n'
                          '                if current != before:\n'
                          '                    touched.add(p)\n'
                          '        for repo_path in touched:\n'
                          '            candidate = Candidate(root, norm(repo_path), display_path(root, repo_path))\n'
                          '            out[candidate.display_path] = candidate\n'
                          '    return [out[k] for k in sorted(out)]\n'
                          '\n'
                          '\n'
                          'def candidate_for_arg(raw: str, roots: list[Path]) -> Candidate | None:\n'
                          '    p = Path(raw)\n'
                          '    absolute = p.resolve() if p.is_absolute() else (ROOT / p).resolve()\n'
                          '    owners = []\n'
                          '    for root in roots:\n'
                          '        try:\n'
                          '            repo_rel = absolute.relative_to(root).as_posix()\n'
                          '            owners.append((root, repo_rel))\n'
                          '        except ValueError:\n'
                          '            continue\n'
                          '    if owners:\n'
                          '        root, repo_rel = max(owners, key=lambda item: len(item[0].parts))\n'
                          '        return Candidate(root, norm(repo_rel), display_path(root, repo_rel))\n'
                          '    if len(roots) == 1:\n'
                          '        root = roots[0]\n'
                          '        repo_rel = norm(raw)\n'
                          '        return Candidate(root, repo_rel, display_path(root, repo_rel))\n'
                          '    return None\n'
                          '\n'
                          '\n'
                          'def is_tracked_at_head(candidate: Candidate) -> bool:\n'
                          '    return run(candidate.root, "git", "cat-file", "-e", f"HEAD:{candidate.repo_path}").returncode == 0\n'
                          '\n'
                          '\n'
                          'def read_head_lines(candidate: Candidate) -> list[str] | None:\n'
                          '    cp = run(candidate.root, "git", "show", f"HEAD:{candidate.repo_path}")\n'
                          '    return cp.stdout.splitlines() if cp.returncode == 0 else None\n'
                          '\n'
                          '\n'
                          'def read_worktree_lines(candidate: Candidate) -> list[str] | None:\n'
                          '    p = candidate.root / candidate.repo_path\n'
                          '    if not p.exists() or not p.is_file():\n'
                          '        return None\n'
                          '    try:\n'
                          '        raw = p.read_bytes()\n'
                          '        if b"\\x00" in raw[:8192]:\n'
                          '            return None\n'
                          '        return raw.decode("utf-8", errors="replace").splitlines()\n'
                          '    except OSError:\n'
                          '        return None\n'
                          '\n'
                          '\n'
                          'def is_text_candidate(path: str) -> bool:\n'
                          '    low = path.lower()\n'
                          '    p = Path(low)\n'
                          '    if p.name in {"dockerfile", "makefile", "agents.md"} or low.endswith(".blade.php"):\n'
                          '        return True\n'
                          '    return p.suffix in TEXT_SUFFIXES or not p.suffix\n'
                          '\n'
                          '\n'
                          'def numstat(candidate: Candidate) -> tuple[int, int] | None:\n'
                          '    cp = run(candidate.root, "git", "diff", "HEAD", "--numstat", "--", candidate.repo_path)\n'
                          '    if cp.returncode != 0 or not cp.stdout.strip():\n'
                          '        return None\n'
                          '    first = cp.stdout.splitlines()[0].split("\\t")\n'
                          '    if len(first) < 2 or first[0] == "-" or first[1] == "-":\n'
                          '        return None\n'
                          '    try:\n'
                          '        return int(first[0]), int(first[1])\n'
                          '    except ValueError:\n'
                          '        return None\n'
                          '\n'
                          '\n'
                          'def suspicious(candidate: Candidate, cfg: dict[str, Any]) -> dict[str, Any] | None:\n'
                          '    if matches_any(candidate.display_path, list(cfg.get("allowlist_globs", []))):\n'
                          '        return None\n'
                          '    if not is_text_candidate(candidate.repo_path) or not is_tracked_at_head(candidate):\n'
                          '        return None\n'
                          '\n'
                          '    old = read_head_lines(candidate)\n'
                          '    new = read_worktree_lines(candidate)\n'
                          '    if old is None or new is None:\n'
                          '        return None\n'
                          '    original = len(old)\n'
                          '    if original < int(cfg["min_original_lines"]):\n'
                          '        return None\n'
                          '\n'
                          '    ns = numstat(candidate)\n'
                          '    if ns is None:\n'
                          '        return None\n'
                          '    added, deleted = ns\n'
                          '    if deleted < int(cfg["min_deleted_lines"]) or added < int(cfg["min_added_lines"]):\n'
                          '        return None\n'
                          '\n'
                          '    delete_ratio = deleted / max(original, 1)\n'
                          '    churn_ratio = (added + deleted) / max(original, 1)\n'
                          '    similarity = difflib.SequenceMatcher(a=old, b=new, autojunk=False).ratio()\n'
                          '\n'
                          '    major_replacement = delete_ratio >= float(cfg["major_delete_ratio"])\n'
                          '    low_similarity_churn = (\n'
                          '        churn_ratio >= float(cfg["rewrite_churn_ratio"])\n'
                          '        and similarity <= float(cfg["low_similarity_ratio"])\n'
                          '    )\n'
                          '    if not (major_replacement or low_similarity_churn):\n'
                          '        return None\n'
                          '\n'
                          '    return {\n'
                          '        "path": candidate.display_path,\n'
                          '        "git_root": root_key(candidate.root),\n'
                          '        "original_lines": original,\n'
                          '        "current_lines": len(new),\n'
                          '        "added": added,\n'
                          '        "deleted": deleted,\n'
                          '        "delete_ratio": delete_ratio,\n'
                          '        "churn_ratio": churn_ratio,\n'
                          '        "similarity": similarity,\n'
                          '    }\n'
                          '\n'
                          '\n'
                          'def main() -> int:\n'
                          '    ap = argparse.ArgumentParser(description="Detect rewrite-like churn in existing tracked text files")\n'
                          '    ap.add_argument("--json", action="store_true")\n'
                          '    ap.add_argument("--quiet", action="store_true")\n'
                          '    ap.add_argument("--warn-only", action="store_true")\n'
                          '    ap.add_argument("--path", action="append", default=[])\n'
                          '    args = ap.parse_args()\n'
                          '\n'
                          '    roots = git_roots()\n'
                          '    if not roots:\n'
                          '        if not args.quiet:\n'
                          '            print("[minimal-diff] no configured/detected Git root; skipped")\n'
                          '        return 0\n'
                          '\n'
                          '    cfg = load_policy()\n'
                          '    if args.path:\n'
                          '        candidates = [c for raw in args.path if (c := candidate_for_arg(raw, roots)) is not None]\n'
                          '    else:\n'
                          '        candidates = task_touched_candidates(cfg)\n'
                          '    findings = [f for c in candidates if (f := suspicious(c, cfg)) is not None]\n'
                          '\n'
                          '    if args.json:\n'
                          '        print(json.dumps({\n'
                          '            "git_roots": [root_key(r) for r in roots],\n'
                          '            "checked_paths": len(candidates),\n'
                          '            "findings": findings,\n'
                          '        }, ensure_ascii=False, indent=2))\n'
                          '    elif findings:\n'
                          '        print("[minimal-diff:BLOCK] rewrite-like existing-file edits detected", file=sys.stderr)\n'
                          '        for f in findings:\n'
                          '            print(\n'
                          '                "  - {path}: +{added} -{deleted}, original={original_lines}, "\n'
                          '                "delete={delete_ratio:.0%}, similarity={similarity:.0%}".format(**f),\n'
                          '                file=sys.stderr,\n'
                          '            )\n'
                          '        print(\n'
                          '            "Re-edit only the required lines/blocks. Do not self-allowlist the file. "\n'
                          '            "A deliberate full rewrite needs a maintainer/user allowlist decision.",\n'
                          '            file=sys.stderr,\n'
                          '        )\n'
                          '    elif not args.quiet:\n'
                          '        roots_text = ", ".join(root_key(r) for r in roots)\n'
                          '        print(f"[minimal-diff:PASS] checked {len(candidates)} changed path(s) across Git root(s): '
                          '{roots_text}")\n'
                          '\n'
                          '    if findings and not args.warn_only and str(cfg.get("mode", "fail")).lower() == "fail":\n'
                          '        return 2\n'
                          '    return 0\n'
                          '\n'
                          '\n'
                          'if __name__ == "__main__":\n'
                          '    raise SystemExit(main())\n',
 'minimal_edit_pretool.py': '#!/usr/bin/env python3\n'
                            'from __future__ import annotations\n'
                            '\n'
                            'import json\n'
                            'import re\n'
                            'import subprocess\n'
                            'import sys\n'
                            'from pathlib import Path\n'
                            'from typing import Any\n'
                            '\n'
                            'WORKSPACE_ROOT = Path(__file__).resolve().parents[3]\n'
                            'CONFIG_PATH = WORKSPACE_ROOT / ".codex" / "harness" / "config.json"\n'
                            'MIN_EXISTING_LINES = 40\n'
                            'LARGE_EDIT_COVERAGE = 0.80\n'
                            'PROTECTED = (\n'
                            '    ".codex/harness/scripts/minimal_diff_guard.py",\n'
                            '    ".codex/harness/hooks/minimal_edit_pretool.py",\n'
                            '    ".codex/harness/minimal_edit_policy.json",\n'
                            ')\n'
                            '\n'
                            '\n'
                            'def deny(reason: str) -> int:\n'
                            '    print(json.dumps({\n'
                            '        "hookSpecificOutput": {\n'
                            '            "hookEventName": "PreToolUse",\n'
                            '            "permissionDecision": "deny",\n'
                            '            "permissionDecisionReason": reason,\n'
                            '        }\n'
                            '    }, ensure_ascii=False))\n'
                            '    return 0\n'
                            '\n'
                            '\n'
                            'def load_config() -> dict[str, Any]:\n'
                            '    try:\n'
                            '        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))\n'
                            '        return raw if isinstance(raw, dict) else {}\n'
                            '    except Exception:\n'
                            '        return {}\n'
                            '\n'
                            '\n'
                            'def configured_git_roots() -> list[Path]:\n'
                            '    roots: list[Path] = []\n'
                            '    cfg = load_config()\n'
                            '    values = cfg.get("project_layout", {}).get("git_roots", [])\n'
                            '    if isinstance(values, list):\n'
                            '        for value in values:\n'
                            '            if not isinstance(value, str) or not value.strip():\n'
                            '                continue\n'
                            '            root = WORKSPACE_ROOT if value == "." else (WORKSPACE_ROOT / value).resolve()\n'
                            '            if (root / ".git").exists() and root not in roots:\n'
                            '                roots.append(root)\n'
                            '    if (WORKSPACE_ROOT / ".git").exists() and WORKSPACE_ROOT not in roots:\n'
                            '        roots.append(WORKSPACE_ROOT)\n'
                            '    if not roots:\n'
                            '        for child in WORKSPACE_ROOT.iterdir():\n'
                            '            if child.is_dir() and (child / ".git").exists():\n'
                            '                roots.append(child.resolve())\n'
                            '    return roots\n'
                            '\n'
                            '\n'
                            'def owning_git_root(path: Path) -> Path | None:\n'
                            '    candidates = []\n'
                            '    for root in configured_git_roots():\n'
                            '        try:\n'
                            '            path.relative_to(root)\n'
                            '            candidates.append(root)\n'
                            '        except ValueError:\n'
                            '            continue\n'
                            '    if candidates:\n'
                            '        return max(candidates, key=lambda p: len(p.parts))\n'
                            '    try:\n'
                            '        cp = subprocess.run(\n'
                            '            ["git", "-C", str(path.parent if path.suffix else path), "rev-parse", "--show-toplevel"],\n'
                            '            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,\n'
                            '        )\n'
                            '        return Path(cp.stdout.strip()).resolve() if cp.returncode == 0 else None\n'
                            '    except OSError:\n'
                            '        return None\n'
                            '\n'
                            '\n'
                            'def all_strings(obj: Any) -> list[str]:\n'
                            '    out: list[str] = []\n'
                            '    if isinstance(obj, str):\n'
                            '        out.append(obj)\n'
                            '    elif isinstance(obj, dict):\n'
                            '        for value in obj.values():\n'
                            '            out.extend(all_strings(value))\n'
                            '    elif isinstance(obj, list):\n'
                            '        for value in obj:\n'
                            '            out.extend(all_strings(value))\n'
                            '    return out\n'
                            '\n'
                            '\n'
                            'def extract_path(tool_input: dict[str, Any]) -> str | None:\n'
                            '    for key in ("file_path", "path", "filename", "file"):\n'
                            '        value = tool_input.get(key)\n'
                            '        if isinstance(value, str) and value.strip():\n'
                            '            return value.strip()\n'
                            '    return None\n'
                            '\n'
                            '\n'
                            'def resolve(raw: str, cwd: Path | None = None) -> Path:\n'
                            '    p = Path(raw)\n'
                            '    if p.is_absolute():\n'
                            '        return p.resolve()\n'
                            '    if cwd is not None:\n'
                            '        candidate = (cwd / p).resolve()\n'
                            '        if candidate.exists() or owning_git_root(candidate) is not None:\n'
                            '            return candidate\n'
                            '    return (WORKSPACE_ROOT / p).resolve()\n'
                            '\n'
                            '\n'
                            'def tracked(root: Path, path: Path) -> bool:\n'
                            '    try:\n'
                            '        rel = path.relative_to(root).as_posix()\n'
                            '    except ValueError:\n'
                            '        return False\n'
                            '    cp = subprocess.run(\n'
                            '        ["git", "-C", str(root), "cat-file", "-e", f"HEAD:{rel}"],\n'
                            '        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n'
                            '    )\n'
                            '    return cp.returncode == 0\n'
                            '\n'
                            '\n'
                            'def line_count(path: Path) -> int:\n'
                            '    try:\n'
                            '        raw = path.read_bytes()\n'
                            '        if b"\\x00" in raw[:8192]:\n'
                            '            return 0\n'
                            '        return len(raw.decode("utf-8", errors="replace").splitlines())\n'
                            '    except OSError:\n'
                            '        return 0\n'
                            '\n'
                            '\n'
                            'def patch_text(tool_input: dict[str, Any]) -> str:\n'
                            '    joined = "\\n".join(all_strings(tool_input))\n'
                            '    return joined if ("*** Update File:" in joined or "@@" in joined) else ""\n'
                            '\n'
                            '\n'
                            'def rewrite_like_patch(text: str, cwd: Path) -> str | None:\n'
                            '    blocks = re.split(r"(?=^\\*\\*\\* Update File: )", text, flags=re.M)\n'
                            '    for block in blocks:\n'
                            '        m = re.match(r"^\\*\\*\\* Update File:\\s*(.+?)\\s*$", block, flags=re.M)\n'
                            '        if not m:\n'
                            '            continue\n'
                            '        raw = m.group(1).strip()\n'
                            '        path = resolve(raw, cwd)\n'
                            '        root = owning_git_root(path)\n'
                            '        if root is None or not path.exists() or not tracked(root, path):\n'
                            '            continue\n'
                            '        original = line_count(path)\n'
                            '        if original < MIN_EXISTING_LINES:\n'
                            '            continue\n'
                            '        deleted = sum(1 for line in block.splitlines() if line.startswith("-") and not '
                            'line.startswith("---"))\n'
                            '        added = sum(1 for line in block.splitlines() if line.startswith("+") and not line.startswith("+++"))\n'
                            '        if deleted >= max(30, int(original * 0.60)) and added >= 15:\n'
                            '            return (\n'
                            '                f"{raw}: patch removes {deleted}/{original} existing lines and adds {added}. "\n'
                            '                "Preserve unchanged content and patch only the required lines/blocks."\n'
                            '            )\n'
                            '    return None\n'
                            '\n'
                            '\n'
                            'def _first_string(tool_input: dict[str, Any], keys: tuple[str, ...]) -> str | None:\n'
                            '    for key in keys:\n'
                            '        value = tool_input.get(key)\n'
                            '        if isinstance(value, str):\n'
                            '            return value\n'
                            '    return None\n'
                            '\n'
                            '\n'
                            'def rewrite_like_edit(tool_input: dict[str, Any], cwd: Path) -> str | None:\n'
                            '    raw = extract_path(tool_input)\n'
                            '    if not raw:\n'
                            '        return None\n'
                            '    path = resolve(raw, cwd)\n'
                            '    root = owning_git_root(path)\n'
                            '    if root is None or not path.exists() or not tracked(root, path):\n'
                            '        return None\n'
                            '    original = line_count(path)\n'
                            '    if original < MIN_EXISTING_LINES:\n'
                            '        return None\n'
                            '    old = _first_string(tool_input, ("old_string", "oldText", "old_text", "before"))\n'
                            '    new = _first_string(tool_input, ("new_string", "newText", "new_text", "after"))\n'
                            '    if old is None or new is None:\n'
                            '        return None\n'
                            '    old_lines = len(old.splitlines())\n'
                            '    new_lines = len(new.splitlines())\n'
                            '    coverage = old_lines / max(original, 1)\n'
                            '    if coverage >= LARGE_EDIT_COVERAGE and old_lines >= 30 and new_lines >= 15:\n'
                            '        return (\n'
                            '            f"{raw}: Edit replaces about {coverage:.0%} of a {original}-line tracked file. "\n'
                            '            "Edit only the smallest required block instead of replacing nearly the whole file."\n'
                            '        )\n'
                            '    return None\n'
                            '\n'
                            '\n'
                            'def main() -> int:\n'
                            '    try:\n'
                            '        payload = json.load(sys.stdin)\n'
                            '    except Exception:\n'
                            '        return 0\n'
                            '\n'
                            '    tool_name = str(payload.get("tool_name") or "")\n'
                            '    tool_input = payload.get("tool_input") or {}\n'
                            '    if not isinstance(tool_input, dict):\n'
                            '        return 0\n'
                            '\n'
                            '    event_cwd = Path(payload.get("cwd") or WORKSPACE_ROOT).resolve()\n'
                            '    joined = "\\n".join(all_strings(tool_input)).lower()\n'
                            '    if tool_name in {"Write", "Edit", "apply_patch"} and any(p.lower() in joined for p in PROTECTED):\n'
                            '        return deny(\n'
                            '            "Adaptive Harness v6.12 blocked direct editing of the minimal-diff guard/policy. "\n'
                            '            "Update guard infrastructure through the installer/maintainer path."\n'
                            '        )\n'
                            '\n'
                            '    if tool_name == "Write":\n'
                            '        raw = extract_path(tool_input)\n'
                            '        if raw:\n'
                            '            path = resolve(raw, event_cwd)\n'
                            '            root = owning_git_root(path)\n'
                            '            if root is not None and path.exists() and tracked(root, path):\n'
                            '                lines = line_count(path)\n'
                            '                if lines >= MIN_EXISTING_LINES:\n'
                            '                    return deny(\n'
                            '                        f"Adaptive Harness v6.12 blocked whole-file Write for existing tracked file "\n'
                            '                        f"{raw} ({lines} lines). Use Edit/apply_patch and modify only the necessary '
                            'lines/blocks."\n'
                            '                    )\n'
                            '        return 0\n'
                            '\n'
                            '    if tool_name == "Edit":\n'
                            '        reason = rewrite_like_edit(tool_input, event_cwd)\n'
                            '        return deny("Adaptive Harness v6.12 blocked rewrite-like Edit. " + reason) if reason else 0\n'
                            '\n'
                            '    if tool_name == "apply_patch":\n'
                            '        text = patch_text(tool_input)\n'
                            '        if text:\n'
                            '            reason = rewrite_like_patch(text, event_cwd)\n'
                            '            if reason:\n'
                            '                return deny("Adaptive Harness v6.12 blocked rewrite-like apply_patch. " + reason)\n'
                            '        return 0\n'
                            '\n'
                            '    return 0\n'
                            '\n'
                            '\n'
                            'if __name__ == "__main__":\n'
                            '    raise SystemExit(main())\n',
 'pre_tool_safety.py': '#!/usr/bin/env python3\n'
                       'from __future__ import annotations\n'
                       '\n'
                       'import json\n'
                       'import re\n'
                       'import sys\n'
                       'from pathlib import Path\n'
                       '\n'
                       'SAFE_WRAPPER = ".codex/harness/scripts/safe_test.py"\n'
                       '\n'
                       'TEST_PATTERNS = (\n'
                       '    re.compile(r"\\bphp\\s+(?:-[^\\s]+\\s+)*artisan\\s+test\\b", re.I),\n'
                       '    re.compile(r"(?:^|[\\s;&|])(?:\\./)?vendor/bin/(?:phpunit|pest)\\b", re.I),\n'
                       '    re.compile(r"(?:^|[\\s;&|])(?:phpunit|pest)\\b", re.I),\n'
                       ')\n'
                       '\n'
                       'DANGEROUS_PATTERNS = (\n'
                       '    (re.compile(r"\\bphp\\s+artisan\\s+migrate(?:\\s|$)", re.I), "persistent migration"),\n'
                       '    '
                       '(re.compile(r"\\bphp\\s+artisan\\s+(?:migrate:fresh|migrate:refresh|migrate:reset|migrate:rollback|db:wipe|db:seed)\\b", '
                       're.I), "destructive/persistent Artisan DB command"),\n'
                       '    (re.compile(r"\\b(?:DROP\\s+(?:TABLE|DATABASE)|TRUNCATE\\s+(?:TABLE\\s+)?|ALTER\\s+TABLE|RENAME\\s+TABLE)\\b", '
                       're.I), "destructive SQL"),\n'
                       '    '
                       '(re.compile(r"\\bphp\\s+artisan\\s+(?:queue:work|queue:listen|queue:restart|schedule:run|schedule:work|horizon)\\b", '
                       're.I), "scheduler/queue worker execution"),\n'
                       '    (re.compile(r"(?:^|[;&|]\\s*)(?:sudo\\s+)?(?:lp|lpr|cancel|lpadmin|cupsenable|cupsdisable)\\b", re.I), '
                       '"printer/CUPS mutation"),\n'
                       '    (re.compile(r"(?:^|[;&|]\\s*)(?:sudo\\s+)?(?:sendmail|mail|mailx)\\b", re.I), "real mail submission"),\n'
                       '    (re.compile(r"\\bcurl\\b[^\\n;&|]*(?:-X|--request)\\s*(?:POST|PUT|PATCH|DELETE)\\b", re.I), "external HTTP '
                       'write"),\n'
                       '    (re.compile(r"\\bcurl\\b[^\\n;&|]*(?:--data(?:-raw|-binary|-urlencode)?|-d|-F|--form|--upload-file|-T)\\b", '
                       're.I), "external HTTP upload/write"),\n'
                       '    (re.compile(r"\\bwget\\b[^\\n;&|]*(?:--post-data|--post-file|--method\\s*=\\s*(?:POST|PUT|PATCH|DELETE))", '
                       're.I), "external HTTP write"),\n'
                       '    (re.compile(r"(?:^|[;&|]\\s*)(?:scp|sftp)\\b", re.I), "remote file transfer"),\n'
                       '    (re.compile(r"\\brsync\\b[^\\n;&|]*(?:\\w+@[\\w.-]+:|[\\w.-]+:[^/])", re.I), "remote rsync transfer"),\n'
                       '    '
                       '(re.compile(r"\\bsmbclient\\b[^\\n;&|]*(?:-c\\s+)?[\'\\"][^\'\\"]*\\b(?:put|mput|del|rm|rename|mkdir|rmdir)\\b", '
                       're.I), "SMB/NAS write"),\n'
                       '    (re.compile(r"(?:^|[;&|]\\s*)\\s*(?:sudo\\s+)?rm\\s+-[^\\n;&|]*r[^\\n;&|]*(?:f[^\\n;&|]*)?\\s+", re.I), '
                       '"recursive filesystem deletion"),\n'
                       '    (re.compile(r"\\bfind\\b[^\\n;&|]*\\s-delete\\b", re.I), "recursive filesystem deletion"),\n'
                       '    (re.compile(r"(?:^|[;&|]\\s*)\\s*(?:sudo\\s+)?shred\\b", re.I), "destructive file overwrite"),\n'
                       '    (re.compile(r"\\bdd\\b[^\\n;&|]*\\bof=", re.I), "raw file/device overwrite"),\n'
                       '    (re.compile(r"\\bgit\\s+reset\\s+--hard\\b", re.I), "destructive Git reset"),\n'
                       '    (re.compile(r"\\bgit\\s+clean\\b", re.I), "destructive Git clean"),\n'
                       '    (re.compile(r"\\bgit\\s+(?:checkout|restore)\\s+--?\\s*(?:\\.|:/)", re.I), "bulk Git worktree overwrite"),\n'
                       '    (re.compile(r"\\bgit\\s+push\\b[^\\n;&|]*(?:--force|-f)\\b", re.I), "force Git push"),\n'
                       '    (re.compile(r"docker\\s+(?:compose\\s+)?down\\b[^\\n;&|]*\\s(?:-v|--volumes)\\b", re.I), "Docker volume '
                       'deletion"),\n'
                       '    (re.compile(r"docker\\s+(?:volume|system|container)\\s+(?:rm|prune)\\b", re.I), "Docker persistent cleanup"),\n'
                       ')\n'
                       '\n'
                       'WRITE_SQL = '
                       're.compile(r"\\b(?:INSERT\\s+INTO|UPDATE\\s+\\w+\\s+SET|DELETE\\s+FROM|CREATE\\s+(?:TABLE|DATABASE)|DROP\\s+(?:TABLE|DATABASE)|TRUNCATE|ALTER\\s+TABLE)\\b", '
                       're.I)\n'
                       'DB_CLIENT_CMD = re.compile(\n'
                       '    r"(?:^|[;&|]\\s*)(?:sudo\\s+)?(?:mysql|mariadb|psql|sqlite3)\\b"\n'
                       '    r"|\\bdocker\\s+(?:compose\\s+)?exec\\b[^\\n;&|]*\\s(?:mysql|mariadb|psql|sqlite3)\\b",\n'
                       '    re.I,\n'
                       ')\n'
                       'TINKER = re.compile(r"\\bartisan\\s+tinker\\b", re.I)\n'
                       'SMBCLIENT = re.compile(r"(?:^|[;&|]\\s*)(?:sudo\\s+)?smbclient\\b", re.I)\n'
                       'CUSTOM_WRITE_ARTISAN = '
                       're.compile(r"\\bphp\\s+artisan\\s+[^\\s;&|]*(?:migrate|import|restore|repair|purge|delete|cleanup|seed|sync)[^\\s;&|]*", '
                       're.I)\n'
                       '\n'
                       'SMB_READ_ONLY_VERBS = {"ls", "dir", "stat", "allinfo", "pwd", "cd", "help", "?", "quit", "exit"}\n'
                       '\n'
                       'def smbclient_is_bounded_read_only(command: str) -> bool:\n'
                       '    """Allow only non-interactive smbclient -c scripts composed of read/navigation verbs."""\n'
                       '    m = re.search(r"\\bsmbclient\\b.*?\\s-c\\s+(?:\'([^\']*)\'|\\"([^\\"]*)\\")", command, re.I)\n'
                       '    if not m:\n'
                       '        return False\n'
                       '    script = m.group(1) if m.group(1) is not None else m.group(2)\n'
                       '    if script is None:\n'
                       '        return False\n'"    for statement in script.split(';'):\n"
                       '        statement = statement.strip()\n'
                       '        if not statement:\n'
                       '            continue\n'
                       '        verb = statement.split(None, 1)[0].lower()\n'
                       '        if verb not in SMB_READ_ONLY_VERBS:\n'
                       '            return False\n'
                       '    return True\n'
                       '\n'
                       'PROTECTED_PATHS = (\n'
                       '    ".codex/harness/hooks/pre_tool_safety.py",\n'
                       '    ".codex/harness/scripts/test_db_guard.py",\n'
                       '    ".codex/harness/scripts/side_effect_guard.py",\n'
                       '    ".codex/harness/scripts/safe_test.py",\n'
                       '    ".codex/harness/scripts/verify.py",\n'
                       '    ".codex/harness/v6_5_policy.json",\n'
                       '    ".codex/hooks.json",\n'
                       '    ".codex/rules/harness-side-effect-safety.rules",\n'
                       '    "tests/concerns/harnesssideeffectisolation.php",\n'
                       ')\n'
                       '\n'
                       'def deny(reason: str) -> int:\n'
                       '    print(json.dumps({\n'
                       '        "hookSpecificOutput": {\n'
                       '            "hookEventName": "PreToolUse",\n'
                       '            "permissionDecision": "deny",\n'
                       '            "permissionDecisionReason": reason,\n'
                       '        }\n'
                       '    }, ensure_ascii=False))\n'
                       '    return 0\n'
                       '\n'
                       'def all_strings(obj) -> list[str]:\n'
                       '    out: list[str] = []\n'
                       '    if isinstance(obj, str):\n'
                       '        out.append(obj)\n'
                       '    elif isinstance(obj, dict):\n'
                       '        for value in obj.values():\n'
                       '            out.extend(all_strings(value))\n'
                       '    elif isinstance(obj, list):\n'
                       '        for value in obj:\n'
                       '            out.extend(all_strings(value))\n'
                       '    return out\n'
                       '\n'
                       'def edit_target(tool_input: dict) -> str:\n'
                       '    for key in ("file_path", "path", "filename", "file"):\n'
                       '        value = tool_input.get(key)\n'
                       '        if isinstance(value, str) and value.strip():\n'
                       '            return value.replace("\\\\", "/").lower()\n'
                       '    return ""\n'
                       '\n'
                       'def edit_removes_isolation(blob: str) -> bool:\n'
                       '    return bool(re.search(\n'
                       '        '
                       'r"^-.*(?:APP_ENV|DB_CONNECTION|DB_DATABASE|MAIL_MAILER|QUEUE_CONNECTION|CACHE_STORE|SESSION_DRIVER|FILESYSTEM_DISK|BROADCAST_CONNECTION|CUPS_SERVER|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY).*force=[\\"\']true[\\"\']",\n'
                       '        blob, re.I | re.M,\n'
                       '    ))\n'
                       '\n'
                       'def main() -> int:\n'
                       '    try:\n'
                       '        payload = json.load(sys.stdin)\n'
                       '    except Exception:\n'
                       '        return 0\n'
                       '\n'
                       '    tool_name = str(payload.get("tool_name") or "")\n'
                       '    tool_input = payload.get("tool_input") or {}\n'
                       '    if not isinstance(tool_input, dict):\n'
                       '        return 0\n'
                       '\n'
                       '    # Edit/Write/apply_patch inputs do not normally contain a shell `command`.\n'
                       '    # Inspect their complete payload before the Bash-only early-return path.\n'
                       '    if tool_name in ("apply_patch", "Edit", "Write"):\n'
                       '        blob = "\\n".join(all_strings(tool_input))\n'
                       '        low_blob = blob.lower().replace("\\\\", "/")\n'
                       '        target = edit_target(tool_input)\n'
                       '        if any(path.lower() in low_blob for path in PROTECTED_PATHS):\n'
                       '            return deny("Adaptive Harness blocked an agent edit to side-effect safety infrastructure. Update the '
                       'Harness through its installer.")\n'
                       '        if "@harness-side-effect-allow" in low_blob:\n'
                       '            return deny("Adaptive Harness blocked adding a side-effect bypass marker. A human must review and add '
                       'any exceptional allow marker outside the agent.")\n'
                       '\n'
                       '        touches_phpunit = target.endswith("phpunit.xml") or target.endswith("phpunit.xml.dist") or "phpunit.xml" '
                       'in low_blob\n'
                       '        if touches_phpunit:\n'
                       '            if tool_name == "Write":\n'
                       '                return deny("Adaptive Harness blocked whole-file replacement of phpunit test-isolation '
                       'configuration. Use a targeted reviewed edit.")\n'
                       '            if '
                       're.search(r"^\\+.*(?:DB_CONNECTION|MAIL_MAILER|QUEUE_CONNECTION|FILESYSTEM_DISK|HTTP_PROXY|CUPS_SERVER).*(?:mysql|smtp|redis|sqs|s3|production|prod)", '
                       'blob, re.I | re.M):\n'
                       '                return deny("Adaptive Harness blocked a phpunit.xml edit that could reconnect tests to '
                       'persistent/external infrastructure.")\n'
                       '            if edit_removes_isolation(blob):\n'
                       '                return deny("Adaptive Harness blocked removal of forced test isolation settings.")\n'
                       '\n'
                       '        touches_testcase = target.endswith("tests/testcase.php") or "tests/testcase.php" in low_blob\n'
                       '        if touches_testcase and '
                       're.search(r"^-.*(?:HarnessSideEffectIsolation|harnessEnableSideEffectIsolation|environment\\([\\"\']testing|:memory:|DB::purge|database\\.connections)", '
                       'blob, re.I | re.M):\n'
                       '            return deny("Adaptive Harness blocked removal of the Laravel TestCase isolation guard.")\n'
                       '        return 0\n'
                       '\n'
                       '    command = tool_input.get("command", "")\n'
                       '    if not isinstance(command, str) or not command.strip():\n'
                       '        return 0\n'
                       '    low = command.lower()\n'
                       '\n'
                       '    if tool_name not in ("Bash", "shell_command", "exec_command", ""):\n'
                       '        return 0\n'
                       '\n'
                       '    if SAFE_WRAPPER in low:\n'
                       '        return 0\n'
                       '\n'
                       '    if any(path in low for path in PROTECTED_PATHS) and re.search(\n'
                       '        r"(?:\\brm\\b|\\bmv\\b|sed\\s+-i|perl\\s+-pi|\\btruncate\\b|(?:>|>>)\\s*[^ ]|\\btee\\b)",\n'
                       '        command,\n'
                       '        re.I,\n'
                       '    ):\n'
                       '        return deny("Adaptive Harness blocked a shell command that could modify/remove safety infrastructure.")\n'
                       '\n'
                       '    for rx, label in DANGEROUS_PATTERNS:\n'
                       '        if rx.search(command):\n'
                       '            return deny(\n'
                       '                f"Adaptive Harness blocked {label}. This is an external, destructive, or persistent side effect, '
                       '"\n'
                       '                "not routine autonomous verification. Use read-only diagnostics or a separately reviewed '
                       'user-supervised procedure."\n'
                       '            )\n'
                       '\n'
                       '    if TINKER.search(command) and not re.search(r"--execute(?:=|\\s)", command, re.I):\n'
                       '        return deny("Adaptive Harness blocked interactive Laravel Tinker. Use a bounded non-interactive read-only '
                       '`tinker --execute=...` probe.")\n'
                       '    if DB_CLIENT_CMD.search(command) and not re.search(r"(?:^|\\s)(?:-e|--execute(?:=|\\s)|-c)(?:\\s|=)", command, '
                       're.I):\n'
                       '        return deny("Adaptive Harness blocked an interactive database client. Use a non-interactive read-only '
                       'SELECT/SHOW/DESCRIBE/EXPLAIN command.")\n'
                       '    if SMBCLIENT.search(command) and not smbclient_is_bounded_read_only(command):\n'
                       '        return deny("Adaptive Harness blocked interactive/non-read-only smbclient. Use a bounded `-c \'ls\'` / '
                       'metadata-only command containing read/navigation verbs only.")\n'
                       '\n'
                       '    if (DB_CLIENT_CMD.search(command) or TINKER.search(command) or re.search(r"\\bphp\\s+-r\\b", command, re.I)) '
                       'and WRITE_SQL.search(command):\n'
                       '        return deny("Adaptive Harness blocked a database write/destructive command before execution.")\n'
                       '    if TINKER.search(command) and '
                       're.search(r"(?:->|::)(?:delete|forceDelete|update|insert|insertGetId|upsert|create|firstOrCreate|updateOrCreate|save|restore|truncate|drop|dropIfExists|statement|unprepared)\\s*\\(", '
                       'command, re.I):\n'
                       '        return deny("Adaptive Harness blocked a Laravel tinker write/destructive call.")\n'
                       '    if CUSTOM_WRITE_ARTISAN.search(command) and not re.search(r"\\b(?:status|check|show|list|dry-run|pretend)\\b", '
                       'command, re.I):\n'
                       '        return deny("Adaptive Harness blocked a custom Artisan command whose name suggests persistent mutation.")\n'
                       '\n'
                       '    root = Path(payload.get("cwd") or ".").resolve()\n'
                       '    laravel = (root / "artisan").exists() or (root / "src" / "artisan").exists()\n'
                       '    if laravel and any(rx.search(command) for rx in TEST_PATTERNS):\n'
                       '        return deny(\n'
                       '            "Adaptive Harness blocked a raw Laravel/PHP test command. Use "\n'
                       '            "`python3 .codex/harness/scripts/safe_test.py --shell \'<command>\'` so DB and external side effects '
                       'are isolated first."\n'
                       '        )\n'
                       '\n'
                       '    return 0\n'
                       '\n'
                       'if __name__ == "__main__":\n'
                       '    raise SystemExit(main())\n',
 'runtime_cleanup.py': '#!/usr/bin/env python3\n'
                       'from __future__ import annotations\n'
                       '\n'
                       'import argparse\n'
                       'import json\n'
                       'import shutil\n'
                       'import time\n'
                       'from datetime import datetime\n'
                       'from pathlib import Path\n'
                       '\n'
                       'from common import config\n'
                       'from harness_paths import RUNTIME_ROOT, ensure_layout\n'
                       '\n'
                       'DEFAULT = {\n'
                       '    "session_days": 7,\n'
                       '    "stop_block_days": 7,\n'
                       '    "telemetry_days": 14,\n'
                       '    "quiet_exec_days": 7,\n'
                       '    "review_log_days": 7,\n'
                       '    "restore_log_days": 14,\n'
                       '    "verification_runs": 8,\n'
                       '    "task_scope_hours": 24,\n'
                       '    "test_storage_hours": 24,\n'
                       '    "legacy_replay_hours": 6,\n'
                       '}\n'
                       '\n'
                       'def retention() -> dict[str, int]:\n'
                       '    raw = config().get("runtime_retention", {})\n'
                       '    result = dict(DEFAULT)\n'
                       '    if isinstance(raw, dict):\n'
                       '        for key in DEFAULT:\n'
                       '            try:\n'
                       '                result[key] = max(0, int(raw.get(key, DEFAULT[key])))\n'
                       '            except (TypeError, ValueError):\n'
                       '                pass\n'
                       '    return result\n'
                       '\n'
                       'def json_timestamp(path: Path, key: str) -> float | None:\n'
                       '    try:\n'
                       '        raw = json.loads(path.read_text(encoding="utf-8"))\n'
                       '        value = raw.get(key) if isinstance(raw, dict) else None\n'
                       '        return float(value) if value is not None else None\n'
                       '    except Exception:\n'
                       '        return None\n'
                       '\n'
                       'def old(path: Path, seconds: int, timestamp: float | None = None) -> bool:\n'
                       '    if seconds <= 0:\n'
                       '        return True\n'
                       '    if timestamp is None:\n'
                       '        try:\n'
                       '            timestamp = path.stat().st_mtime\n'
                       '        except OSError:\n'
                       '            return False\n'
                       '    return time.time() - timestamp >= seconds\n'
                       '\n'
                       'def replay_timestamp(path: Path) -> float | None:\n'
                       '    stamp = path.name.removeprefix("legacy-replay-")\n'
                       '    try:\n'
                       '        return datetime.strptime(stamp, "%Y%m%d-%H%M%S").timestamp()\n'
                       '    except ValueError:\n'
                       '        return None\n'
                       '\n'
                       'def collect() -> list[Path]:\n'
                       '    ensure_layout()\n'
                       '    cfg = retention(); found: set[Path] = set()\n'
                       '    for p in RUNTIME_ROOT.glob("session-*.json"):\n'
                       '        if old(p, cfg["session_days"] * 86400, json_timestamp(p, "created_at")):\n'
                       '            found.add(p)\n'
                       '    for p in RUNTIME_ROOT.glob("stop-block-*.json"):\n'
                       '        if old(p, cfg["stop_block_days"] * 86400, json_timestamp(p, "timestamp")):\n'
                       '            found.add(p)\n'
                       '    for folder, pattern, days in (("telemetry", "*.jsonl", cfg["telemetry_days"]), ("quiet-exec", "*.log", '
                       'cfg["quiet_exec_days"])):\n'
                       '        base = RUNTIME_ROOT / folder\n'
                       '        if base.is_dir():\n'
                       '            for p in base.glob(pattern):\n'
                       '                if old(p, days * 86400): found.add(p)\n'
                       '    for p in RUNTIME_ROOT.glob("review-*.log"):\n'
                       '        if old(p, cfg["review_log_days"] * 86400): found.add(p)\n'
                       '    for p in RUNTIME_ROOT.glob("restore-*.log"):\n'
                       '        if old(p, cfg["restore_log_days"] * 86400): found.add(p)\n'
                       '    scope = RUNTIME_ROOT / "task_scope" / "current.json"\n'
                       '    if scope.is_file() and old(scope, cfg["task_scope_hours"] * 3600, json_timestamp(scope, "created_at")):\n'
                       '        found.add(scope)\n'
                       '    storage = RUNTIME_ROOT / "test-storage"\n'
                       '    if storage.is_dir():\n'
                       '        for child in storage.iterdir():\n'
                       '            if old(child, cfg["test_storage_hours"] * 3600): found.add(child)\n'
                       '    for replay in RUNTIME_ROOT.glob("legacy-replay-*"):\n'
                       '        if replay.is_dir() and old(replay, cfg["legacy_replay_hours"] * 3600, replay_timestamp(replay)):\n'
                       '            found.add(replay)\n'
                       '    verify = RUNTIME_ROOT / "verification"\n'
                       '    if verify.is_dir():\n'
                       '        runs = sorted((p for p in verify.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)\n'
                       '        for p in runs[cfg["verification_runs"]:]: found.add(p)\n'
                       '    return sorted(found)\n'
                       '\n'
                       'def main() -> int:\n'
                       '    ap = argparse.ArgumentParser(description="Prune only known stale Adaptive Harness runtime artifacts")\n'
                       '    ap.add_argument("--dry-run", action="store_true")\n'
                       '    args = ap.parse_args()\n'
                       '    items = collect()\n'
                       '    for path in items:\n'
                       '        rel = path.relative_to(RUNTIME_ROOT.parent.parent) if RUNTIME_ROOT.parent.parent in path.parents else '
                       'path\n'
                       '        print(f"{\'WOULD REMOVE\' if args.dry_run else \'REMOVE\'} {rel}")\n'
                       '        if args.dry_run: continue\n'
                       '        if path.is_dir(): shutil.rmtree(path)\n'
                       '        else: path.unlink(missing_ok=True)\n'
                       '    for base in (RUNTIME_ROOT / "task_scope", RUNTIME_ROOT / "telemetry", RUNTIME_ROOT / "quiet-exec", '
                       'RUNTIME_ROOT / "test-storage"):\n'
                       '        try: base.rmdir()\n'
                       '        except OSError: pass\n'
                       '    if not items: print("runtime cleanup: no stale known artifacts")\n'
                       '    return 0\n'
                       '\n'
                       'if __name__ == "__main__":\n'
                       '    raise SystemExit(main())\n',
 'selftest.py': '#!/usr/bin/env python3\n'
                'from __future__ import annotations\n'
                '\n'
                'import argparse\n'
                'import hashlib\n'
                'import json\n'
                'import os\n'
                'import re\n'
                'import shutil\n'
                'import subprocess\n'
                'import sys\n'
                'from pathlib import Path\n'
                '\n'
                'try:\n'
                '    import tomllib\n'
                'except Exception:  # pragma: no cover\n'
                '    tomllib = None\n'
                '\n'
                'SCRIPT_DIR = Path(__file__).resolve().parent\n'
                'HARNESS_DIR = SCRIPT_DIR.parent\n'
                'WORKSPACE_ROOT = HARNESS_DIR.parents[1]\n'
                '\n'
                'REQUIRED_SKILLS = [\n'
                '    "harness-bootstrap",\n'
                '    "harness-debug",\n'
                '    "harness-develop",\n'
                '    "harness-review",\n'
                '    "harness-verify",\n'
                '    "maintain-project-knowledge",\n'
                ']\n'
                'REQUIRED_FILES = [\n'
                '    "AGENTS.md",\n'
                '    ".codex/config.toml",\n'
                '    ".codex/hooks.json",\n'
                '    ".codex/harness/VERSION",\n'
                '    ".codex/harness/config.json",\n'
                '    ".codex/harness/commands.json",\n'
                '    ".codex/harness/architecture_rules.json",\n'
                '    ".codex/harness/minimal_edit_policy.json",\n'
                '    ".codex/harness/bin/codex-project",\n'
                '    ".codex/harness/hooks/harness_hook.py",\n'
                '    ".codex/harness/hooks/pre_tool_safety.py",\n'
                '    ".codex/harness/hooks/minimal_edit_pretool.py",\n'
                '    ".codex/harness/scripts/verify.py",\n'
                '    ".codex/harness/scripts/output_guard.py",\n'
                '    ".codex/harness/scripts/quiet_exec.py",\n'
                '    ".codex/harness/scripts/change_inventory.py",\n'
                '    ".codex/harness/scripts/test_inventory.py",\n'
                '    ".codex/harness/scripts/architecture_check.py",\n'
                '    ".codex/harness/scripts/telemetry_hook.py",\n'
                '    ".codex/harness/scripts/telemetry_report.py",\n'
                '    ".codex/harness/scripts/runtime_cleanup.py",\n'
                '    ".codex/harness/scripts/harness_paths.py",\n'
                '    ".codex/harness/scripts/task_scope.py",\n'
                '    ".codex/harness/scripts/task_state.py",\n'
                '    ".codex/harness/scripts/safe_test.py",\n'
                '    ".codex/harness/scripts/test_db_guard.py",\n'
                '    ".codex/harness/scripts/side_effect_guard.py",\n'
                '    ".codex/harness/scripts/minimal_diff_guard.py",\n'
                '    ".codex/rules/harness-safety.rules",\n'
                '    ".codex/rules/harness-side-effect-safety.rules",\n'
                ']\n'
                '\n'
                '\n'
                'def read_json(path: Path) -> tuple[dict | None, str | None]:\n'
                '    try:\n'
                '        value = json.loads(path.read_text(encoding="utf-8"))\n'
                '        return (value if isinstance(value, dict) else None), None\n'
                '    except Exception as exc:\n'
                '        return None, str(exc)\n'
                '\n'
                '\n'
                'def run_hook(rel: str, payload: dict) -> tuple[int, dict]:\n'
                '    env = os.environ.copy()\n'
                '    env["PYTHONDONTWRITEBYTECODE"] = "1"\n'
                '    cp = subprocess.run(\n'
                '        [sys.executable, str(WORKSPACE_ROOT / rel)],\n'
                '        input=json.dumps(payload, ensure_ascii=False),\n'
                '        text=True,\n'
                '        stdout=subprocess.PIPE,\n'
                '        stderr=subprocess.PIPE,\n'
                '        cwd=WORKSPACE_ROOT,\n'
                '        env=env,\n'
                '        timeout=10,\n'
                '    )\n'
                '    try:\n'
                '        data = json.loads(cp.stdout.strip() or "{}")\n'
                '    except json.JSONDecodeError:\n'
                '        data = {}\n'
                '    return cp.returncode, data if isinstance(data, dict) else {}\n'
                '\n'
                '\n'
                'def hook_denied(data: dict) -> bool:\n'
                '    out = data.get("hookSpecificOutput", {})\n'
                '    return isinstance(out, dict) and out.get("permissionDecision") == "deny"\n'
                '\n'
                '\n'
                'def configured_git_roots(cfg: dict) -> list[Path]:\n'
                '    roots: list[Path] = []\n'
                '    values = cfg.get("project_layout", {}).get("git_roots", [])\n'
                '    if isinstance(values, list):\n'
                '        for value in values:\n'
                '            if not isinstance(value, str) or not value.strip():\n'
                '                continue\n'
                '            path = WORKSPACE_ROOT if value == "." else (WORKSPACE_ROOT / value).resolve()\n'
                '            if (path / ".git").exists() and path not in roots:\n'
                '                roots.append(path)\n'
                '    if (WORKSPACE_ROOT / ".git").exists() and WORKSPACE_ROOT not in roots:\n'
                '        roots.append(WORKSPACE_ROOT)\n'
                '    return roots\n'
                '\n'
                '\n'
                'def main() -> int:\n'
                '    parser = argparse.ArgumentParser(description="Adaptive Codex Harness self-test")\n'
                '    parser.add_argument("--install-check", action="store_true", help="Installer mode; environment-only warnings do not '
                'fail installation")\n'
                '    parser.add_argument("--quiet", action="store_true")\n'
                '    args = parser.parse_args()\n'
                '\n'
                '    errors: list[str] = []\n'
                '    warnings: list[str] = []\n'
                '    oks: list[str] = []\n'
                '\n'
                '    def ok(message: str) -> None:\n'
                '        oks.append(message)\n'
                '\n'
                '    def err(message: str) -> None:\n'
                '        errors.append(message)\n'
                '\n'
                '    def warn(message: str) -> None:\n'
                '        warnings.append(message)\n'
                '\n'
                '    for rel in REQUIRED_FILES:\n'
                '        path = WORKSPACE_ROOT / rel\n'
                '        (ok if path.exists() else err)(f"required file: {rel}")\n'
                '\n'
                '    version_path = HARNESS_DIR / "VERSION"\n'
                '    expected_version = version_path.read_text(encoding="utf-8", errors="replace").strip() if version_path.exists() else '
                '""\n'
                '    if expected_version == "6.12.0":\n'
                '        ok("Harness version 6.12.0")\n'
                '    else:\n'
                '        err(f"VERSION is {expected_version or \'missing\'!r}, expected \'6.12.0\'")\n'
                '\n'
                '    cfg, cfg_error = read_json(HARNESS_DIR / "config.json")\n'
                '    if cfg_error or cfg is None:\n'
                '        err(f"config.json parse: {cfg_error}")\n'
                '        cfg = {}\n'
                '    else:\n'
                '        ok("config.json parse")\n'
                '        if int(cfg.get("schema_version", 0)) >= 3:\n'
                '            ok("config schema >= 3")\n'
                '        else:\n'
                '            err(f"config schema is {cfg.get(\'schema_version\')!r}, expected >= 3")\n'
                '        meta = cfg.get("harness_meta", {}) if isinstance(cfg.get("harness_meta"), dict) else {}\n'
                '        if meta.get("version") == expected_version:\n'
                '            ok("harness_meta.version matches VERSION")\n'
                '        else:\n'
                '            err(f"harness_meta.version={meta.get(\'version\')!r}, expected {expected_version!r}")\n'
                '        gate = cfg.get("quality_gate", {}).get("nontrivial", {}) if isinstance(cfg.get("quality_gate"), dict) else {}\n'
                '        if gate.get("changed_files") == 5:\n'
                '            ok("quality review file threshold = 5")\n'
                '        else:\n'
                '            err(f"quality_gate.nontrivial.changed_files={gate.get(\'changed_files\')!r}, expected 5")\n'
                '        state = cfg.get("task_state", {}) if isinstance(cfg.get("task_state"), dict) else {}\n'
                '        if state.get("storage") == ".harness/state/task-state":\n'
                '            ok("task-state storage is durable .harness/state")\n'
                '        else:\n'
                '            err(f"task_state.storage={state.get(\'storage\')!r}, expected \'.harness/state/task-state\'")\n'
                '\n'
                '    for name in ("commands.json", "architecture_rules.json", "minimal_edit_policy.json"):\n'
                '        value, parse_error = read_json(HARNESS_DIR / name)\n'
                '        if parse_error or value is None:\n'
                '            err(f"{name} parse: {parse_error}")\n'
                '        else:\n'
                '            ok(f"{name} parse")\n'
                '            if name == "minimal_edit_policy.json" and value.get("version") != expected_version:\n'
                '                err(f"minimal_edit_policy version={value.get(\'version\')!r}, expected {expected_version!r}")\n'
                '\n'
                '    manifest, manifest_error = read_json(HARNESS_DIR / "installed-manifest.json")\n'
                '    if manifest_error or manifest is None:\n'
                '        err(f"installed-manifest.json parse: {manifest_error}")\n'
                '    else:\n'
                '        if manifest.get("version") == expected_version:\n'
                '            ok("installed-manifest version matches VERSION")\n'
                '        else:\n'
                '            err(f"installed-manifest version={manifest.get(\'version\')!r}, expected {expected_version!r}")\n'
                '        drift: list[str] = []\n'
                '        payload = manifest.get("payload_sha256", {})\n'
                '        if not isinstance(payload, dict) or not payload:\n'
                '            drift.append("empty payload")\n'
                '        else:\n'
                '            for rel, expected in payload.items():\n'
                '                path = WORKSPACE_ROOT / str(rel)\n'
                '                if not path.is_file():\n'
                '                    drift.append(f"missing:{rel}")\n'
                '                    continue\n'
                '                actual = hashlib.sha256(path.read_bytes()).hexdigest()\n'
                '                if actual != expected:\n'
                '                    drift.append(str(rel))\n'
                '        if drift:\n'
                '            err("harness-owned file drift: " + ", ".join(drift[:10]))\n'
                '        else:\n'
                '            ok("harness-owned payload matches installed manifest")\n'
                '\n'
                '    toml_path = WORKSPACE_ROOT / ".codex/config.toml"\n'
                '    if tomllib is None:\n'
                '        warn("tomllib unavailable; skipped config.toml parse")\n'
                '    elif toml_path.exists():\n'
                '        try:\n'
                '            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))\n'
                '            ok("config.toml parse")\n'
                '            if data.get("model") == "gpt-5.6-sol":\n'
                '                ok("model = gpt-5.6-sol")\n'
                '            else:\n'
                '                err(f"model={data.get(\'model\')!r}, expected \'gpt-5.6-sol\'")\n'
                '            if data.get("model_reasoning_effort") == "high":\n'
                '                ok("reasoning = high")\n'
                '            else:\n'
                '                err(f"model_reasoning_effort={data.get(\'model_reasoning_effort\')!r}, expected \'high\'")\n'
                '            agents = data.get("agents", {}) if isinstance(data.get("agents"), dict) else {}\n'
                '            if int(agents.get("max_concurrent_threads_per_session", 99)) <= 2:\n'
                '                ok("subagent concurrency <= 2")\n'
                '            else:\n'
                '                err("subagent concurrency exceeds 2")\n'
                '        except Exception as exc:\n'
                '            err(f"config.toml parse: {exc}")\n'
                '\n'
                '    hooks, hooks_error = read_json(WORKSPACE_ROOT / ".codex/hooks.json")\n'
                '    if hooks_error or hooks is None:\n'
                '        err(f"hooks.json parse: {hooks_error}")\n'
                '    else:\n'
                '        ok("hooks.json parse")\n'
                '        hook_map = hooks.get("hooks", {}) if isinstance(hooks.get("hooks"), dict) else {}\n'
                '        if "PostToolUse" in hook_map and "SubagentStart" in hook_map:\n'
                '            ok("observability hooks installed")\n'
                '        else:\n'
                '            err("observability hooks missing")\n'
                '        commands: list[str] = []\n'
                '        for groups in hook_map.values():\n'
                '            if not isinstance(groups, list):\n'
                '                continue\n'
                '            for group in groups:\n'
                '                if not isinstance(group, dict):\n'
                '                    continue\n'
                '                for item in group.get("hooks", []) if isinstance(group.get("hooks"), list) else []:\n'
                '                    if isinstance(item, dict) and isinstance(item.get("command"), str):\n'
                '                        commands.append(item["command"])\n'
                '        for required in ("pre_tool_safety.py", "minimal_edit_pretool.py", "runtime_cleanup.py"):\n'
                '            if any(required in command for command in commands):\n'
                '                ok(f"hook registered: {required}")\n'
                '            else:\n'
                '                err(f"hook missing: {required}")\n'
                '        absolute = [command for command in commands if re.search(r"python3\\s+/home/[^\\s]+/\\.codex/harness/", '
                'command)]\n'
                '        if absolute:\n'
                '            err("hooks.json still contains project-absolute Harness paths")\n'
                '        else:\n'
                '            ok("Harness hook paths are workspace-relative/dynamic")\n'
                '        harness_python = [command for command in commands if ".codex/harness/" in command and "python" in command]\n'
                '        if all("PYTHONDONTWRITEBYTECODE=1" in command for command in harness_python):\n'
                '            ok("Harness hooks suppress __pycache__ writes")\n'
                '        else:\n'
                '            err("one or more Harness hooks do not suppress Python bytecode writes")\n'
                '        if isinstance(hook_map.get("Stop", []), list):\n'
                '            ok("Stop hook remains advisory/non-blocking")\n'
                '\n'
                '    if (HARNESS_DIR / "runtime").exists():\n'
                '        err("legacy mutable .codex/harness/runtime still exists")\n'
                '    else:\n'
                '        ok("no mutable .codex/harness/runtime tree")\n'
                '\n'
                '    task_state = (SCRIPT_DIR / "task_state.py").read_text(encoding="utf-8", errors="replace") if (SCRIPT_DIR / '
                '"task_state.py").exists() else ""\n'
                '    telemetry_report = (SCRIPT_DIR / "telemetry_report.py").read_text(encoding="utf-8", errors="replace") if (SCRIPT_DIR '
                '/ "telemetry_report.py").exists() else ""\n'
                '    if "STATE_ROOT" in task_state and \'parent.parent / "runtime"\' not in task_state:\n'
                '        ok("task_state uses .harness/state")\n'
                '    else:\n'
                '        err("task_state still targets static Harness runtime")\n'
                '    if "RUNTIME_ROOT" in telemetry_report and \'parent / "runtime"\' not in telemetry_report:\n'
                '        ok("telemetry_report uses .harness/runtime")\n'
                '    else:\n'
                '        err("telemetry_report still targets static Harness runtime")\n'
                '\n'
                '    agents_path = WORKSPACE_ROOT / "AGENTS.md"\n'
                '    if agents_path.exists():\n'
                '        text = agents_path.read_text(encoding="utf-8", errors="replace")\n'
                '        if len(text.splitlines()) > 240:\n'
                '            warn(f"AGENTS.md is {len(text.splitlines())} lines; keep it router-like where possible")\n'
                '        conflict_patterns = [\n'
                '            r"Explorer\\s*(?:→|->).*Planner\\s*(?:→|->).*Worker",\n'
                '            r"Planner/Explorer/Workerを(?:必ず|常に)",\n'
                '        ]\n'
                '        if any(re.search(pattern, text, re.I | re.S) for pattern in conflict_patterns):\n'
                '            err("AGENTS.md contains a legacy mandatory-agent-chain directive")\n'
                '        else:\n'
                '            ok("AGENTS.md has no known mandatory-agent-chain conflict")\n'
                '        if ".codex/harness/runtime/" in text:\n'
                '            err("AGENTS.md still directs mutable output to .codex/harness/runtime")\n'
                '\n'
                '    skills_root = WORKSPACE_ROOT / ".agents/skills"\n'
                '    for skill in REQUIRED_SKILLS:\n'
                '        path = skills_root / skill / "SKILL.md"\n'
                '        if not path.exists():\n'
                '            err(f"skill missing: {skill}")\n'
                '            continue\n'
                '        text = path.read_text(encoding="utf-8", errors="replace")\n'
                '        if text.startswith("---") and f"name: {skill}" in text[:700]:\n'
                '            ok(f"skill metadata: {skill}")\n'
                '        else:\n'
                '            err(f"skill metadata invalid: {skill}")\n'
                '\n'
                '    launcher = WORKSPACE_ROOT / ".codex/harness/bin/codex-project"\n'
                '    if launcher.exists():\n'
                '        if os.access(launcher, os.X_OK):\n'
                '            ok("codex-project launcher executable")\n'
                '        else:\n'
                '            err("codex-project launcher is not executable")\n'
                '        launcher_text = launcher.read_text(encoding="utf-8", errors="replace")\n'
                '        if "PYTHONDONTWRITEBYTECODE=1" in launcher_text:\n'
                '            ok("launcher suppresses Python bytecode writes")\n'
                '        else:\n'
                '            err("launcher does not suppress Python bytecode writes")\n'
                '\n'
                '    git_roots = configured_git_roots(cfg)\n'
                '    if git_roots:\n'
                '        ok("configured Git root detected")\n'
                '        if all(path != WORKSPACE_ROOT for path in git_roots):\n'
                '            warn("workspace root differs from Git root; use the project launcher or start Codex from the workspace '
                'root")\n'
                '    else:\n'
                '        message = "no configured Git root detected"\n'
                '        (warn if args.install_check else err)(message)\n'
                '\n'
                '    # Verify edit-safety hooks with tool payloads that historically bypassed command-only checks.\n'
                '    if (WORKSPACE_ROOT / ".codex/harness/hooks/pre_tool_safety.py").exists():\n'
                '        rc, data = run_hook(\n'
                '            ".codex/harness/hooks/pre_tool_safety.py",\n'
                '            {\n'
                '                "hook_event_name": "PreToolUse",\n'
                '                "tool_name": "Edit",\n'
                '                "tool_input": {\n'
                '                    "file_path": ".codex/harness/scripts/safe_test.py",\n'
                '                    "old_string": "x",\n'
                '                    "new_string": "y",\n'
                '                },\n'
                '            },\n'
                '        )\n'
                '        if rc == 0 and hook_denied(data):\n'
                '            ok("pre_tool_safety blocks protected-file Edit")\n'
                '        else:\n'
                '            err("pre_tool_safety failed protected-file Edit self-check")\n'
                '\n'
                '    if (WORKSPACE_ROOT / ".codex/harness/hooks/minimal_edit_pretool.py").exists():\n'
                '        rc, data = run_hook(\n'
                '            ".codex/harness/hooks/minimal_edit_pretool.py",\n'
                '            {\n'
                '                "hook_event_name": "PreToolUse",\n'
                '                "tool_name": "Write",\n'
                '                "tool_input": {\n'
                '                    "file_path": ".codex/harness/minimal_edit_policy.json",\n'
                '                    "content": "{}",\n'
                '                },\n'
                '            },\n'
                '        )\n'
                '        if rc == 0 and hook_denied(data):\n'
                '            ok("minimal-edit hook protects its own policy")\n'
                '        else:\n'
                '            err("minimal-edit hook failed protected-policy self-check")\n'
                '\n'
                '    py_files = list((HARNESS_DIR / "scripts").glob("*.py")) + list((HARNESS_DIR / "hooks").glob("*.py"))\n'
                '    for path in py_files:\n'
                '        try:\n'
                '            compile(path.read_text(encoding="utf-8"), str(path), "exec")\n'
                '        except Exception as exc:\n'
                '            err(f"Python syntax: {path.relative_to(WORKSPACE_ROOT)}: {exc}")\n'
                '            break\n'
                '    else:\n'
                '        ok("Harness Python syntax")\n'
                '\n'
                '    if shutil.which("codex") is None:\n'
                '        warn("codex executable not found in PATH; launcher runtime not tested")\n'
                '\n'
                '    if not args.quiet:\n'
                '        for message in oks:\n'
                '            print(f"[OK] {message}")\n'
                '        for message in warnings:\n'
                '            print(f"[WARN] {message}")\n'
                '        for message in errors:\n'
                '            print(f"[ERROR] {message}")\n'
                '        print(f"selftest: {len(errors)} error(s), {len(warnings)} warning(s), {len(oks)} ok")\n'
                '    return 1 if errors else 0\n'
                '\n'
                '\n'
                'if __name__ == "__main__":\n'
                '    raise SystemExit(main())\n',
 'task_scope.py': '#!/usr/bin/env python3\n'
                  'from __future__ import annotations\n'
                  'import argparse, hashlib, json, subprocess, time\n'
                  'from pathlib import Path\n'
                  '\n'
                  'from harness_paths import RUNTIME_ROOT, ensure_layout\n'
                  'from common import config as harness_config, git_roots as configured_git_roots\n'
                  '\n'
                  'ROOT = Path(__file__).resolve().parents[3]\n'
                  'STATE = RUNTIME_ROOT / "task_scope" / "current.json"\n'
                  'MAX_SCOPE_AGE_SECONDS = 24 * 60 * 60\n'
                  '\n'
                  'HIGH_RISK_PARTS = (\n'
                  '    "auth", "permission", "policy", "middleware", "migration", "schema", "routes/", "security",\n'
                  '    "composer.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",\n'
                  ')\n'
                  '\n'
                  'def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:\n'
                  '    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n'
                  '\n'
                  'def git_roots() -> list[Path]:\n'
                  '    return configured_git_roots(harness_config())\n'
                  '\n'
                  'def state_is_stale() -> bool:\n'
                  '    if not STATE.exists():\n'
                  '        return False\n'
                  '    try:\n'
                  '        data = json.loads(STATE.read_text(encoding="utf-8"))\n'
                  '        created_at = float(data.get("created_at", 0))\n'
                  '    except Exception:\n'
                  '        return True\n'
                  '    return created_at <= 0 or time.time() - created_at > MAX_SCOPE_AGE_SECONDS\n'
                  '\n'
                  'def status_paths(git_root: Path) -> set[str]:\n'
                  '    cp = run(git_root, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all")\n'
                  '    if cp.returncode != 0: return set()\n'
                  '    chunks = cp.stdout.split("\\0"); out: set[str] = set(); i = 0\n'
                  '    while i < len(chunks):\n'
                  '        item = chunks[i]\n'
                  '        if not item: i += 1; continue\n'
                  '        if len(item) >= 4:\n'
                  '            code, path = item[:2], item[3:]; out.add(path)\n'
                  '            if (code.startswith("R") or code.startswith("C")) and i + 1 < len(chunks) and chunks[i+1]:\n'
                  '                out.add(chunks[i+1]); i += 1\n'
                  '        i += 1\n'
                  '    return out\n'
                  '\n'
                  'def digest(path: Path) -> str:\n'
                  '    if not path.exists(): return "<missing>"\n'
                  '    if path.is_dir(): return "<dir>"\n'
                  '    h = hashlib.sha256()\n'
                  '    try:\n'
                  '        with path.open("rb") as f:\n'
                  '            for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)\n'
                  '        return h.hexdigest()\n'
                  '    except OSError: return "<unreadable>"\n'
                  '\n'
                  'def snapshot() -> dict:\n'
                  '    data = {"version": 1, "created_at": int(time.time()), "roots": {}}\n'
                  '    for gr in git_roots():\n'
                  '        relroot = "." if gr == ROOT else gr.relative_to(ROOT).as_posix()\n'
                  '        paths = status_paths(gr)\n'
                  '        data["roots"][relroot] = {"dirty": {p: digest(gr / p) for p in sorted(paths)}}\n'
                  '    return data\n'
                  '\n'
                  'def begin(force: bool) -> int:\n'
                  '    ensure_layout()\n'
                  '    if STATE.exists() and not force and not state_is_stale():\n'
                  '        print("task scope already active; baseline preserved"); return 0\n'
                  '    if STATE.exists() and state_is_stale():\n'
                  '        print("stale task scope baseline replaced")\n'
                  '    STATE.parent.mkdir(parents=True, exist_ok=True)\n'
                  '    STATE.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n'
                  '    print("task scope baseline recorded"); return 0\n'
                  '\n'
                  'def task_touched(baseline: dict) -> dict[str, list[str]]:\n'
                  '    result: dict[str, list[str]] = {}\n'
                  '    for gr in git_roots():\n'
                  '        relroot = "." if gr == ROOT else gr.relative_to(ROOT).as_posix()\n'
                  '        base_dirty = baseline.get("roots", {}).get(relroot, {}).get("dirty", {})\n'
                  '        now_paths = status_paths(gr); union = set(base_dirty) | now_paths; touched = []\n'
                  '        for p in sorted(union):\n'
                  '            before = base_dirty.get(p, "<clean>")\n'
                  '            after = digest(gr / p) if p in now_paths else "<clean>"\n'
                  '            if before != after: touched.append(p)\n'
                  '        result[relroot] = touched\n'
                  '    return result\n'
                  '\n'
                  'def numstat_for(gr: Path, paths: list[str]) -> int:\n'
                  '    if not paths: return 0\n'
                  '    cp = run(gr, "git", "diff", "--numstat", "--", *paths)\n'
                  '    total = 0\n'
                  '    if cp.returncode == 0:\n'
                  '        for line in cp.stdout.splitlines():\n'
                  '            parts = line.split("\\t")\n'
                  '            if len(parts) >= 2:\n'
                  '                try: total += int(parts[0]) + int(parts[1])\n'
                  '                except ValueError: pass\n'
                  '    return total\n'
                  '\n'
                  'def report(as_json: bool) -> int:\n'
                  '    if not STATE.exists():\n'
                  '        print("no active task scope; run begin first", file=__import__(\'sys\').stderr); return 2\n'
                  '    if state_is_stale():\n'
                  '        print("task scope baseline is older than 24h; run begin --force before using it", '
                  "file=__import__('sys').stderr); return 2\n"
                  '    baseline = json.loads(STATE.read_text(encoding="utf-8")); touched = task_touched(baseline)\n'
                  '    all_paths = []; approx_lines = 0\n'
                  '    roots = {"." if gr == ROOT else gr.relative_to(ROOT).as_posix(): gr for gr in git_roots()}\n'
                  '    for relroot, paths in touched.items():\n'
                  '        gr = roots.get(relroot)\n'
                  '        for p in paths: all_paths.append(p if relroot == "." else f"{relroot}/{p}")\n'
                  '        if gr: approx_lines += numstat_for(gr, paths)\n'
                  '    high = len(all_paths) >= 5 or approx_lines >= 200 or any(any(k in p.lower() for k in HIGH_RISK_PARTS) for p in '
                  'all_paths)\n'
                  '    data = {"files": all_paths, "file_count": len(all_paths), "approx_diff_lines": approx_lines, '
                  '"reviewer_recommended": high}\n'
                  '    if as_json: print(json.dumps(data, ensure_ascii=False, indent=2))\n'
                  '    else:\n'
                  '        print(f"task-touched files: {len(all_paths)}")\n'
                  '        print(f"approx task diff lines: {approx_lines}")\n'
                  '        print(f"reviewer recommended: {\'yes\' if high else \'no\'}")\n'
                  '        for p in all_paths: print(f"  {p}")\n'
                  '    return 0\n'
                  '\n'
                  'def clear() -> int:\n'
                  '    if STATE.exists(): STATE.unlink()\n'
                  '    print("task scope cleared"); return 0\n'
                  '\n'
                  'def main() -> int:\n'
                  '    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)\n'
                  '    b = sub.add_parser("begin"); b.add_argument("--force", action="store_true")\n'
                  '    r = sub.add_parser("report"); r.add_argument("--json", action="store_true")\n'
                  '    sub.add_parser("clear"); a = ap.parse_args()\n'
                  '    if a.cmd == "begin": return begin(a.force)\n'
                  '    if a.cmd == "report": return report(a.json)\n'
                  '    return clear()\n'
                  'if __name__ == "__main__": raise SystemExit(main())\n',
 'task_state.py': '#!/usr/bin/env python3\n'
                  'from __future__ import annotations\n'
                  '\n'
                  'import argparse\n'
                  'import json\n'
                  'import time\n'
                  'from harness_paths import STATE_ROOT, ensure_layout\n'
                  '\n'
                  'ROOT = STATE_ROOT / "task-state"\n'
                  'LATEST = ROOT / "latest.json"\n'
                  '\n'
                  '\n'
                  'def load() -> dict:\n'
                  '    try:\n'
                  '        v = json.loads(LATEST.read_text(encoding="utf-8"))\n'
                  '        return v if isinstance(v, dict) else {}\n'
                  '    except Exception:\n'
                  '        return {}\n'
                  '\n'
                  '\n'
                  'def save(v: dict) -> None:\n'
                  '    ensure_layout()\n'
                  '    ROOT.mkdir(parents=True, exist_ok=True)\n'
                  '    LATEST.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n'
                  '\n'
                  '\n'
                  'def main() -> int:\n'
                  '    ap = argparse.ArgumentParser(description="Optional compact state for genuinely long/multi-session tasks")\n'
                  '    sub = ap.add_subparsers(dest="cmd", required=True)\n'
                  '    s = sub.add_parser("start"); s.add_argument("title")\n'
                  '    c = sub.add_parser("checkpoint"); c.add_argument("summary")\n'
                  '    sub.add_parser("show")\n'
                  '    sub.add_parser("finish")\n'
                  '    args = ap.parse_args()\n'
                  '    if args.cmd == "start":\n'
                  '        save({"title": args.title, "status": "active", "created_at": time.time(), "checkpoints": []})\n'
                  '    elif args.cmd == "checkpoint":\n'
                  '        v = load()\n'
                  '        if not v:\n'
                  '            raise SystemExit("No active task state. Use start first.")\n'
                  '        cps = v.setdefault("checkpoints", [])\n'
                  '        cps.append({"ts": time.time(), "summary": args.summary[:1200]})\n'
                  '        v["checkpoints"] = cps[-8:]\n'
                  '        save(v)\n'
                  '    elif args.cmd == "show":\n'
                  '        v = load(); print(json.dumps(v, ensure_ascii=False, indent=2) if v else "No task state.")\n'
                  '    elif args.cmd == "finish":\n'
                  '        v = load()\n'
                  '        if v:\n'
                  '            v["status"] = "finished"; v["finished_at"] = time.time(); save(v)\n'
                  '    return 0\n'
                  '\n'
                  '\n'
                  'if __name__ == "__main__":\n'
                  '    raise SystemExit(main())\n',
 'telemetry_report.py': '#!/usr/bin/env python3\n'
                        'from __future__ import annotations\n'
                        '\n'
                        'import argparse\n'
                        'import json\n'
                        'import time\n'
                        'from collections import Counter\n'
                        'from harness_paths import RUNTIME_ROOT\n'
                        '\n'
                        'ROOT = RUNTIME_ROOT / "telemetry"\n'
                        '\n'
                        '\n'
                        'def load_records(days: int) -> list[dict]:\n'
                        '    if not ROOT.exists():\n'
                        '        return []\n'
                        '    cutoff = time.time() - max(days, 1) * 86400\n'
                        '    rows: list[dict] = []\n'
                        '    for path in sorted(ROOT.glob("*.jsonl")):\n'
                        '        try:\n'
                        '            if path.stat().st_mtime < cutoff:\n'
                        '                continue\n'
                        '            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():\n'
                        '                try:\n'
                        '                    v = json.loads(line)\n'
                        '                    if isinstance(v, dict):\n'
                        '                        rows.append(v)\n'
                        '                except Exception:\n'
                        '                    pass\n'
                        '        except OSError:\n'
                        '            pass\n'
                        '    return rows\n'
                        '\n'
                        '\n'
                        'def main() -> int:\n'
                        '    ap = argparse.ArgumentParser(description="Compact local Harness observability report")\n'
                        '    ap.add_argument("--days", type=int, default=7)\n'
                        '    args = ap.parse_args()\n'
                        '    rows = load_records(args.days)\n'
                        '    if not rows:\n'
                        '        print("No telemetry records yet.")\n'
                        '        return 0\n'
                        '\n'
                        '    events = Counter(str(r.get("event", "unknown")) for r in rows)\n'
                        '    tools = Counter(str(r.get("tool", "")) for r in rows if r.get("tool"))\n'
                        '    families = Counter(str(r.get("command_family", "")) for r in rows if r.get("command_family"))\n'
                        '    agents = Counter(str(r.get("agent_type", "unknown")) for r in rows if r.get("event") == "SubagentStart")\n'
                        '    sessions = len({r.get("session") for r in rows if r.get("session")})\n'
                        '\n'
                        '    print(f"Harness telemetry ({args.days}d): {len(rows)} events / {sessions} sessions")\n'
                        '    print("Events: " + ", ".join(f"{k}={v}" for k, v in events.most_common(8)))\n'
                        '    if tools:\n'
                        '        print("Tools : " + ", ".join(f"{k}={v}" for k, v in tools.most_common(8)))\n'
                        '    if families:\n'
                        '        print("Bash  : " + ", ".join(f"{k}={v}" for k, v in families.most_common(8)))\n'
                        '    if agents:\n'
                        '        print("Agents: " + ", ".join(f"{k}={v}" for k, v in agents.most_common()))\n'
                        '    return 0\n'
                        '\n'
                        '\n'
                        'if __name__ == "__main__":\n'
                        '    raise SystemExit(main())\n',
 'verify.py': '#!/usr/bin/env python3\n'
              'from __future__ import annotations\n'
              '\n'
              '# adaptive-codex-harness-v6.10-minimal-diff-preflight:begin\n'
              'def _adaptive_harness_v610_minimal_diff_preflight() -> None:\n'
              '    import subprocess as _subprocess\n'
              '    import sys as _sys\n'
              '    from pathlib import Path as _Path\n'
              '\n'
              '    _root = _Path(__file__).resolve().parents[3]\n'
              '    _guard = _root / ".codex" / "harness" / "scripts" / "minimal_diff_guard.py"\n'
              '    if _guard.exists():\n'
              '        _cp = _subprocess.run([_sys.executable, str(_guard), "--quiet"], cwd=_root)\n'
              '        if _cp.returncode != 0:\n'
              '            raise SystemExit(\n'
              '                "Harness minimal-diff preflight failed; reduce rewrite-like edits before formal verification."\n'
              '            )\n'
              '# preflight is invoked from main only when verification commands will run\n'
              '# adaptive-codex-harness-v6.10-minimal-diff-preflight:end\n'
              '# adaptive-codex-harness-v6.5-side-effect-preflight:begin\n'
              '# Fail closed before formal verification can launch any Laravel test command.\n'
              'def _adaptive_harness_v65_preflight() -> None:\n'
              '    import subprocess as _subprocess\n'
              '    import sys as _sys\n'
              '    from pathlib import Path as _Path\n'
              '\n'
              '    _root = _Path(__file__).resolve().parents[3]\n'
              '    _scripts = _root / ".codex" / "harness" / "scripts"\n'
              '    if str(_scripts) not in _sys.path:\n'
              '        _sys.path.insert(0, str(_scripts))\n'
              '    from harness_paths import ensure_layout as _ensure_layout\n'
              '    _ensure_layout()\n'
              '    for _name in ("test_db_guard.py", "side_effect_guard.py"):\n'
              '        _guard = _root / ".codex" / "harness" / "scripts" / _name\n'
              '        if _guard.exists():\n'
              '            _cp = _subprocess.run([_sys.executable, str(_guard), "--quiet"], cwd=_root)\n'
              '            if _cp.returncode != 0:\n'
              '                raise SystemExit(f"Harness safety preflight failed in {_name}; verification aborted before tests.")\n'
              '# preflight is invoked from main only when verification commands will run\n'
              '# adaptive-codex-harness-v6.5-side-effect-preflight:end\n'
              '\n'
              'import argparse\n'
              'import json\n'
              'import subprocess\n'
              'import sys\n'
              'import time\n'
              'from pathlib import Path\n'
              '\n'
              'from common import WORKSPACE_ROOT, COMMANDS_PATH, RUNTIME_DIR, config, load_json, repo_state_hash\n'
              'from output_guard import prune_failed_logs, read_detail, run_guarded\n'
              '\n'
              'VERIFY_ROOT = RUNTIME_DIR / "verification"\n'
              'LATEST_PATH = VERIFY_ROOT / "latest.json"\n'
              '\n'
              '\n'
              'def _selected_commands(cfg: dict, profile: str) -> list[dict]:\n'
              '    return [\n'
              '        c for c in cfg.get("commands", [])\n'
              '        if c.get("enabled", True) and profile in c.get("profiles", ["quick", "full"])\n'
              '    ]\n'
              '\n'
              '\n'
              'def _load_latest() -> dict:\n'
              '    return load_json(LATEST_PATH, {})\n'
              '\n'
              '\n'
              'def _show_previous(name_filter: str | None, raw: bool) -> int:\n''    latest = _load_latest()\n'
              '    if not latest:\n'
              '        print("No previous verification log is available.")\n'
              '        return 2\n'
              '\n'
              '    token_cfg = config().get("token_efficiency", {})\n'
              '    verification_cfg = token_cfg.get("verification", {}) if isinstance(token_cfg, dict) else {}\n'
              '    detail_max = int(verification_cfg.get("detail_max_lines", 400))\n'
              '    scan_bytes = int(verification_cfg.get("tail_scan_bytes", 2 * 1024 * 1024))\n'
              '\n'
              '    matched = 0\n'
              '    for result in latest.get("results", []):\n'
              '        name = str(result.get("name", ""))\n'
              '        if name_filter and name_filter.casefold() not in name.casefold():\n'
              '            continue\n'
              '        rel = result.get("log_path")\n'
              '        if not rel:\n'
              '            continue\n'
              '        log_path = RUNTIME_DIR / rel\n'
              '        if not log_path.exists():\n'
              '            continue\n'
              '        matched += 1\n'
              '        print(f"\\n==> {\'RAW\' if raw else \'DETAIL\'}: {name}")\n'
              '        lines = read_detail(log_path, detail_max, scan_bytes, raw=raw)\n'
              '        if raw:\n'
              '            for line in lines:\n'
              '                print(line)\n'
              '        else:\n'
              '            for line in lines[:detail_max]:\n'
              '                print(line)\n'
              '            if len(lines) >= detail_max:\n'
              '                print(f"... detail capped at {detail_max} lines; use --raw only if still necessary")\n'
              '\n'
              '    if matched == 0:\n'
              '        print("No retained failed log matched. Successful command logs are discarded by default.")\n'
              '        return 2\n'
              '    return 0\n'
              '\n'
              '\n'
              'def main() -> int:\n'
              '    ap = argparse.ArgumentParser(description="Token-efficient harness verification")\n'
              '    ap.add_argument("--profile", default="quick", choices=["quick", "full"])\n'
              '    ap.add_argument("--list", action="store_true")\n'
              '    group = ap.add_mutually_exclusive_group()\n'
              '    group.add_argument("--detail", nargs="?", const="", metavar="NAME", help="Show a bounded excerpt from the latest '
              'retained failed log without rerunning tests")\n'
              '    group.add_argument("--raw", nargs="?", const="", metavar="NAME", help="Show the full latest retained failed log without '
              'rerunning tests")\n'
              '    args = ap.parse_args()\n'
              '\n'
              '    if args.detail is not None:\n'
              '        return _show_previous(args.detail or None, raw=False)\n'
              '    if args.raw is not None:\n'
              '        return _show_previous(args.raw or None, raw=True)\n'
              '\n'
              '    command_cfg = load_json(COMMANDS_PATH, {"status": "uninitialized", "commands": []})\n'
              '    commands = _selected_commands(command_cfg, args.profile)\n'
              '    if args.list:\n'
              '        print(json.dumps(commands, ensure_ascii=False, indent=2))\n'
              '        return 0\n'
              '\n'
              '    _adaptive_harness_v610_minimal_diff_preflight()\n'
              '    _adaptive_harness_v65_preflight()\n'
              '\n'
              '    if command_cfg.get("status") != "ready" or not commands:\n'
              '        print("Harness verification commands are not initialized. Run `$harness-bootstrap` and confirm real project '
              'commands.")\n'
              '        return 2\n'
              '\n'
              '    harness_cfg = config()\n'
              '\n'
              '    # Architecture ratchet is part of the same human/Codex/CI gate.\n'
              '    # Default mode is advisory and an empty rule set is a no-op.\n'
              '    arch_script = Path(__file__).resolve().parent / "architecture_check.py"\n'
              '    if arch_script.exists():\n'
              '        arch = subprocess.run([sys.executable, str(arch_script), "--json"], cwd=WORKSPACE_ROOT, text=True, '
              'capture_output=True)\n'
              '        try:\n'
              '            payload = json.loads((arch.stdout or "{}").strip() or "{}")\n'
              '        except Exception:\n'
              '            payload = {}\n'
              '        findings = payload.get("findings", []) if isinstance(payload, dict) else []\n'
              '        mode = payload.get("mode", "advisory") if isinstance(payload, dict) else "advisory"\n'
              '        if findings:\n'
              '            print(f"[{\'FAIL\' if arch.returncode else \'WARN\'}] Architecture ratchet ({len(findings)} finding(s), '
              'mode={mode})")\n'
              '            for f in findings[:8]:\n'
              '                print(f"  {f.get(\'path\')}:{f.get(\'line\',\'?\')} [{f.get(\'rule\',\'?\')}] {f.get(\'message\',\'\')}")\n'
              '            if len(findings) > 8:\n'
              '                print(f"  ... {len(findings)-8} more; run architecture_check.py for details")\n'
              '        elif mode != "off":\n'
              '            print(f"[PASS] Architecture ratchet ({mode})")\n'
              '        if arch.returncode != 0:\n'
              '            print("==> Harness verification: FAIL (architecture gate)")\n'
              '            return 1\n'
              '    token_cfg = harness_cfg.get("token_efficiency", {})\n'
              '    verification_cfg = token_cfg.get("verification", {}) if isinstance(token_cfg, dict) else {}\n'
              '    keep_runs = int(verification_cfg.get("failed_log_retention_runs", 12))\n'
              '\n'
              '    run_id = time.strftime("%Y%m%d-%H%M%S")\n'
              '    run_dir = VERIFY_ROOT / run_id\n'
              '    results: list[dict] = []\n'
              '    required_pass = True\n'
              '\n'
              '    print(f"==> Harness verification [{args.profile}] ({len(commands)} checks)")\n'
              '    for item in commands:\n'
              '        cmd = item.get("command")\n'
              '        name = item.get("name", cmd)\n'
              '        required = item.get("required", True)\n'
              '        timeout = int(item.get("timeout_seconds", 900))\n'
              '        cwd = WORKSPACE_ROOT / item.get("cwd", ".")\n'
              '\n'
              '        result = run_guarded(\n'
              '            name=name,\n'
              '            command=cmd,\n'
              '            cwd=cwd,\n'
              '            timeout=timeout,\n'
              '            item=item,\n'
              '            token_cfg=token_cfg,\n'
              '            run_dir=run_dir,\n'
              '        )\n'
              '        result["required"] = required\n'
              '        results.append(result)\n'
              '        passed = bool(result["passed"])\n'
              '        required_pass = required_pass and (passed or not required)\n'
              '\n'
              '        state = "PASS" if passed else "FAIL"\n'
              '        print(f"[{state}] {name} ({result[\'elapsed_seconds\']}s, exit={result[\'exit_code\']})")\n'
              '        for line in result.get("excerpt", []):\n'
              '            print(f"  {line}")\n'
              '        if not passed and result.get("log_path"):\n'
              '            print(f"  retained log: .harness/runtime/{result[\'log_path\']}")\n'
              '            print(f"  more detail: python3 .codex/harness/scripts/verify.py --detail \\"{name}\\"")\n'
              '\n'
              '    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)\n'
              '    VERIFY_ROOT.mkdir(parents=True, exist_ok=True)\n'
              '    stamp = {\n'
              '        "state_hash": repo_state_hash(harness_cfg),\n'
              '        "passed": required_pass,\n'
              '        "profile": args.profile,\n'
              '        "timestamp": time.time(),\n'
              '        "results": results,\n'
              '    }\n'
              '    (RUNTIME_DIR / "verify-stamp.json").write_text(json.dumps(stamp, ensure_ascii=False, indent=2), encoding="utf-8")\n'
              '    LATEST_PATH.write_text(json.dumps(stamp, ensure_ascii=False, indent=2), encoding="utf-8")\n'
              '    prune_failed_logs(VERIFY_ROOT, keep_runs)\n'
              '\n'
              '    print(f"==> Harness verification: {\'PASS\' if required_pass else \'FAIL\'}")\n'
              '    if not required_pass:\n'
              '        print("Use --detail first. Use --raw only if the bounded detail is insufficient.")\n'
              '    return 0 if required_pass else 1\n'
              '\n'
              '\n'
              'if __name__ == "__main__":\n'
              '    raise SystemExit(main())\n'}
V612_DOC = '# Adaptive Codex Harness v6.12\n\nv6.12 adds an evidence-based diagnosis policy on top of the reviewed v6.11 Harness.\n\nChanges:\n- Preserves the v6.11 minimal-edit, runtime-hygiene, safety, verification, and lifecycle behavior.\n- Requires the actual user screen/route/action to be identified before a reported UI or validation defect is diagnosed.\n- Requires relevant runtime/data flow to be traced far enough to explain the observed symptom before a cause is called confirmed.\n- For UI/form/validation defects, checks rendered values, JavaScript/DOM mutation, submitted values, server validation/lookup, redirect/re-render state, and CSS only where relevant.\n- A declaration such as `required`, a route definition, or one controller branch is treated as partial evidence rather than proof of end-to-end behavior.\n- The first plausible cause remains a hypothesis until it matches the observed behavior and important contradictory evidence has been checked.\n- When direct execution or observation is unavailable, findings must distinguish verified code facts from inference.\n- Review/verification now check the decisive boundary/value and the reported symptom, not merely the presence of static validation or tests.\n- Keeps defect explanations concise: concrete boundary/value, incorrect effect, and correct effect; no unnecessary implementation dump.\n\nNo new runtime hook is added for causal diagnosis because this is a reasoning/evidence policy rather than a mechanically safe pre-tool block.\n'
AGENTS_BLOCK = "<!-- adaptive-codex-harness-v6.12:begin -->\n## Adaptive Codex Harness v6.12 — evidence-based diagnosis / minimal edits\n- Existing tracked files are edited with the smallest practical `Edit`/`apply_patch`; do not replace nearly the whole file for a local change.\n- Resolve each file to its configured Git root (for example `src/`) and run `python3 .codex/harness/scripts/minimal_diff_guard.py` before final verification. A `checked 0` result is not evidence for a changed application file.\n- `.codex/` and `.agents/` are static Harness configuration. Mutable logs and transient state belong in `.harness/runtime/`; durable Harness state belongs in `.harness/state/`. Do not leave source-tree snapshots/worktrees in runtime after the operation ends.\n- Before declaring a bug cause, identify the user's actual screen/route/action and trace the relevant runtime/data flow far enough to explain the observed symptom.\n- Do not infer end-to-end behavior from a declaration alone. For UI/form/validation bugs, check rendered values, JavaScript/DOM mutation, submitted values, server validation/lookup, redirect/re-render state, and CSS only as applicable.\n- Treat the first plausible cause as a hypothesis until it explains the observed behavior and important contradictory evidence has been checked. If direct execution is unavailable, separate verified code facts from inference.\n- Bug explanations are concise and concrete: include the decisive code boundary/value and the incorrect vs correct effect; include calculations only when they materially clarify the symptom.\n<!-- adaptive-codex-harness-v6.12:end -->"
SKILL_BLOCK_BASE = "<!-- adaptive-codex-harness-v6.12:begin -->\n### v6.12 evidence / minimal-edit policy\n- Resolve edited files to the owning configured Git root; do not assume the workspace root itself is the repository.\n- Preserve unchanged existing content; use targeted edits and run `python3 .codex/harness/scripts/minimal_diff_guard.py` before final verification.\n- Keep Harness mutable output under `.harness/`; do not create runtime/state/log/cache data under `.codex/` or `.agents/`, and do not leave temporary source snapshots in runtime.\n- Do not promote a plausible cause to confirmed until the relevant evidence explains the user's observed symptom.\n{extra}- Keep defect explanations to the decisive boundary/value and effect required to understand the issue.\n<!-- adaptive-codex-harness-v6.12:end -->"
SKILL_EXTRAS = {'harness-debug': '- For UI/form/validation defects, identify the actual screen/route/action, then trace rendered value -> JavaScript/DOM mutation -> submitted value -> server validation/lookup -> redirect/re-render/CSS as relevant; skip irrelevant stages but do not assume them.\n- A declaration such as `required`, a route definition, or one controller branch proves only that declaration, not end-to-end behavior.\n- When execution/observation is incomplete, label the remaining conclusion as a hypothesis and state the missing observation instead of asserting it.\n', 'harness-develop': '- Before fixing a reported defect, verify the causal path enough to avoid patching the wrong layer; a static rule or nearby branch alone is insufficient.\n', 'harness-review': '- Flag causal conclusions supported only by partial code inspection; confirm that the proposed cause matches the reported symptom and the relevant runtime/data flow.\n', 'harness-verify': '- Verify the reported symptom and decisive boundary/value where practical; the existence of tests or static validation alone does not prove the original behavior is fixed.\n'}


class InstallError(RuntimeError):
    pass


@dataclass
class Plan:
    target: Path
    writes: dict[Path, bytes] = field(default_factory=dict)
    chmods: dict[Path, int] = field(default_factory=dict)
    archive_remove: list[Path] = field(default_factory=list)
    direct_remove: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def stage_text(self, rel: str, text: str) -> None:
        path = self.target / rel
        data = text.encode("utf-8")
        current = path.read_bytes() if path.is_file() else None
        if current != data:
            self.writes[path] = data

    def staged_or_disk(self, rel: str) -> bytes:
        path = self.target / rel
        if path in self.writes:
            return self.writes[path]
        if not path.is_file():
            raise InstallError(f"manifest target is missing: {rel}")
        return path.read_bytes()


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", text)
    if not match:
        raise InstallError(f"invalid Harness VERSION: {text!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InstallError(f"cannot read {path}: {exc}") from exc


def require_files(target: Path, rels: Iterable[str]) -> None:
    missing = [rel for rel in rels if not (target / rel).is_file()]
    if missing:
        raise InstallError("required file(s) missing: " + ", ".join(missing))


def validate_current_state(target: Path, current_version: tuple[int, int, int]) -> None:
    if current_version == (6, 10, 0):
        drift = []
        for rel, expected in REVIEWED_V610_CORE.items():
            path = target / rel
            if not path.is_file():
                drift.append(f"missing:{rel}")
            elif sha256_file(path) != expected:
                drift.append(rel)
        if drift:
            raise InstallError(
                "Reviewed v6.10 core files contain unreviewed changes: " + ", ".join(drift[:12]) +
                ". Refusing to overwrite them automatically."
            )
        return

    expected_manifest_version = "6.11.0" if current_version == (6, 11, 0) else VERSION
    manifest_path = target / ".codex/harness/installed-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise InstallError(f"v{current_version[0]}.{current_version[1]} installed-manifest.json is invalid: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != expected_manifest_version:
        raise InstallError(
            f"target VERSION is {current_version[0]}.{current_version[1]}.{current_version[2]} "
            f"but installed manifest is not {expected_manifest_version}"
        )
    payload = manifest.get("payload_sha256")
    if not isinstance(payload, dict) or not payload:
        raise InstallError(f"{expected_manifest_version} installed manifest has no payload hashes")
    drift = []
    for rel, expected in payload.items():
        path = target / str(rel)
        if not path.is_file() or sha256_file(path) != str(expected):
            drift.append(str(rel))
    if drift:
        raise InstallError(
            f"Existing {expected_manifest_version} Harness-owned drift detected: " + ", ".join(drift[:12])
        )


def upsert_managed_block(text: str, block: str, names: Iterable[str]) -> str:
    for name in names:
        begin = f"<!-- adaptive-codex-harness-{name}:begin -->"
        end = f"<!-- adaptive-codex-harness-{name}:end -->"
        if begin in text or end in text:
            if text.count(begin) != 1 or text.count(end) != 1:
                raise InstallError(f"malformed managed block {name}")
            start = text.index(begin)
            finish = text.index(end, start) + len(end)
            out = text[:start] + block + text[finish:]
            return out if out.endswith("\n") else out + "\n"
    base = text.rstrip()
    return (base + "\n\n" + block + "\n") if base else block + "\n"


def patch_config(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception as exc:
        raise InstallError(f"config.json is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("config.json root must be an object")
    meta = data.setdefault("harness_meta", {})
    if not isinstance(meta, dict):
        raise InstallError("config.harness_meta must be an object")
    meta["version"] = VERSION
    gate = data.setdefault("quality_gate", {})
    if not isinstance(gate, dict):
        raise InstallError("config.quality_gate must be an object")
    nontrivial = gate.setdefault("nontrivial", {})
    if not isinstance(nontrivial, dict):
        raise InstallError("config.quality_gate.nontrivial must be an object")
    nontrivial["changed_files"] = 5
    task_state = data.setdefault("task_state", {})
    if not isinstance(task_state, dict):
        raise InstallError("config.task_state must be an object")
    task_state["storage"] = ".harness/state/task-state"
    data["runtime_retention"] = {
        "session_days": 7,
        "stop_block_days": 7,
        "telemetry_days": 14,
        "quiet_exec_days": 7,
        "review_log_days": 7,
        "restore_log_days": 14,
        "verification_runs": 8,
        "task_scope_hours": 24,
        "test_storage_hours": 24,
        "legacy_replay_hours": 6,
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def patch_minimal_policy(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception as exc:
        raise InstallError(f"minimal_edit_policy.json is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("minimal_edit_policy root must be an object")
    data["version"] = VERSION
    guard = data.setdefault("guard", {})
    if not isinstance(guard, dict):
        raise InstallError("minimal_edit_policy.guard must be an object")
    guard["split_git_roots"] = True
    guard["block_large_edit_replacements"] = True
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def dynamic_command(subdir: str, filename: str) -> str:
    return (
        "/bin/sh -c 'd=$PWD; while [ \"$d\" != / ]; do "
        f"p=\"$d/.codex/harness/{subdir}/{filename}\"; "
        "if [ -f \"$p\" ]; then exec /usr/bin/env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 \"$p\"; fi; "
        "d=${d%/*}; [ -n \"$d\" ] || d=/; done; exit 0'"
    )


def iter_hook_commands(hooks: dict[str, Any]):
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            inner = entry.get("hooks", [])
            if not isinstance(inner, list):
                continue
            for hook in inner:
                if isinstance(hook, dict):
                    yield hook


def patch_hooks(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception as exc:
        raise InstallError(f"hooks.json is invalid: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        raise InstallError("hooks.json lacks a hooks object")
    hooks = data["hooks"]
    data["description"] = "Adaptive Codex Harness v6.12 lifecycle, safety, runtime hygiene, and evidence-based diagnosis."

    found = {"pre_tool_safety.py": 0, "minimal_edit_pretool.py": 0}
    for hook in iter_hook_commands(hooks):
        command = hook.get("command")
        if not isinstance(command, str):
            continue
        if "pre_tool_safety.py" in command:
            hook["command"] = dynamic_command("hooks", "pre_tool_safety.py")
            found["pre_tool_safety.py"] += 1
        elif "minimal_edit_pretool.py" in command:
            hook["command"] = dynamic_command("hooks", "minimal_edit_pretool.py")
            found["minimal_edit_pretool.py"] += 1
        elif ".codex/harness/" in command and "exec /usr/bin/python3 \"$p\"" in command:
            hook["command"] = command.replace(
                "exec /usr/bin/python3 \"$p\"",
                "exec /usr/bin/env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 \"$p\"",
            )
    for filename, count in found.items():
        if count != 1:
            raise InstallError(f"expected exactly one hook for {filename}, found {count}")

    starts = hooks.setdefault("SessionStart", [])
    if not isinstance(starts, list):
        raise InstallError("hooks.SessionStart must be a list")
    # Remove only previous runtime-cleanup entries so reruns stay idempotent.
    cleaned = []
    for entry in starts:
        if not isinstance(entry, dict):
            cleaned.append(entry); continue
        inner = entry.get("hooks", [])
        if isinstance(inner, list) and any(isinstance(h, dict) and "runtime_cleanup.py" in str(h.get("command", "")) for h in inner):
            continue
        cleaned.append(entry)
    cleaned.append({
        "matcher": "startup|resume|clear|compact",
        "hooks": [{
            "type": "command",
            "command": dynamic_command("scripts", "runtime_cleanup.py"),
            "timeout": 3,
            "async": True,
        }],
    })
    hooks["SessionStart"] = cleaned
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def patch_agents(text: str) -> str:
    text = text.replace("一時audit/report/logは `.codex/harness/runtime/` に置く。", "一時audit/report/logは `.harness/runtime/` に置く。")
    return upsert_managed_block(text, AGENTS_BLOCK, ("v6.12", "v6.11", "v6.10"))


def patch_skill(text: str, skill: str) -> str:
    if skill not in SKILL_EXTRAS:
        raise InstallError(f"unsupported skill patch target: {skill}")
    block = SKILL_BLOCK_BASE.format(extra=SKILL_EXTRAS[skill])
    return upsert_managed_block(text, block, ("v6.12", "v6.11", "v6.10"))


def merge_install_history(target: Path) -> str | None:
    sources = [target / ".harness/state/install-history.jsonl", target / ".codex/harness/runtime/install-history.jsonl"]
    lines: list[str] = []
    seen: set[str] = set()
    for path in sources:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and line not in seen:
                seen.add(line); lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "") if lines else None


def manifest_candidates(target: Path) -> list[str]:
    rels: set[str] = set()
    harness = target / ".codex/harness"
    if harness.is_dir():
        for path in harness.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(target).as_posix()
            if "/runtime/" in "/" + rel or "__pycache__" in path.parts:
                continue
            if rel in {
                ".codex/harness/config.json",
                ".codex/harness/commands.json",
                ".codex/harness/architecture_rules.json",
                ".codex/harness/installed-manifest.json",
            }:
                continue
            rels.add(rel)
    for base in (target / ".codex/agents", target / ".codex/rules", target / ".agents/skills"):
        if base.is_dir():
            for path in base.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    rels.add(path.relative_to(target).as_posix())
    return sorted(rels)


def manifest_text(plan: Plan) -> str:
    payload: dict[str, str] = {}
    for rel in manifest_candidates(plan.target):
        payload[rel] = sha256_bytes(plan.staged_or_disk(rel))
    # Newly-created owned files are not visible to manifest_candidates until after install.
    for rel in (
        ".codex/harness/V6_12.md",
        ".codex/harness/hooks/pre_tool_safety.py",
        ".codex/harness/hooks/minimal_edit_pretool.py",
        ".codex/harness/scripts/minimal_diff_guard.py",
        ".codex/harness/scripts/runtime_cleanup.py",
    ):
        payload[rel] = sha256_bytes(plan.staged_or_disk(rel))
    return json.dumps({"version": VERSION, "payload_sha256": dict(sorted(payload.items()))}, ensure_ascii=False, indent=2) + "\n"


def _same_or_note(plan: Plan, rel: str, expected: str | tuple[str, ...], purpose: str) -> None:
    path = plan.target / rel
    if not path.is_file():
        return
    accepted = {expected} if isinstance(expected, str) else set(expected)
    if sha256_file(path) in accepted:
        plan.archive_remove.append(path)
    else:
        plan.notes.append(f"PRESERVE modified {rel}: {purpose}; hash differs from reviewed copy")


def legacy_knowledge_safe_to_archive(target: Path) -> tuple[bool, list[str]]:
    legacy = target / ".agents/knowledge"
    docs = target / "docs"
    if not legacy.is_dir() or not docs.is_dir():
        return False, []
    missing = []
    for path in legacy.rglob("*"):
        if path.is_file():
            rel = path.relative_to(legacy)
            if not (docs / rel).is_file():
                missing.append(rel.as_posix())
    return not missing, missing


def timestamp_from_name(path: Path, prefix: str, fmt: str) -> float | None:
    raw = path.name.removeprefix(prefix)
    try:
        return datetime.strptime(raw, fmt).timestamp()
    except ValueError:
        return None


def json_timestamp(path: Path, key: str) -> float | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get(key) if isinstance(data, dict) else None
        return float(value) if value is not None else None
    except Exception:
        return None


def old_enough(path: Path, seconds: int, timestamp: float | None = None) -> bool:
    if timestamp is None:
        try:
            timestamp = path.stat().st_mtime
        except OSError:
            return False
    return time.time() - timestamp >= seconds


def collect_runtime_prune(target: Path) -> list[Path]:
    runtime = target / ".harness/runtime"
    if not runtime.is_dir():
        return []
    found: set[Path] = set()
    for path in runtime.glob("session-*.json"):
        if old_enough(path, 7 * 86400, json_timestamp(path, "created_at")):
            found.add(path)
    for path in runtime.glob("stop-block-*.json"):
        if old_enough(path, 7 * 86400, json_timestamp(path, "timestamp")):
            found.add(path)
    for folder, pattern, days in (("telemetry", "*.jsonl", 14), ("quiet-exec", "*.log", 7)):
        base = runtime / folder
        if base.is_dir():
            for path in base.glob(pattern):
                if old_enough(path, days * 86400): found.add(path)
    for path in runtime.glob("review-*.log"):
        if old_enough(path, 7 * 86400): found.add(path)
    for path in runtime.glob("restore-*.log"):
        stamp = re.search(r"(\d{8}-\d{6})$", path.stem)
        ts = None
        if stamp:
            try: ts = datetime.strptime(stamp.group(1), "%Y%m%d-%H%M%S").timestamp()
            except ValueError: pass
        if old_enough(path, 14 * 86400, ts): found.add(path)
    scope = runtime / "task_scope/current.json"
    if scope.is_file() and old_enough(scope, 24 * 3600, json_timestamp(scope, "created_at")):
        found.add(scope)
    storage = runtime / "test-storage"
    if storage.is_dir():
        for child in storage.iterdir():
            if old_enough(child, 24 * 3600): found.add(child)
    for replay in runtime.glob("legacy-replay-*"):
        if replay.is_dir() and old_enough(replay, 6 * 3600, timestamp_from_name(replay, "legacy-replay-", "%Y%m%d-%H%M%S")):
            found.add(replay)
    verify = runtime / "verification"
    if verify.is_dir():
        runs = sorted((p for p in verify.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)
        found.update(runs[8:])
    return sorted(found)


def build_plan(target: Path) -> Plan:
    required = [
        "AGENTS.md",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/harness/VERSION",
        ".codex/harness/config.json",
        ".codex/harness/installed-manifest.json",
        ".codex/harness/minimal_edit_policy.json",
        ".codex/harness/hooks/pre_tool_safety.py",
        ".codex/harness/hooks/minimal_edit_pretool.py",
        ".codex/harness/hooks/harness_hook.py",
        ".codex/harness/scripts/selftest.py",
        ".codex/harness/scripts/verify.py",
        ".codex/harness/scripts/task_scope.py",
        ".codex/harness/scripts/task_state.py",
        ".codex/harness/scripts/telemetry_report.py",
        ".codex/harness/scripts/architecture_check.py",
        ".codex/harness/scripts/minimal_diff_guard.py",
        ".codex/harness/bin/codex-project",
    ]
    require_files(target, required)
    version = parse_version(load_text(target / ".codex/harness/VERSION"))
    if version not in SUPPORTED_FROM:
        raise InstallError(f"supported source versions are 6.10.0/6.11.0/6.12.0, found {version}")
    validate_current_state(target, version)

    plan = Plan(target=target)
    plan.stage_text(".codex/harness/VERSION", VERSION + "\n")
    plan.stage_text(".codex/harness/V6_12.md", V612_DOC)
    plan.stage_text(".codex/harness/config.json", patch_config(load_text(target / ".codex/harness/config.json")))
    plan.stage_text(".codex/harness/minimal_edit_policy.json", patch_minimal_policy(load_text(target / ".codex/harness/minimal_edit_policy.json")))
    plan.stage_text(".codex/hooks.json", patch_hooks(load_text(target / ".codex/hooks.json")))
    plan.stage_text("AGENTS.md", patch_agents(load_text(target / "AGENTS.md")))

    mapping = {
        ".codex/harness/hooks/pre_tool_safety.py": "pre_tool_safety.py",
        ".codex/harness/hooks/minimal_edit_pretool.py": "minimal_edit_pretool.py",
        ".codex/harness/hooks/harness_hook.py": "harness_hook.py",
        ".codex/harness/scripts/minimal_diff_guard.py": "minimal_diff_guard.py",
        ".codex/harness/scripts/selftest.py": "selftest.py",
        ".codex/harness/scripts/task_state.py": "task_state.py",
        ".codex/harness/scripts/telemetry_report.py": "telemetry_report.py",
        ".codex/harness/scripts/task_scope.py": "task_scope.py",
        ".codex/harness/scripts/architecture_check.py": "architecture_check.py",
        ".codex/harness/scripts/verify.py": "verify.py",
        ".codex/harness/scripts/runtime_cleanup.py": "runtime_cleanup.py",
        ".codex/harness/bin/codex-project": "codex-project",
    }
    for rel, name in mapping.items():
        plan.stage_text(rel, DESIRED_SOURCES[name])

    for skill in ("harness-debug", "harness-develop", "harness-review", "harness-verify"):
        rel = f".agents/skills/{skill}/SKILL.md"
        require_files(target, [rel])
        plan.stage_text(rel, patch_skill(load_text(target / rel), skill))

    history = merge_install_history(target)
    if history is not None:
        plan.stage_text(".harness/state/install-history.jsonl", history)

    launcher = target / ".codex/harness/bin/codex-project"
    current_mode = launcher.stat().st_mode & 0o7777
    desired_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if current_mode != desired_mode:
        plan.chmods[launcher] = desired_mode

    static_runtime = target / ".codex/harness/runtime"
    if static_runtime.exists():
        plan.archive_remove.append(static_runtime)
        plan.notes.append("archive/remove legacy mutable .codex/harness/runtime/")

    for rel, expected in LEGACY_HOOK_HASHES.items():
        _same_or_note(plan, rel, expected, "obsolete .agents knowledge lifecycle hook is no longer registered")
    for rel, expected in ONEOFF_RUNTIME_HASHES.items():
        _same_or_note(plan, rel, expected, "reviewed one-off restore/analysis source should not remain in live runtime")

    safe, missing = legacy_knowledge_safe_to_archive(target)
    legacy_knowledge = target / ".agents/knowledge"
    if safe and legacy_knowledge.is_dir():
        plan.archive_remove.append(legacy_knowledge)
        plan.notes.append("archive/remove legacy .agents/knowledge because every relative document has a docs/ counterpart")
    elif legacy_knowledge.is_dir():
        suffix = ", ".join(missing[:6]) if missing else "docs/ counterpart tree unavailable"
        plan.notes.append(f"PRESERVE .agents/knowledge: canonical docs migration cannot be proven complete ({suffix})")

    for base in (target / ".codex", target / ".agents"):
        if base.exists():
            plan.direct_remove.extend(p for p in base.rglob("__pycache__") if p.is_dir())

    empty_backup = target / ".harness/backups/approval-20260922-20260924-002921"
    if empty_backup.is_dir() and not any(empty_backup.iterdir()):
        plan.direct_remove.append(empty_backup)

    plan.direct_remove.extend(collect_runtime_prune(target))

    # Avoid children when a parent is already scheduled, and avoid direct removal of anything archived.
    archive = sorted(set(plan.archive_remove), key=lambda p: (len(p.parts), str(p)))
    archive_final: list[Path] = []
    for path in archive:
        if not any(parent == path or parent in path.parents for parent in archive_final):
            archive_final.append(path)
    plan.archive_remove = archive_final
    direct = sorted(set(plan.direct_remove), key=lambda p: (len(p.parts), str(p)))
    direct_final: list[Path] = []
    for path in direct:
        if any(parent == path or parent in path.parents for parent in plan.archive_remove):
            continue
        if any(parent == path or parent in path.parents for parent in direct_final):
            continue
        direct_final.append(path)
    plan.direct_remove = direct_final

    # Manifest must be staged after every owned static payload has reached its desired content.
    plan.stage_text(".codex/harness/installed-manifest.json", manifest_text(plan))
    return plan


def rel_to_target(target: Path, path: Path) -> Path:
    try:
        return path.relative_to(target)
    except ValueError as exc:
        raise InstallError(f"path escapes target: {path}") from exc


def atomic_write(path: Path, data: bytes, mode: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.v611-", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.chmod(tmp, mode if mode is not None else 0o644)
        os.replace(tmp, path)
    finally:
        if tmp.exists(): tmp.unlink()


def run_checked(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    cp = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if cp.returncode != 0:
        raise InstallError(f"check failed ({' '.join(cmd)}):\n{cp.stdout.rstrip()}")
    return cp.stdout


def run_checks(target: Path) -> None:
    for base in (target / ".codex/harness/scripts", target / ".codex/harness/hooks"):
        for path in base.glob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
    for rel in (
        ".codex/harness/config.json", ".codex/harness/commands.json", ".codex/harness/architecture_rules.json",
        ".codex/harness/minimal_edit_policy.json", ".codex/harness/installed-manifest.json", ".codex/hooks.json",
    ):
        json.loads((target / rel).read_text(encoding="utf-8"))
    try:
        import tomllib
        tomllib.loads((target / ".codex/config.toml").read_text(encoding="utf-8"))
    except ImportError:
        pass
    except Exception as exc:
        raise InstallError(f"config.toml parse failed: {exc}") from exc

    env = os.environ.copy(); env["PYTHONDONTWRITEBYTECODE"] = "1"
    run_checked(["bash", "-n", str(target / ".codex/harness/bin/codex-project")], target, env)
    tests = target / ".codex/harness/hooks/tests"
    if tests.is_dir():
        run_checked([sys.executable, "-m", "unittest", "discover", "-s", str(tests), "-p", "test_*.py"], target, env)
    run_checked([sys.executable, str(target / ".codex/harness/scripts/selftest.py"), "--install-check", "--quiet"], target, env)


def backup_path(backup_root: Path, target: Path, path: Path) -> Path:
    return backup_root / rel_to_target(target, path)


def copy_to_backup(backup_root: Path, target: Path, path: Path) -> None:
    dest = backup_path(backup_root, target, path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir(): shutil.copytree(path, dest, copy_function=shutil.copy2)
    else: shutil.copy2(path, dest)


def restore_from_backup(backup_root: Path, target: Path, path: Path) -> None:
    src = backup_path(backup_root, target, path)
    if not src.exists(): return
    if path.exists():
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir(): shutil.copytree(src, path, copy_function=shutil.copy2)
    else: shutil.copy2(src, path)


def apply_plan(plan: Plan, dry_run: bool) -> int:
    target = plan.target
    writes = sorted(plan.writes)
    chmods = sorted(plan.chmods)
    archive_remove = sorted(plan.archive_remove)
    direct_remove = sorted(plan.direct_remove)
    changed = bool(writes or chmods or archive_remove or direct_remove)

    print(f"Adaptive Codex Harness v6.12 target: {target}")
    for note in plan.notes:
        print(f"  NOTE {note}")
    if not changed:
        print("No changes required; Harness is already at the v6.12 target state.")
        return 0
    prefix = "WOULD " if dry_run else ""
    for path in writes: print(f"  {prefix}UPDATE {rel_to_target(target, path)}")
    for path in chmods: print(f"  {prefix}CHMOD +x {rel_to_target(target, path)}")
    for path in archive_remove: print(f"  {prefix}ARCHIVE/REMOVE {rel_to_target(target, path)}{'/' if path.is_dir() else ''}")
    for path in direct_remove: print(f"  {prefix}REMOVE EPHEMERAL {rel_to_target(target, path)}{'/' if path.is_dir() else ''}")
    if dry_run: return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = target / ".harness/backups" / f"v6.12-{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    existed: set[Path] = set()
    backed: set[Path] = set()
    try:
        for path in sorted(set(writes) | set(chmods)):
            if path.exists():
                copy_to_backup(backup_root, target, path); existed.add(path); backed.add(path)
        for path in archive_remove:
            if path.exists():
                copy_to_backup(backup_root / "_removed", target, path); backed.add(path)

        for path, data in plan.writes.items():
            mode = (path.stat().st_mode & 0o7777) if path.exists() else None
            atomic_write(path, data, mode)
        for path, mode in plan.chmods.items(): os.chmod(path, mode)
        for path in archive_remove:
            if path.is_dir(): shutil.rmtree(path)
            elif path.exists(): path.unlink()

        # Removing old .agents hooks can leave empty scaffolding; only remove it if empty.
        for path in (target / ".agents/hooks/tests", target / ".agents/hooks"):
            try: path.rmdir()
            except OSError: pass

        run_checks(target)

        # Ephemeral data is reconstructible and intentionally is not duplicated into the installer backup.
        for path in direct_remove:
            if path.is_dir(): shutil.rmtree(path, ignore_errors=True)
            else: path.unlink(missing_ok=True)
        for path in (
            target / ".agents/hooks/tests", target / ".agents/hooks",
            target / ".harness/runtime/task_scope", target / ".harness/runtime/telemetry",
            target / ".harness/runtime/quiet-exec", target / ".harness/runtime/test-storage",
        ):
            try: path.rmdir()
            except OSError: pass

        history = target / ".harness/state/install-history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(), "to": VERSION, "backup": str(backup_root.relative_to(target)),
            "changed_files": len(writes), "archived_removed": len(archive_remove), "ephemeral_removed": len(direct_remove),
        }
        with history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        # Restore archive-removed paths first from _removed.
        removed_root = backup_root / "_removed"
        for path in reversed(archive_remove):
            src = backup_path(removed_root, target, path)
            if src.exists():
                if path.exists():
                    if path.is_dir(): shutil.rmtree(path)
                    else: path.unlink()
                path.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir(): shutil.copytree(src, path, copy_function=shutil.copy2)
                else: shutil.copy2(src, path)
        for path in reversed(writes):
            src = backup_path(backup_root, target, path)
            if src.exists():
                restore_from_backup(backup_root, target, path)
            elif path not in existed and path.exists():
                if path.is_dir(): shutil.rmtree(path)
                else: path.unlink()
        for path in chmods:
            src = backup_path(backup_root, target, path)
            if src.exists(): shutil.copy2(src, path)
        raise

    print(f"Installed Harness {VERSION}")
    print(f"Backup: {backup_root.relative_to(target)}")
    print("Post-install selftest: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reviewed Adaptive Codex Harness v6.10/v6.11/v6.12 -> v6.12 repair installer")
    parser.add_argument("--target", default=".", help="Harness workspace root (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    args = parser.parse_args()
    target = Path(args.target).expanduser().resolve()
    try:
        return apply_plan(build_plan(target), args.dry_run)
    except InstallError as exc:
        print(f"[install_v6_12:ERROR] {exc}", file=sys.stderr); return 2
    except Exception as exc:
        print(f"[install_v6_12:ERROR] unexpected failure: {type(exc).__name__}: {exc}", file=sys.stderr); return 3


if __name__ == "__main__":
    raise SystemExit(main())