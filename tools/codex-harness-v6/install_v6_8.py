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

VERSION = "6.8.0"
MIN_EXISTING_MAJOR = 6

AGENTS_BEGIN = "<!-- adaptive-codex-harness-v6.8-plan-scope:begin -->"
AGENTS_END = "<!-- adaptive-codex-harness-v6.8-plan-scope:end -->"
SKILL_BEGIN = "<!-- adaptive-codex-harness-v6.8-plan-scope-skill:begin -->"
SKILL_END = "<!-- adaptive-codex-harness-v6.8-plan-scope-skill:end -->"

AGENTS_BLOCK = f'''{AGENTS_BEGIN}
## Adaptive Codex Harness v6.8 — Plan Scope Guard + Review Convergence

When creating or reviewing implementation plans, optimize for implementability, not exhaustive design.

### Plan purpose
A plan should decide only:
- what requirement is being implemented;
- what is in/out of scope;
- which existing/new files or components are affected;
- the implementation order and integration boundaries;
- data-protection / backward-compatibility constraints that materially affect the approach;
- acceptance and targeted verification criteria.

Do not expand plan.md into a detailed implementation specification. Unless a user requirement explicitly requires it, keep the following out of plan.md: finished code/SQL, DB-driver branch code, private-method internals, full column lists, sentinel constants, low-level framework syntax, speculative failure-recovery mechanisms, or detailed design for future phases. Record implementation-time discoveries separately instead of feeding them back into plan.md.

### Scope guard
- Requirements/proposal are the scope authority. Do not create new scope merely because a reviewer can imagine a safer, cleaner, more generic, or future-proof design.
- For an artifact not requested by the requirements (new model/service/repository/migration/table/abstraction), include it only when it is necessary for an acceptance condition or existing-code evidence proves it is necessary.
- Items explicitly marked future/out-of-scope get only: item name, reason deferred, and target phase. Do not design their files, algorithms, tests, or data flow now.
- Prefer implementation-time decisions for details that can be settled safely by reading the touched code during implementation.

### Blocking finding definition
A plan-review finding is Blocking only when at least one is true:
1. requirements conflict so implementation direction cannot be chosen;
2. a required dependency/data source/interface is missing so the requirement cannot be implemented;
3. the planned approach would materially corrupt/overwrite protected data or break a required existing path;
4. an acceptance condition cannot be met;
5. an unresolved scope/integration boundary would materially change the implementation approach.

Hardening ideas, future-proofing, optional DB constraints, possible edge cases, stylistic architecture preferences, and details discoverable during implementation are Non-blocking / Implementation notes unless they satisfy the Blocking definition above.

### Review convergence
- Review round 1 may discover new Blocking findings across the plan.
- From review round 2 onward, do not introduce a new Blocking category unless it was caused by the previous fix, or it is a newly evidenced data-loss/build/acceptance impossibility missed earlier.
- Later rounds verify previously identified blockers; they do not restart the design review at a finer granularity.
- New non-blocking observations after round 1 go to Implementation notes and must not force another planning round.

### Plan Ready gate
Declare the plan READY and stop expanding it when all are true:
1. target requirements are identified;
2. in-scope and out-of-scope boundaries are explicit;
3. affected files/components can be identified sufficiently to start implementation;
4. required DB/schema change direction is known, if any;
5. legacy/new-path switching or integration boundary is known;
6. protected-data/backward-compatibility constraints are known;
7. acceptance conditions have a verification strategy.

Once this gate is satisfied, lack of implementation-level detail is not a reason to return the plan to Blocking.

### Conversation continuity
This v6.8 block is additive. Preserve existing v6.7 continuity/investigation rules. If the current request refers to earlier discussion, keep that subject as the active task and do not pivot to adjacent Harness maintenance unless the user asks.
{AGENTS_END}'''

