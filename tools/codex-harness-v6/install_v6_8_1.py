#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

VERSION = "6.8.1"
MIN_VERSION = (6, 8, 0)
TARGET_VERSION = (6, 8, 1)

AGENTS_OLD_BEGIN = "<!-- adaptive-codex-harness-v6.8-plan-scope:begin -->"
AGENTS_OLD_END = "<!-- adaptive-codex-harness-v6.8-plan-scope:end -->"
AGENTS_BEGIN = "<!-- adaptive-codex-harness-v6.8.1-plan-scope:begin -->"
AGENTS_END = "<!-- adaptive-codex-harness-v6.8.1-plan-scope:end -->"
SKILL_OLD_BEGIN = "<!-- adaptive-codex-harness-v6.8-plan-scope-skill:begin -->"
SKILL_OLD_END = "<!-- adaptive-codex-harness-v6.8-plan-scope-skill:end -->"
SKILL_BEGIN = "<!-- adaptive-codex-harness-v6.8.1-plan-scope-skill:begin -->"
SKILL_END = "<!-- adaptive-codex-harness-v6.8.1-plan-scope-skill:end -->"
SELFTEST_MARKER_BEGIN = "# adaptive-codex-harness-v6.8.1-dynamic-version:begin"
SELFTEST_MARKER_END = "# adaptive-codex-harness-v6.8.1-dynamic-version:end"

AGENTS_BLOCK = f'''{AGENTS_BEGIN}
## Adaptive Codex Harness v6.8.1 — Plan Scope Guard + Blocking Qualification

The planning/review goal is **implementation-ready**, not exhaustive design.

### Plan purpose
A plan decides only:
- what requirement is being implemented;
- what is in/out of scope;
- which files/components are affected sufficiently to start implementation;
- implementation order and integration boundaries;
- data-protection/backward-compatibility constraints that materially affect the approach;
- acceptance and targeted verification criteria.

Do not expand plan.md into a code-level implementation specification. Finished code/SQL, DB-driver branch code, private-method internals, complete column lists, sentinel constants, speculative recovery mechanisms, and detailed future-phase design belong to implementation notes unless an acceptance-critical compatibility constraint requires them.

### Mandatory Blocking Qualification Gate
**Before writing any finding as Blocking, explicitly test it against the five conditions below.**
A finding may be Blocking only when at least one answer is YES:
1. Do requirements conflict so implementation direction cannot be chosen?
2. Is a required dependency/data source/interface missing so the requirement cannot be implemented?
3. Would the planned approach materially corrupt/overwrite protected data or break a required existing path?
4. Is an acceptance condition impossible to meet with the current plan?
5. Is an unresolved scope/integration boundary large enough to materially change the implementation approach?

If all five answers are NO, the finding **MUST NOT** be classified Blocking. Put it in Implementation notes or Future/out-of-scope instead.

Operational/tooling observations are not planning blockers by default. Examples include an incorrect test command, service/container name, Harness doctor warning/version-label mismatch, test runner incompatibility, or a verification command that needs adjustment. They become Blocking only if they satisfy one of the five conditions above—e.g. acceptance truly cannot be verified or the implementation direction itself must change.

Hardening ideas, future-proofing, optional DB constraints, hypothetical edge cases, architecture preferences, and details discoverable safely during implementation are non-blocking unless the five-condition gate says otherwise.

### Scope guard
- Requirements/proposal are the scope authority. Do not create scope merely because a reviewer can imagine a safer, cleaner, more generic, or future-proof design.
- A new model/service/repository/migration/table/abstraction not requested or clearly implied by the requirements needs an acceptance-condition reason or existing-code evidence proving necessity.
- Items explicitly future/out-of-scope get only: item name, defer reason, target phase. Do not design their files, algorithms, tests, or data flow now.
- Prefer implementation-time decisions for details that can be settled safely by reading the touched code during implementation.

### Review convergence
- Round 1: discover and classify findings, but every proposed blocker must pass the Blocking Qualification Gate first.
- Round 2+: verify prior blockers. A new Blocking category is allowed only if caused by the previous fix or newly evidenced data loss, build impossibility, or acceptance impossibility.
- Later rounds do not restart design review at finer granularity.
- New non-blocking observations go to Implementation notes and do not force another planning round.

### Plan Ready gate
Declare READY and stop expanding the plan when all are true:
1. target requirements are identified;
2. in/out scope boundaries are explicit;
3. affected files/components are identified sufficiently to start implementation;
4. DB/schema direction is known if needed;
5. legacy/new integration boundary is known;
6. protected-data/backward-compatibility constraints are known;
7. acceptance conditions have a verification strategy.

Once READY, missing implementation-level detail is not a reason to return to Blocking.

### Conversation continuity
This block is additive to prior Harness rules. Preserve v6.7 continuity/investigation behavior and v6.5 safety behavior. Do not pivot from the user's active task into Harness maintenance unless requested.
{AGENTS_END}'''

