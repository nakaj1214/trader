#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

VERSION = "6.5.0"

WRITABLE_ROOT = ".harness"
WRITABLE_RUNTIME = ".harness/runtime"
WRITABLE_STATE = ".harness/state"
WRITABLE_CACHE = ".harness/cache"
WRITABLE_REPORTS = ".harness/reports"
WRITABLE_BACKUPS = ".harness/backups"

PROJECT_MARKERS = (
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "artisan", "composer.json", "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
)

# Project-owned / learned state. Never replace by default.
PROJECT_STATE_PATHS = (
    "docs/", "memo/", ".codex/harness/config.json", ".codex/harness/commands.json",
    ".codex/harness/architecture_rules.json",
)

MANAGED_BEGIN = "<!-- adaptive-codex-harness-v6.5:begin -->"
MANAGED_END = "<!-- adaptive-codex-harness-v6.5:end -->"
OLD_MANAGED_BLOCKS = (
    ("<!-- adaptive-codex-harness-v6.4:begin -->", "<!-- adaptive-codex-harness-v6.4:end -->"),
    ("<!-- adaptive-codex-harness-v6.3:begin -->", "<!-- adaptive-codex-harness-v6.3:end -->"),
    ("<!-- adaptive-codex-harness-v6.2:begin -->", "<!-- adaptive-codex-harness-v6.2:end -->"),
    ("<!-- adaptive-codex-harness-v6.1:begin -->", "<!-- adaptive-codex-harness-v6.1:end -->"),
)

AGENTS_BLOCK = f"""{MANAGED_BEGIN}
## Adaptive Codex Harness v6.5 — fail-closed side-effect isolation + bounded execution
- Keep work scoped to the current user task. Pre-existing dirty-worktree changes/failures are non-blocking unless explicitly requested.
- Treat `.codex/` and `.agents/` as static read-only Harness configuration during Codex execution. Do not store mutable runtime/state/log/cache/report data there.
- All Harness-generated mutable data must live under project-root `.harness/`: transient execution data in `.harness/runtime/`, durable machine state in `.harness/state/`, caches in `.harness/cache/`, generated reports in `.harness/reports/`, and installer backups in `.harness/backups/`.
- Verification is risk-based: targeted checks by default; repository-wide/full gates only for broad/high-risk/release-sensitive work or when targeted checks are insufficient.
- Prefer existing tests, then extend an existing relevant test file. Create a new test file only for a material regression risk that existing coverage cannot reasonably validate. Never create tests merely to satisfy the Harness.
- **Tests must not reach persistent business infrastructure.** Laravel/PHP tests must pass both `test_db_guard.py` and `side_effect_guard.py` and should run through `safe_test.py`.
- Persistent DB access is forbidden during tests. Do not bypass, weaken, remove, or work around the SQLite-memory isolation guard.
- Outbound HTTP, real mail/notifications, real queues/jobs, real filesystem/cloud disks, printing/CUPS, SMB/NAS writes, and stray child processes are denied or faked during tests. If isolation cannot be proven, fail closed instead of falling back to the normal environment.
- Event dispatch is not globally faked because doing so can hide real integration regressions; listeners may run, but their external side-effect channels remain isolated. Tests that only assert dispatch may use `Event::fake()` locally.
- `Schema::drop*`, DROP/TRUNCATE, migrations/wipes, destructive imports/restores, recursive filesystem deletion, Docker volume deletion, force Git cleanup/reset, external HTTP writes, remote file transfer, printer submission, queue workers, and scheduler execution are not routine agent verification operations. Codex must not execute them autonomously against persistent resources.
- Read-only diagnostics are allowed when bounded: SELECT/SHOW/schema metadata, `migrate:status`, `route:list`, `lpstat`, and read-only remote listings. Interactive DB/SMB shells are denied because later input is not rechecked by `PreToolUse`.
- Independent reviewer is normally skipped for small/low-risk work. Use at most one reviewer for broad/high-risk changes (roughly >=5 task-touched files, >=200 task-diff lines, auth/permission/security, schema/migration/persistent-data risk, cross-component behavioral change, or explicit review request).
- Review and verification must inspect the current task diff, not every unrelated pre-existing change.
- Do not repeatedly run the same full gate, re-read unchanged large diffs, or open raw/full logs when bounded output is sufficient.
- Stop hooks are advisory; do not rely on a blocking Stop loop for correctness.
- Update durable project knowledge only for stable/repeated evidence or explicit user intent, not as automatic closeout for every task.
{MANAGED_END}
"""

POLICY = {
    "schema_version": 5,
    "version": VERSION,
    "quality_gate_mode": "advisory",
    "writable_layout": {
        "root": ".harness",
        "runtime": ".harness/runtime",
        "state": ".harness/state",
        "cache": ".harness/cache",
        "reports": ".harness/reports",
        "backups": ".harness/backups",
        "immutable_config_roots": [".codex", ".agents"],
        "legacy_runtime_under_codex": "forbidden",
    },
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
        "database_preflight": "required_before_formal_verification",
        "side_effect_preflight": "required_before_formal_verification",
    },
    "tests": {
        "prefer_existing_tests": True,
        "prefer_extending_existing_test_file": True,
        "new_test_file": "only_for_material_uncovered_regression_risk",
        "never_create_just_for_harness": True,
        "persistent_database_access": "forbidden",
        "fail_closed_if_isolation_unproven": True,
        "laravel": {
            "required_app_env": "testing",
            "required_default_connection": "sqlite",
            "required_default_database": ":memory:",
            "standard_mysql_fallback": "network_and_credentials_blocked",
            "phpunit_env_force": True,
            "direct_test_command": "deny_and_use_safe_test_wrapper",
        },
    },
    "database_safety": {
        "persistent_schema_or_data_changes": "explicit_user_supervision_only",
        "raw_destructive_commands": "deny_by_pretool_hook",
        "destructive_test_fixture_operations": "allowed_only_after_isolation_guard_passes",
        "read_only_diagnostics": "allowed",
    },
    "side_effect_safety": {
        "default": "deny_or_fake",
        "http_outbound": "prevent_stray_requests_and_block_write_cli",
        "mail": "fake",
        "notifications": "fake",
        "queue": "fake",
        "bus": "fake",
        "events": "not_globally_faked_downstream_side_effects_isolated",
        "storage_disks": "fake_all_configured_laravel_disks",
        "native_file_destructive_test_code": "static_guard",
        "processes": "prevent_stray_laravel_processes_and_shadow_high_risk_binaries",
        "cups_printing": "deny",
        "smb_nas_writes": "deny",
        "scheduler_workers": "deny",
        "remote_file_transfer": "deny",
        "git_destructive": "deny",
        "docker_persistent_cleanup": "deny",
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
        "pretool_side_effect_safety": True,
        "restart_codex_after_hook_changes": True,
    },
}

DEVELOP_APPEND = r"""
### v6.5 writable layout / side-effect safety / bounded execution
- `.codex/` and `.agents/` are static configuration. Runtime/state/cache/report writes belong under project-root `.harness/`.
- For medium/high-risk work, run `python3 .codex/harness/scripts/task_scope.py begin` before edits and `... task_scope.py report` near closeout.
- Keep unrelated dirty files and unrelated existing failures untouched.
- Prefer the smallest coherent edit; do not expand scope merely to make a repository-wide gate green.
- Tests: existing relevant tests first, then extend an existing test file; new test file only for a material uncovered regression risk.
- **Before any Laravel/PHP test command, use `safe_test.py`.** It requires both DB isolation and side-effect isolation to pass.
- If either safety guard refuses a run, do not bypass or weaken it. Diagnose the isolation problem instead.
- Test-time external effects are default-deny/fake: outbound HTTP, real mail/notification, real queue/bus work, real filesystem/cloud disks, CUPS/printing, SMB/NAS writes, and stray child processes.
- Do not globally fake Laravel events by default; that can hide listener regressions. Keep listeners active while downstream external effects stay isolated. Use `Event::fake()` only in tests whose contract is event dispatch itself.
- Never use a test failure as justification to run migrations/wipes, DROP/TRUNCATE, destructive import/restore, recursive deletion, remote upload, printer submission, scheduler/worker commands, or persistent writes.
- Persistent/external mutations are user-supervised operations, not autonomous Harness verification. Prepare a bounded command + backup/recovery plan; do not execute the mutation yourself.
- Use targeted verification by default. Full verification is not an automatic closeout step.
"""

VERIFY_APPEND = r"""
### v6.5 verification policy
1. Harness verification output/logs/state must be written under `.harness/`, never `.codex/` or `.agents/`.
2. Start from task-touched files / task scope, not the whole dirty worktree.
3. Before any Laravel/PHP test, run through `python3 .codex/harness/scripts/safe_test.py --shell '<original test command>'`.
4. `safe_test.py` requires `test_db_guard.py` and `side_effect_guard.py` to pass before launching the test process.
5. If isolation cannot be proven, fail closed. Never fall back to the container's normal DB, network, mail, queue, storage, print, or remote-share environment.
6. Small/low-risk: diff check + directly relevant tests/checks.
7. Moderate: add lint/format for task-touched files and the relevant regression group.
8. Broad/high-risk/release-sensitive: full gate may be appropriate, but unrelated pre-existing failures stay non-blocking.
9. Do not create new test files just to satisfy verification. Prefer existing coverage or extending an existing test.
10. Do not re-run an unchanged full gate repeatedly. After a small edit, re-run only invalidated checks unless final risk justifies a full pass.
11. Use bounded detail first; raw/full logs only when bounded detail cannot diagnose the failure.
"""

REVIEW_APPEND = r"""
### v6.5 reviewer policy
- Reviewer is normally skipped for small/low-risk changes.
- Spawn at most one bounded independent reviewer when the current task is broad/high-risk: roughly >=5 task-touched files, >=200 task-diff lines, auth/permission/security, schema/migration/persistent-data behavior, material cross-component behavior, or explicit review request.
- Review only the current-task diff. Pre-existing dirty changes are context only when necessary and are not findings to fix.
- When tests or integration code changed, explicitly check that tests cannot reach persistent DBs, external HTTP, real mail/notification channels, real queues, real disks/NAS/S3, printers/CUPS, scheduler/workers, or uncontrolled child processes.
- Do not repeatedly poll a reviewer or spawn replacement reviewers. If a reviewer cannot complete, report that once instead of starting a loop.
- A review PASS is invalidated only by later edits relevant to the reviewed scope, not by unrelated pre-existing worktree changes.
"""

DEBUG_APPEND = r"""
### v6.5 debug safety
- Harness-generated debug logs/state belong under `.harness/`; do not write runtime data below `.codex/` or `.agents/`.
- Prefer read-only diagnostics. Persistent/external mutation is not diagnosis.
- Do not run tests until both DB and side-effect guards pass. Do not assume `phpunit.xml` wins over populated container environment unless `force="true"` is verified.
- For HTTP, mail, queue, storage/NAS/S3, printer/CUPS, external processes, scheduler/worker, and remote-transfer problems, inspect configuration/logs/read-only status first. Do not send a real probe that creates, updates, deletes, prints, emails, uploads, or queues work merely to reproduce an issue.
- Interactive DB or SMB shells are denied because later input is not rechecked by `PreToolUse`; use bounded non-interactive read-only commands.
- If a missing table/data/file issue is found, first determine whether it is drift, accidental deletion, wrong connection/path, or pre-existing state. Do not reconstruct/restore persistent state without explicit user supervision.
"""

KNOWLEDGE_APPEND = r"""
### v6.5 knowledge policy
- Project knowledge is not an automatic per-task closeout step.
- Promote only stable, repeated, evidenced patterns or explicit user decisions.
- Safety incidents that can cause persistent/external side effects may be promoted when the rule is general and mechanically enforceable.
- Do not turn one-off debugging observations, temporary failures, or task-local implementation details into durable rules.
"""

