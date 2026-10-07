#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

VERSION = "6.9.0"
MIN_VERSION = (6, 8, 1)
TARGET_VERSION = (6, 9, 0)

AGENTS_BEGIN = "<!-- adaptive-codex-harness-v6.9-execution-evidence:begin -->"
AGENTS_END = "<!-- adaptive-codex-harness-v6.9-execution-evidence:end -->"
PLAYBOOK_BEGIN = "<!-- adaptive-codex-harness-v6.9-execution-diagnosis:begin -->"
PLAYBOOK_END = "<!-- adaptive-codex-harness-v6.9-execution-diagnosis:end -->"
SKILL_BEGIN = "<!-- adaptive-codex-harness-v6.9-execution-safety:begin -->"
SKILL_END = "<!-- adaptive-codex-harness-v6.9-execution-safety:end -->"

AGENTS_BLOCK = f'''{AGENTS_BEGIN}
## Adaptive Codex Harness v6.9 — Execution Evidence & Runtime Safety

Apply these rules across Shell, PHP, JavaScript, containers, jobs, and migration/restore work:

1. **Separate execution failure from business-condition mismatch.** Preserve the causal error class and exit/status code. Do not turn command/network/runtime failure into a domain message such as “dirty worktree”, “validation failed”, or “not found”.
2. **Prove completion with final evidence.** Creating/Started/sent/loading messages are progress only. Success requires the final exit/status plus the expected postcondition. Distinguish timeout, user cancel, signal termination, dependency failure, and normal command failure.
3. **Verify changing data structurally.** Prefer keys, mappings, referential integrity, versions, and other invariants over snapshot-specific total counts unless the snapshot and expected count are explicitly bound together.
4. **Verify execution context when it can change behavior.** Confirm the relevant run ID/time, requested vs effective operation, execution user, working/Git root, container, mount, and write target. Re-check critical mutable preconditions immediately before persistent changes when practical.
5. **Keep command boundaries and diagnostics safe.** Prefer structured argv over shell string concatenation; redact secrets, credentials, auth headers/cookies, private keys, and personal data before logs/chat/Git output. A single severe persistent-data, authorization, external-send, or secret-leak incident may justify a narrowly targeted fail-closed guard when the hazardous condition is mechanically identifiable.

Detailed diagnosis belongs in `docs/playbooks.md` and existing Harness skills. Do not create a new Skill or broad lint rule from a one-off ordinary failure.
{AGENTS_END}'''

PLAYBOOK_BLOCK = f'''{PLAYBOOK_BEGIN}
## Execution/result diagnosis (v6.9)

Use this flow when a command, container operation, PHP process, JavaScript request, job, migration, restore, or generated artifact has an unclear or failed result.

1. **Identify the exact run.** Confirm run/request/job ID where available, start time, command/operation, and the newest log. Never treat an old log path as the current run merely because it was printed again.
2. **Find the first causal failure.** Capture the original exit/status code and redact-safe stderr/exception/HTTP failure. Keep this separate from any later domain interpretation.
3. **Classify the terminal state.** Distinguish success, normal failure, timeout, user cancel, signal termination, and dependency/service failure.
4. **Separate progress from completion.** Docker `Creating`/`Created`, process start, queue dispatch, request send, modal/loading UI, and rollback start are not final success evidence.
5. **Compare requested and effective operation.** Record what the caller requested and what actually ran after wrapper/Compose/shell/environment/default resolution. Include execution user, cwd/Git root, relevant container, mounts, and write target. Redact secret-bearing values before recording.
6. **Check argument and shell boundaries.** Prefer argv/structured APIs. When a shell is unavoidable, verify quoting, `--` boundaries where applicable, working directory, variable expansion, leading hyphens, whitespace/newlines, globbing, and command substitution risks.
7. **Verify mutable preconditions at the write boundary.** For persistent changes, re-check critical DB/file/container/mount/source fingerprint/version/backup conditions immediately before mutation when practical; use locks, transactions, compare-and-swap/version columns, or equivalent concurrency controls where needed.
8. **Verify postconditions and recovery.** Confirm the intended final data/files/service state. If rollback/compensation ran, verify the rollback command completed and the restored state is correct; “rollback started” is not enough.
9. **Before retrying, improve observability.** Add only the smallest run ID, causal error, effective-operation, or postcondition evidence needed to distinguish the suspected causes. Do not broaden the design merely to gather more telemetry.

### Safety notes
- Redact passwords, tokens, cookies, Authorization headers, private keys, secret connection strings, and personal data before logs/chat/Git-managed artifacts.
- Prefer “configured/not configured”, hashes/fingerprints, counts, names of parameters/services, and error categories when raw values are unnecessary.
- Preserve enough non-secret context to diagnose the cause: exit/status code, error category, argument/parameter name, target service, and relevant run identifier.
- Ordinary one-off failures stay as implementation/debug notes. A one-off incident may become an automatic guard only when impact is severe and the dangerous condition can be detected narrowly with a fail-closed response.
{PLAYBOOK_END}'''

