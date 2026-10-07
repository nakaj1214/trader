#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

VERSION = "6.7.0"
MIN_BASE = (6, 6)

BLOCK_BEGIN = "<!-- adaptive-codex-harness-v6.7-continuity:begin -->"
BLOCK_END = "<!-- adaptive-codex-harness-v6.7-continuity:end -->"

CONTINUITY_BLOCK = f"""{BLOCK_BEGIN}
## Adaptive Codex Harness v6.7 — conversation continuity and drift prevention

### Active-intent continuity
- Treat a follow-up user turn as continuing the nearest compatible unresolved user intent unless the user clearly starts a different task.
- Resolve omitted subjects, pronouns, shorthand, and phrases such as `それ`, `その方針`, `切り替えたら`, `確認したい`, `直して`, `続けて`, and equivalent wording against the nearest compatible user-established context before inventing a new target.
- Keep user-established target entities and constraints sticky across compatible follow-ups: named records/users/employees, IDs, categories, branches, files, dates, environments, requested modes, and explicit success criteria remain active until the user changes them, the task is completed, or they become incompatible with the new request.
- A user correction immediately overrides the conflicting part of the active context while preserving the non-conflicting remainder.

### No silent target substitution
- Never replace a user-established target with a sibling/example/convenient substitute merely because it is easier to test or inspect.
- Assistant-introduced examples and alternatives have lower priority than user-established targets and must not become the active target unless the user accepts them or the original target is impossible and the substitution is explicitly disclosed.
- Mentioning a comparison candidate does not itself switch the task target.

### Drift guard before actions
- Before a tool call, code change, DB operation, or concrete recommendation that uses a named target not present in the current user turn, verify that the target comes from the active conversation chain.
- If the contemplated action would change the target entity, date, branch, environment, operation, or success criterion relative to the active chain, first re-resolve the recent context. Do not silently proceed on a newly invented target.
- Classify the new turn mentally as one of:
  - `CONTINUE`: same objective; inherit target and constraints.
  - `REFINE`: user changes one or more parameters; preserve all non-conflicting context.
  - `SWITCH`: clearly different objective/target; drop only context that no longer applies.
- Prefer `CONTINUE` over `SWITCH` when the new turn is elliptical but compatible with the existing task.

### Confirmation discipline
- Do not ask the user to repeat or reconfirm a target already established in the active conversation merely because the latest message omits it.
- Preserve normal safety/destructive-action confirmation requirements. Conversation continuity never authorizes an otherwise disallowed or confirmation-gated action.
- When ambiguity genuinely remains between two still-active user-established targets, state the competing interpretations briefly rather than choosing an unrelated third option.

### Scope and persistence
- Use the nearest relevant conversation chain, not the entire historical session. Do not resurrect stale targets from unrelated older topics.
- Do not create or update repository files solely to store conversational state. The continuity anchor is conversational unless the user explicitly asks for durable task state.
- Keep the continuity check lightweight; it must not trigger broad repository scans or repeated document reads.
{BLOCK_END}
"""

DEVELOP_APPEND = r"""
### v6.7 conversation continuity
- On follow-up implementation requests, inherit the nearest compatible user-established objective, target entities, dates, branch/environment, and success criteria.
- Do not swap the requested target for an easier example or sibling case. If a substitute is technically necessary, disclose it before using it and keep it separate from the requested target.
- Before editing or executing against an entity not named in the latest turn, verify it is the active target from the recent conversation chain.
- Interpret elliptical follow-ups as CONTINUE by default; parameter changes are REFINE; only a clear incompatible request is SWITCH.
"""

DEBUG_APPEND = r"""
### v6.7 conversation continuity
- Debug follow-ups inherit the active reproduction target and expected behavior unless the user changes them.
- Never replace the active target with a different example to make diagnosis easier. Additional examples are secondary evidence only.
- When the user asks what happens "if it is switched/changed" after naming a specific target earlier, test or reason about that specific target unless the new turn explicitly changes it.
- A correction from the user overrides the conflicting debug assumption immediately; retain the remaining context.
"""

POLICY = {
    "version": VERSION,
    "conversation_continuity": {
        "followup_default": "continue_nearest_compatible_user_intent",
        "classifications": ["CONTINUE", "REFINE", "SWITCH"],
        "sticky_user_entities": True,
        "sticky_constraints": True,
        "user_correction_overrides_conflict": True,
        "assistant_examples_are_lower_priority": True,
        "silent_target_substitution_forbidden": True,
        "drift_guard_before_tool_or_change": True,
        "reconfirm_known_target_on_ellipsis": False,
        "nearest_relevant_chain_only": True,
        "persist_context_to_repo_by_default": False,
        "broad_rescan_for_continuity": False,
    },
}

