#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

VERSION = "6.6.0"
MIN_BASE = (6, 5)

MANAGED_BEGIN = "<!-- adaptive-codex-harness-v6.6:begin -->"
MANAGED_END = "<!-- adaptive-codex-harness-v6.6:end -->"
OLD_MANAGED_BLOCKS = (
    ("<!-- adaptive-codex-harness-v6.5:begin -->", "<!-- adaptive-codex-harness-v6.5:end -->"),
    ("<!-- adaptive-codex-harness-v6.4:begin -->", "<!-- adaptive-codex-harness-v6.4:end -->"),
    ("<!-- adaptive-codex-harness-v6.3:begin -->", "<!-- adaptive-codex-harness-v6.3:end -->"),
    ("<!-- adaptive-codex-harness-v6.2:begin -->", "<!-- adaptive-codex-harness-v6.2:end -->"),
    ("<!-- adaptive-codex-harness-v6.1:begin -->", "<!-- adaptive-codex-harness-v6.1:end -->"),
)

AGENTS_BLOCK = f"""{MANAGED_BEGIN}
## Adaptive Codex Harness v6.6 — semantic investigation + fail-closed safety + bounded execution
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

### Semantic task interpretation
- Interpret documents by **content and user intent**, not by filename. Do not require per-file registration for task-like Markdown/text files.
- Headings or sections such as `質問`, `依頼`, `質問・依頼`, `TODO`, `未対応`, `確認事項`, `調査項目`, `課題`, `既知バグ`, `修正待ち`, `Open questions`, `Action items`, `Pending`, and `Known bugs` are unresolved-work candidates unless their surrounding context clearly marks them historical or completed.
- When the user asks to **確認する / 調べる / 状況を教える / 原因を見る / 対応状況を見る / verify / investigate / check status**, reading or restating the document is not completion. Extract the relevant unresolved items, then inspect the current source of truth needed to answer each item: implementation, routes, controllers/services/repositories/models, migrations/schema, configuration, scheduler/cron, views, tests, logs, or Git state/diff as appropriate.
- When the user explicitly asks only to **要約する / 一覧化する / 内容を読む / summarize / list**, a document-only answer is allowed.
- For an investigation item, prefer at least one concrete implementation/configuration evidence source before concluding. If the repository contains no evidence sufficient to decide, say that it is unresolved instead of converting the memo text into a factual answer.
- Treat `現行コード` / `現在のコード` as the checked-out working tree including relevant uncommitted changes unless the user names a branch, commit, or remote ref. Distinguish `main`, `origin/main`, and the working tree when that distinction can change the answer.
- Sections explicitly marked `対応済み`, `完了`, `Resolved`, `Done`, or equivalent are reference-only by default; inspect them only when needed to answer an active item or when the user asks for them.
- Use targeted evidence first. Do not scan the entire repository merely because a task queue exists; follow links/symbols from the active items and stop when enough evidence exists.
- Optional project metadata/front matter may override classification, but absence of metadata must never prevent semantic task recognition.
{MANAGED_END}
"""

DEVELOP_APPEND = r"""
### v6.6 semantic investigation policy
- Treat task-like sections in project documents as work queues by meaning, not by filename. New memo/checklist files do not need Harness registration.
- If the user asks to check/investigate/status-review items in such a section, first extract the active items and then inspect the implementation/configuration/test/Git evidence needed for each one. Do not finish by paraphrasing the queue.
- If the user asks only for a summary/list/read-through, stay document-only unless implementation evidence is necessary to explain ambiguity.
- `current code` means the checked-out working tree, including relevant uncommitted changes, unless a branch/ref is explicitly named.
- Prefer bounded, directly relevant evidence. One concrete source is usually enough to establish a simple item; use more only where the behavior spans components or evidence conflicts.
"""

DEBUG_APPEND = r"""
### v6.6 investigation semantics
- A bug/TODO/question memo is a hypothesis/work queue, not a source of truth about current behavior.
- For `確認`, `調査`, `状況`, or equivalent requests, validate the memo against current code/config/schema/scheduler/tests/Git state before reporting status.
- Do not report the memo's wording itself as the finding. Report `confirmed`, `already fixed`, `partially fixed`, `not reproducible from code`, or `insufficient evidence`, with the smallest useful evidence trail.
- Inspect uncommitted task-relevant changes before concluding that a known bug still exists.
"""

