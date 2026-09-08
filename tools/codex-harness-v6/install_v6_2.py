#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

VERSION = "6.2.0"

PROJECT_MARKERS = (
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "artisan", "composer.json", "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
)

# These are project-owned / learned state. v6.2 never replaces them by default.
PROJECT_STATE_PATHS = (
    "docs/", "memo/", ".codex/harness/config.json", ".codex/harness/commands.json",
    ".codex/harness/architecture_rules.json",
)

MANAGED_BEGIN = "<!-- adaptive-codex-harness-v6.2:begin -->"
MANAGED_END = "<!-- adaptive-codex-harness-v6.2:end -->"

AGENTS_BLOCK = f"""{MANAGED_BEGIN}
## Adaptive Codex Harness v6.2 — bounded execution
- Keep work scoped to the current user task. Pre-existing dirty-worktree changes/failures are non-blocking unless explicitly requested.
- Verification is risk-based: targeted checks by default; repository-wide/full gates only for broad/high-risk/release-sensitive work or when targeted checks are insufficient.
- Prefer existing tests, then extend an existing relevant test file. Create a new test file only for a material regression risk that existing coverage cannot reasonably validate. Never create tests merely to satisfy the Harness.
- Independent reviewer is normally skipped for small/low-risk work. Use at most one reviewer for broad/high-risk changes (roughly >=5 task-touched files, >=200 task-diff lines, auth/permission/security, schema/migration/persistent-data risk, cross-component behavioral change, or explicit review request).
- Review and verification must inspect the current task diff, not every unrelated pre-existing change.
- Do not repeatedly run the same full gate, re-read unchanged large diffs, or open raw/full logs when bounded output is sufficient.
- Stop hooks are advisory by default in v6.2; do not rely on a blocking Stop loop for correctness.
- Update durable project knowledge only for stable/repeated evidence or explicit user intent, not as automatic closeout for every task.
{MANAGED_END}
"""