SKILL_BLOCKS = {
    "harness-debug": f'''{SKILL_BEGIN}
### v6.9 execution-diagnosis policy
- Identify the exact/latest run before interpreting logs; retain the first causal failure and exit/status code.
- Keep execution/runtime failure distinct from business-condition mismatch.
- Distinguish success, timeout, user cancel, signal termination, dependency failure, and normal failure.
- Compare requested operation with the effective operation after wrappers, environment injection, cwd/user/container/mount/default resolution.
- Redact secrets and personal data before surfacing command/env/stderr/HTTP context; keep non-secret diagnostic evidence such as error category, exit code, parameter name, service, and run ID.
- Treat progress messages as non-terminal; verify final state and any rollback/cleanup result.
{SKILL_END}''',
    "harness-develop": f'''{SKILL_BEGIN}
### v6.9 implementation-safety policy
- For time-varying production-like data, validate structural invariants (keys, mappings, references, versions) instead of unbound total-count literals.
- Prefer isolated copies/worktrees/temporary artifacts when historical code or destructive experiments would otherwise rewrite the active worktree.
- Verify that the real execution user can read/write generated files, caches, build outputs, mounts, and target paths.
- Prefer structured argv/process APIs over shell-string concatenation. When shell use is unavoidable, preserve safe argument boundaries and explicit working directory; do not interpolate untrusted external input directly into shell commands.
- Persistent updates must re-check critical mutable conditions near the write boundary; use transactions, locks, version checks, idempotency, or compensation when partial success/concurrency matters.
- Preserve causal exceptions when translating them into domain-facing messages, while redacting secret/personal values from logs and surfaced diagnostics.
{SKILL_END}''',
    "harness-verify": f'''{SKILL_BEGIN}
### v6.9 verification policy
- PASS requires both a successful terminal status and the expected postcondition; Started/Created/sent/loading/rollback-start messages are insufficient.
- Verify the effective operation, not only the requested command, when Harness/wrappers/Compose/environment injection may change execution.
- Classify timeout/cancel/signal/dependency failures separately from assertion/business failures.
- For persistent mutations, require the critical preconditions to be revalidated close to the mutation boundary when the state can change between preflight and write.
- Verify rollback/compensation by command result plus restored post-state.
- Do not turn ordinary tooling/test-runner mistakes into planning blockers when the product plan and acceptance remain implementable.
{SKILL_END}''',
    "maintain-project-knowledge": f'''{SKILL_BEGIN}
### v6.9 guard-promotion policy
- Do not generalize one ordinary incident into a new Skill, broad lint, or global rule. Prefer existing docs/tests/skills and wait for repeated, structurally similar failures.
- Exception: one incident may justify an automatic guard when impact is severe (persistent data destruction, unauthorized action, external mis-send, secret leakage, irrecoverable mutation) **and** the hazardous condition is mechanically identifiable with an acceptably narrow fail-closed check.
- Record the evidence for promotion: concrete incident/risk, detection condition, expected false-positive cost, fail-closed behavior, and why an existing guard/test cannot cover it.
{SKILL_END}''',
}