PLAN_SKILL_ADDENDUM = f'''{SKILL_BEGIN}
### v6.8.1 plan-scope policy
Before finalizing plan.md:
1. Map each plan step to an explicit requirement/acceptance condition.
2. Remove detailed design for future/out-of-scope work; keep only item + defer reason + target phase.
3. Move code-level discoveries (sentinel values, exact private-method logic, SQL/driver branches, complete column lists) to implementation notes unless acceptance-critical.
4. Challenge each new artifact not required/implied by the requirements; keep it only when acceptance requires it or existing-code evidence proves necessity.
5. Apply the Plan Ready gate. If it passes, finish the plan rather than searching for more design detail.
6. Tooling/doctor/test-command problems are Implementation notes by default, not plan blockers, unless they make acceptance impossible or materially change the implementation approach.
7. `plan_scope_guard.py` warnings are advisory cleanup prompts, never automatic blockers.
{SKILL_END}'''

REVIEW_SKILL_ADDENDUM = f'''{SKILL_BEGIN}
### v6.8.1 review-convergence + Blocking Qualification policy
Review for implementability and requirement coverage, not maximal detail.

Before recording **each** Blocking finding, run this qualification gate and record the matching reason:
- B1 requirement conflict prevents choosing implementation direction;
- B2 required dependency/data/interface is missing and prevents implementation;
- B3 planned approach would materially corrupt protected data or break a required existing path;
- B4 an acceptance condition cannot be met;
- B5 unresolved scope/integration boundary materially changes the implementation approach.

If none of B1-B5 applies, Blocking is forbidden. Classify as:
- Implementation note: actionable detail that can be resolved during implementation/verification; or
- Future/out-of-scope: valid concern intentionally deferred.

Important classification examples:
- wrong test command/service name -> Implementation note unless acceptance becomes impossible;
- Harness doctor/version-label mismatch -> Implementation note unless it prevents required verification entirely;
- test runner incompatibility such as a disabled runtime function -> Implementation note when the guard can be repaired without changing the product plan;
- optional DB hardening / alternative locking strategy -> Implementation note unless current plan risks protected data;
- future Phase design -> Future/out-of-scope, not Blocking.

Round behavior:
- Round 1: discover findings comprehensively, but qualify every blocker before writing it.
- Round 2+: verify previous blockers; new blocker categories require prior-fix causation or new evidence of data loss/build impossibility/acceptance impossibility.
- Do not promote implementation notes into plan requirements on later rounds.
- If Plan Ready passes, write READY and stop expanding review.md.
{SKILL_END}'''

POLICY = {
    "version": VERSION,
    "name": "plan-scope-guard-blocking-qualification-runtime-fixes",
    "blocking_qualification": {
        "mandatory_before_classification": True,
        "allowed_reasons": [
            "requirement_conflict_blocks_direction",
            "missing_required_dependency_blocks_implementation",
            "planned_data_corruption_or_required_path_breakage",
            "acceptance_condition_impossible",
            "scope_or_integration_boundary_changes_approach",
        ],
        "all_no_result": "blocking_forbidden",
        "operational_tooling_default": "implementation_note",
    },
    "review": {
        "round1": "discover_then_qualify_each_blocker",
        "round2_plus": "verify_existing_blockers_only",
        "new_blocker_exceptions": [
            "caused_by_previous_fix",
            "new_evidence_data_loss",
            "new_evidence_build_impossible",
            "new_evidence_acceptance_impossible",
        ],
    },
    "runtime_fixes": {
        "safe_test_proc_open": "allowed_for_framework_test_runner_while_other_guards_remain",
        "selftest_version": "read_current_VERSION_instead_of_hardcoded_6_0_0",
        "hook_version_label": "remove_stale_fixed_version_from_runtime_denial_messages",
    },
}