NOTES = r"""# Adaptive Codex Harness v6.7

v6.7 adds conversation-continuity protection on top of v6.6 semantic investigation.

## Problem addressed

Long or iterative coding/debugging conversations can drift when a follow-up omits a subject.
The agent may accidentally replace a previously established target with a convenient example.

Example of the failure class:

1. User establishes employee `9999999` and target category `TESTT`.
2. User asks whether switching the category changes attendance baseline times.
3. Agent silently substitutes an unrelated `A -> B` example.
4. The answer is locally plausible but no longer answers the active task.

## v6.7 behavior

- Follow-ups default to CONTINUE when compatible with the active user intent.
- User-established entities/constraints stay sticky across compatible turns.
- Parameter changes are REFINE: unchanged context is retained.
- Only a clear incompatible task is SWITCH.
- Assistant-created examples cannot silently replace the user's target.
- Before tools/edits/DB operations, a lightweight drift check verifies that named targets come from the active conversation chain.
- Known targets are not re-asked merely because the latest follow-up is elliptical.
- No repository file is used as conversational memory by default, avoiding stale state and extra token/file churn.

## Safety

v6.7 does not modify hooks or weaken v6.5/v6.6 DB/test/side-effect protections.
Start a new Codex session after installation so updated project instructions are loaded.
"""


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"\s*(\d+)\.(\d+)(?:\.(\d+))?\s*", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def find_root(script_dir: Path, target: str | None) -> Path:
    if target:
        p = Path(target).expanduser().resolve()
        if not p.exists():
            raise SystemExit(f"target does not exist: {p}")
        return p
    for p in (Path.cwd().resolve(), script_dir.resolve(), *script_dir.resolve().parents):
        if (p / ".codex/harness/VERSION").exists():
            return p
        if p.name == "tools" and (p.parent / ".codex/harness/VERSION").exists():
            return p.parent
    raise SystemExit("project root not found; run from project root or pass --target")


class Txn:
    def __init__(self, root: Path, dry_run: bool):
        self.root = root
        self.dry_run = dry_run
        self.original: dict[Path, bytes | None] = {}
        self.changed: list[Path] = []
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup = root / ".harness/backups" / f"v6.7-{stamp}"

    def remember(self, p: Path) -> None:
        if p not in self.original:
            self.original[p] = p.read_bytes() if p.exists() and p.is_file() else None

    def write(self, p: Path, text: str) -> None:
        self.remember(p)
        old = p.read_text(encoding="utf-8", errors="replace") if p.exists() and p.is_file() else None
        if old == text:
            return
        self.changed.append(p)
        if self.dry_run:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def backup_originals(self) -> None:
        if self.dry_run:
            return
        for p in set(self.changed):
            data = self.original.get(p)
            if data is None:
                continue
            dst = self.backup / p.relative_to(self.root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)

    def rollback(self) -> None:
        if self.dry_run:
            return
        for p in reversed(list(dict.fromkeys(self.changed))):
            data = self.original.get(p)
            if data is None:
                if p.exists():
                    p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)


def replace_block(text: str, begin: str, end: str, block: str) -> str:
    cleaned = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", text, flags=re.S).rstrip()
    return (cleaned + ("\n\n" if cleaned else "") + block.strip() + "\n")


def replace_eof_addendum(text: str, heading: str, addition: str) -> str:
    # Installer-owned addendum: if already present, replace from heading through EOF.
    pos = text.rfind("\n" + heading)
    if pos < 0 and text.startswith(heading):
        pos = 0
    if pos >= 0:
        prefix = text[:pos].rstrip()
        return prefix + ("\n\n" if prefix else "") + addition.strip() + "\n"
    return text.rstrip() + ("\n\n" if text.strip() else "") + addition.strip() + "\n"


def merged_policy(root: Path) -> dict[str, Any]:
    p = root / ".codex/harness/v6_6_policy.json"
    if not p.exists():
        raise RuntimeError("v6_6_policy.json is missing; apply v6.6 first")
    base = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(base, dict):
        raise RuntimeError("v6_6_policy.json must be an object")
    result = dict(base)
    result["version"] = VERSION
    result["schema_version"] = 7
    result["conversation_continuity"] = POLICY["conversation_continuity"]
    return result