HARNESS_PATHS_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WRITABLE_ROOT = ROOT / ".harness"
RUNTIME_ROOT = WRITABLE_ROOT / "runtime"
STATE_ROOT = WRITABLE_ROOT / "state"
CACHE_ROOT = WRITABLE_ROOT / "cache"
REPORTS_ROOT = WRITABLE_ROOT / "reports"
BACKUPS_ROOT = WRITABLE_ROOT / "backups"


def ensure_layout() -> None:
    for path in (WRITABLE_ROOT, RUNTIME_ROOT, STATE_ROOT, CACHE_ROOT, REPORTS_ROOT, BACKUPS_ROOT):
        path.mkdir(parents=True, exist_ok=True)
'''

TASK_SCOPE_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, subprocess, time
from pathlib import Path

from harness_paths import RUNTIME_ROOT, ensure_layout

ROOT = Path(__file__).resolve().parents[3]
STATE = RUNTIME_ROOT / "task_scope" / "current.json"

HIGH_RISK_PARTS = (
    "auth", "permission", "policy", "middleware", "migration", "schema", "routes/", "security",
    "composer.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
)

def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def git_roots() -> list[Path]:
    roots = []
    for p in [ROOT, *(x for x in ROOT.iterdir() if x.is_dir())]:
        if (p / ".git").exists(): roots.append(p)
    return roots

def status_paths(git_root: Path) -> set[str]:
    cp = run(git_root, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if cp.returncode != 0: return set()
    chunks = cp.stdout.split("\0"); out: set[str] = set(); i = 0
    while i < len(chunks):
        item = chunks[i]
        if not item: i += 1; continue
        if len(item) >= 4:
            code, path = item[:2], item[3:]; out.add(path)
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
            for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
        return h.hexdigest()
    except OSError: return "<unreadable>"

def snapshot() -> dict:
    data = {"version": 1, "created_at": int(time.time()), "roots": {}}
    for gr in git_roots():
        relroot = "." if gr == ROOT else gr.relative_to(ROOT).as_posix()
        paths = status_paths(gr)
        data["roots"][relroot] = {"dirty": {p: digest(gr / p) for p in sorted(paths)}}
    return data

def begin(force: bool) -> int:
    ensure_layout()
    if STATE.exists() and not force:
        print("task scope already active; baseline preserved"); return 0
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("task scope baseline recorded"); return 0

def task_touched(baseline: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for gr in git_roots():
        relroot = "." if gr == ROOT else gr.relative_to(ROOT).as_posix()
        base_dirty = baseline.get("roots", {}).get(relroot, {}).get("dirty", {})
        now_paths = status_paths(gr); union = set(base_dirty) | now_paths; touched = []
        for p in sorted(union):
            before = base_dirty.get(p, "<clean>")
            after = digest(gr / p) if p in now_paths else "<clean>"
            if before != after: touched.append(p)
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
                try: total += int(parts[0]) + int(parts[1])
                except ValueError: pass
    return total

def report(as_json: bool) -> int:
    if not STATE.exists():
        print("no active task scope; run begin first", file=__import__('sys').stderr); return 2
    baseline = json.loads(STATE.read_text(encoding="utf-8")); touched = task_touched(baseline)
    all_paths = []; approx_lines = 0
    roots = {"." if gr == ROOT else gr.relative_to(ROOT).as_posix(): gr for gr in git_roots()}
    for relroot, paths in touched.items():
        gr = roots.get(relroot)
        for p in paths: all_paths.append(p if relroot == "." else f"{relroot}/{p}")
        if gr: approx_lines += numstat_for(gr, paths)
    high = len(all_paths) >= 5 or approx_lines >= 200 or any(any(k in p.lower() for k in HIGH_RISK_PARTS) for p in all_paths)
    data = {"files": all_paths, "file_count": len(all_paths), "approx_diff_lines": approx_lines, "reviewer_recommended": high}
    if as_json: print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"task-touched files: {len(all_paths)}")
        print(f"approx task diff lines: {approx_lines}")
        print(f"reviewer recommended: {'yes' if high else 'no'}")
        for p in all_paths: print(f"  {p}")
    return 0

def clear() -> int:
    if STATE.exists(): STATE.unlink()
    print("task scope cleared"); return 0

def main() -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin"); b.add_argument("--force", action="store_true")
    r = sub.add_parser("report"); r.add_argument("--json", action="store_true")
    sub.add_parser("clear"); a = ap.parse_args()
    if a.cmd == "begin": return begin(a.force)
    if a.cmd == "report": return report(a.json)
    return clear()
if __name__ == "__main__": raise SystemExit(main())
'''

TEST_DB_GUARD_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

REQUIRED = {
    "APP_ENV": "testing",
    "DB_CONNECTION": "sqlite",
    "DB_DATABASE": ":memory:",
    # Standard Laravel MySQL fallback is deliberately made unreachable during tests.
    # This protects explicit DB::connection('mysql') calls even if application code uses them.
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "1",
    "DB_USERNAME": "__harness_test_blocked__",
    "DB_PASSWORD": "__harness_test_blocked__",
    "DB_URL": "",
}

DESTRUCTIVE_TEST_PATTERNS = (
    re.compile(r"Schema::\s*(?:connection\([^)]*\)\s*->\s*)?drop(?:IfExists)?\s*\(", re.I),
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I),
    re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?", re.I),
    re.compile(r"artisan\s+(?:migrate:fresh|migrate:refresh|migrate:reset|db:wipe)", re.I),
)

ABSOLUTE_DANGER_PATTERNS = (
    re.compile(r"\bDROP\s+DATABASE\b", re.I),
    re.compile(r"DB::(?:statement|unprepared)\s*\(\s*['\"]\s*DROP\s+DATABASE", re.I),
)

def laravel_root() -> Path | None:
    for p in (ROOT, ROOT / "src"):
        if (p / "artisan").is_file() and (p / "composer.json").is_file(): return p
    return None

def phpunit_file(app: Path) -> Path | None:
    for name in ("phpunit.xml", "phpunit.xml.dist"):
        p = app / name
        if p.exists(): return p
    return None

def env_map(xml_path: Path) -> dict[str, dict[str, str]]:
    tree = ET.parse(xml_path); root = tree.getroot(); out = {}
    for elem in root.iter("env"):
        name = elem.attrib.get("name")
        if name: out[name] = dict(elem.attrib)
    return out

def has_strong_testcase_guard(app: Path) -> bool:
    testcase = app / "tests" / "TestCase.php"
    trait = app / "tests" / "Concerns" / "HarnessSideEffectIsolation.php"
    if not testcase.exists():
        return False
    text = testcase.read_text(encoding="utf-8", errors="replace")
    combined = text
    if trait.exists():
        combined += "\n" + trait.read_text(encoding="utf-8", errors="replace")
    indicators = (
        ("app()->environment('testing')" in combined or 'app()->environment("testing")' in combined),
        ":memory:" in combined,
        "DB::purge" in combined,
        "database.connections" in combined,
        "HarnessSideEffectIsolation" in text,
        "harnessEnableSideEffectIsolation();" in text,
    )
    return all(indicators)

def scan_tests(app: Path) -> tuple[list[str], list[str]]:
    destructive, absolute = [], []
    base = app / "tests"
    if not base.exists(): return destructive, absolute
    for p in base.rglob("*.php"):
        try: text = p.read_text(encoding="utf-8", errors="replace")
        except OSError: continue
        rel = p.relative_to(app).as_posix()
        if any(rx.search(text) for rx in DESTRUCTIVE_TEST_PATTERNS): destructive.append(rel)
        if any(rx.search(text) for rx in ABSOLUTE_DANGER_PATTERNS): absolute.append(rel)
    return destructive, absolute

def audit(verbose: bool = True) -> int:
    app = laravel_root()
    if app is None:
        if verbose: print("[DB-GUARD] non-Laravel project: no Laravel DB preflight required")
        return 0
    xml_path = phpunit_file(app)
    if xml_path is None:
        print("[DB-GUARD:BLOCK] phpunit.xml/phpunit.xml.dist がありません。DB隔離を証明できないためLaravelテストを拒否します。", file=sys.stderr)
        return 2
    try: envs = env_map(xml_path)
    except Exception as exc:
        print(f"[DB-GUARD:BLOCK] {xml_path.name} を解析できません: {exc}", file=sys.stderr); return 2
    problems = []
    for name, value in REQUIRED.items():
        item = envs.get(name)
        if not item:
            problems.append(f"{name} が未定義")
            continue
        if item.get("value") != value: problems.append(f"{name}={item.get('value')!r} (required {value!r})")
        if item.get("force", "").lower() != "true": problems.append(f"{name} に force=\"true\" がない")
    for name, item in envs.items():
        if name.endswith("_DATABASE") and name != "DB_DATABASE":
            value = item.get("value", "")
            safe = value == ":memory:" or "test" in value.lower()
            if not safe: problems.append(f"{name}={value!r} はtesting専用DBと判定できない")
            if item.get("force", "").lower() != "true": problems.append(f"{name} に force=\"true\" がない")
    destructive, absolute = scan_tests(app)
    if absolute:
        problems.append("DROP DATABASE等の絶対破壊SQLを含むテスト: " + ", ".join(absolute[:8]))
    if destructive and not has_strong_testcase_guard(app):
        problems.append("DROP/TRUNCATE等を含むテストがあるが tests/TestCase.php の強制SQLite隔離ガードを確認できない: " + ", ".join(destructive[:8]))
    if problems:
        print("[DB-GUARD:BLOCK] LaravelテストDB隔離を証明できません。", file=sys.stderr)
        for p in problems: print(f"  - {p}", file=sys.stderr)
        print("ガードを弱めたり実DBへフォールバックせず、テスト設定を修正してください。", file=sys.stderr)
        return 2
    if verbose:
        print(f"[DB-GUARD:PASS] {app.relative_to(ROOT) if app != ROOT else '.'}: testing + sqlite + :memory: are forced")
        if destructive: print(f"[DB-GUARD] destructive fixture operations detected in {len(destructive)} test file(s); strong TestCase isolation guard confirmed")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Laravel test database isolation audit")
    ap.add_argument("--quiet", action="store_true"); args = ap.parse_args()
    return audit(not args.quiet)
if __name__ == "__main__": raise SystemExit(main())
'''

SIDE_EFFECT_TRAIT_PHP = r'''<?php

namespace Tests\Concerns;

use Illuminate\Support\Facades\Bus;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\Notification;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\Storage;
use RuntimeException;
use Throwable;