PLAN_SKILL_ADDENDUM = f'''{SKILL_BEGIN}
### v6.8 plan-scope policy
Before finalizing plan.md:
1. Map each plan step to an explicit requirement/acceptance condition.
2. Remove detailed design for anything marked Phase 2/3/later or otherwise out of scope; retain only defer reason + target phase.
3. Move code-level discoveries (sentinel values, exact private method implementation, SQL/driver branches, complete column enumerations) out of plan.md unless they are required to explain an acceptance-critical compatibility constraint.
4. Challenge every newly proposed artifact not named or implied by the requirements: keep it only if acceptance requires it or existing-code evidence makes it necessary.
5. Apply the Plan Ready gate. If it passes, finish the plan rather than searching for more design detail.
6. Run `.codex/harness/scripts/plan_scope_guard.py <plan-path> [--proposal <proposal-path>]` when available. WARN findings are advisory cleanup prompts, not automatic blockers.
{SKILL_END}'''

REVIEW_SKILL_ADDENDUM = f'''{SKILL_BEGIN}
### v6.8 review-convergence policy
Review plan/proposal for implementability and requirement coverage, not maximal detail.

Classify findings into exactly these buckets:
- Blocking: only issues matching the v6.8 Blocking definition.
- Implementation note: useful code-level detail to resolve during implementation.
- Future/out-of-scope: valid concern intentionally deferred; do not design it now.

Round behavior:
- Round 1: discover Blocking findings comprehensively.
- Round 2+: verify prior blockers. A new Blocking category is allowed only if caused by the prior fix or supported by newly discovered evidence of data loss, build impossibility, or acceptance impossibility.
- Do not turn implementation notes into new plan requirements on later rounds.
- If the Plan Ready gate passes, write READY and stop expanding review.md.
{SKILL_END}'''

POLICY = {
    "version": VERSION,
    "name": "plan-scope-guard-review-convergence",
    "plan": {
        "goal": "implementable_not_exhaustive",
        "forbid_by_default": [
            "finished_code_or_sql",
            "db_driver_branch_code",
            "private_method_internals",
            "full_column_enumerations",
            "sentinel_constants",
            "future_phase_detailed_design",
            "speculative_recovery_design",
        ],
        "out_of_scope_detail": "name_reason_target_phase_only",
        "new_artifact_rule": "acceptance_required_or_existing_code_evidence",
        "ready_gate": [
            "requirements_identified",
            "scope_boundaries_explicit",
            "affected_components_identified",
            "db_direction_known_if_needed",
            "integration_boundary_known",
            "data_compat_constraints_known",
            "verification_strategy_known",
        ],
    },
    "review": {
        "round1": "discover_blockers",
        "round2_plus": "verify_existing_blockers_only",
        "new_blocker_exceptions": [
            "caused_by_previous_fix",
            "new_evidence_data_loss",
            "new_evidence_build_impossible",
            "new_evidence_acceptance_impossible",
        ],
        "non_blocking_destination": "implementation_notes",
    },
}

GUARD_SCRIPT = r'''#!/usr/bin/env python3
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
'''

NOTES = '''# Adaptive Codex Harness v6.8

v6.8 adds **Plan Scope Guard** and **Review Convergence** on top of an existing v6.x Harness.

It is intentionally a delta update: it does not replace v6.7 conversation-continuity, investigation, safety, hooks, or project-owned state.

## Main behavior
- Plans stop at implementation-ready detail rather than expanding into code-level design.
- Out-of-scope/future work is summarized, not designed.
- New artifacts outside the requirements need an acceptance/evidence reason.
- Blocking findings have a narrow definition.
- Round 2+ reviews verify existing blockers instead of discovering ever-finer new blocker categories.
- A Plan Ready gate ends the planning loop once implementation can safely start.
- `plan_scope_guard.py` is a heuristic advisory linter; its warnings are not blockers by themselves.
'''