POLICY_DELTA: dict[str, Any] = {
    "schema_version": 6,
    "version": VERSION,
    "document_semantics": {
        "classification": "semantic_by_default",
        "per_file_registration_required": False,
        "task_section_hints": [
            "質問", "依頼", "質問・依頼", "TODO", "未対応", "確認事項",
            "調査項目", "課題", "既知バグ", "修正待ち",
            "Open questions", "Action items", "Pending", "Known bugs",
        ],
        "completed_section_hints": ["対応済み", "完了", "Resolved", "Done"],
        "investigation_intent_hints": [
            "確認", "調べ", "調査", "状況", "原因", "対応状況",
            "verify", "investigate", "check status",
        ],
        "summary_intent_hints": ["要約", "一覧", "内容を読む", "summarize", "list"],
        "investigation_requires_source_of_truth": True,
        "memo_text_is_not_implementation_evidence": True,
        "working_tree_is_default_current_code": True,
        "file_specific_overrides": "optional_only",
        "bounded_evidence": True,
    },
}

NOTES = r"""# Adaptive Codex Harness v6.6

v6.6 adds semantic investigation behavior on top of the v6.5 safety and writable-layout baseline.

## What changed

- Task queues are recognized from document content and headings, not from registered filenames.
- `質問・依頼`, `TODO`, `未対応`, `確認事項`, `調査項目`, `既知バグ`, `Pending`, `Known bugs`, etc. are treated as unresolved-work candidates.
- If the user asks to check/investigate/status-review those items, the agent must inspect the relevant code/config/schema/scheduler/tests/Git state instead of merely summarizing the memo.
- Explicit summary/list requests remain document-only.
- `current code` defaults to the checked-out working tree including relevant uncommitted changes.
- Completed/resolved sections remain reference-only unless they are relevant to an active item.
- No per-file registration is required. Optional metadata may override classification when a project truly needs an exception.
- Evidence stays bounded and targeted; this feature must not turn every checklist into a repository-wide scan.

## Safety inheritance

v6.6 intentionally does not weaken or replace the v6.5 fail-closed DB/test/side-effect protections. Existing hooks and safety scripts remain in place.

## After installation

Start a new Codex session (or otherwise reload project instructions) so the updated `AGENTS.md` / skill instructions are picked up.
No hook definition is changed by this v6.6 delta, so `/hooks` re-trust is not normally required.
"""


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"\s*(\d+)\.(\d+)(?:\.(\d+))?\s*", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def find_project_root(script_dir: Path, target: str | None) -> Path:
    if target:
        root = Path(target).expanduser().resolve()
        if not root.exists():
            raise SystemExit(f"target does not exist: {root}")
        return root

    candidates = [Path.cwd().resolve(), script_dir.resolve(), *script_dir.resolve().parents]
    seen: set[Path] = set()
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        if (base / ".codex/harness/VERSION").exists():
            return base
        if base.name == "tools" and (base.parent / ".codex/harness/VERSION").exists():
            return base.parent
    raise SystemExit(
        "project root could not be detected. Run from the project root or pass --target /path/to/project."
    )


class Txn:
    def __init__(self, root: Path, dry_run: bool):
        self.root = root
        self.dry_run = dry_run
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup = root / ".harness" / "backups" / f"v6.6-{stamp}"
        self.originals: dict[Path, bytes | None] = {}
        self.modes: dict[Path, int | None] = {}
        self.changed: list[Path] = []

    def _remember(self, path: Path) -> None:
        if path in self.originals:
            return
        if path.exists() and path.is_file():
            self.originals[path] = path.read_bytes()
            self.modes[path] = path.stat().st_mode
        else:
            self.originals[path] = None
            self.modes[path] = None

    def write_text(self, path: Path, content: str) -> None:
        self._remember(path)
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() and path.is_file() else None
        if old == content:
            return
        self.changed.append(path)
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_json(self, path: Path, value: Any) -> None:
        self.write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def commit_backup(self) -> None:
        if self.dry_run or not self.changed:
            return
        changed_set = set(self.changed)
        for path, data in self.originals.items():
            if path not in changed_set or data is None:
                continue
            rel = path.relative_to(self.root)
            dst = self.backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)

    def rollback(self) -> None:
        if self.dry_run:
            return
        for path in reversed(list(dict.fromkeys(self.changed))):
            data = self.originals.get(path)
            try:
                if data is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    mode = self.modes.get(path)
                    if mode is not None:
                        path.chmod(mode)
            except OSError as exc:
                eprint(f"[ROLLBACK-WARN] {path}: {exc}")