POLICY = {
    "version": VERSION,
    "name": "execution-evidence-runtime-safety",
    "principles": {
        "failure_classification": "separate_runtime_failure_from_business_mismatch",
        "completion_evidence": "terminal_status_plus_postcondition",
        "variable_data": "structural_invariants_over_unbound_total_counts",
        "execution_context": [
            "run_id_and_time",
            "requested_vs_effective_operation",
            "execution_user",
            "working_and_git_root",
            "container_and_mount",
            "write_target",
        ],
        "redaction": "secrets_and_personal_data_before_persist_or_surface",
        "termination": ["success", "failure", "timeout", "cancel", "signal", "dependency_failure"],
        "toctou": "revalidate_critical_mutable_preconditions_at_write_boundary",
        "shell_safety": "structured_argv_preferred",
        "guard_promotion": "repeat_for_ordinary_failures_single_severe_incident_allowed_when_narrow_fail_closed",
    },
    "scope": {
        "new_skill": False,
        "broad_lint": False,
        "patterns_index_promotion": False,
        "reason": "first confirmed restore incident; keep reusable guidance in existing surfaces until repeated",
    },
}

NOTES = '''# Adaptive Codex Harness v6.9.0

v6.9 adds execution-evidence and runtime-safety guidance learned from restore/debug failures without expanding Harness into a new skill/lint layer.

Included:
- Distinguishes runtime/transport/process failure from business-condition mismatch.
- Requires final status + expected postcondition for success.
- Adds requested-vs-effective operation diagnostics.
- Adds secret/personal-data redaction requirements for commands, env, stderr, exceptions and HTTP context.
- Separates timeout/cancel/signal/dependency failure from normal failure.
- Adds write-boundary precondition revalidation (TOCTOU awareness).
- Adds structured argv / safe shell-boundary guidance.
- Prefers structural invariants over time-dependent total-count literals.
- Allows a one-off severe incident to become a narrowly targeted fail-closed guard when mechanically identifiable.
- Updates existing Harness skills only; no new Skill, broad lint or patterns-index promotion is created by this installer.

This is a delta updater for Harness >= 6.8.1.
'''


