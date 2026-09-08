#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

VERSION = "6.1.0"

# v6で実際にStop hookから出力されていた文言。
V6_STOP_TEXT = (
    "Adaptive Harness v6 quality gate: run `python3 .codex/harness/scripts/verify.py` "
    "and resolve required failures; spawn one bounded independent `reviewer`, address "
    "blocking findings, and obtain `VERDICT: PASS`. Later edits invalidate the relevant stamp."
)

V61_STOP_TEXT = (
    "Adaptive Harness v6.1 scoped quality gate: validate the current task first. "
    "Resolve only failures caused by the current task. Do not modify unrelated pre-existing "
    "dirty-worktree changes or failures; report them as non-blocking instead. "
    "Use targeted verification for small/low-risk changes. Run full verification only when "
    "the current task is broad/high-risk or targeted verification is insufficient. "
    "Spawn one bounded independent `reviewer` only for broad/high-risk changes "
    "(for example: >=5 task-touched files, >=200 task diff lines, auth/permission/security, "
    "migration/schema, cross-service/repository behavior, or an explicit review request). "
    "A reviewer is not required for a small low-risk fix with adequate targeted verification. "
    "Later edits invalidate only the verification/review evidence relevant to those edits."
)

POLICY_MARKER = "## Adaptive Codex Harness v6.1 scoped quality gate"
POLICY_TEXT = r"""
## Adaptive Codex Harness v6.1 scoped quality gate

### Scope ownership
- Separate current-task changes from pre-existing dirty-worktree changes before expanding verification.
- Fix only failures reasonably attributable to the current task.
- Do not repair, reformat, refactor, or update unrelated pre-existing changes merely to make a repository-wide gate pass.
- Pre-existing/unrelated failures are reported as non-blocking unless the user's task explicitly includes them.

### Verification escalation
Use the smallest verification level that gives adequate confidence.

Level 1 — small / low risk:
- inspect the task diff
- `git diff --check` for task-touched files when applicable
- run directly relevant tests/checks only

Level 2 — moderate:
- Level 1
- lint/format task-touched files
- run the relevant Unit/Feature/regression group

Level 3 — broad / high risk:
- repository verification gate
- broader test/lint/architecture checks
- independent reviewer when the reviewer threshold below is met

Do not automatically escalate from Level 1/2 to Level 3 solely because unrelated dirty-worktree
changes make a repository-wide verification command fail.

### Reviewer threshold
Spawn at most one bounded independent reviewer only when at least one applies:
- 5 or more files were touched by the current task
- current-task diff is roughly 200 lines or more
- authentication, authorization, permissions, security, secrets, or access boundaries changed
- database migration/schema or destructive/persistent data behavior changed
- behavior spans multiple services/repositories/components and regression risk is material
- the user explicitly requested independent review
- there is another concrete high-risk reason documented by the parent agent

For a small low-risk fix with adequate targeted verification, reviewer is optional and normally skipped.

### Existing failures
When a full gate is run and fails:
1. determine whether each failure is caused by the current task;
2. fix current-task-caused failures;
3. do not edit unrelated files to clear pre-existing failures;
4. report unrelated failures concisely and allow task completion when targeted evidence is sufficient.

### Re-runs and logs
- Avoid repeatedly re-running the full gate after every tiny edit.
- Re-run only checks invalidated by the edit, unless a final full gate is justified by task risk.
- Prefer bounded detail output. Do not read raw/full logs unless bounded detail is insufficient.
- Avoid re-reading unchanged large diffs and unchanged logs.
""".strip() + "\n"

CANDIDATE_TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".sh", ".toml", ".json", ".yaml", ".yml"
}

SEARCH_ROOTS = (
    ".codex",
    ".agents",
)

PRESERVE_PATHS = (
    "docs",
    "memo",
    ".codex/harness/commands.json",
    ".codex/harness/config.json",
    ".codex/harness/architecture_rules.json",
)

def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)

def detect_project_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"Project rootが存在しません: {root}")
        return root

    here = Path.cwd().resolve()
    candidates = [here, *here.parents]
    for root in candidates:
        if (root / ".codex" / "harness").is_dir() and (root / ".agents").is_dir():
            return root

    script_dir = Path(__file__).resolve().parent
    for root in [script_dir, *script_dir.parents]:
        if (root / ".codex" / "harness").is_dir() and (root / ".agents").is_dir():
            return root

    raise SystemExit(
        "Adaptive Codex Harnessが導入済みのProject rootを検出できません。\n"
        "Project rootで実行するか、--target /path/to/project を指定してください。"
    )