def remove_managed_blocks(text: str) -> str:
    new = text
    for begin, end in (*OLD_MANAGED_BLOCKS, (MANAGED_BEGIN, MANAGED_END)):
        new = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", new, flags=re.S)
    return new.rstrip() + ("\n" if new.strip() else "")


def patch_agents(root: Path, txn: Txn) -> None:
    path = root / "AGENTS.md"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    base = remove_managed_blocks(old)
    sep = "\n" if base.endswith("\n") or not base else "\n\n"
    txn.write_text(path, base + sep + AGENTS_BLOCK.rstrip() + "\n")


def append_or_replace_addendum(text: str, heading: str, addition: str) -> str:
    idx = text.rfind("\n" + heading)
    if idx < 0 and text.startswith(heading):
        idx = 0
    if idx >= 0:
        prefix = text[:idx].rstrip()
        sep = "\n\n" if prefix else ""
        return prefix + sep + addition.strip() + "\n"
    sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + addition.strip() + "\n"


def patch_skills(root: Path, txn: Txn) -> None:
    targets = (
        (root / ".agents/skills/harness-develop/SKILL.md",
         "### v6.6 semantic investigation policy", DEVELOP_APPEND),
        (root / ".agents/skills/harness-debug/SKILL.md",
         "### v6.6 investigation semantics", DEBUG_APPEND),
    )
    for path, heading, addition in targets:
        if not path.exists():
            continue
        old = path.read_text(encoding="utf-8", errors="replace")
        txn.write_text(path, append_or_replace_addendum(old, heading, addition))


def build_policy(root: Path) -> dict[str, Any]:
    base_path = root / ".codex/harness/v6_5_policy.json"
    if not base_path.exists():
        raise RuntimeError("v6.5 policy is missing; install/repair v6.5 before applying v6.6")
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"cannot parse {base_path.relative_to(root)}: {exc}") from exc
    if not isinstance(base, dict):
        raise RuntimeError("v6.5 policy must be a JSON object")
    merged = dict(base)
    merged.update({
        "schema_version": POLICY_DELTA["schema_version"],
        "version": VERSION,
        "document_semantics": POLICY_DELTA["document_semantics"],
    })
    return merged