NOTES = '''# Adaptive Codex Harness v6.8.1

v6.8.1 is a corrective update for an installed v6.8.0 Harness.

Fixes:
- Makes the Blocking Qualification Gate mandatory on the first review, not only on re-review.
- Treats tooling/doctor/test-command issues as Implementation notes by default unless they truly block implementation/acceptance.
- Removes `proc_open` from PHP `disable_functions` in `safe_test.py` so Laravel/Symfony Process-based test execution can start; DB, network, mail, queue, storage, printing, SMB and other side-effect protections remain in place.
- Removes the original `selftest.py` hard-coded `6.0.0` expectation and reads `.codex/harness/VERSION` dynamically.
- Removes stale fixed `v6.5`/older labels from PreToolUse denial messages so messages do not falsely report the installed Harness version.

This installer is intentionally a v6.8.x delta. It refuses versions older than 6.8.0 unless `--force` is explicitly used.
'''

SELFTEST_HELPER = f'''{SELFTEST_MARKER_BEGIN}
def _adaptive_harness_expected_version() -> str:
    """Return the installed Harness VERSION instead of pinning selftest to v6.0.0."""
    from pathlib import Path as _HarnessPath
    version_file = _HarnessPath(__file__).resolve().parents[1] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "<missing>"
{SELFTEST_MARKER_END}
'''


@dataclass
class Txn:
    root: Path
    dry_run: bool

    def __post_init__(self) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup = self.root / ".harness" / "backups" / f"v6.8.1-{stamp}"
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
    # Typical: <project>/tools/codex-harness-v6/install_v6_8_1.py or <project>/tools/install_v6_8_1.py
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


def replace_managed_block(text: str, old_begin: str, old_end: str, begin: str, end: str, block: str) -> str:
    text = strip_block(text, old_begin, old_end)
    text = strip_block(text, begin, end)
    text = text.rstrip() + "\n\n" + block.strip() + "\n"
    return text


def candidate_skill_files(root: Path) -> list[Path]:
    skill_root = root / ".agents" / "skills"
    if not skill_root.exists():
        return []
    found: list[Path] = []
    for p in skill_root.rglob("SKILL.md"):
        parent = p.parent.name.lower()
        rel = p.as_posix().lower()
        if parent in {"harness-review", "create-plan", "harness-create-plan", "review-plan", "harness-plan", "plan", "planning"} or "plan" in parent or "harness-review" in rel:
            found.append(p)
    return sorted(set(found))


def patch_agents(root: Path, txn: Txn) -> None:
    path = root / "AGENTS.md"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    new = replace_managed_block(old, AGENTS_OLD_BEGIN, AGENTS_OLD_END, AGENTS_BEGIN, AGENTS_END, AGENTS_BLOCK)
    txn.write_text(path, new)


def patch_skills(root: Path, txn: Txn) -> list[str]:
    changed: list[str] = []
    for path in candidate_skill_files(root):
        old = path.read_text(encoding="utf-8", errors="replace")
        low = path.parent.name.lower()
        block = REVIEW_SKILL_ADDENDUM if "review" in low else PLAN_SKILL_ADDENDUM
        new = replace_managed_block(old, SKILL_OLD_BEGIN, SKILL_OLD_END, SKILL_BEGIN, SKILL_END, block)
        if txn.write_text(path, new):
            changed.append(path.relative_to(root).as_posix())
    return changed