def read_version(root: Path) -> str:
    version_file = root / ".codex" / "harness" / "VERSION"
    if not version_file.exists():
        raise SystemExit(".codex/harness/VERSION がありません。v6導入済みProjectで実行してください。")
    return version_file.read_text(encoding="utf-8", errors="replace").strip()

def looks_like_v6(version: str) -> bool:
    return version.startswith("6.")

def backup_file(root: Path, backup_root: Path, path: Path) -> None:
    rel = path.relative_to(root)
    dst = backup_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)

def restore_backup(root: Path, backup_root: Path, touched: list[Path], created: list[Path]) -> None:
    for path in created:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    for path in touched:
        rel = path.relative_to(root)
        src = backup_root / rel
        if src.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, path)

def iter_candidate_files(root: Path):
    for rel_root in SEARCH_ROOTS:
        base = root / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in CANDIDATE_TEXT_EXTENSIONS:
                continue
            # runtime/log/backup類は触らない
            parts = set(path.relative_to(root).parts)
            if {"runtime", "logs", "verification", "__pycache__"} & parts:
                continue
            yield path

def patch_exact_stop_feedback(text: str) -> tuple[str, bool]:
    if V6_STOP_TEXT in text:
        return text.replace(V6_STOP_TEXT, V61_STOP_TEXT), True

    # 改行や空白差を許容した安全な限定置換。
    anchors = (
        "Adaptive Harness v6 quality gate:",
        "resolve required failures",
        "spawn one bounded independent `reviewer`",
        "obtain `VERDICT: PASS`",
    )
    if all(anchor in text for anchor in anchors):
        start = text.find("Adaptive Harness v6 quality gate:")
        end_marker = "Later edits invalidate the relevant stamp."
        end = text.find(end_marker, start)
        if start >= 0 and end >= 0:
            end += len(end_marker)
            return text[:start] + V61_STOP_TEXT + text[end:], True

    return text, False

def append_policy_if_relevant(path: Path, text: str) -> tuple[str, bool]:
    if POLICY_MARKER in text:
        return text, False

    name = path.name.lower()
    rel = path.as_posix().lower()

    relevant = (
        "harness-verify" in rel
        or "harness-review" in rel
        or "harness-develop" in rel
        or "agents.md" == name
        or "stop" in name and "hook" in rel
        or "quality" in name and "hook" in rel
    )
    if not relevant:
        return text, False

    separator = "\n" if text.endswith("\n") else "\n\n"
    return text + separator + POLICY_TEXT, True

def write_version(root: Path, backup_root: Path, dry_run: bool,
                  touched: list[Path], created: list[Path]) -> None:
    path = root / ".codex" / "harness" / "VERSION"
    if dry_run:
        return
    if path.exists():
        backup_file(root, backup_root, path)
        touched.append(path)
    else:
        created.append(path)
    path.write_text(VERSION + "\n", encoding="utf-8")

def write_policy_file(root: Path, backup_root: Path, dry_run: bool,
                      touched: list[Path], created: list[Path]) -> Path:
    path = root / ".codex" / "harness" / "SCOPED_QUALITY_GATE.md"
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(root, backup_root, path)
        touched.append(path)
    else:
        created.append(path)
    path.write_text(POLICY_TEXT, encoding="utf-8")
    return path