POLICY = {
    "schema_version": 2,
    "version": VERSION,
    "quality_gate_mode": "advisory",
    "scope": {
        "preexisting_dirty_is_nonblocking": True,
        "task_scope_tool_for_medium_or_high_risk": True,
    },
    "verification": {
        "default": "targeted",
        "full_gate_for": [
            "release_or_deploy", "auth_permission_security", "database_schema_or_migration",
            "persistent_data_behavior", "broad_cross_component_change", "targeted_checks_insufficient",
            "explicit_user_request",
        ],
        "avoid_repeat_full_gate": True,
        "bounded_detail_lines": 120,
        "raw_logs": "manual_only_when_bounded_detail_is_insufficient",
    },
    "tests": {
        "prefer_existing_tests": True,
        "prefer_extending_existing_test_file": True,
        "new_test_file": "only_for_material_uncovered_regression_risk",
        "never_create_just_for_harness": True,
    },
    "reviewer": {
        "default": "skip",
        "max_reviewers": 1,
        "min_task_touched_files": 5,
        "approx_min_task_diff_lines": 200,
        "high_risk_paths": [
            "auth", "permission", "policy", "middleware", "migration", "schema", "routes",
            "security", "composer.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        ],
        "review_task_diff_only": True,
        "avoid_polling_loop": True,
    },
    "subagents": {
        "default": 0,
        "max": 2,
        "use_only_for_independent_workstreams": True,
        "do_not_spawn_replacement_reviewer_on_stall": True,
    },
    "knowledge": {
        "automatic_per_task_update": False,
        "promote_only_stable_repeated_evidence": True,
    },
    "hooks": {
        "blocking_stop_gate_default": False,
        "reason": "Avoid false continuation loops and parent/subagent ambiguity; explicit workflow checks remain authoritative.",
        "restart_codex_after_hook_changes": True,
    },
}

DEVELOP_APPEND = """

### v6.2 bounded execution addendum
- For medium/high-risk work, run `python3 .codex/harness/scripts/task_scope.py begin` before edits; use `... task_scope.py report` near closeout so pre-existing dirty changes are not reviewed as task changes.
- Keep unrelated dirty files and unrelated existing failures untouched.
- Prefer the smallest coherent edit; do not expand scope merely to make a repository-wide gate green.
- Tests: existing relevant tests first, then extend an existing test file; new test file only for a material uncovered regression risk.
- Use targeted verification by default. Full verification is not an automatic closeout step.
"""

VERIFY_APPEND = """

### v6.2 verification policy
1. Start from task-touched files / task scope, not the whole dirty worktree.
2. Small/low-risk: diff check + directly relevant tests/checks.
3. Moderate: add lint/format for task-touched files and the relevant regression group.
4. Broad/high-risk/release-sensitive: full gate may be appropriate, but unrelated pre-existing failures stay non-blocking.
5. Do not create new test files just to satisfy verification. Prefer existing coverage or extending an existing test.
6. Do not re-run an unchanged full gate repeatedly. After a small edit, re-run only invalidated checks unless final risk justifies a full pass.
7. Use bounded detail (about 120 lines or less) first; raw/full logs only when bounded detail cannot diagnose the failure.
"""

REVIEW_APPEND = """

### v6.2 reviewer policy
- Reviewer is normally skipped for small/low-risk changes.
- Spawn at most one bounded independent reviewer when the current task is broad/high-risk: roughly >=5 task-touched files, >=200 task-diff lines, auth/permission/security, schema/migration/persistent-data behavior, material cross-component behavior, or explicit review request.
- Review only the current-task diff. Pre-existing dirty changes are context only when necessary and are not findings to fix.
- Do not repeatedly poll a reviewer or spawn replacement reviewers. If a reviewer cannot complete, report that once instead of starting a loop.
- A review PASS is invalidated only by later edits relevant to the reviewed scope, not by unrelated pre-existing worktree changes.
"""

KNOWLEDGE_APPEND = """

### v6.2 knowledge policy
- Project knowledge is not an automatic per-task closeout step.
- Promote only stable, repeated, evidenced patterns or explicit user decisions.
- Do not turn one-off debugging observations, temporary failures, or task-local implementation details into durable rules.
"""

TASK_SCOPE_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / ".codex" / "harness" / "runtime" / "task_scope" / "current.json"

HIGH_RISK_PARTS = (
    "auth", "permission", "policy", "middleware", "migration", "schema", "routes/", "security",
    "composer.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
)

def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def git_roots() -> list[Path]:
    roots = []
    for p in [ROOT, *(x for x in ROOT.iterdir() if x.is_dir())]:
        if (p / ".git").exists():
            roots.append(p)
    return roots

def status_paths(git_root: Path) -> set[str]:
    cp = run(git_root, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if cp.returncode != 0:
        return set()
    chunks = cp.stdout.split("\0")
    out: set[str] = set()
    i = 0
    while i < len(chunks):
        item = chunks[i]
        if not item:
            i += 1; continue
        if len(item) >= 4:
            code, path = item[:2], item[3:]
            out.add(path)
            if (code.startswith("R") or code.startswith("C")) and i + 1 < len(chunks) and chunks[i+1]:
                out.add(chunks[i+1]); i += 1
        i += 1
    return out

def digest(path: Path) -> str:
    if not path.exists(): return "<missing>"
    if path.is_dir(): return "<dir>"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return "<unreadable>"

def snapshot() -> dict:
    data = {"version": 1, "created_at": int(time.time()), "roots": {}}
    for gr in git_roots():
        relroot = "." if gr == ROOT else gr.relative_to(ROOT).as_posix()
        paths = status_paths(gr)
        data["roots"][relroot] = {"dirty": {p: digest(gr / p) for p in sorted(paths)}}
    return data

def begin(force: bool) -> int:
    if STATE.exists() and not force:
        print("task scope already active; baseline preserved")
        return 0
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("task scope baseline recorded")
    return 0

def task_touched(baseline: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for gr in git_roots():
        relroot = "." if gr == ROOT else gr.relative_to(ROOT).as_posix()
        base_dirty = baseline.get("roots", {}).get(relroot, {}).get("dirty", {})
        now_paths = status_paths(gr)
        union = set(base_dirty) | now_paths
        touched = []
        for p in sorted(union):
            before = base_dirty.get(p, "<clean>")
            after = digest(gr / p) if p in now_paths else "<clean>"
            if before != after:
                touched.append(p)
        result[relroot] = touched
    return result

def numstat_for(gr: Path, paths: list[str]) -> int:
    if not paths: return 0
    cp = run(gr, "git", "diff", "--numstat", "--", *paths)
    total = 0
    if cp.returncode == 0:
        for line in cp.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                for v in parts[:2]:
                    if v.isdigit(): total += int(v)
    # untracked files are absent from git diff --numstat; use line count as a bounded approximation
    tracked = set()
    cp2 = run(gr, "git", "ls-files", "--", *paths)
    if cp2.returncode == 0: tracked = set(cp2.stdout.splitlines())
    for p in paths:
        if p not in tracked:
            fp = gr / p
            if fp.is_file():
                try: total += min(sum(1 for _ in fp.open("rb")), 10000)
                except OSError: pass
    return total

def report(as_json: bool) -> int:
    if not STATE.exists():
        print("no task scope baseline; run task_scope.py begin before medium/high-risk edits", file=__import__('sys').stderr)
        return 2
    baseline = json.loads(STATE.read_text(encoding="utf-8"))
    touched = task_touched(baseline)
    all_paths = []
    approx_lines = 0
    roots = {("." if gr == ROOT else gr.relative_to(ROOT).as_posix()): gr for gr in git_roots()}
    for relroot, paths in touched.items():
        all_paths.extend([f"{relroot}/{p}" if relroot != "." else p for p in paths])
        if relroot in roots: approx_lines += numstat_for(roots[relroot], paths)
    high = len(all_paths) >= 5 or approx_lines >= 200 or any(any(k in p.lower() for k in HIGH_RISK_PARTS) for p in all_paths)
    data = {"task_touched_files": all_paths, "file_count": len(all_paths), "approx_diff_lines": approx_lines, "reviewer_recommended": high}
    if as_json: print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"task-touched files: {len(all_paths)}")
        print(f"approx task diff lines: {approx_lines}")
        print(f"reviewer recommended: {'yes' if high else 'no'}")
        for p in all_paths: print(f"  {p}")
    return 0

def clear() -> int:
    if STATE.exists(): STATE.unlink()
    print("task scope cleared")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin"); b.add_argument("--force", action="store_true")
    r = sub.add_parser("report"); r.add_argument("--json", action="store_true")
    sub.add_parser("clear")
    a = ap.parse_args()
    if a.cmd == "begin": return begin(a.force)
    if a.cmd == "report": return report(a.json)
    return clear()
if __name__ == "__main__": raise SystemExit(main())
'''


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def norm_rel(path: Path) -> str:
    return path.as_posix().lstrip("./")


def is_project_state(rel: Path) -> bool:
    value = norm_rel(rel)
    for item in PROJECT_STATE_PATHS:
        if item.endswith("/") and value.startswith(item):
            return True
        if value == item:
            return True
    return False


def looks_like_project(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any((path / m).exists() for m in PROJECT_MARKERS):
        return True
    if (path / ".git").exists():
        return True
    if any((path / "src" / m).exists() for m in (".git", "artisan", "composer.json")):
        return True
    return False


def find_package_root() -> Path:
    script = Path(__file__).resolve().parent
    for c in (script, script.parent):
        if (c / "CURRENT_PROJECT_OVERLAY").is_dir() or (c / "payload").is_dir():
            return c
        if (c / "REUSABLE_TEMPLATE").is_dir():
            return c
    return script


def find_project_root(package_root: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            raise SystemExit(f"Project rootが存在しません: {p}")
        return p
    if package_root.parent.name == "tools":
        p = package_root.parent.parent.resolve()
        if looks_like_project(p):
            return p
    cwd = Path.cwd().resolve()
    for p in (cwd, *cwd.parents):
        if p == package_root or package_root in p.parents:
            continue
        if looks_like_project(p) or (p / ".codex" / "harness").exists():
            return p
    for p in package_root.parents:
        if p.name == "tools":
            continue
        if looks_like_project(p):
            return p
    raise SystemExit("Project rootを検出できません。project/tools/配下へ置くか --target を指定してください。")


def installed_version(root: Path) -> str | None:
    vf = root / ".codex" / "harness" / "VERSION"
    if not vf.exists():
        return None
    return vf.read_text(encoding="utf-8", errors="replace").strip()


def base_source(package_root: Path, generic: bool) -> Path | None:
    if (package_root / "CURRENT_PROJECT_OVERLAY").is_dir() or (package_root / "REUSABLE_TEMPLATE").is_dir():
        p = package_root / ("REUSABLE_TEMPLATE" if generic else "CURRENT_PROJECT_OVERLAY")
        if p.is_dir(): return p
    if (package_root / "payload").is_dir():
        return package_root / "payload"
    return None


class Txn:
    def __init__(self, root: Path, dry_run: bool):
        self.root = root
        self.dry_run = dry_run
        self.backup = root / ".codex-harness-backup" / f"v6.2-{time.strftime('%Y%m%d-%H%M%S')}"
        self.backed: set[Path] = set()
        self.created: set[Path] = set()
        self.changed: list[Path] = []

    def backup_once(self, path: Path) -> None:
        if self.dry_run or path in self.backed or not path.exists(): return
        rel = path.relative_to(self.root)
        dst = self.backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir(): shutil.copytree(path, dst, dirs_exist_ok=True)
        else: shutil.copy2(path, dst)
        self.backed.add(path)

    def write_text(self, path: Path, text: str, mode: int | None = None) -> None:
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() and path.is_file() else None
        if old == text: return
        self.changed.append(path)
        if self.dry_run: return
        if path.exists(): self.backup_once(path)
        else: self.created.add(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if mode is not None: path.chmod(mode)

    def write_json(self, path: Path, data: Any) -> None:
        self.write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def copy_file(self, src: Path, dst: Path) -> None:
        if dst.exists() and dst.is_file() and src.read_bytes() == dst.read_bytes(): return
        self.changed.append(dst)
        if self.dry_run: return
        if dst.exists(): self.backup_once(dst)
        else: self.created.add(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def rollback(self) -> None:
        if self.dry_run: return
        for p in sorted(self.created, key=lambda x: len(x.parts), reverse=True):
            try:
                if p.is_file() or p.is_symlink(): p.unlink()
                elif p.is_dir(): shutil.rmtree(p)
            except OSError: pass
        if self.backup.exists():
            for src in sorted(self.backup.rglob("*")):
                if src.is_dir(): continue
                rel = src.relative_to(self.backup)
                dst = self.root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)


def migrate_docs(root: Path, txn: Txn, enabled: bool, already_installed: bool) -> None:
    if not enabled or already_installed: return
    docs, memo = root / "docs", root / "memo"
    if not docs.exists(): return
    if memo.exists():
        print("[WARN] docs/ と memo/ が両方存在するため自動移動をスキップします。")
        return
    print("[PLAN] docs/ -> memo/")
    if txn.dry_run: return
    txn.backup_once(docs)
    shutil.move(str(docs), str(memo))
    txn.created.add(memo)


def install_base(source: Path, root: Path, txn: Txn, reset_state: bool) -> tuple[int,int,int]:
    copied = updated = preserved = 0
    memo_exists = (root / "memo").exists()
    for src in sorted(source.rglob("*")):
        if not src.is_file(): continue
        rel = src.relative_to(source)
        dst = root / rel
        if rel.parts and rel.parts[0] == "memo" and memo_exists:
            preserved += 1; continue
        if dst.exists() and is_project_state(rel) and not reset_state:
            preserved += 1; continue
        existed = dst.exists()
        txn.copy_file(src, dst)
        if existed: updated += 1
        else: copied += 1
    return copied, updated, preserved


def replace_managed_block(text: str, block: str) -> str:
    pattern = re.compile(re.escape(MANAGED_BEGIN) + r".*?" + re.escape(MANAGED_END) + r"\n?", re.S)
    if pattern.search(text):
        return pattern.sub(block.rstrip() + "\n", text)
    sep = "\n" if text.endswith("\n") else "\n\n"
    return text + sep + block


def append_once(text: str, marker: str, addition: str) -> str:
    if marker in text: return text
    sep = "\n" if text.endswith("\n") else "\n\n"
    return text + sep + addition.strip() + "\n"


def patch_skills(root: Path, txn: Txn) -> None:
    targets = [
        (root / ".agents/skills/harness-develop/SKILL.md", "### v6.2 bounded execution addendum", DEVELOP_APPEND),
        (root / ".agents/skills/harness-debug/SKILL.md", "### v6.2 bounded execution addendum", DEVELOP_APPEND),
        (root / ".agents/skills/harness-verify/SKILL.md", "### v6.2 verification policy", VERIFY_APPEND),
        (root / ".agents/skills/harness-review/SKILL.md", "### v6.2 reviewer policy", REVIEW_APPEND),
        (root / ".agents/skills/maintain-project-knowledge/SKILL.md", "### v6.2 knowledge policy", KNOWLEDGE_APPEND),
    ]
    for path, marker, addition in targets:
        if path.exists():
            txn.write_text(path, append_once(path.read_text(encoding="utf-8", errors="replace"), marker, addition))


def suspicious_gate_scripts(root: Path) -> set[str]:
    names: set[str] = set()
    phrases = (
        "Adaptive Harness v6 quality gate", "Adaptive Harness v6.1 scoped quality gate",
        "spawn one bounded independent `reviewer`", "obtain `VERDICT: PASS`",
    )
    for base in (root / ".codex", root / ".agents"):
        if not base.exists(): continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".py", ".sh", ".js", ".mjs", ".ts"}: continue
            try: text = p.read_text(encoding="utf-8", errors="replace")
            except OSError: continue
            if any(q in text for q in phrases):
                names.add(p.name)
                names.add(p.relative_to(root).as_posix())
    return names


def is_old_harness_stop_command(command: str, gate_names: set[str]) -> bool:
    low = command.lower()
    if any(name.lower() in low for name in gate_names): return True
    local_harness = ".codex/harness" in low or ".agents/hooks" in low
    keywords = ("quality_gate", "quality-gate", "stop_gate", "stop-gate", "review_gate", "verification_gate")
    if local_harness and any(k in low for k in keywords): return True
    return False


def disable_blocking_stop_hooks(root: Path, txn: Txn) -> int:
    path = root / ".codex" / "hooks.json"
    if not path.exists(): return 0
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] hooks.jsonを解析できないためStop hook自動整理をスキップ: {exc}")
        return 0
    hooks = data.get("hooks")
    if not isinstance(hooks, dict): return 0
    stop = hooks.get("Stop")
    if not isinstance(stop, list): return 0
    gate_names = suspicious_gate_scripts(root)
    removed = 0
    new_entries = []
    for entry in stop:
        if not isinstance(entry, dict):
            new_entries.append(entry); continue
        commands = entry.get("hooks")
        if not isinstance(commands, list):
            new_entries.append(entry); continue
        kept = []
        for h in commands:
            cmd = h.get("command", "") if isinstance(h, dict) else ""
            if isinstance(cmd, str) and is_old_harness_stop_command(cmd, gate_names):
                removed += 1
                continue
            kept.append(h)
        if kept:
            e = dict(entry); e["hooks"] = kept; new_entries.append(e)
    if removed:
        hooks["Stop"] = new_entries
        data["hooks"] = hooks
        txn.write_json(path, data)
    return removed


def patch_old_feedback_text(root: Path, txn: Txn) -> int:
    # Even after disabling the hook, remove stale instructions that tell the agent to force unrelated failures green.
    changed = 0
    replacements = {
        "resolve required failures": "resolve failures caused by the current task",
        "spawn one bounded independent `reviewer`, address blocking findings, and obtain `VERDICT: PASS`":
            "use at most one bounded independent reviewer only when current-task risk justifies it",
        "Adaptive Harness v6.1 scoped quality gate:": "Adaptive Harness v6.2 advisory quality policy:",
        "Adaptive Harness v6 quality gate:": "Adaptive Harness v6.2 advisory quality policy:",
    }
    for base in (root / ".codex", root / ".agents"):
        if not base.exists(): continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".md", ".txt", ".py", ".sh", ".json", ".toml", ".yaml", ".yml"}: continue
            parts = set(p.relative_to(root).parts)
            if "runtime" in parts or "logs" in parts: continue
            try: old = p.read_text(encoding="utf-8", errors="replace")
            except OSError: continue
            new = old
            for a,b in replacements.items(): new = new.replace(a,b)
            if new != old:
                txn.write_text(p, new); changed += 1
    return changed


def write_v62_files(root: Path, txn: Txn) -> None:
    txn.write_json(root / ".codex/harness/v6_2_policy.json", POLICY)
    txn.write_text(root / ".codex/harness/VERSION", VERSION + "\n")
    txn.write_text(root / ".codex/harness/scripts/task_scope.py", TASK_SCOPE_SCRIPT, mode=0o755)
    notes = """# Adaptive Codex Harness v6.2\n\nDefault quality gate is advisory, not blocking. Verification and review are risk-based and scoped to the current task.\n\nKey commands:\n\n```bash\npython3 .codex/harness/scripts/task_scope.py begin\npython3 .codex/harness/scripts/task_scope.py report\npython3 .codex/harness/scripts/task_scope.py clear\n```\n\nAfter installing or changing `.codex/hooks.json`, restart the Codex session and review/trust hooks again.\n"""
    txn.write_text(root / ".codex/harness/V6_2.md", notes)


def patch_agents(root: Path, txn: Txn) -> None:
    path = root / "AGENTS.md"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    txn.write_text(path, replace_managed_block(old, AGENTS_BLOCK))


def self_check(root: Path) -> list[str]:
    problems = []
    vf = root / ".codex/harness/VERSION"
    if not vf.exists() or vf.read_text(encoding="utf-8", errors="replace").strip() != VERSION:
        problems.append("VERSION is not 6.2.0")
    for p in (root / ".codex/harness/scripts/task_scope.py",):
        if not p.exists(): problems.append(f"missing {p.relative_to(root)}"); continue
        try: ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as exc: problems.append(f"syntax error {p.relative_to(root)}: {exc}")
    hp = root / ".codex/hooks.json"
    if hp.exists():
        try: json.loads(hp.read_text(encoding="utf-8"))
        except Exception as exc: problems.append(f"invalid hooks.json: {exc}")
    pp = root / ".codex/harness/v6_2_policy.json"
    if not pp.exists(): problems.append("missing v6_2_policy.json")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6/v6.1 -> v6.2 unified installer/upgrader")
    ap.add_argument("--target", help="Project root. Omit when package is under project/tools/.")
    ap.add_argument("--generic", action="store_true", help="For a new install, use REUSABLE_TEMPLATE instead of CURRENT_PROJECT_OVERLAY.")
    ap.add_argument("--dry-run", action="store_true", help="Show planned changes without writing files.")
    ap.add_argument("--refresh-base", action="store_true", help="Re-copy the v6 base even when a harness is already installed. Project state is preserved unless --reset-project-state is used.")
    ap.add_argument("--reset-project-state", action="store_true", help="Allow base template to replace project state. Normally do not use.")
    ap.add_argument("--no-rename-docs", action="store_true", help="On a new install, do not migrate existing docs/ to memo/.")
    args = ap.parse_args()

    package_root = find_package_root()
    root = find_project_root(package_root, args.target)
    current = installed_version(root)
    already = current is not None or (root / ".codex/harness").exists()
    source = base_source(package_root, args.generic)

    print(f"Project root : {root}")
    print(f"Package root : {package_root}")
    print(f"Current      : {current or 'not installed'}")
    print(f"Target       : {VERSION}")
    print(f"Mode         : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    if not already and source is None:
        raise SystemExit("新規導入にはv6のCURRENT_PROJECT_OVERLAY/REUSABLE_TEMPLATEまたはpayload/が必要です。v6配布フォルダ内へこのinstall_v6_2.pyを置いて実行してください。")

    txn = Txn(root, args.dry_run)
    try:
        migrate_docs(root, txn, not args.no_rename_docs, already)
        if not already or args.refresh_base:
            assert source is not None
            c,u,p = install_base(source, root, txn, args.reset_project_state)
            print(f"[BASE] new={c} update={u} preserve={p}")
        else:
            print("[BASE] existing harness preserved; applying v6.2 delta only")

        removed = disable_blocking_stop_hooks(root, txn)
        print(f"[HOOK] disabled old Harness blocking Stop commands: {removed}")
        config_toml = root / ".codex" / "config.toml"
        if config_toml.exists():
            cfg_text = config_toml.read_text(encoding="utf-8", errors="replace")
            if "hooks.Stop" in cfg_text and any(k in cfg_text.lower() for k in ("quality_gate", "stop_gate", "review_gate", "verification_gate")):
                print("[WARN] .codex/config.toml にStop gateらしき定義があります。project-owned configのため自動削除していません。内容を確認してください。")
        stale = patch_old_feedback_text(root, txn)
        print(f"[POLICY] stale v6/v6.1 gate text updated in {stale} files")

        patch_agents(root, txn)
        patch_skills(root, txn)
        write_v62_files(root, txn)

        if args.dry_run:
            print(f"\n[DRY-RUN] planned changed files: {len(set(txn.changed))}")
            for p in sorted(set(txn.changed)):
                try: print("  " + p.relative_to(root).as_posix())
                except ValueError: print("  " + str(p))
            print("No files were changed.")
            return 0

        problems = self_check(root)
        if problems:
            raise RuntimeError("; ".join(problems))

    except Exception as exc:
        eprint(f"[FAIL] {exc}")
        eprint("[ROLLBACK] restoring files changed by this installer")
        txn.rollback()
        return 1

    print(f"\n[OK] Adaptive Codex Harness {VERSION} applied")
    if txn.backup.exists(): print(f"[OK] Backup: {txn.backup}")
    print("\nImportant:")
    print("  - Restart Codex after install so hook changes are reloaded.")
    print("  - Review/trust project hooks again if Codex asks.")
    print("  - Stop quality gate is advisory by default; existing non-Harness Stop hooks are preserved.")
    print("  - For medium/high-risk tasks: task_scope.py begin -> work -> task_scope.py report.")
    print("  - Existing docs/memo/commands/config/architecture rules remain project-owned by default.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