trait HarnessSideEffectIsolation
{
    protected function harnessEnableSideEffectIsolation(): void
    {
        if (! app()->environment('testing')) {
            throw new RuntimeException('Harness side-effect isolation is available only in the testing environment.');
        }

        $applicationRoot = base_path();
        $workspaceRoot = is_dir(dirname($applicationRoot).DIRECTORY_SEPARATOR.'.codex'.DIRECTORY_SEPARATOR.'harness')
            ? dirname($applicationRoot)
            : $applicationRoot;
        $storageRoot = $workspaceRoot
            .DIRECTORY_SEPARATOR.'.harness'
            .DIRECTORY_SEPARATOR.'runtime'
            .DIRECTORY_SEPARATOR.'test-storage'
            .DIRECTORY_SEPARATOR.'php-'.getmypid();

        foreach ([
            $storageRoot,
            $storageRoot.DIRECTORY_SEPARATOR.'app',
            $storageRoot.DIRECTORY_SEPARATOR.'framework',
            $storageRoot.DIRECTORY_SEPARATOR.'framework'.DIRECTORY_SEPARATOR.'cache',
            $storageRoot.DIRECTORY_SEPARATOR.'framework'.DIRECTORY_SEPARATOR.'sessions',
            $storageRoot.DIRECTORY_SEPARATOR.'framework'.DIRECTORY_SEPARATOR.'testing',
            $storageRoot.DIRECTORY_SEPARATOR.'framework'.DIRECTORY_SEPARATOR.'views',
            $storageRoot.DIRECTORY_SEPARATOR.'logs',
        ] as $directory) {
            if (! is_dir($directory) && ! @mkdir($directory, 0777, true) && ! is_dir($directory)) {
                throw new RuntimeException("Could not create isolated test storage directory: {$directory}");
            }
        }

        app()->useStoragePath($storageRoot);

        // Every configured named DB connection is redirected to its own SQLite memory DB.
        // This protects explicit DB::connection('mysql') / legacy named-connection calls too.
        $connectionNames = array_keys((array) config('database.connections', []));
        foreach ($connectionNames as $connectionName) {
            config([
                "database.connections.{$connectionName}" => [
                    'driver' => 'sqlite',
                    'database' => ':memory:',
                    'prefix' => '',
                    'foreign_key_constraints' => true,
                ],
            ]);
            DB::purge((string) $connectionName);
        }

        config([
            'database.default' => 'sqlite',
            'mail.default' => 'array',
            'queue.default' => 'sync',
            'cache.default' => 'array',
            'session.driver' => 'array',
        ]);

        $defaultConnection = DB::connection();
        if ($defaultConnection->getDriverName() !== 'sqlite'
            || $defaultConnection->getDatabaseName() !== ':memory:') {
            throw new RuntimeException('Harness could not isolate the default database to SQLite memory.');
        }

        Mail::fake();
        Notification::fake();
        Queue::fake();
        Bus::fake();

        try {
            $httpFactory = app(\Illuminate\Http\Client\Factory::class);
            if (method_exists($httpFactory, 'preventStrayRequests')) {
                Http::preventStrayRequests();
            } else {
                Http::fake(function (): never {
                    throw new RuntimeException('Harness blocked an unfaked outbound HTTP request during tests.');
                });
            }
        } catch (Throwable $e) {
            throw new RuntimeException('Harness could not install outbound HTTP isolation.', previous: $e);
        }

        $disks = (array) config('filesystems.disks', []);
        foreach (array_keys($disks) as $disk) {
            try {
                Storage::fake((string) $disk);
            } catch (Throwable $e) {
                throw new RuntimeException("Harness could not fake filesystem disk [{$disk}].", previous: $e);
            }
        }

        if (class_exists(\Illuminate\Support\Facades\Process::class)
            && class_exists(\Illuminate\Process\Factory::class)) {
            try {
                $processFactory = app(\Illuminate\Process\Factory::class);
                if (method_exists($processFactory, 'preventStrayProcesses')) {
                    \Illuminate\Support\Facades\Process::preventStrayProcesses();
                }
            } catch (Throwable $e) {
                throw new RuntimeException('Harness could not install process isolation.', previous: $e);
            }
        }

        // Intentionally do NOT call Event::fake() globally.
        // Listener behavior remains testable while DB/HTTP/mail/queue/storage/process side effects are isolated.
    }
}
'''

SIDE_EFFECT_GUARD_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

REQUIRED_ENV = {
    "APP_ENV": "testing",
    "MAIL_MAILER": "array",
    "MAIL_HOST": "127.0.0.1",
    "MAIL_PORT": "1",
    "QUEUE_CONNECTION": "sync",
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "FILESYSTEM_DISK": "local",
    "BROADCAST_CONNECTION": "log",
    "BROADCAST_DRIVER": "log",
    "CUPS_SERVER": "127.0.0.1:1",
    "HTTP_PROXY": "http://127.0.0.1:1",
    "HTTPS_PROXY": "http://127.0.0.1:1",
    "ALL_PROXY": "http://127.0.0.1:1",
    "NO_PROXY": "",
    "AWS_ACCESS_KEY_ID": "__harness_test_blocked__",
    "AWS_SECRET_ACCESS_KEY": "__harness_test_blocked__",
    "AWS_SESSION_TOKEN": "__harness_test_blocked__",
    "AWS_EC2_METADATA_DISABLED": "true",
    "REDIS_HOST": "127.0.0.1",
    "REDIS_PORT": "1",
    "MEMCACHED_HOST": "127.0.0.1",
    "MEMCACHED_PORT": "1",
}

TRAIT_REQUIRED = (
    "database.connections",
    "DB::purge",
    ":memory:",
    "Http::preventStrayRequests",
    "Mail::fake",
    "Notification::fake",
    "Queue::fake",
    "Bus::fake",
    "Storage::fake",
    "useStoragePath",
    "preventStrayProcesses",
    "Intentionally do NOT call Event::fake",
)

LOW_LEVEL_TEST_SIDE_EFFECTS = (
    ("native filesystem deletion", re.compile(r"\b(?:unlink|rmdir)\s*\(", re.I)),
    ("native filesystem write/move", re.compile(r"\b(?:file_put_contents|touch|rename|copy|move_uploaded_file|mkdir)\s*\(", re.I)),
    ("native fopen write mode", re.compile(r"\bfopen\s*\([^,]+,\s*['\"](?:w|a|x|c)[+bte]*['\"]", re.I)),
    ("Illuminate File mutation", re.compile(r"\bFile::(?:delete|deleteDirectory|cleanDirectory|put|append|prepend|move|copy|makeDirectory|moveDirectory|copyDirectory)\s*\(", re.I)),
    ("dynamic Laravel storage construction", re.compile(r"\bStorage::build\s*\(", re.I)),
    ("raw process execution", re.compile(r"\b(?:shell_exec|exec|system|passthru|proc_open|popen)\s*\(", re.I)),
    ("raw curl execution", re.compile(r"\bcurl_(?:exec|multi_exec)\s*\(", re.I)),
    ("raw socket connection", re.compile(r"\b(?:fsockopen|pfsockopen|stream_socket_client)\s*\(", re.I)),
)

SAFE_PATH_HINTS = (
    "sys_get_temp_dir", "tempnam(", "storage_path(", "Storage::fake", "fake(",
)
ALLOW_MARKER = "@harness-side-effect-allow"

WEAKENING_PATTERNS = (
    re.compile(r"Http::allowStrayRequests\s*\(", re.I),
    re.compile(r"Process::allowStrayProcesses\s*\(", re.I),
)

def laravel_root() -> Path | None:
    for p in (ROOT, ROOT / "src"):
        if (p / "artisan").is_file() and (p / "composer.json").is_file():
            return p
    return None

def phpunit_file(app: Path) -> Path | None:
    for name in ("phpunit.xml", "phpunit.xml.dist"):
        p = app / name
        if p.exists():
            return p
    return None

def env_map(xml_path: Path) -> dict[str, dict[str, str]]:
    tree = ET.parse(xml_path)
    out: dict[str, dict[str, str]] = {}
    for elem in tree.getroot().iter("env"):
        name = elem.attrib.get("name")
        if name:
            out[name] = dict(elem.attrib)
    return out

def scan_low_level_tests(app: Path) -> list[str]:
    problems: list[str] = []
    test_root = app / "tests"
    if not test_root.exists():
        return problems
    for path in test_root.rglob("*.php"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if ALLOW_MARKER in text:
            continue
        rel = path.relative_to(app).as_posix()
        if rel.lower() == "tests/concerns/harnesssideeffectisolation.php":
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(rx.search(line) for rx in WEAKENING_PATTERNS):
                problems.append(f"{rel}:{line_no}: side-effect isolation weakening call")
                continue
            for label, rx in LOW_LEVEL_TEST_SIDE_EFFECTS:
                if not rx.search(line):
                    continue
                if any(hint.lower() in line.lower() for hint in SAFE_PATH_HINTS):
                    continue
                problems.append(f"{rel}:{line_no}: {label} bypasses Laravel fakes")
    return problems

def audit(verbose: bool = True) -> int:
    app = laravel_root()
    if app is None:
        if verbose:
            print("[SIDE-EFFECT-GUARD] non-Laravel project: no Laravel side-effect preflight required")
        return 0

    problems: list[str] = []
    xml = phpunit_file(app)
    if xml is None:
        problems.append("phpunit.xml/phpunit.xml.dist がないためtesting副作用隔離を証明できない")
    else:
        try:
            envs = env_map(xml)
        except Exception as exc:
            problems.append(f"{xml.name} parse error: {exc}")
            envs = {}
        for name, value in REQUIRED_ENV.items():
            item = envs.get(name)
            if item is None:
                problems.append(f"{name} が未定義")
                continue
            if item.get("value", "") != value:
                problems.append(f"{name}={item.get('value')!r} (required {value!r})")
            if item.get("force", "").lower() != "true":
                problems.append(f"{name} に force=\"true\" がない")

    testcase = app / "tests" / "TestCase.php"
    trait = app / "tests" / "Concerns" / "HarnessSideEffectIsolation.php"
    if not testcase.exists():
        problems.append("tests/TestCase.php がない")
    else:
        t = testcase.read_text(encoding="utf-8", errors="replace")
        if "HarnessSideEffectIsolation" not in t or "harnessEnableSideEffectIsolation();" not in t:
            problems.append("tests/TestCase.php に HarnessSideEffectIsolation が組み込まれていない")
    if not trait.exists():
        problems.append("tests/Concerns/HarnessSideEffectIsolation.php がない")
    else:
        tt = trait.read_text(encoding="utf-8", errors="replace")
        for marker in TRAIT_REQUIRED:
            if marker not in tt:
                problems.append(f"HarnessSideEffectIsolation trait missing: {marker}")

    problems.extend(scan_low_level_tests(app))

    if problems:
        print("[SIDE-EFFECT-GUARD:BLOCK] テストの実環境副作用隔離を証明できません。", file=sys.stderr)
        for p in problems[:40]:
            print(f"  - {p}", file=sys.stderr)
        if len(problems) > 40:
            print(f"  - ... and {len(problems) - 40} more", file=sys.stderr)
        print("ガードを弱めず、fake / temp storage / mock へ置き換えてください。", file=sys.stderr)
        return 2

    if verbose:
        print("[SIDE-EFFECT-GUARD:PASS] HTTP/mail/notification/queue/storage/process isolation is installed")
        print("[SIDE-EFFECT-GUARD] Laravel events stay active; downstream side effects remain isolated")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Laravel test side-effect isolation audit")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    return audit(not args.quiet)

if __name__ == "__main__":
    raise SystemExit(main())
'''

SAFE_TEST_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB_GUARD = ROOT / ".codex" / "harness" / "scripts" / "test_db_guard.py"
SIDE_GUARD = ROOT / ".codex" / "harness" / "scripts" / "side_effect_guard.py"

DANGEROUS = (
    re.compile(r"\bartisan\s+(?:migrate(?::fresh|:refresh|:reset|:rollback)?|db:wipe|db:seed)\b", re.I),
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I),
    re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?", re.I),
    re.compile(r"\bartisan\s+(?:queue:work|queue:listen|queue:restart|schedule:run|schedule:work|horizon)\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:lp|lpr|cancel|lpadmin|cupsenable|cupsdisable)\b", re.I),
    re.compile(r"docker\s+(?:compose\s+)?down\b[^\n;&|]*\s(?:-v|--volumes)\b", re.I),
    re.compile(r"docker\s+(?:volume|system|container)\s+(?:rm|prune)\b", re.I),
)

TEST_PATTERNS = (
    re.compile(r"\bphp\s+(?:-[^\s]+\s+)*artisan\s+test\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:\./)?vendor/bin/(?:phpunit|pest)\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:phpunit|pest)\b", re.I),
)

EXTRA_SIDE_EFFECTS = (
    re.compile(r"\bcurl\b[^\n;&|]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)\b", re.I),
    re.compile(r"\bcurl\b[^\n;&|]*(?:--data(?:-raw|-binary|-urlencode)?|-d|-F|--form|--upload-file|-T)\b", re.I),
    re.compile(r"\bwget\b[^\n;&|]*(?:--post-data|--post-file|--method\s*=\s*(?:POST|PUT|PATCH|DELETE))", re.I),
    re.compile(r"(?:^|[;&|]\s*)(?:scp|sftp)\b", re.I),
    re.compile(r"\bsmbclient\b[^\n;&|]*\b(?:put|mput|del|rm|rename|mkdir|rmdir)\b", re.I),
    re.compile(r"(?:^|[;&|]\s*)\s*(?:sudo\s+)?rm\s+-[^\n;&|]*r", re.I),
    re.compile(r"\bfind\b[^\n;&|]*\s-delete\b", re.I),
    re.compile(r"\bgit\s+(?:reset\s+--hard|clean\b|push\b[^\n;&|]*(?:--force|-f))", re.I),
)