def patch_safe_test(root: Path, txn: Txn) -> str:
    path = root / ".codex" / "harness" / "scripts" / "safe_test.py"
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    old = text

    # v6.4/v6.5 layout: remove proc_open only from PHP_DISABLED_FUNCTIONS.
    m = re.search(r"PHP_DISABLED_FUNCTIONS\s*=.*?(?=\nTEST_ENV\s*=)", text, flags=re.S)
    if m:
        block = m.group(0)
        block2 = re.sub(r"([\"'])proc_open\1\s*,\s*", "", block)
        block2 = re.sub(r",\s*([\"'])proc_open\1", "", block2)
        text = text[:m.start()] + block2 + text[m.end():]
    else:
        # Fallback for a direct disable_functions string in safe_test.py.
        text = re.sub(r"(?i)(disable_functions[^\n]*?)(?:,?\s*proc_open\s*,?)", lambda m: m.group(1).rstrip(", "), text)

    if text != old:
        txn.write_text(path, text, mode=0o755)
        return "patched"
    if re.search(r"PHP_DISABLED_FUNCTIONS\s*=.*?(?=\nTEST_ENV\s*=)", text, flags=re.S) and "proc_open" not in re.search(r"PHP_DISABLED_FUNCTIONS\s*=.*?(?=\nTEST_ENV\s*=)", text, flags=re.S).group(0):
        return "already-fixed"
    return "not-recognized"


def insert_after_future_or_shebang(text: str, block: str) -> str:
    future = re.search(r"^from __future__ import annotations\s*$", text, flags=re.M)
    if future:
        pos = future.end()
        return text[:pos] + "\n\n" + block.strip() + "\n" + text[pos:]
    first_nl = text.find("\n")
    pos = first_nl + 1 if text.startswith("#!") and first_nl >= 0 else 0
    return text[:pos] + block.strip() + "\n\n" + text[pos:]


def patch_selftest(root: Path, txn: Txn) -> str:
    path = root / ".codex" / "harness" / "scripts" / "selftest.py"
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    original = text

    if SELFTEST_MARKER_BEGIN not in text:
        text = insert_after_future_or_shebang(text, SELFTEST_HELPER)

    lines = text.splitlines(keepends=True)
    changed_literal = False
    for i, line in enumerate(lines):
        if not re.search(r"(['\"])6\.0\.0\1", line):
            continue
        context = "".join(lines[max(0, i - 2): min(len(lines), i + 3)]).lower()
        if "version" not in context:
            continue
        lines[i] = re.sub(r"(['\"])6\.0\.0\1", "_adaptive_harness_expected_version()", line)
        changed_literal = True
    text = "".join(lines)

    # Fallback for a known selftest message/condition where the literal may be separated slightly.
    if "6.0.0" in text and "Harness version mismatch" in text:
        # Only replace remaining 6.0.0 literals on lines mentioning VERSION/version.
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if "6.0.0" in line and "version" in line.lower():
                lines[i] = line.replace('"6.0.0"', "_adaptive_harness_expected_version()").replace("'6.0.0'", "_adaptive_harness_expected_version()")
                changed_literal = True
        text = "".join(lines)

    if text != original:
        txn.write_text(path, text, mode=0o755)
        return "patched" if changed_literal else "helper-added"
    return "already-fixed"


def patch_hook_labels(root: Path, txn: Txn) -> str:
    path = root / ".codex" / "harness" / "hooks" / "pre_tool_safety.py"
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    # Runtime denial messages should not claim a stale historical installer version.
    new = re.sub(r"Adaptive Harness v6\.(?:[0-9]+)(?:\.[0-9]+)?", "Adaptive Harness", text)
    if new != text:
        txn.write_text(path, new, mode=0o755)
        return "patched"
    return "already-versionless"