@dataclass
class Txn:
    root: Path
    dry_run: bool

    def __post_init__(self) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup = self.root / ".harness" / "backups" / f"v6.9-{stamp}"
        self.changed: list[Path] = []
        self._backed: set[Path] = set()

    def _backup_once(self, path: Path) -> None:
        if self.dry_run or path in self._backed or not path.exists():
            return
        rel = path.relative_to(self.root)
        dest = self.backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        self._backed.add(path)

    def write_text(self, path: Path, text: str, mode: int | None = None) -> bool:
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        if old == text:
            return False
        self.changed.append(path)
        if self.dry_run:
            return True
        self._backup_once(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if mode is not None:
            path.chmod(mode)
        return True

    def write_json(self, path: Path, data: object) -> bool:
        return self.write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def rollback(self) -> None:
        if self.dry_run:
            return
        backed_rels: set[Path] = set()
        if self.backup.exists():
            for src in self.backup.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(self.backup)
                backed_rels.add(rel)
                dest = self.root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        for path in reversed(self.changed):
            try:
                rel = path.relative_to(self.root)
            except ValueError:
                continue
            if rel not in backed_rels and path.exists():
                path.unlink()


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def parse_version(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def installed_version(root: Path) -> str | None:
    p = root / ".codex" / "harness" / "VERSION"
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace").strip()


def looks_like_project(path: Path) -> bool:
    return any((path / marker).exists() for marker in (".git", ".codex", ".agents", "composer.json", "package.json", "artisan", "src"))


def find_project_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.exists():
            raise SystemExit(f"project root not found: {root}")
        return root
    script = Path(__file__).resolve()
    candidates = [script.parent.parent, script.parent.parent.parent, Path.cwd().resolve()]
    for candidate in candidates:
        if looks_like_project(candidate):
            return candidate
    for parent in Path.cwd().resolve().parents:
        if looks_like_project(parent):
            return parent
    raise SystemExit("project root not detected; pass --target PATH")


def strip_block(text: str, begin: str, end: str) -> str:
    return re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", text, flags=re.S)


def upsert_block(text: str, begin: str, end: str, block: str) -> str:
    text = strip_block(text, begin, end)
    return text.rstrip() + "\n\n" + block.strip() + "\n"


def patch_agents(root: Path, txn: Txn) -> None:
    path = root / "AGENTS.md"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    txn.write_text(path, upsert_block(old, AGENTS_BEGIN, AGENTS_END, AGENTS_BLOCK))


def patch_playbook(root: Path, txn: Txn) -> None:
    path = root / "docs" / "playbooks.md"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else "# Playbooks\n"
    txn.write_text(path, upsert_block(old, PLAYBOOK_BEGIN, PLAYBOOK_END, PLAYBOOK_BLOCK))


def patch_skills(root: Path, txn: Txn) -> dict[str, str]:
    statuses: dict[str, str] = {}
    base = root / ".agents" / "skills"
    for name, block in SKILL_BLOCKS.items():
        path = base / name / "SKILL.md"
        if not path.is_file():
            statuses[name] = "missing"
            continue
        old = path.read_text(encoding="utf-8", errors="replace")
        changed = txn.write_text(path, upsert_block(old, SKILL_BEGIN, SKILL_END, block))
        statuses[name] = "patched" if changed else "already-fixed"
    return statuses


def patch_config_version(root: Path, txn: Txn) -> str:
    path = root / ".codex" / "harness" / "config.json"
    if not path.is_file():
        return "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"config.json parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("config.json root is not an object")
    meta = data.get("harness_meta")
    if not isinstance(meta, dict):
        meta = {}
        data["harness_meta"] = meta
    if meta.get("version") == VERSION:
        return "already-fixed"
    meta["version"] = VERSION
    txn.write_json(path, data)
    return "patched"


def write_release_files(root: Path, txn: Txn) -> None:
    txn.write_text(root / ".codex" / "harness" / "VERSION", VERSION + "\n")
    txn.write_json(root / ".codex" / "harness" / "v6_9_policy.json", POLICY)
    txn.write_text(root / ".codex" / "harness" / "V6_9.md", NOTES)


def refresh_manifest_for_changed_files(root: Path, txn: Txn) -> str:
    path = root / ".codex" / "harness" / "installed-manifest.json"
    if not path.is_file() or txn.dry_run:
        return "skipped"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "invalid"
    payload = data.get("payload_sha256")
    if not isinstance(payload, dict):
        return "no-payload-map"

    modified = False
    for changed in txn.changed:
        try:
            rel = changed.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel not in payload or not changed.is_file():
            continue
        digest = hashlib.sha256(changed.read_bytes()).hexdigest()
        if payload.get(rel) != digest:
            payload[rel] = digest
            modified = True

    # Update common version metadata only when those keys already exist.
    for key in ("version", "harness_version"):
        if key in data and data.get(key) != VERSION:
            data[key] = VERSION
            modified = True

    if modified:
        txn.write_json(path, data)
        return "refreshed"
    return "unchanged"


def self_check(root: Path) -> list[str]:
    issues: list[str] = []

    vf = root / ".codex" / "harness" / "VERSION"
    if not vf.is_file() or vf.read_text(encoding="utf-8", errors="replace").strip() != VERSION:
        issues.append(f"VERSION is not {VERSION}")

    agents = root / "AGENTS.md"
    if not agents.is_file():
        issues.append("missing AGENTS.md")
    else:
        text = agents.read_text(encoding="utf-8", errors="replace")
        if AGENTS_BEGIN not in text or "requested vs effective" not in text.lower():
            issues.append("v6.9 execution-evidence block missing from AGENTS.md")

    playbook = root / "docs" / "playbooks.md"
    if not playbook.is_file():
        issues.append("missing docs/playbooks.md")
    else:
        text = playbook.read_text(encoding="utf-8", errors="replace")
        if PLAYBOOK_BEGIN not in text or "Verify postconditions and recovery" not in text:
            issues.append("v6.9 execution diagnosis block missing from docs/playbooks.md")

    for name in SKILL_BLOCKS:
        path = root / ".agents" / "skills" / name / "SKILL.md"
        if not path.is_file():
            issues.append(f"required existing skill missing: {name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SKILL_BEGIN not in text:
            issues.append(f"v6.9 block missing from skill: {name}")

    config = root / ".codex" / "harness" / "config.json"
    if config.is_file():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
            meta = data.get("harness_meta", {}) if isinstance(data, dict) else {}
            if not isinstance(meta, dict) or meta.get("version") != VERSION:
                issues.append("config.json harness_meta.version mismatch")
        except Exception as exc:
            issues.append(f"config.json invalid: {exc}")

    policy = root / ".codex" / "harness" / "v6_9_policy.json"
    if not policy.is_file():
        issues.append("missing v6_9_policy.json")
    else:
        try:
            data = json.loads(policy.read_text(encoding="utf-8"))
            if data.get("version") != VERSION:
                issues.append("v6_9_policy.json version mismatch")
        except Exception as exc:
            issues.append(f"v6_9_policy.json invalid: {exc}")

    # v6.9 intentionally does not create a new Skill or broad lint/checker.
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6.9 execution-evidence updater")
    ap.add_argument("--target", "--project-root", dest="project_root", help="Project root. Usually omitted when this file is under project/tools/codex-harness-v6/.")
    ap.add_argument("--dry-run", action="store_true", help="Show planned changes without writing files.")
    ap.add_argument("--force", action="store_true", help="Allow use on versions older than 6.8.1 or with an unparseable VERSION after manual compatibility review.")
    args = ap.parse_args()

    root = find_project_root(args.project_root)
    current_raw = installed_version(root)
    current = parse_version(current_raw)

    print(f"Project root : {root}")
    print(f"Current      : {current_raw or 'unknown/not installed'}")
    print(f"Target       : {VERSION}")
    print(f"Mode         : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    if current is None and not args.force:
        eprint("[FAIL] Harness VERSION missing/unparseable. v6.9 is a delta updater; use --force only after manual compatibility review.")
        return 2
    if current is not None and current > TARGET_VERSION and not args.force:
        eprint(f"[FAIL] refusing to downgrade newer Harness VERSION {current_raw}")
        return 2
    if current is not None and current < MIN_VERSION and not args.force:
        eprint(f"[FAIL] v6.9 requires Harness >= 6.8.1; found {current_raw}. Install earlier required versions first.")
        return 2

    txn = Txn(root, args.dry_run)
    try:
        patch_agents(root, txn)
        patch_playbook(root, txn)
        skill_status = patch_skills(root, txn)
        config_status = patch_config_version(root, txn)
        write_release_files(root, txn)

        print(f"[CONFIG] harness_meta.version: {config_status}")
        for name, status in skill_status.items():
            print(f"[SKILL] {name}: {status}")

        if args.dry_run:
            print(f"\n[DRY-RUN] planned changed files: {len(set(txn.changed))}")
            for p in sorted(set(txn.changed)):
                print("  " + p.relative_to(root).as_posix())
            print("No files were changed.")
            return 0

        manifest_status = refresh_manifest_for_changed_files(root, txn)
        print(f"[MANIFEST] changed-file hashes: {manifest_status}")

        issues = self_check(root)
        if issues:
            raise RuntimeError("; ".join(issues))
    except Exception as exc:
        eprint(f"[FAIL] {exc}")
        eprint("[ROLLBACK] restoring files changed by this installer")
        txn.rollback()
        return 1

    print(f"\n[OK] Adaptive Codex Harness {VERSION} applied")
    if txn.backup.exists():
        print(f"[OK] Backup: {txn.backup}")
    print("[OK] Existing v6.8.1 plan/review/runtime fixes were preserved; v6.9 adds execution-evidence guidance only.")
    print("[OK] No new Skill, broad lint rule, or patterns-index promotion was added.")
    print("\nRecommended checks:")
    print("  python3 .codex/harness/scripts/doctor.py")
    print("  python3 .codex/harness/scripts/selftest.py")
    print("  python3 .codex/harness/scripts/test_db_guard.py")
    print("  python3 .codex/harness/scripts/side_effect_guard.py")
    print("\nRestart Codex with a NEW session (`codex`) so updated AGENTS/skills are loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