PHP_DISABLED_FUNCTIONS = ",".join((
    "exec", "shell_exec", "system", "passthru", "proc_open", "popen",
    "curl_exec", "curl_multi_exec", "fsockopen", "pfsockopen", "stream_socket_client",
    "mail",
    "smbclient_state_new", "smbclient_state_init", "smbclient_open", "smbclient_unlink",
    "smbclient_rename", "smbclient_mkdir", "smbclient_rmdir", "smbclient_write",
))

TEST_ENV = {
    "ADAPTIVE_HARNESS_ROOT": str(ROOT / ".harness"),
    "ADAPTIVE_HARNESS_RUNTIME": str(ROOT / ".harness" / "runtime"),
    "APP_ENV": "testing",
    "DB_CONNECTION": "sqlite",
    "DB_DATABASE": ":memory:",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "1",
    "DB_USERNAME": "__harness_test_blocked__",
    "DB_PASSWORD": "__harness_test_blocked__",
    "DB_URL": "",
    "MAIL_MAILER": "array",
    "MAIL_HOST": "127.0.0.1",
    "MAIL_PORT": "1",
    "QUEUE_CONNECTION": "sync",
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "FILESYSTEM_DISK": "local",
    "BROADCAST_CONNECTION": "log",
    "BROADCAST_DRIVER": "log",
    "CUPS_SERVER": "127.0.0.1:1",
    "HTTP_PROXY": "http://127.0.0.1:1",
    "HTTPS_PROXY": "http://127.0.0.1:1",
    "ALL_PROXY": "http://127.0.0.1:1",
    "NO_PROXY": "",
    "http_proxy": "http://127.0.0.1:1",
    "https_proxy": "http://127.0.0.1:1",
    "all_proxy": "http://127.0.0.1:1",
    "no_proxy": "",
    "AWS_ACCESS_KEY_ID": "__harness_test_blocked__",
    "AWS_SECRET_ACCESS_KEY": "__harness_test_blocked__",
    "AWS_SESSION_TOKEN": "__harness_test_blocked__",
    "AWS_EC2_METADATA_DISABLED": "true",
    "REDIS_HOST": "127.0.0.1",
    "REDIS_PORT": "1",
    "MEMCACHED_HOST": "127.0.0.1",
    "MEMCACHED_PORT": "1",
}

def harden_php_invocation(cmd: str) -> str:
    ini = f"-d disable_functions={shlex.quote(PHP_DISABLED_FUNCTIONS)}"

    cmd = re.sub(
        r"\bphp\s+(?!-d\s+disable_functions=)artisan\s+test\b",
        lambda m: f"php {ini} artisan test",
        cmd,
        count=1,
        flags=re.I,
    )

    cmd = re.sub(
        r"\bphp\s+(?!-d\s+disable_functions=)((?:\./)?vendor/bin/(?:phpunit|pest))\b",
        lambda m: f"php {ini} {m.group(1)}",
        cmd,
        count=1,
        flags=re.I,
    )

    if not re.search(r"\bphp\s+-d\s+disable_functions=", cmd, re.I):
        cmd = re.sub(
            r"(?<![\w/])((?:\./)?vendor/bin/(?:phpunit|pest))\b",
            lambda m: f"php {ini} {m.group(1)}",
            cmd,
            count=1,
            flags=re.I,
        )

    return cmd

def inject_docker_env(cmd: str) -> str:
    opts = " ".join(f"-e {shlex.quote(k + '=' + v)}" for k, v in TEST_ENV.items())
    patterns = (
        re.compile(r"(\bdocker\s+compose(?:\s+--env-file\s+\S+)?\s+exec\b)", re.I),
        re.compile(r"(\bdocker-compose\s+exec\b)", re.I),
    )
    for rx in patterns:
        if rx.search(cmd):
            return rx.sub(lambda m: m.group(1) + " " + opts, cmd, count=1)
    return cmd

def run_guard(path: Path) -> int:
    if not path.exists():
        print(f"[SAFE-TEST:BLOCK] missing guard: {path.name}", file=sys.stderr)
        return 2
    return subprocess.run([sys.executable, str(path), "--quiet"], cwd=ROOT).returncode

def validate_test_command(cmd: str) -> str | None:
    if not any(rx.search(cmd) for rx in TEST_PATTERNS):
        return "safe_test.py only accepts Laravel/PHP test commands"

    if any(rx.search(cmd) for rx in DANGEROUS + EXTRA_SIDE_EFFECTS):
        return "test command contains a persistent/external side-effect operation"

    # Refuse command chaining. Quoted regex filters such as '(A|B)' remain a single shlex word.
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return "test command has invalid shell quoting"
    if any(tok in {";", "&&", "||", "|", "&"} for tok in tokens):
        return "safe_test.py accepts one test command only; shell chaining/pipelines are blocked"
    if re.search(r"(?<![<])(?:>|>>|<)\\s*\\S", cmd):
        return "shell redirection is blocked in safe_test.py"

    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Laravel/PHP tests only after DB and side-effect isolation audits pass")
    ap.add_argument("--shell", required=True, help="Original test command string")
    args = ap.parse_args()
    cmd = args.shell

    problem = validate_test_command(cmd)
    if problem:
        print(f"[SAFE-TEST:BLOCK] {problem}", file=sys.stderr)
        return 2

    for guard in (DB_GUARD, SIDE_GUARD):
        rc = run_guard(guard)
        if rc != 0:
            return rc

    hardened = inject_docker_env(harden_php_invocation(cmd))
    env = os.environ.copy()
    env.update(TEST_ENV)
    print("[SAFE-TEST] DB + side-effect guards passed; running isolated test command")
    return subprocess.run(hardened, cwd=ROOT, env=env, shell=True, executable="/bin/bash").returncode

if __name__ == "__main__":
    raise SystemExit(main())
'''

PRETOOL_SAFETY_HOOK = r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SAFE_WRAPPER = ".codex/harness/scripts/safe_test.py"

TEST_PATTERNS = (
    re.compile(r"\bphp\s+(?:-[^\s]+\s+)*artisan\s+test\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:\./)?vendor/bin/(?:phpunit|pest)\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:phpunit|pest)\b", re.I),
)

DANGEROUS_PATTERNS = (
    (re.compile(r"\bphp\s+artisan\s+migrate(?:\s|$)", re.I), "persistent migration"),
    (re.compile(r"\bphp\s+artisan\s+(?:migrate:fresh|migrate:refresh|migrate:reset|migrate:rollback|db:wipe|db:seed)\b", re.I), "destructive/persistent Artisan DB command"),
    (re.compile(r"\b(?:DROP\s+(?:TABLE|DATABASE)|TRUNCATE\s+(?:TABLE\s+)?|ALTER\s+TABLE|RENAME\s+TABLE)\b", re.I), "destructive SQL"),
    (re.compile(r"\bphp\s+artisan\s+(?:queue:work|queue:listen|queue:restart|schedule:run|schedule:work|horizon)\b", re.I), "scheduler/queue worker execution"),
    (re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:lp|lpr|cancel|lpadmin|cupsenable|cupsdisable)\b", re.I), "printer/CUPS mutation"),
    (re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:sendmail|mail|mailx)\b", re.I), "real mail submission"),
    (re.compile(r"\bcurl\b[^\n;&|]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)\b", re.I), "external HTTP write"),
    (re.compile(r"\bcurl\b[^\n;&|]*(?:--data(?:-raw|-binary|-urlencode)?|-d|-F|--form|--upload-file|-T)\b", re.I), "external HTTP upload/write"),
    (re.compile(r"\bwget\b[^\n;&|]*(?:--post-data|--post-file|--method\s*=\s*(?:POST|PUT|PATCH|DELETE))", re.I), "external HTTP write"),
    (re.compile(r"(?:^|[;&|]\s*)(?:scp|sftp)\b", re.I), "remote file transfer"),
    (re.compile(r"\brsync\b[^\n;&|]*(?:\w+@[\w.-]+:|[\w.-]+:[^/])", re.I), "remote rsync transfer"),
    (re.compile(r"\bsmbclient\b[^\n;&|]*(?:-c\s+)?['\"][^'\"]*\b(?:put|mput|del|rm|rename|mkdir|rmdir)\b", re.I), "SMB/NAS write"),
    (re.compile(r"(?:^|[;&|]\s*)\s*(?:sudo\s+)?rm\s+-[^\n;&|]*r[^\n;&|]*(?:f[^\n;&|]*)?\s+", re.I), "recursive filesystem deletion"),
    (re.compile(r"\bfind\b[^\n;&|]*\s-delete\b", re.I), "recursive filesystem deletion"),
    (re.compile(r"(?:^|[;&|]\s*)\s*(?:sudo\s+)?shred\b", re.I), "destructive file overwrite"),
    (re.compile(r"\bdd\b[^\n;&|]*\bof=", re.I), "raw file/device overwrite"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "destructive Git reset"),
    (re.compile(r"\bgit\s+clean\b", re.I), "destructive Git clean"),
    (re.compile(r"\bgit\s+(?:checkout|restore)\s+--?\s*(?:\.|:/)", re.I), "bulk Git worktree overwrite"),
    (re.compile(r"\bgit\s+push\b[^\n;&|]*(?:--force|-f)\b", re.I), "force Git push"),
    (re.compile(r"docker\s+(?:compose\s+)?down\b[^\n;&|]*\s(?:-v|--volumes)\b", re.I), "Docker volume deletion"),
    (re.compile(r"docker\s+(?:volume|system|container)\s+(?:rm|prune)\b", re.I), "Docker persistent cleanup"),
)

WRITE_SQL = re.compile(r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+(?:TABLE|DATABASE)|DROP\s+(?:TABLE|DATABASE)|TRUNCATE|ALTER\s+TABLE)\b", re.I)
DB_CLIENT_CMD = re.compile(
    r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:mysql|mariadb|psql|sqlite3)\b"
    r"|\bdocker\s+(?:compose\s+)?exec\b[^\n;&|]*\s(?:mysql|mariadb|psql|sqlite3)\b",
    re.I,
)
TINKER = re.compile(r"\bartisan\s+tinker\b", re.I)
SMBCLIENT = re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?smbclient\b", re.I)
CUSTOM_WRITE_ARTISAN = re.compile(r"\bphp\s+artisan\s+[^\s;&|]*(?:migrate|import|restore|repair|purge|delete|cleanup|seed|sync)[^\s;&|]*", re.I)

SMB_READ_ONLY_VERBS = {"ls", "dir", "stat", "allinfo", "pwd", "cd", "help", "?", "quit", "exit"}

def smbclient_is_bounded_read_only(command: str) -> bool:
    """Allow only non-interactive smbclient -c scripts composed of read/navigation verbs."""
    m = re.search(r"\bsmbclient\b.*?\s-c\s+(?:'([^']*)'|\"([^\"]*)\")", command, re.I)
    if not m:
        return False
    script = m.group(1) if m.group(1) is not None else m.group(2)
    if script is None:
        return False
    for statement in script.split(';'):
        statement = statement.strip()
        if not statement:
            continue
        verb = statement.split(None, 1)[0].lower()
        if verb not in SMB_READ_ONLY_VERBS:
            return False
    return True

PROTECTED_PATHS = (
    ".codex/harness/hooks/pre_tool_safety.py",
    ".codex/harness/scripts/test_db_guard.py",
    ".codex/harness/scripts/side_effect_guard.py",
    ".codex/harness/scripts/safe_test.py",
    ".codex/harness/scripts/verify.py",
    ".codex/harness/v6_5_policy.json",
    ".codex/hooks.json",
    ".codex/rules/harness-side-effect-safety.rules",
    "tests/concerns/harnesssideeffectisolation.php",
)

def deny(reason: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    return 0

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not command.strip():
        return 0
    low = command.lower()

    if tool_name == "apply_patch":
        if any(path in low for path in PROTECTED_PATHS):
            return deny("Adaptive Harness v6.5 blocked an agent edit to side-effect safety infrastructure. Update the Harness through its installer.")
        if "@harness-side-effect-allow" in low:
            return deny("Adaptive Harness v6.5 blocked adding a side-effect bypass marker. A human must review and add any exceptional allow marker outside the agent.")
        if "phpunit.xml" in low:
            if re.search(r"^\+.*(?:DB_CONNECTION|MAIL_MAILER|QUEUE_CONNECTION|FILESYSTEM_DISK|HTTP_PROXY|CUPS_SERVER).*(?:mysql|smtp|redis|sqs|s3|production|prod)", command, re.I | re.M):
                return deny("Adaptive Harness v6.5 blocked a phpunit.xml edit that could reconnect tests to persistent/external infrastructure.")
            if re.search(r"^-.*(?:APP_ENV|DB_CONNECTION|DB_DATABASE|MAIL_MAILER|QUEUE_CONNECTION|CACHE_STORE|SESSION_DRIVER|FILESYSTEM_DISK|BROADCAST_CONNECTION|CUPS_SERVER|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY).*force=[\"']true[\"']", command, re.I | re.M):
                return deny("Adaptive Harness v6.5 blocked removal of forced test isolation settings.")
        if "tests/testcase.php" in low and re.search(r"^-.*(?:HarnessSideEffectIsolation|harnessEnableSideEffectIsolation|environment\(['\"]testing|:memory:|DB::purge|database\.connections)", command, re.I | re.M):
            return deny("Adaptive Harness v6.5 blocked removal of the Laravel TestCase isolation guard.")
        return 0

    if tool_name not in ("Bash", "shell_command", "exec_command", None):
        return 0

    if SAFE_WRAPPER in low:
        return 0

    if any(path in low for path in PROTECTED_PATHS) and re.search(
        r"(?:\brm\b|\bmv\b|sed\s+-i|perl\s+-pi|\btruncate\b|(?:>|>>)\s*[^ ]|\btee\b)",
        command,
        re.I,
    ):
        return deny("Adaptive Harness v6.5 blocked a shell command that could modify/remove safety infrastructure.")

    for rx, label in DANGEROUS_PATTERNS:
        if rx.search(command):
            return deny(
                f"Adaptive Harness v6.5 blocked {label}. This is an external, destructive, or persistent side effect, "
                "not routine autonomous verification. Use read-only diagnostics or a separately reviewed user-supervised procedure."
            )

    if TINKER.search(command) and not re.search(r"--execute(?:=|\s)", command, re.I):
        return deny("Adaptive Harness v6.5 blocked interactive Laravel Tinker. Use a bounded non-interactive read-only `tinker --execute=...` probe.")
    if DB_CLIENT_CMD.search(command) and not re.search(r"(?:^|\s)(?:-e|--execute(?:=|\s)|-c)(?:\s|=)", command, re.I):
        return deny("Adaptive Harness v6.5 blocked an interactive database client. Use a non-interactive read-only SELECT/SHOW/DESCRIBE/EXPLAIN command.")
    if SMBCLIENT.search(command) and not smbclient_is_bounded_read_only(command):
        return deny("Adaptive Harness v6.5 blocked interactive/non-read-only smbclient. Use a bounded `-c 'ls'` / metadata-only command containing read/navigation verbs only.")

    if (DB_CLIENT_CMD.search(command) or TINKER.search(command) or re.search(r"\bphp\s+-r\b", command, re.I)) and WRITE_SQL.search(command):
        return deny("Adaptive Harness v6.5 blocked a database write/destructive command before execution.")
    if TINKER.search(command) and re.search(r"(?:->|::)(?:delete|forceDelete|update|insert|insertGetId|upsert|create|firstOrCreate|updateOrCreate|save|restore|truncate|drop|dropIfExists|statement|unprepared)\s*\(", command, re.I):
        return deny("Adaptive Harness v6.5 blocked a Laravel tinker write/destructive call.")
    if CUSTOM_WRITE_ARTISAN.search(command) and not re.search(r"\b(?:status|check|show|list|dry-run|pretend)\b", command, re.I):
        return deny("Adaptive Harness v6.5 blocked a custom Artisan command whose name suggests persistent mutation.")

    root = Path(payload.get("cwd") or ".").resolve()
    laravel = (root / "artisan").exists() or (root / "src" / "artisan").exists()
    if laravel and any(rx.search(command) for rx in TEST_PATTERNS):
        return deny(
            "Adaptive Harness v6.5 blocked a raw Laravel/PHP test command. Use "
            "`python3 .codex/harness/scripts/safe_test.py --shell '<command>'` so DB and external side effects are isolated first."
        )

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''

RULES_TEXT = r'''# Adaptive Codex Harness v6.5 side-effect safety rules.
# PreToolUse is primary because Docker-wrapped commands do not have a stable inner prefix.
# These prefix rules are a second layer for common bare destructive commands.