def self_check(root: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []

    version = read_version(root)
    if version != VERSION:
        problems.append(f"VERSIONが{VERSION}ではありません: {version}")

    policy = root / ".codex" / "harness" / "SCOPED_QUALITY_GATE.md"
    if not policy.exists():
        problems.append("SCOPED_QUALITY_GATE.md がありません")
    else:
        text = policy.read_text(encoding="utf-8", errors="replace")
        for required in (
            "Fix only failures reasonably attributable to the current task.",
            "5 or more files",
            "roughly 200 lines",
            "reviewer is optional and normally skipped",
        ):
            if required not in text:
                problems.append(f"policy不足: {required}")

    remaining = []
    for path in iter_candidate_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if V6_STOP_TEXT in text:
            remaining.append(str(path.relative_to(root)))
    if remaining:
        problems.append("旧v6 Stop hook文言が残っています: " + ", ".join(remaining))

    return not problems, problems

def install(root: Path, dry_run: bool) -> int:
    current = read_version(root)
    if not looks_like_v6(current):
        raise SystemExit(
            f"対象VERSIONは {current!r} です。"
            "このinstall.pyはAdaptive Codex Harness v6系専用です。"
        )

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = root / ".codex-harness-backup" / f"v6.1-{timestamp}"
    touched: list[Path] = []
    created: list[Path] = []

    candidates = list(iter_candidate_files(root))
    exact_patches: list[Path] = []
    policy_appends: list[Path] = []

    planned: dict[Path, str] = {}
    for path in candidates:
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        updated, exact = patch_exact_stop_feedback(original)
        updated, appended = append_policy_if_relevant(path, updated)

        if updated != original:
            planned[path] = updated
            if exact:
                exact_patches.append(path)
            if appended:
                policy_appends.append(path)

    print(f"Project root : {root}")
    print(f"Current      : {current}")
    print(f"Target       : {VERSION}")
    print(f"Mode         : {'DRY-RUN' if dry_run else 'APPLY'}")
    print()
    print("v6.1 changes:")
    print("  - current-task起因の失敗だけをblocking修正")
    print("  - unrelated / pre-existing dirty failuresは報告のみ")
    print("  - small fixはtargeted verificationで完了可能")
    print("  - full gateはbroad/high-risk時のみ")
    print("  - reviewerは>=5 files / >=200 lines / high-risk等でのみ必須")
    print("  - full gateの無駄な再実行とraw log読込を抑制")
    print()

    if exact_patches:
        print("[PLAN] Stop hook feedback更新:")
        for p in exact_patches:
            print(f"  - {p.relative_to(root)}")
    else:
        print("[INFO] 既知のv6 Stop hook固定文言は見つかりませんでした。")
        print("       ただしv6.1 policyをHarness skillsへ追記し、共通policy fileを配置します。")

    if policy_appends:
        print("[PLAN] scoped policy追記:")
        for p in policy_appends:
            print(f"  - {p.relative_to(root)}")

    print("[PLAN] .codex/harness/SCOPED_QUALITY_GATE.md")
    print("[PLAN] .codex/harness/VERSION -> 6.1.0")

    if dry_run:
        print()
        print("[DRY-RUN] ファイルは変更していません。")
        return 0

    try:
        backup_root.mkdir(parents=True, exist_ok=True)

        for path, new_text in planned.items():
            backup_file(root, backup_root, path)
            touched.append(path)
            path.write_text(new_text, encoding="utf-8")

        write_policy_file(root, backup_root, False, touched, created)
        write_version(root, backup_root, False, touched, created)

        ok, problems = self_check(root)
        if not ok:
            raise RuntimeError("\n".join(problems))

    except Exception as exc:
        eprint(f"[FAIL] v6.1適用に失敗しました: {exc}")
        eprint("[ROLLBACK] 変更を復元します。")
        restore_backup(root, backup_root, touched, created)
        return 1

    print()
    print("[OK] Adaptive Codex Harness v6.1.0 を適用しました。")
    print(f"[OK] Backup: {backup_root}")
    print()
    print("保持:")
    for item in PRESERVE_PATHS:
        print(f"  - {item}")
    print()
    print("確認:")
    print("  1. cat .codex/harness/VERSION")
    print("  2. grep -R \"v6.1 scoped quality gate\" .codex .agents 2>/dev/null")
    print("  3. python3 .codex/harness/scripts/doctor.py")
    print()
    print("既存のcommands/config/docs/memo/architecture_rulesは変更しません。")
    return 0

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Adaptive Codex Harness v6 -> v6.1 scoped quality-gate patch installer"
    )
    parser.add_argument(
        "--target",
        help="Project rootを明示指定。省略時はcwd/親ディレクトリからv6を自動検出します。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更予定だけ表示し、ファイルは変更しません。",
    )
    args = parser.parse_args()

    root = detect_project_root(args.target)
    raise SystemExit(install(root, args.dry_run))

if __name__ == "__main__":
    main()