def write_release_files(root: Path, txn: Txn) -> None:
    txn.write_text(root / ".codex" / "harness" / "VERSION", VERSION + "\n")
    txn.write_json(root / ".codex" / "harness" / "v6_8_1_policy.json", POLICY)
    txn.write_text(root / ".codex" / "harness" / "V6_8_1.md", NOTES)


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
        if AGENTS_BEGIN not in text or "Mandatory Blocking Qualification Gate" not in text:
            issues.append("v6.8.1 Blocking Qualification policy missing from AGENTS.md")

    safe = root / ".codex" / "harness" / "scripts" / "safe_test.py"
    if safe.is_file():
        try:
            ast.parse(safe.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            issues.append(f"safe_test.py syntax error: {exc}")
        sm = re.search(r"PHP_DISABLED_FUNCTIONS\s*=.*?(?=\nTEST_ENV\s*=)", safe.read_text(encoding="utf-8", errors="replace"), flags=re.S)
        if sm and "proc_open" in sm.group(0):
            issues.append("safe_test.py still disables proc_open")

    selftest = root / ".codex" / "harness" / "scripts" / "selftest.py"
    if selftest.is_file():
        st = selftest.read_text(encoding="utf-8", errors="replace")
        try:
            ast.parse(st)
        except SyntaxError as exc:
            issues.append(f"selftest.py syntax error: {exc}")
        if re.search(r"(['\"])6\.0\.0\1", st) and "version" in st.lower():
            issues.append("selftest.py still contains hard-coded 6.0.0 version expectation")

    hook = root / ".codex" / "harness" / "hooks" / "pre_tool_safety.py"
    if hook.is_file():
        ht = hook.read_text(encoding="utf-8", errors="replace")
        try:
            ast.parse(ht)
        except SyntaxError as exc:
            issues.append(f"pre_tool_safety.py syntax error: {exc}")
        if re.search(r"Adaptive Harness v6\.(?:[0-9]+)(?:\.[0-9]+)?", ht):
            issues.append("pre_tool_safety.py still contains a stale fixed Harness version label")

    policy = root / ".codex" / "harness" / "v6_8_1_policy.json"
    if not policy.is_file():
        issues.append("missing v6_8_1_policy.json")
    else:
        try:
            data = json.loads(policy.read_text(encoding="utf-8"))
            if data.get("version") != VERSION:
                issues.append("v6_8_1_policy.json version mismatch")
        except Exception as exc:
            issues.append(f"invalid v6_8_1_policy.json: {exc}")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6.8.1 corrective updater")
    ap.add_argument("--target", "--project-root", dest="project_root", help="Project root. Usually omitted when this file is under project/tools/codex-harness-v6/.")
    ap.add_argument("--dry-run", action="store_true", help="Show changes without writing files.")
    ap.add_argument("--force", action="store_true", help="Allow use on versions older than 6.8.0 or with unparseable VERSION after manual review.")
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
        eprint("[FAIL] Harness VERSION missing/unparseable. v6.8.1 is a delta updater; use --force only after manual compatibility review.")
        return 2
    if current is not None and current > TARGET_VERSION and not args.force:
        eprint(f"[FAIL] refusing to downgrade newer Harness VERSION {current_raw}")
        return 2
    if current is not None and current < MIN_VERSION and not args.force:
        eprint(f"[FAIL] v6.8.1 requires Harness >= 6.8.0; found {current_raw}. Install the missing earlier versions first.")
        return 2

    txn = Txn(root, args.dry_run)
    try:
        patch_agents(root, txn)
        skill_changes = patch_skills(root, txn)
        safe_status = patch_safe_test(root, txn)
        selftest_status = patch_selftest(root, txn)
        hook_status = patch_hook_labels(root, txn)
        write_release_files(root, txn)

        print(f"[PLAN-SCOPE] skills: {len(skill_changes)} changed")
        print(f"[SAFE-TEST] proc_open compatibility: {safe_status}")
        print(f"[SELFTEST] dynamic VERSION expectation: {selftest_status}")
        print(f"[HOOK] stale runtime version labels: {hook_status}")

        if args.dry_run:
            print(f"\n[DRY-RUN] planned changed files: {len(set(txn.changed))}")
            for p in sorted(set(txn.changed)):
                print("  " + p.relative_to(root).as_posix())
            print("No files were changed.")
            return 0

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
    print("[OK] v6.8 planning scope rules retained and strengthened; v6.5-v6.7 safety/continuity state preserved.")
    print("\nRecommended checks:")
    print("  python3 .codex/harness/scripts/doctor.py")
    print("  python3 .codex/harness/scripts/test_db_guard.py")
    print("  python3 .codex/harness/scripts/side_effect_guard.py")
    print("  grep -n \"proc_open\" .codex/harness/scripts/safe_test.py")
    print("\nRestart Codex with a NEW session (`codex`), not an old `codex resume --last`, so updated instructions/hooks are reloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