README_INSTALL = '''# Adaptive Codex Harness v6.8 installer

This installer applies the v6.8 planning/review delta to an **existing Adaptive Codex Harness v6.x project**.

## Recommended

```bash
python3 tools/install_v6_8.py --project-root /path/to/project --dry-run
python3 tools/install_v6_8.py --project-root /path/to/project
```

If the installer is placed under `<project>/tools/`, `--project-root` can normally be omitted.

## Options
- `--project-root PATH`: explicit project root.
- `--dry-run`: show changes without writing.
- `--force`: allow application when the existing Harness version cannot be parsed or is not v6.x. This does **not** delete project state.

## Files changed/added
- `AGENTS.md`: append/replace only the managed v6.8 block.
- matching planning/review Harness skills under `.agents/skills/`: append/replace only the managed v6.8 addendum.
- `.codex/harness/VERSION`: `6.8.0`.
- `.codex/harness/v6_8_policy.json`: machine-readable policy.
- `.codex/harness/V6_8.md`: release behavior.
- `.codex/harness/scripts/plan_scope_guard.py`: advisory plan linter.

Backups are stored under `.harness/backups/v6.8-<timestamp>/`.
'''

@dataclass
class Txn:
    root: Path
    dry_run: bool

    def __post_init__(self) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup = self.root / ".harness" / "backups" / f"v6.8-{stamp}"
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

    def write_text(self, path: Path, text: str, mode: int | None = None) -> None:
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        if old == text:
            return
        self.changed.append(path)
        if self.dry_run:
            return
        self._backup_once(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if mode is not None:
            path.chmod(mode)

    def write_json(self, path: Path, data: object) -> None:
        self.write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def rollback(self) -> None:
        if self.dry_run:
            return
        # Restore backed-up files. Remove newly created files from this transaction.
        backed_rels = set()
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
    # Typical layout: <project>/tools/install_v6_8.py
    for candidate in (script.parent.parent, Path.cwd().resolve()):
        if looks_like_project(candidate):
            return candidate
    for parent in Path.cwd().resolve().parents:
        if looks_like_project(parent):
            return parent
    raise SystemExit("project root not detected; pass --project-root PATH")


def replace_managed_block(text: str, begin: str, end: str, block: str) -> str:
    rx = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if rx.search(text):
        return rx.sub(block, text, count=1)
    sep = "\n" if text.endswith("\n") else "\n\n"
    return text + sep + block.strip() + "\n"


def candidate_skill_files(root: Path) -> list[Path]:
    skill_root = root / ".agents" / "skills"
    if not skill_root.exists():
        return []
    exact = {
        "harness-develop", "harness-review", "create-plan", "harness-create-plan",
        "plan", "planning", "review-plan", "harness-plan",
    }
    found: list[Path] = []
    for p in skill_root.rglob("SKILL.md"):
        parent = p.parent.name.lower()
        if parent in exact or "plan" in parent or parent == "harness-review":
            found.append(p)
    return sorted(set(found))


def patch_agents(root: Path, txn: Txn) -> None:
    path = root / "AGENTS.md"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    txn.write_text(path, replace_managed_block(old, AGENTS_BEGIN, AGENTS_END, AGENTS_BLOCK))


def patch_skills(root: Path, txn: Txn) -> list[str]:
    changed: list[str] = []
    for path in candidate_skill_files(root):
        old = path.read_text(encoding="utf-8", errors="replace")
        lowname = path.parent.name.lower()
        if "review" in lowname:
            block = REVIEW_SKILL_ADDENDUM
        else:
            block = PLAN_SKILL_ADDENDUM
        new = replace_managed_block(old, SKILL_BEGIN, SKILL_END, block)
        if new != old:
            txn.write_text(path, new)
            changed.append(path.relative_to(root).as_posix())
    return changed


def write_v68_files(root: Path, txn: Txn) -> None:
    txn.write_text(root / ".codex" / "harness" / "VERSION", VERSION + "\n")
    txn.write_json(root / ".codex" / "harness" / "v6_8_policy.json", POLICY)
    txn.write_text(root / ".codex" / "harness" / "V6_8.md", NOTES)
    txn.write_text(root / ".codex" / "harness" / "scripts" / "plan_scope_guard.py", GUARD_SCRIPT, mode=0o755)


def self_check(root: Path) -> list[str]:
    issues: list[str] = []
    required = [
        root / "AGENTS.md",
        root / ".codex/harness/VERSION",
        root / ".codex/harness/v6_8_policy.json",
        root / ".codex/harness/V6_8.md",
        root / ".codex/harness/scripts/plan_scope_guard.py",
    ]
    for p in required:
        if not p.is_file():
            issues.append(f"missing {p.relative_to(root)}")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8", errors="replace") if (root / "AGENTS.md").exists() else ""
    if AGENTS_BEGIN not in agents or AGENTS_END not in agents:
        issues.append("v6.8 AGENTS managed block missing")
    try:
        policy = json.loads((root / ".codex/harness/v6_8_policy.json").read_text(encoding="utf-8"))
        if policy.get("version") != VERSION:
            issues.append("v6_8_policy.json version mismatch")
    except Exception as exc:
        issues.append(f"invalid v6_8_policy.json: {exc}")
    script = root / ".codex/harness/scripts/plan_scope_guard.py"
    if script.exists():
        try:
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
        except SyntaxError as exc:
            issues.append(f"plan_scope_guard.py syntax error: {exc}")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6.8 Plan Scope Guard / Review Convergence updater")
    ap.add_argument("--project-root", "--target", dest="project_root", help="Project root. If omitted, auto-detect from cwd or project/tools/.")
    ap.add_argument("--dry-run", action="store_true", help="Show planned changes without writing files.")
    ap.add_argument("--force", action="store_true", help="Apply even when an existing v6.x version cannot be verified.")
    args = ap.parse_args()

    root = find_project_root(args.project_root)
    current_raw = installed_version(root)
    current = parse_version(current_raw)
    harness_dir = root / ".codex" / "harness"

    print(f"Project root : {root}")
    print(f"Current      : {current_raw or 'unknown/not installed'}")
    print(f"Target       : {VERSION}")
    print(f"Mode         : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    if not harness_dir.exists() and not args.force:
        eprint("[FAIL] existing Adaptive Codex Harness not found. v6.8 is a delta updater; install a v6.x base first, or use --force only when you know this project is compatible.")
        return 2
    if current is not None and current[0] != MIN_EXISTING_MAJOR and not args.force:
        eprint(f"[FAIL] expected existing Harness v6.x, found {current_raw}. Use --force only after manual compatibility review.")
        return 2
    if current is None and harness_dir.exists() and not args.force:
        eprint("[FAIL] Harness directory exists but VERSION is missing/unparseable. Use --force after reviewing the project.")
        return 2

    txn = Txn(root, args.dry_run)
    try:
        patch_agents(root, txn)
        skill_changes = patch_skills(root, txn)
        write_v68_files(root, txn)

        if args.dry_run:
            print(f"[DRY-RUN] planned changed files: {len(set(txn.changed))}")
            for p in sorted(set(txn.changed)):
                print("  " + p.relative_to(root).as_posix())
            if skill_changes:
                print("[DRY-RUN] skill addenda: " + ", ".join(skill_changes))
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

    print(f"[OK] Adaptive Codex Harness {VERSION} applied")
    if txn.backup.exists():
        print(f"[OK] Backup: {txn.backup}")
    print("[OK] v6.7-era rules/state were preserved; v6.8 adds only planning/review scope controls.")
    print("\nRecommended check:")
    print("  python3 .codex/harness/scripts/plan_scope_guard.py memo/implement/plan.md --proposal memo/implement/proposal.md")
    print("\nRestart Codex after installation so updated project instructions are reloaded.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