def self_check(root: Path) -> list[str]:
    errors: list[str] = []
    if (root / ".codex/harness/VERSION").read_text().strip() != VERSION:
        errors.append("VERSION mismatch")

    agents = (root / "AGENTS.md").read_text(encoding="utf-8", errors="replace")
    required = [
        BLOCK_BEGIN,
        "No silent target substitution",
        "`CONTINUE`",
        "Do not ask the user to repeat or reconfirm a target already established",
        "Do not create or update repository files solely to store conversational state",
    ]
    for token in required:
        if token not in agents:
            errors.append(f"AGENTS.md missing: {token}")

    pol = json.loads((root / ".codex/harness/v6_7_policy.json").read_text(encoding="utf-8"))
    cc = pol.get("conversation_continuity", {})
    if cc.get("silent_target_substitution_forbidden") is not True:
        errors.append("target substitution guard missing")
    if cc.get("followup_default") != "continue_nearest_compatible_user_intent":
        errors.append("follow-up continuity default missing")
    if cc.get("persist_context_to_repo_by_default") is not False:
        errors.append("unexpected durable conversation state")

    # Verify prior semantic-investigation layer and safety substrate still exist.
    if not (root / ".codex/harness/v6_6_policy.json").exists():
        errors.append("v6.6 policy disappeared")
    for p in (
        root / ".codex/harness/scripts/test_db_guard.py",
        root / ".codex/harness/scripts/side_effect_guard.py",
        root / ".codex/harness/scripts/safe_test.py",
        root / ".codex/harness/hooks/pre_tool_safety.py",
        root / ".codex/hooks.json",
    ):
        if not p.exists():
            errors.append(f"safety substrate missing: {p.relative_to(root)}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6.6 -> v6.7 continuity updater")
    ap.add_argument("--target")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = find_root(Path(__file__).resolve().parent, args.target)
    vp = root / ".codex/harness/VERSION"
    if not vp.exists():
        raise SystemExit("Harness not installed")

    current_text = vp.read_text(encoding="utf-8", errors="replace").strip()
    current = parse_version(current_text)
    if current is None or current[0] != 6:
        raise SystemExit(f"unsupported Harness VERSION: {current_text!r}")
    if current[:2] < MIN_BASE:
        raise SystemExit(f"v6.7 requires v6.6 baseline; current VERSION is {current_text}")
    if current[:2] > (6, 7):
        raise SystemExit(f"refusing to downgrade newer VERSION {current_text}")

    print(f"Project root : {root}")
    print(f"Current      : {current_text}")
    print(f"Target       : {VERSION}")
    print(f"Mode         : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()
    print("v6.7 continuity rules:")
    print("  - compatible follow-ups inherit the active user intent")
    print("  - named targets/constraints remain sticky")
    print("  - assistant examples cannot silently replace user targets")
    print("  - CONTINUE / REFINE / SWITCH drift classification")
    print("  - lightweight pre-action target re-anchor")
    print("  - no repo-backed conversational state by default")
    print("  - v6.6 semantic investigation and safety hooks remain unchanged")
    print()

    tx = Txn(root, args.dry_run)
    try:
        policy = merged_policy(root)

        agents_p = root / "AGENTS.md"
        agents = agents_p.read_text(encoding="utf-8", errors="replace") if agents_p.exists() else ""
        tx.write(agents_p, replace_block(agents, BLOCK_BEGIN, BLOCK_END, CONTINUITY_BLOCK))

        for p, heading, addition in (
            (root / ".agents/skills/harness-develop/SKILL.md", "### v6.7 conversation continuity", DEVELOP_APPEND),
            (root / ".agents/skills/harness-debug/SKILL.md", "### v6.7 conversation continuity", DEBUG_APPEND),
        ):
            if p.exists():
                old = p.read_text(encoding="utf-8", errors="replace")
                tx.write(p, replace_eof_addendum(old, heading, addition))

        tx.write(root / ".codex/harness/v6_7_policy.json",
                 json.dumps(policy, ensure_ascii=False, indent=2) + "\n")
        tx.write(root / ".codex/harness/V6_7.md", NOTES)
        tx.write(vp, VERSION + "\n")

        if args.dry_run:
            print(f"[DRY-RUN] planned changed files: {len(set(tx.changed))}")
            for p in sorted(set(tx.changed)):
                print("  " + p.relative_to(root).as_posix())
            print("No files changed.")
            return 0

        errors = self_check(root)
        if errors:
            raise RuntimeError("; ".join(errors))
        tx.backup_originals()

    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        print("[ROLLBACK] restoring updater changes", file=sys.stderr)
        tx.rollback()
        return 1

    print(f"[OK] Adaptive Codex Harness {VERSION} applied")
    if tx.backup.exists():
        print(f"[OK] Backup: {tx.backup}")
    print("Start a new Codex session / reload project instructions.")
    print("Hook definitions were not changed; /hooks re-trust is normally unnecessary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