def self_check(root: Path) -> list[str]:
    problems: list[str] = []
    version_path = root / ".codex/harness/VERSION"
    if not version_path.exists() or version_path.read_text(encoding="utf-8", errors="replace").strip() != VERSION:
        problems.append(f"VERSION is not {VERSION}")

    policy_path = root / ".codex/harness/v6_6_policy.json"
    if not policy_path.exists():
        problems.append("missing v6_6_policy.json")
    else:
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            semantics = policy.get("document_semantics", {})
            if semantics.get("per_file_registration_required") is not False:
                problems.append("semantic policy does not disable per-file registration")
            if semantics.get("investigation_requires_source_of_truth") is not True:
                problems.append("semantic policy does not require source-of-truth investigation")
            if semantics.get("working_tree_is_default_current_code") is not True:
                problems.append("semantic policy does not define working-tree current code")
        except Exception as exc:
            problems.append(f"invalid v6_6_policy.json: {exc}")

    agents = root / "AGENTS.md"
    if not agents.exists():
        problems.append("missing AGENTS.md")
    else:
        text = agents.read_text(encoding="utf-8", errors="replace")
        for token in (
            MANAGED_BEGIN,
            "Interpret documents by **content and user intent**, not by filename.",
            "reading or restating the document is not completion",
            "checked-out working tree including relevant uncommitted changes",
        ):
            if token not in text:
                problems.append(f"AGENTS.md missing v6.6 semantic rule: {token}")

    for path in (
        root / ".codex/harness/scripts/test_db_guard.py",
        root / ".codex/harness/scripts/side_effect_guard.py",
        root / ".codex/harness/scripts/safe_test.py",
        root / ".codex/harness/hooks/pre_tool_safety.py",
        root / ".codex/hooks.json",
    ):
        if not path.exists():
            problems.append(f"v6.5 safety substrate missing: {path.relative_to(root)}")

    hooks = root / ".codex/hooks.json"
    if hooks.exists():
        try:
            raw = json.dumps(json.loads(hooks.read_text(encoding="utf-8")))
            if "pre_tool_safety.py" not in raw:
                problems.append("v6.5 PreToolUse safety hook is not referenced by hooks.json")
        except Exception as exc:
            problems.append(f"invalid .codex/hooks.json: {exc}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Adaptive Codex Harness v6.5 -> v6.6 semantic-investigation updater"
    )
    ap.add_argument("--target", help="Project root. Omit when run from the project or project/tools/.")
    ap.add_argument("--dry-run", action="store_true", help="Show planned files without changing them.")
    args = ap.parse_args()

    root = find_project_root(Path(__file__).resolve().parent, args.target)
    version_path = root / ".codex/harness/VERSION"
    if not version_path.exists():
        raise SystemExit("Adaptive Codex Harness is not installed in the target project.")

    current_text = version_path.read_text(encoding="utf-8", errors="replace").strip()
    current = parse_version(current_text)
    if current is None or current[0] != 6:
        raise SystemExit(f"unsupported Harness VERSION: {current_text!r}")
    if current[:2] < MIN_BASE:
        raise SystemExit(
            f"v6.6 requires the v6.5 safety/writable-layout baseline; current VERSION is {current_text}. "
            "Apply v6.5 first, then run this updater."
        )
    if current[:2] > (6, 6):
        raise SystemExit(f"refusing to downgrade newer Harness VERSION {current_text}")

    print(f"Project root : {root}")
    print(f"Current      : {current_text}")
    print(f"Target       : {VERSION}")
    print(f"Mode         : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()
    print("v6.6 changes:")
    print("  - task/checklist documents are classified by semantic content, not filename")
    print("  - check/investigate/status requests must inspect current source-of-truth evidence")
    print("  - summary/list requests may remain document-only")
    print("  - current code defaults to working tree + relevant uncommitted changes")
    print("  - completed sections are reference-only by default")
    print("  - targeted evidence only; no automatic repository-wide scan")
    print("  - v6.5 hooks and fail-closed safety are preserved")
    print()

    txn = Txn(root, args.dry_run)
    try:
        policy = build_policy(root)
        patch_agents(root, txn)
        patch_skills(root, txn)
        txn.write_json(root / ".codex/harness/v6_6_policy.json", policy)
        txn.write_text(root / ".codex/harness/V6_6.md", NOTES)
        txn.write_text(root / ".codex/harness/VERSION", VERSION + "\n")

        if args.dry_run:
            print(f"[DRY-RUN] planned changed files: {len(set(txn.changed))}")
            for path in sorted(set(txn.changed)):
                print("  " + path.relative_to(root).as_posix())
            print("No files were changed.")
            return 0

        problems = self_check(root)
        if problems:
            raise RuntimeError("; ".join(problems))
        txn.commit_backup()

    except Exception as exc:
        eprint(f"[FAIL] {exc}")
        eprint("[ROLLBACK] restoring files changed by this updater")
        txn.rollback()
        return 1

    print(f"[OK] Adaptive Codex Harness {VERSION} applied")
    if txn.backup.exists():
        print(f"[OK] Backup: {txn.backup}")
    print()
    print("After install:")
    print("  - Start a new Codex session / reload project instructions.")
    print("  - Hook definitions were not changed, so /hooks re-trust is normally unnecessary.")
    print("  - To confirm the safety hook separately, use /hooks in Codex.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