prefix_rule(
    pattern = ["php", "artisan", ["migrate:fresh", "migrate:refresh", "migrate:reset", "migrate:rollback", "db:wipe"]],
    decision = "forbidden",
    justification = "Harness v6.5 forbids destructive database reset/wipe commands from Codex."
)

prefix_rule(
    pattern = ["php", "artisan", ["queue:work", "queue:listen", "schedule:run", "schedule:work", "horizon"]],
    decision = "forbidden",
    justification = "Harness v6.5 forbids starting workers/schedulers as autonomous verification because they may perform persistent external work."
)

prefix_rule(
    pattern = ["git", ["clean", "reset"]],
    decision = "prompt",
    justification = "Harness v6.5 treats Git cleanup/reset as potentially destructive; prefer scoped reversible operations."
)
'''

VERIFY_PREFLIGHT = r'''# adaptive-codex-harness-v6.5-side-effect-preflight:begin
# Fail closed before formal verification can launch any Laravel test command.
def _adaptive_harness_v65_preflight() -> None:
    import subprocess as _subprocess
    import sys as _sys
    from pathlib import Path as _Path

    _root = _Path(__file__).resolve().parents[3]
    _scripts = _root / ".codex" / "harness" / "scripts"
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from harness_paths import ensure_layout as _ensure_layout
    _ensure_layout()
    for _name in ("test_db_guard.py", "side_effect_guard.py"):
        _guard = _root / ".codex" / "harness" / "scripts" / _name
        if _guard.exists():
            _cp = _subprocess.run([_sys.executable, str(_guard), "--quiet"], cwd=_root)
            if _cp.returncode != 0:
                raise SystemExit(f"Harness safety preflight failed in {_name}; verification aborted before tests.")
_adaptive_harness_v65_preflight()
# adaptive-codex-harness-v6.5-side-effect-preflight:end
'''


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def norm_rel(path: Path) -> str:
    return path.as_posix().lstrip("./")


def is_project_state(rel: Path) -> bool:
    value = norm_rel(rel)
    for item in PROJECT_STATE_PATHS:
        if item.endswith("/") and value.startswith(item): return True
        if value == item: return True
    return False


def looks_like_project(path: Path) -> bool:
    if not path.is_dir(): return False
    if any((path / m).exists() for m in PROJECT_MARKERS): return True
    if (path / ".git").exists(): return True
    if any((path / "src" / m).exists() for m in (".git", "artisan", "composer.json")): return True
    return False


def find_package_root() -> Path:
    script = Path(__file__).resolve().parent
    for c in (script, script.parent):
        if (c / "CURRENT_PROJECT_OVERLAY").is_dir() or (c / "payload").is_dir() or (c / "REUSABLE_TEMPLATE").is_dir(): return c
    return script


def find_project_root(package_root: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir(): raise SystemExit(f"Project rootが存在しません: {p}")
        return p
    if package_root.parent.name == "tools":
        p = package_root.parent.parent.resolve()
        if looks_like_project(p): return p
    cwd = Path.cwd().resolve()
    for p in (cwd, *cwd.parents):
        if p == package_root or package_root in p.parents: continue
        if looks_like_project(p) or (p / ".codex" / "harness").exists(): return p
    for p in package_root.parents:
        if p.name == "tools": continue
        if looks_like_project(p): return p
    raise SystemExit("Project rootを検出できません。project/tools/配下へ置くか --target を指定してください。")


def installed_version(root: Path) -> str | None:
    vf = root / ".codex" / "harness" / "VERSION"
    if not vf.exists(): return None
    return vf.read_text(encoding="utf-8", errors="replace").strip()


def base_source(package_root: Path, generic: bool) -> Path | None:
    if (package_root / "CURRENT_PROJECT_OVERLAY").is_dir() or (package_root / "REUSABLE_TEMPLATE").is_dir():
        p = package_root / ("REUSABLE_TEMPLATE" if generic else "CURRENT_PROJECT_OVERLAY")
        if p.is_dir(): return p
    if (package_root / "payload").is_dir(): return package_root / "payload"
    return None


class Txn:
    def __init__(self, root: Path, dry_run: bool):
        self.root = root; self.dry_run = dry_run
        self.backup = root / ".harness" / "backups" / f"v6.5-{time.strftime('%Y%m%d-%H%M%S')}"
        self.backed: set[Path] = set(); self.created: set[Path] = set(); self.changed: list[Path] = []

    def backup_once(self, path: Path) -> None:
        if self.dry_run or path in self.backed or not path.exists(): return
        rel = path.relative_to(self.root); dst = self.backup / rel; dst.parent.mkdir(parents=True, exist_ok=True)
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
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")
        if mode is not None: path.chmod(mode)

    def write_json(self, path: Path, data: Any) -> None:
        self.write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def copy_file(self, src: Path, dst: Path) -> None:
        if dst.exists() and dst.is_file() and src.read_bytes() == dst.read_bytes(): return
        self.changed.append(dst)
        if self.dry_run: return
        if dst.exists(): self.backup_once(dst)
        else: self.created.add(dst)
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)

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
                rel = src.relative_to(self.backup); dst = self.root / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)


def migrate_docs(root: Path, txn: Txn, enabled: bool, already_installed: bool) -> None:
    if not enabled or already_installed: return
    docs, memo = root / "docs", root / "memo"
    if not docs.exists(): return
    if memo.exists(): print("[WARN] docs/ と memo/ が両方存在するため自動移動をスキップします。"); return
    print("[PLAN] docs/ -> memo/")
    if txn.dry_run: return
    txn.backup_once(docs); shutil.move(str(docs), str(memo)); txn.created.add(memo)


def install_base(source: Path, root: Path, txn: Txn, reset_state: bool) -> tuple[int, int, int]:
    copied = updated = preserved = 0; memo_exists = (root / "memo").exists()
    for src in sorted(source.rglob("*")):
        if not src.is_file(): continue
        rel = src.relative_to(source); dst = root / rel
        if rel.parts and rel.parts[0] == "memo" and memo_exists: preserved += 1; continue
        if dst.exists() and is_project_state(rel) and not reset_state: preserved += 1; continue
        existed = dst.exists(); txn.copy_file(src, dst)
        if existed: updated += 1
        else: copied += 1
    return copied, updated, preserved


def replace_managed_block(text: str, block: str) -> str:
    for begin, end in OLD_MANAGED_BLOCKS:
        text = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", text, flags=re.S)
    pattern = re.compile(re.escape(MANAGED_BEGIN) + r".*?" + re.escape(MANAGED_END) + r"\n?", re.S)
    if pattern.search(text): return pattern.sub(block.rstrip() + "\n", text)
    sep = "\n" if text.endswith("\n") else "\n\n"
    return text + sep + block


def strip_known_skill_addenda(text: str) -> str:
    headings = (
        "### v6.4 side-effect safety / bounded execution", "### v6.4 debug safety", "### v6.4 verification policy",
        "### v6.4 reviewer policy", "### v6.4 knowledge policy",
        "### v6.3 safety / bounded execution", "### v6.3 debug safety", "### v6.3 verification policy",
        "### v6.3 reviewer policy", "### v6.3 knowledge policy",
        "### v6.2 bounded execution addendum", "### v6.2 verification policy", "### v6.2 reviewer policy", "### v6.2 knowledge policy",
        "### v6.1 scoped quality gate", "### v6.1 verification policy", "### v6.1 reviewer policy",
    )
    for heading in headings:
        # Previous installers appended these sections at file end. Remove only an end-of-file occurrence.
        idx = text.rfind("\n" + heading)
        if idx >= 0:
            tail = text[idx + 1:]
            if tail.startswith(heading): text = text[:idx].rstrip() + "\n"
    return text


def append_once(text: str, marker: str, addition: str) -> str:
    if marker in text: return text
    sep = "\n" if text.endswith("\n") else "\n\n"
    return text + sep + addition.strip() + "\n"


def patch_skills(root: Path, txn: Txn) -> None:
    targets = [
        (root / ".agents/skills/harness-develop/SKILL.md", "### v6.5 writable layout / side-effect safety / bounded execution", DEVELOP_APPEND),
        (root / ".agents/skills/harness-debug/SKILL.md", "### v6.5 debug safety", DEBUG_APPEND),
        (root / ".agents/skills/harness-verify/SKILL.md", "### v6.5 verification policy", VERIFY_APPEND),
        (root / ".agents/skills/harness-review/SKILL.md", "### v6.5 reviewer policy", REVIEW_APPEND),
        (root / ".agents/skills/maintain-project-knowledge/SKILL.md", "### v6.5 knowledge policy", KNOWLEDGE_APPEND),
    ]
    for path, marker, addition in targets:
        if path.exists():
            # Preserve project-owned skill content but remove only known Harness addenda
            # from older v6.x installers to avoid conflicting safety instructions.
            old = path.read_text(encoding="utf-8", errors="replace")
            base = strip_known_skill_addenda(old)
            txn.write_text(path, append_once(base, marker, addition))


def suspicious_gate_scripts(root: Path) -> set[str]:
    names: set[str] = set(); phrases = (
        "Adaptive Harness v6 quality gate", "Adaptive Harness v6.1 scoped quality gate",
        "spawn one bounded independent `reviewer`", "obtain `VERDICT: PASS`",
    )
    for base in (root / ".codex", root / ".agents"):
        if not base.exists(): continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".py", ".sh", ".js", ".mjs", ".ts"}: continue
            try: text = p.read_text(encoding="utf-8", errors="replace")
            except OSError: continue
            if any(q in text for q in phrases): names.add(p.name); names.add(p.relative_to(root).as_posix())
    return names


def is_old_harness_stop_command(command: str, gate_names: set[str]) -> bool:
    low = command.lower()
    if any(name.lower() in low for name in gate_names): return True
    local_harness = ".codex/harness" in low or ".agents/hooks" in low
    return local_harness and any(k in low for k in ("quality_gate", "quality-gate", "stop_gate", "stop-gate", "review_gate", "verification_gate"))


def merge_hooks(root: Path, txn: Txn) -> tuple[int, int]:
    path = root / ".codex" / "hooks.json"
    if path.exists():
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc: raise RuntimeError(f"hooks.jsonを解析できません: {exc}")
    else: data = {"hooks": {}}
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict): raise RuntimeError("hooks.json の hooks がobjectではありません")

    removed = 0; stop = hooks.get("Stop", [])
    if isinstance(stop, list):
        gate_names = suspicious_gate_scripts(root); new_entries = []
        for entry in stop:
            if not isinstance(entry, dict): new_entries.append(entry); continue
            commands = entry.get("hooks")
            if not isinstance(commands, list): new_entries.append(entry); continue
            kept = []
            for h in commands:
                cmd = h.get("command", "") if isinstance(h, dict) else ""
                if isinstance(cmd, str) and is_old_harness_stop_command(cmd, gate_names): removed += 1; continue
                kept.append(h)
            if kept:
                e = dict(entry); e["hooks"] = kept; new_entries.append(e)
        hooks["Stop"] = new_entries

    pre = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre, list): raise RuntimeError("hooks.PreToolUse がarrayではありません")
    # Remove only prior Harness safety hook definitions; preserve user/project hooks.
    cleaned = []
    for entry in pre:
        if not isinstance(entry, dict): cleaned.append(entry); continue
        hs = entry.get("hooks")
        if isinstance(hs, list) and any(isinstance(h, dict) and "pre_tool_safety.py" in str(h.get("command", "")) for h in hs):
            continue
        cleaned.append(entry)
    cleaned.append({
        "matcher": "^(Bash|apply_patch|Edit|Write)$",
        "hooks": [{
            "type": "command",
            "command": f"python3 {shlex.quote(str(root / '.codex/harness/hooks/pre_tool_safety.py'))}",
            "timeout": 3,
            "statusMessage": "Checking side-effect safety",
        }],
    })
    hooks["PreToolUse"] = cleaned; data["hooks"] = hooks; txn.write_json(path, data)
    return removed, 1


def patch_old_feedback_text(root: Path, txn: Txn) -> int:
    changed = 0; replacements = {
        "resolve required failures": "resolve failures caused by the current task",
        "spawn one bounded independent `reviewer`, address blocking findings, and obtain `VERDICT: PASS`": "use at most one bounded independent reviewer only when current-task risk justifies it",
        "Adaptive Harness v6.4 advisory quality policy:": "Adaptive Harness v6.5 advisory quality policy:",
        "Adaptive Harness v6.3 advisory quality policy:": "Adaptive Harness v6.5 advisory quality policy:",
        "Adaptive Harness v6.1 scoped quality gate:": "Adaptive Harness v6.5 advisory quality policy:",
        "Adaptive Harness v6 quality gate:": "Adaptive Harness v6.5 advisory quality policy:",
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
            for a, b in replacements.items(): new = new.replace(a, b)
            if new != old: txn.write_text(p, new); changed += 1
    return changed


MUTABLE_PATH_REPLACEMENTS = (
    (".codex/harness/runtime", ".harness/runtime"),
    (".codex/harness/verification", ".harness/runtime/verification"),
    (".codex/harness/logs", ".harness/runtime/logs"),
    (".codex/harness/tmp", ".harness/runtime/tmp"),
    (".codex/harness/temp", ".harness/runtime/tmp"),
    (".codex/harness/sessions", ".harness/runtime/sessions"),
    (".codex/harness/cache", ".harness/cache"),
    (".codex/harness/state", ".harness/state"),
    (".codex/harness/stamps", ".harness/state/stamps"),
    (".codex/harness/locks", ".harness/state/locks"),
    (".codex/harness/reports", ".harness/reports"),
    (".codex/harness/artifacts", ".harness/reports/artifacts"),
    (".codex-harness-backup", ".harness/backups"),
)


def _relocate_mutable_text(text: str) -> str:
    new = text
    for old, replacement in MUTABLE_PATH_REPLACEMENTS:
        new = new.replace(old, replacement)

    for quote in ('"', "'"):
        for old_leaf, new_parts in (
            ("runtime", (".harness", "runtime")),
            ("verification", (".harness", "runtime", "verification")),
            ("logs", (".harness", "runtime", "logs")),
            ("tmp", (".harness", "runtime", "tmp")),
            ("temp", (".harness", "runtime", "tmp")),
            ("sessions", (".harness", "runtime", "sessions")),
            ("cache", (".harness", "cache")),
            ("state", (".harness", "state")),
            ("reports", (".harness", "reports")),
            ("artifacts", (".harness", "reports", "artifacts")),
            ("stamps", (".harness", "state", "stamps")),
            ("locks", (".harness", "state", "locks")),
        ):
            old = f" / {quote}.codex{quote} / {quote}harness{quote} / {quote}{old_leaf}{quote}"
            repl = "".join(f" / {quote}{part}{quote}" for part in new_parts)
            new = new.replace(old, repl)

    # Common pattern: RUNTIME_ROOT = HARNESS_ROOT / "runtime" while HARNESS_ROOT
    # itself must stay pointed at the static .codex/harness configuration tree.
    base_expr = "WORKSPACE_ROOT" if re.search(r"\bWORKSPACE_ROOT\b", new) else (
        "PROJECT_ROOT" if re.search(r"\bPROJECT_ROOT\b", new) else "ROOT"
    )
    leaf_map = {
        "runtime": (".harness", "runtime"),
        "verification": (".harness", "runtime", "verification"),
        "logs": (".harness", "runtime", "logs"),
        "tmp": (".harness", "runtime", "tmp"),
        "temp": (".harness", "runtime", "tmp"),
        "sessions": (".harness", "runtime", "sessions"),
        "cache": (".harness", "cache"),
        "state": (".harness", "state"),
        "reports": (".harness", "reports"),
        "artifacts": (".harness", "reports", "artifacts"),
        "stamps": (".harness", "state", "stamps"),
        "locks": (".harness", "state", "locks"),
    }
    pattern = re.compile(
        r"(?im)^(\s*[A-Z0-9_]*(?:RUNTIME|LOG|CACHE|STATE|REPORT|STAMP|VERIFY|ARTIFACT|SESSION|LOCK|TMP|TEMP)[A-Z0-9_]*\s*=\s*)"
        r"[A-Z0-9_]*HARNESS[A-Z0-9_]*\s*/\s*([\"'])(runtime|verification|logs|tmp|temp|sessions|cache|state|reports|artifacts|stamps|locks)\2\s*$"
    )

    def repl(match: re.Match[str]) -> str:
        parts = leaf_map[match.group(3).lower()]
        rhs = base_expr + "".join(f' / "{part}"' for part in parts)
        return match.group(1) + rhs

    return pattern.sub(repl, new)


def relocate_mutable_harness_paths(root: Path, txn: Txn) -> int:
    changed = 0
    bases = (root / ".codex" / "harness", root / ".agents")
    text_exts = {".py", ".sh", ".js", ".mjs", ".ts", ".json", ".toml", ".yaml", ".yml", ".md", ".txt"}
    for base in bases:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_exts:
                continue
            if ".harness" in path.parts or "runtime" in path.parts:
                continue
            try:
                old = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            new = _relocate_mutable_text(old)
            if new != old:
                txn.write_text(path, new)
                changed += 1
    return changed


def protected_root_write_findings(root: Path) -> list[str]:
    """Best-effort AST audit for Python scripts that still write below static .codex/.agents roots."""
    findings: list[str] = []
    methods = {"mkdir", "write_text", "write_bytes", "touch", "unlink", "rmdir", "rename", "replace"}

    for base in (root / ".codex" / "harness" / "scripts", root / ".codex" / "harness" / "hooks", root / ".agents" / "hooks"):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(text)
            except (OSError, SyntaxError):
                continue

            protected: set[str] = set()

            def expr_is_protected(node: ast.AST | None) -> bool:
                if node is None:
                    return False
                segment = ast.get_source_segment(text, node) or ""
                if ".harness" in segment and ".codex" not in segment and ".agents" not in segment:
                    return False
                if (".codex" in segment and "harness" in segment) or ".agents" in segment:
                    return True
                return any(isinstance(n, ast.Name) and n.id in protected for n in ast.walk(node))

            changed = True
            while changed:
                changed = False
                for node in ast.walk(tree):
                    target_name = None
                    value = None
                    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                        target_name = node.targets[0].id
                        value = node.value
                    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                        target_name = node.target.id
                        value = node.value
                    if target_name and target_name not in protected and expr_is_protected(value):
                        protected.add(target_name)
                        changed = True

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Attribute) and node.func.attr in methods and expr_is_protected(node.func.value):
                    findings.append(f"{path.relative_to(root).as_posix()}:{getattr(node, 'lineno', '?')}:{node.func.attr}")
                    continue
                if isinstance(node.func, ast.Name) and node.func.id == "open" and node.args and expr_is_protected(node.args[0]):
                    mode = "r"
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                        mode = node.args[1].value
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            mode = kw.value.value
                    if any(ch in mode for ch in "wax+"):
                        findings.append(f"{path.relative_to(root).as_posix()}:{getattr(node, 'lineno', '?')}:open({mode})")

    return sorted(set(findings))


def legacy_mutable_references(root: Path) -> list[str]:
    findings: list[str] = []
    bases = (root / ".codex" / "harness", root / ".agents")
    text_exts = {".py", ".sh", ".js", ".mjs", ".ts", ".json", ".toml", ".yaml", ".yml", ".md", ".txt"}
    needles = tuple(old for old, _ in MUTABLE_PATH_REPLACEMENTS[:-1])
    for base in bases:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_exts:
                continue
            if "runtime" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(needle in text for needle in needles):
                findings.append(path.relative_to(root).as_posix())
    return sorted(set(findings))


def prepare_writable_layout(root: Path, dry_run: bool) -> None:
    if dry_run:
        return
    for rel in (WRITABLE_RUNTIME, WRITABLE_STATE, WRITABLE_CACHE, WRITABLE_REPORTS, WRITABLE_BACKUPS):
        (root / rel).mkdir(parents=True, exist_ok=True)


def patch_gitignore_for_writable_root(root: Path, txn: Txn) -> bool:
    # When workspace root itself is a Git root, keep machine/runtime state out of Git.
    if not (root / ".git").exists():
        return False
    path = root / ".gitignore"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    marker = "/.harness/"
    if any(line.strip() == marker for line in old.splitlines()):
        return False
    sep = "" if not old else ("" if old.endswith("\n") else "\n")
    txn.write_text(path, old + sep + "# Adaptive Codex Harness writable runtime/state\n/.harness/\n")
    return True


def patch_agents(root: Path, txn: Txn) -> None:
    path = root / "AGENTS.md"; old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    txn.write_text(path, replace_managed_block(old, AGENTS_BLOCK))


def patch_phpunit_env(root: Path, txn: Txn) -> tuple[Path | None, list[str]]:
    app = root if (root / "artisan").exists() else root / "src" if (root / "src" / "artisan").exists() else None
    if app is None: return None, []
    xml = next((app / n for n in ("phpunit.xml", "phpunit.xml.dist") if (app / n).exists()), None)
    if xml is None: return None, ["Laravel project detected but phpunit.xml/phpunit.xml.dist is missing"]
    text = xml.read_text(encoding="utf-8", errors="replace"); changed_names = []

    def set_env(src: str, name: str, value: str) -> str:
        nonlocal changed_names
        pat = re.compile(r'<env\b(?=[^>]*\bname=["\']' + re.escape(name) + r'["\'])[^>]*/?>', re.I)
        m = pat.search(src)
        if m:
            tag = m.group(0)
            new = re.sub(r'\s+value=["\'][^"\']*["\']', '', tag, flags=re.I)
            new = re.sub(r'\s+force=["\'][^"\']*["\']', '', new, flags=re.I)
            if new.endswith('/>'): new = new[:-2].rstrip() + f' value="{value}" force="true"/>'
            else: new = new[:-1].rstrip() + f' value="{value}" force="true">'
            if new != tag: changed_names.append(name)
            return src[:m.start()] + new + src[m.end():]
        close = src.find("</php>")
        if close < 0: return src
        indent = "        "; entry = f'{indent}<env name="{name}" value="{value}" force="true"/>\n'; changed_names.append(name)
        return src[:close] + entry + src[close:]

    for name, value in (
        ("APP_ENV", "testing"),
        ("DB_CONNECTION", "sqlite"),
        ("DB_DATABASE", ":memory:"),
        # Fail closed for any explicit mysql connection that bypasses the default sqlite driver.
        ("DB_HOST", "127.0.0.1"),
        ("DB_PORT", "1"),
        ("DB_USERNAME", "__harness_test_blocked__"),
        ("DB_PASSWORD", "__harness_test_blocked__"),
        ("DB_URL", ""),
        # Fail closed for external/persistent side-effect channels during tests.
        ("MAIL_MAILER", "array"),
        ("MAIL_HOST", "127.0.0.1"),
        ("MAIL_PORT", "1"),
        ("QUEUE_CONNECTION", "sync"),
        ("CACHE_STORE", "array"),
        ("SESSION_DRIVER", "array"),
        ("FILESYSTEM_DISK", "local"),
        ("BROADCAST_CONNECTION", "log"),
        ("BROADCAST_DRIVER", "log"),
        ("CUPS_SERVER", "127.0.0.1:1"),
        ("HTTP_PROXY", "http://127.0.0.1:1"),
        ("HTTPS_PROXY", "http://127.0.0.1:1"),
        ("ALL_PROXY", "http://127.0.0.1:1"),
        ("NO_PROXY", ""),
        ("AWS_ACCESS_KEY_ID", "__harness_test_blocked__"),
        ("AWS_SECRET_ACCESS_KEY", "__harness_test_blocked__"),
        ("AWS_SESSION_TOKEN", "__harness_test_blocked__"),
        ("AWS_EC2_METADATA_DISABLED", "true"),
        ("REDIS_HOST", "127.0.0.1"),
        ("REDIS_PORT", "1"),
        ("MEMCACHED_HOST", "127.0.0.1"),
        ("MEMCACHED_PORT", "1"),
    ):
        text = set_env(text, name, value)
    # Existing secondary DB variables must be forced as well. Do not silently rename a dedicated test DB.
    for m in list(re.finditer(r'<env\b[^>]*\bname=["\']([A-Z0-9_]*_DATABASE)["\'][^>]*/?>', text, re.I)):
        name = m.group(1)
        if name == "DB_DATABASE": continue
        tag = m.group(0)
        if re.search(r'\bforce=["\']true["\']', tag, re.I): continue
        new = tag[:-2].rstrip() + ' force="true"/>' if tag.endswith('/>') else tag[:-1].rstrip() + ' force="true">'
        text = text[:m.start()] + new + text[m.end():]; changed_names.append(name)
        break  # re-scan safely after one positional mutation
    # Re-scan until no unforced secondary DB env remains.
    while True:
        match = None
        for m in re.finditer(r'<env\b[^>]*\bname=["\']([A-Z0-9_]*_DATABASE)["\'][^>]*/?>', text, re.I):
            if m.group(1) != "DB_DATABASE" and not re.search(r'\bforce=["\']true["\']', m.group(0), re.I): match = m; break
        if match is None: break
        tag = match.group(0); new = tag[:-2].rstrip() + ' force="true"/>' if tag.endswith('/>') else tag[:-1].rstrip() + ' force="true">'
        text = text[:match.start()] + new + text[match.end():]; changed_names.append(match.group(1))
    txn.write_text(xml, text)
    return xml, sorted(set(changed_names))



def laravel_app_root(root: Path) -> Path | None:
    if (root / "artisan").exists() and (root / "composer.json").exists():
        return root
    if (root / "src" / "artisan").exists() and (root / "src" / "composer.json").exists():
        return root / "src"
    return None


def patch_laravel_testcase(root: Path, txn: Txn) -> tuple[Path | None, list[str]]:
    app = laravel_app_root(root)
    if app is None:
        return None, []

    testcase = app / "tests" / "TestCase.php"
    if not testcase.exists():
        return None, ["Laravel tests/TestCase.php is missing"]

    trait_path = app / "tests" / "Concerns" / "HarnessSideEffectIsolation.php"
    txn.write_text(trait_path, SIDE_EFFECT_TRAIT_PHP)

    text = testcase.read_text(encoding="utf-8", errors="replace")
    changes: list[str] = []

    import_line = "use Tests\\Concerns\\HarnessSideEffectIsolation;"
    if import_line not in text:
        ns = re.search(r"^namespace\s+Tests\s*;\s*$", text, flags=re.M)
        if ns:
            pos = ns.end()
            text = text[:pos] + "\n\n" + import_line + text[pos:]
            changes.append("trait import")
        else:
            return testcase, ["could not locate `namespace Tests;` in tests/TestCase.php"]

    class_match = re.search(r"abstract\s+class\s+TestCase\s+extends\s+[^\{]+\{", text, flags=re.S)
    if not class_match:
        class_match = re.search(r"class\s+TestCase\s+extends\s+[^\{]+\{", text, flags=re.S)
    if not class_match:
        return testcase, ["could not locate TestCase class body"]

    body_start = class_match.end()
    class_tail = text[body_start:]
    if not re.search(r"^\s*use\s+HarnessSideEffectIsolation\s*;", class_tail, flags=re.M):
        text = text[:body_start] + "\n    use HarnessSideEffectIsolation;\n" + text[body_start:]
        changes.append("trait use")

    if "$this->harnessEnableSideEffectIsolation();" not in text:
        setup = re.search(r"protected\s+function\s+setUp\s*\(\s*\)\s*:\s*void\s*\{", text)
        if setup:
            # The application must be booted before facades/fakes are installed.
            parent = re.search(r"parent::setUp\s*\(\s*\)\s*;", text[setup.end():])
            if not parent:
                return testcase, ["existing TestCase::setUp() has no parent::setUp(); cannot safely install side-effect isolation"]
            pos = setup.end() + parent.end()
            text = text[:pos] + "\n        $this->harnessEnableSideEffectIsolation();" + text[pos:]
            changes.append("setUp isolation call")
        else:
            marker = re.search(r"^\s*use\s+HarnessSideEffectIsolation\s*;\s*$", text, flags=re.M)
            if not marker:
                return testcase, ["could not place TestCase::setUp()"]
            method = (
                "\n\n    protected function setUp(): void\n"
                "    {\n"
                "        parent::setUp();\n"
                "        $this->harnessEnableSideEffectIsolation();\n"
                "    }"
            )
            text = text[:marker.end()] + method + text[marker.end():]
            changes.append("setUp method")

    txn.write_text(testcase, text)
    return testcase, changes


def is_test_command(s: str) -> bool:
    low = s.lower()
    return ("php artisan test" in low or "vendor/bin/phpunit" in low or "vendor/bin/pest" in low or re.search(r'(^|[\s;&|])phpunit([\s;&|]|$)', low) is not None)


def patch_commands_json(root: Path, txn: Txn) -> int:
    path = root / ".codex" / "harness" / "commands.json"
    if not path.exists(): return 0
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc: print(f"[WARN] commands.json parse failed; not patched: {exc}"); return 0
    changed = 0

    def walk(obj: Any, key: str | None = None) -> Any:
        nonlocal changed
        if isinstance(obj, dict): return {k: walk(v, k) for k, v in obj.items()}
        if isinstance(obj, list): return [walk(v, key) for v in obj]
        if isinstance(obj, str) and key in {"command", "cmd", "run", "shell"} and is_test_command(obj) and "safe_test.py" not in obj:
            changed += 1
            return f"python3 .codex/harness/scripts/safe_test.py --shell {shlex.quote(obj)}"
        return obj

    new = walk(data)
    if changed: txn.write_json(path, new)
    return changed


def patch_verify_preflight(root: Path, txn: Txn) -> bool:
    path = root / ".codex" / "harness" / "scripts" / "verify.py"
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8", errors="replace")
    if "adaptive-codex-harness-v6.5-side-effect-preflight:begin" in text:
        return False

    # Remove earlier Harness preflight blocks before installing the v6.5 combined guard.
    text = re.sub(
        r"# adaptive-codex-harness-v6\.(?:3|4)-db-preflight:begin.*?# adaptive-codex-harness-v6\.(?:3|4)-db-preflight:end\n?",
        "",
        text,
        flags=re.S,
    )
    text = re.sub(
        r"# adaptive-codex-harness-v6\.4-side-effect-preflight:begin.*?# adaptive-codex-harness-v6\.4-side-effect-preflight:end\n?",
        "",
        text,
        flags=re.S,
    )

    m = re.search(r"^from __future__ import annotations\s*$", text, flags=re.M)
    if m:
        pos = m.end()
        new = text[:pos] + "\n\n" + VERIFY_PREFLIGHT + text[pos:]
    else:
        first_nl = text.find("\n")
        pos = first_nl + 1 if text.startswith("#!") and first_nl >= 0 else 0
        new = text[:pos] + VERIFY_PREFLIGHT + "\n" + text[pos:]

    txn.write_text(path, new)
    return True


def write_v65_files(root: Path, txn: Txn) -> None:
    txn.write_json(root / ".codex/harness/v6_5_policy.json", POLICY)
    txn.write_text(root / ".codex/harness/VERSION", VERSION + "\n")
    txn.write_text(root / ".codex/harness/scripts/harness_paths.py", HARNESS_PATHS_SCRIPT, mode=0o755)
    txn.write_text(root / ".codex/harness/scripts/task_scope.py", TASK_SCOPE_SCRIPT, mode=0o755)
    txn.write_text(root / ".codex/harness/scripts/test_db_guard.py", TEST_DB_GUARD_SCRIPT, mode=0o755)
    txn.write_text(root / ".codex/harness/scripts/side_effect_guard.py", SIDE_EFFECT_GUARD_SCRIPT, mode=0o755)
    txn.write_text(root / ".codex/harness/scripts/safe_test.py", SAFE_TEST_SCRIPT, mode=0o755)
    txn.write_text(root / ".codex/harness/hooks/pre_tool_safety.py", PRETOOL_SAFETY_HOOK, mode=0o755)
    txn.write_text(root / ".codex/rules/harness-side-effect-safety.rules", RULES_TEXT)

    # Keep an old v6.3 rule file from becoming a second conflicting source after upgrade.
    old_rule = root / ".codex/rules/harness-db-safety.rules"
    if old_rule.exists():
        old_text = old_rule.read_text(encoding="utf-8", errors="replace")
        if "Adaptive Codex Harness v6.3" in old_text or "Adaptive Codex Harness v6.5 DB safety" in old_text:
            txn.write_text(old_rule, "# Superseded by harness-side-effect-safety.rules in Adaptive Codex Harness v6.5.\n")

    notes = """# Adaptive Codex Harness v6.5

v6.5 keeps v6.4 fail-closed side-effect isolation and separates static configuration from writable Harness data.

Writable layout:
- `.harness/runtime/` - task scope, verification runs, logs and transient execution data
- `.harness/state/` - mutable Harness machine state
- `.harness/cache/` - regenerable cache
- `.harness/reports/` - generated reports
- `.harness/backups/` - installer backups

`.codex/` and `.agents/` remain static configuration/script roots during Codex execution.

Protected during Laravel/PHP tests:
- persistent DBs
- outbound HTTP not explicitly faked
- real mail and notifications
- real queues / bus dispatch
- configured Laravel filesystem disks (including S3-like disks)
- Laravel Process stray child processes
- storage_path() is redirected to project `.harness/runtime/test-storage/`
- CUPS/server/network environment is forced away from real endpoints

Agent-side PreToolUse protection also denies:
- destructive DB/schema commands
- recursive filesystem deletion and raw overwrite commands
- external HTTP writes/uploads
- SMB/NAS writes and interactive SMB shells
- printer submission / CUPS mutations
- queue workers and scheduler execution
- remote scp/sftp/rsync writes
- destructive Git reset/clean/force-push
- Docker persistent-volume cleanup

Events are intentionally not globally faked. Listener behavior remains testable while downstream side-effect channels are isolated.

Commands:
```bash
python3 .codex/harness/scripts/test_db_guard.py
python3 .codex/harness/scripts/side_effect_guard.py
python3 .codex/harness/scripts/safe_test.py --shell 'docker compose exec -T laravel php artisan test --filter=ExampleTest'
python3 .codex/harness/scripts/task_scope.py begin
python3 .codex/harness/scripts/task_scope.py report
```

After installing or changing `.codex/hooks.json`, restart Codex and review/trust the hook using `/hooks`.
"""
    txn.write_text(root / ".codex/harness/V6_5.md", notes)


def self_check(root: Path) -> list[str]:
    problems: list[str] = []
    vf = root / ".codex/harness/VERSION"
    if not vf.exists() or vf.read_text(encoding="utf-8", errors="replace").strip() != VERSION:
        problems.append("VERSION is not 6.5.0")

    for p in (
        root / ".codex/harness/scripts/harness_paths.py",
        root / ".codex/harness/scripts/task_scope.py",
        root / ".codex/harness/scripts/test_db_guard.py",
        root / ".codex/harness/scripts/side_effect_guard.py",
        root / ".codex/harness/scripts/safe_test.py",
        root / ".codex/harness/hooks/pre_tool_safety.py",
    ):
        if not p.exists():
            problems.append(f"missing {p.relative_to(root)}")
            continue
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"syntax error {p.relative_to(root)}: {exc}")

    hp = root / ".codex/hooks.json"
    if not hp.exists():
        problems.append("missing .codex/hooks.json")
    else:
        try:
            data = json.loads(hp.read_text(encoding="utf-8"))
            raw = json.dumps(data)
            if "pre_tool_safety.py" not in raw:
                problems.append("PreToolUse side-effect safety hook not installed")
        except Exception as exc:
            problems.append(f"invalid hooks.json: {exc}")

    if not (root / ".codex/harness/v6_5_policy.json").exists():
        problems.append("missing v6_5_policy.json")

    for rel in (WRITABLE_RUNTIME, WRITABLE_STATE, WRITABLE_CACHE, WRITABLE_REPORTS, WRITABLE_BACKUPS):
        directory = root / rel
        if not directory.is_dir():
            problems.append(f"missing writable Harness directory: {rel}")
            continue
        probe = directory / ".v6_5_write_probe"
        try:
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            problems.append(f"Harness writable directory is not writable: {rel}: {exc}")

    legacy_refs = legacy_mutable_references(root)
    if legacy_refs:
        problems.append("legacy mutable path remains under .codex/.agents: " + ", ".join(legacy_refs[:8]))

    protected_writes = protected_root_write_findings(root)
    if protected_writes:
        problems.append("runtime write to static .codex/.agents remains: " + ", ".join(protected_writes[:8]))

    app = laravel_app_root(root)
    if app is not None:
        testcase = app / "tests" / "TestCase.php"
        trait = app / "tests" / "Concerns" / "HarnessSideEffectIsolation.php"
        if not testcase.exists():
            problems.append("missing Laravel tests/TestCase.php")
        else:
            tt = testcase.read_text(encoding="utf-8", errors="replace")
            if "HarnessSideEffectIsolation" not in tt or "harnessEnableSideEffectIsolation();" not in tt:
                problems.append("Laravel TestCase side-effect isolation not installed")
        if not trait.exists():
            problems.append("missing HarnessSideEffectIsolation trait")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Adaptive Codex Harness v6/v6.1/v6.2/v6.3/v6.4 -> v6.5 writable-layout + fail-closed safety installer/upgrader"
    )
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
        raise SystemExit(
            "新規導入にはv6のCURRENT_PROJECT_OVERLAY/REUSABLE_TEMPLATEまたはpayload/が必要です。"
            "v6配布フォルダ内へこのinstall_v6_5.pyを置いて実行してください。"
        )

    txn = Txn(root, args.dry_run)
    try:
        migrate_docs(root, txn, not args.no_rename_docs, already)

        if not already or args.refresh_base:
            assert source is not None
            c, u, p = install_base(source, root, txn, args.reset_project_state)
            print(f"[BASE] new={c} update={u} preserve={p}")
        else:
            print("[BASE] existing harness preserved; applying v6.5 delta only")

        removed, added = merge_hooks(root, txn)
        print(f"[HOOK] old blocking Stop commands removed={removed}; side-effect PreToolUse installed={added}")

        stale = patch_old_feedback_text(root, txn)
        print(f"[POLICY] stale v6-v6.4 gate text updated in {stale} files")

        patch_agents(root, txn)
        patch_skills(root, txn)
        write_v65_files(root, txn)

        xml, env_changes = patch_phpunit_env(root, txn)
        if xml:
            print(
                f"[TEST-SAFETY] PHPUnit env hardened: {xml.relative_to(root)} "
                f"({', '.join(env_changes) if env_changes else 'already safe'})"
            )
        else:
            print("[TEST-SAFETY] no Laravel phpunit.xml detected; Laravel tests will fail closed if later introduced")

        testcase, testcase_changes = patch_laravel_testcase(root, txn)
        if testcase:
            print(
                f"[TEST-SAFETY] Laravel TestCase isolation: {testcase.relative_to(root)} "
                f"({', '.join(testcase_changes) if testcase_changes else 'already safe'})"
            )
        elif testcase_changes:
            print("[TEST-SAFETY] " + "; ".join(testcase_changes))

        wrapped = patch_commands_json(root, txn)
        print(f"[TEST-SAFETY] commands.json test commands wrapped: {wrapped}")

        preflight = patch_verify_preflight(root, txn)
        print(f"[TEST-SAFETY] verify.py combined preflight {'installed' if preflight else 'already present/not found'}")

        relocated = relocate_mutable_harness_paths(root, txn)
        print(f"[WRITABLE] legacy mutable paths relocated to .harness/: {relocated} files")
        gitignore_changed = patch_gitignore_for_writable_root(root, txn)
        if gitignore_changed:
            print("[WRITABLE] root .gitignore updated for /.harness/")

        if args.dry_run:
            print(f"\n[DRY-RUN] planned changed files: {len(set(txn.changed))}")
            for p in sorted(set(txn.changed)):
                try:
                    print("  " + p.relative_to(root).as_posix())
                except ValueError:
                    print("  " + str(p))
            print("No files were changed.")
            return 0

        prepare_writable_layout(root, False)
        problems = self_check(root)
        if problems:
            raise RuntimeError("; ".join(problems))

    except Exception as exc:
        eprint(f"[FAIL] {exc}")
        eprint("[ROLLBACK] restoring files changed by this installer")
        txn.rollback()
        return 1

    print(f"\n[OK] Adaptive Codex Harness {VERSION} applied")
    if txn.backup.exists():
        print(f"[OK] Backup: {txn.backup}")

    all_safe = True
    for name, label in (
        ("test_db_guard.py", "Laravel test DB safety"),
        ("side_effect_guard.py", "Laravel test side-effect safety"),
    ):
        guard = root / ".codex/harness/scripts" / name
        if not guard.exists():
            continue
        cp = subprocess.run([sys.executable, str(guard), "--quiet"], cwd=root)
        if cp.returncode == 0:
            print(f"[OK] {label}: PASS")
        else:
            all_safe = False
            print(f"[SAFE-BLOCK] {label}: BLOCKED. Tests remain disabled until isolation is repaired.")

    print("\nRequired after install:")
    print("  1. Restart Codex (hook definitions changed).")
    print("  2. Run /hooks and trust the project PreToolUse safety hook.")
    print("  3. python3 .codex/harness/scripts/test_db_guard.py")
    print("  4. python3 .codex/harness/scripts/side_effect_guard.py")
    print("\nBehavior:")
    print("  - .codex/ and .agents/ are static configuration roots during Codex execution.")
    print("  - Mutable Harness data is written under .harness/{runtime,state,cache,reports,backups}.")
    print("  - Raw Laravel/PHP tests are blocked; use safe_test.py.")
    print("  - verify.py aborts before tests unless DB + side-effect isolation is proven.")
    print("  - Tests fake/block HTTP, mail, notifications, queue/bus, Laravel storage disks and stray Laravel Process calls.")
    print("  - Test storage_path() is redirected to .harness/runtime/test-storage/.")
    print("  - PHP test execution disables raw process, mail, curl/socket and common SMB-client functions.")
    print("  - CUPS writes, SMB/NAS writes, external HTTP writes, worker/scheduler execution, destructive filesystem/Git/Docker operations are denied before execution.")
    print("  - Laravel Event is not globally faked; listener behavior stays testable while downstream effects are isolated.")
    print("  - docs/memo/config/architecture rules remain project-owned; commands.json is changed only to wrap test commands.")
    if not all_safe:
        print("\n[IMPORTANT] Harness v6.5 is installed, but tests are intentionally fail-closed until both guards PASS.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
