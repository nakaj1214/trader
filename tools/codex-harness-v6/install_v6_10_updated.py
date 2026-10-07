#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

VERSION = "6.10.0"

MANAGED_BEGIN = "<!-- adaptive-codex-harness-v6.10:begin -->"
MANAGED_END = "<!-- adaptive-codex-harness-v6.10:end -->"

AGENTS_BLOCK = f"""{MANAGED_BEGIN}
## Adaptive Codex Harness v6.10 — minimal-diff editing + concise explanations

### Existing-file editing
- Existing files must be edited with the smallest coherent diff. Preserve unchanged lines and blocks instead of deleting and regenerating them.
- Prefer `apply_patch` / targeted Edit operations for existing tracked files.
- Do not use whole-file `Write`, delete-and-recreate, `cat > file`, `tee file`, `Path.write_text()`-style regeneration, or equivalent replacement merely because rewriting is easier.
- A one-line change should normally produce a one-line-scale diff. A section change should normally touch only that section.
- Full-file replacement is allowed only when the task itself explicitly requires a full rewrite, the file is generated/lock/output content, or preserving the old structure is not meaningful.
- Before expensive/final verification, run `python3 .codex/harness/scripts/minimal_diff_guard.py`.
- If the guard reports rewrite-like churn, reduce the edit to the required lines/blocks. Do not self-allowlist a file to make an agent edit pass.

### User-facing bug / behavior explanations
- Explain the cause in the shortest form that still lets the user understand it.
- Avoid abstract-only wording. Include only the concrete code value or boundary needed to understand the cause.
- Prefer 1–3 short sentences. Do not mechanically list every input, branch, calculation, expected result, and impact when some are obvious.
- For calculations, show only the key comparison or interval. Example: `現行コードは05:00を残業開始として扱うため、定時07:00・退勤08:00でも05:00〜08:00を3時間残業としてしまう。本来は07:00〜08:00の1時間。`
- Add another calculation only when it explains a separate symptom. Example: `深夜残業も05:00 - 07:00 = -2時間になる。`
- Do not repeat the same fact in different wording or add implementation detail that is not needed for the user's decision.

### Guard ownership
- Do not weaken, bypass, edit, or allowlist `.codex/harness/scripts/minimal_diff_guard.py`, `.codex/harness/hooks/minimal_edit_pretool.py`, or `.codex/harness/minimal_edit_policy.json` merely to pass a task. Harness guard changes are installer/maintainer work.
{MANAGED_END}
"""

SKILL_BLOCK = f"""{MANAGED_BEGIN}
### v6.10 minimal edits / explanation clarity
- Preserve unchanged existing content; use targeted patches instead of whole-file regeneration.
- Run `python3 .codex/harness/scripts/minimal_diff_guard.py` before expensive/final verification.
- Explain bugs briefly: normally 1–3 sentences.
- Include only the concrete code value/boundary or calculation needed to understand the cause.
- Do not mechanically enumerate every internal step or repeat the same fact in multiple forms.
{MANAGED_END}
"""

POLICY: dict[str, Any] = {
    "schema_version": 1,
    "version": VERSION,
    "existing_file_editing": {
        "default": "minimal_diff",
        "prefer": ["apply_patch", "targeted_edit"],
        "whole_file_rewrite": "disallowed_by_default",
    },
    "explanation": {
        "style": "concise_and_concrete",
        "target_sentences": "1_to_3",
        "concrete_code_value_or_boundary_when_material": True,
        "show_only_key_calculation": True,
        "avoid_mechanical_step_listing": True,
        "avoid_repetition": True,
        "extra_detail_only_when_needed_for_understanding_or_decision": True,
    },
    "guard": {
        "min_original_lines": 40,
        "min_deleted_lines": 30,
        "min_added_lines": 15,
        "major_delete_ratio": 0.60,
        "rewrite_churn_ratio": 0.90,
        "low_similarity_ratio": 0.55,
        "mode": "fail",
        "task_scope_aware": True,
        "allowlist_globs": [
            "*.lock",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "composer.lock",
            "*.min.js",
            "*.min.css",
            "*.map",
            "dist/**",
            "build/**",
            "coverage/**",
            ".harness/**",
        ],
    },
}

MINIMAL_DIFF_GUARD = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / ".codex" / "harness" / "minimal_edit_policy.json"
TASK_SCOPE = ROOT / ".harness" / "runtime" / "task_scope" / "current.json"

DEFAULT = {
    "min_original_lines": 40,
    "min_deleted_lines": 30,
    "min_added_lines": 15,
    "major_delete_ratio": 0.60,
    "rewrite_churn_ratio": 0.90,
    "low_similarity_ratio": 0.55,
    "mode": "fail",
    "task_scope_aware": True,
    "allowlist_globs": [
        "*.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "composer.lock",
        "*.min.js", "*.min.css", "*.map", "dist/**", "build/**", "coverage/**", ".harness/**",
    ],
}

TEXT_SUFFIXES = {
    ".php", ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".md", ".txt",
    ".json", ".toml", ".yaml", ".yml", ".xml", ".ini", ".conf", ".css",
    ".scss", ".html", ".htm", ".sql", ".sh", ".bash", ".zsh", ".rules",
}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def load_policy() -> dict[str, Any]:
    cfg = dict(DEFAULT)
    try:
        raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        guard = raw.get("guard", raw)
        if isinstance(guard, dict):
            for key in DEFAULT:
                if key in guard:
                    cfg[key] = guard[key]
    except (OSError, ValueError, TypeError):
        pass
    return cfg


def norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def matches_any(path: str, patterns: list[str]) -> bool:
    p = norm(path)
    return any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(Path(p).name, pat) for pat in patterns)


def digest(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return "<missing>"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return "<unreadable>"


def git_ok() -> bool:
    cp = run("git", "rev-parse", "--is-inside-work-tree")
    return cp.returncode == 0 and cp.stdout.strip() == "true"


def status_paths() -> set[str]:
    cp = run("git", "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if cp.returncode != 0:
        return set()
    chunks = cp.stdout.split("\0")
    out: set[str] = set()
    i = 0
    while i < len(chunks):
        item = chunks[i]
        if not item:
            i += 1
            continue
        if len(item) >= 4:
            code, path = item[:2], item[3:]
            out.add(norm(path))
            if (code.startswith("R") or code.startswith("C")) and i + 1 < len(chunks) and chunks[i + 1]:
                out.add(norm(chunks[i + 1]))
                i += 1
        i += 1
    return out


def baseline_dirty() -> dict[str, str]:
    if not TASK_SCOPE.exists():
        return {}
    try:
        data = json.loads(TASK_SCOPE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    roots = data.get("roots", {})
    if not isinstance(roots, dict):
        return {}
    entry = roots.get(".")
    if not isinstance(entry, dict):
        entry = next((v for v in roots.values() if isinstance(v, dict)), {})
    dirty = entry.get("dirty", {}) if isinstance(entry, dict) else {}
    return {norm(k): str(v) for k, v in dirty.items()} if isinstance(dirty, dict) else {}


def task_touched_candidates(cfg: dict[str, Any]) -> set[str]:
    now = status_paths()
    if not cfg.get("task_scope_aware", True):
        return now
    base = baseline_dirty()
    if not base:
        return now
    touched: set[str] = set()
    for p in now | set(base):
        current = digest(ROOT / p) if p in now else "<clean>"
        before = base.get(p, "<clean>")
        if current != before:
            touched.add(p)
    return touched


def is_tracked_at_head(path: str) -> bool:
    return run("git", "cat-file", "-e", f"HEAD:{path}").returncode == 0


def read_head_lines(path: str) -> list[str] | None:
    cp = run("git", "show", f"HEAD:{path}")
    return cp.stdout.splitlines() if cp.returncode == 0 else None


def read_worktree_lines(path: str) -> list[str] | None:
    p = ROOT / path
    if not p.exists() or not p.is_file():
        return None
    try:
        raw = p.read_bytes()
        if b"\x00" in raw[:8192]:
            return None
        return raw.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None


def is_text_candidate(path: str) -> bool:
    low = path.lower()
    p = Path(low)
    if p.name in {"dockerfile", "makefile", "agents.md"} or low.endswith(".blade.php"):
        return True
    return p.suffix in TEXT_SUFFIXES or not p.suffix


def numstat(path: str) -> tuple[int, int] | None:
    cp = run("git", "diff", "HEAD", "--numstat", "--", path)
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    first = cp.stdout.splitlines()[0].split("\t")
    if len(first) < 2 or first[0] == "-" or first[1] == "-":
        return None
    try:
        return int(first[0]), int(first[1])
    except ValueError:
        return None


def suspicious(path: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    if matches_any(path, list(cfg.get("allowlist_globs", []))):
        return None
    if not is_text_candidate(path) or not is_tracked_at_head(path):
        return None

    old = read_head_lines(path)
    new = read_worktree_lines(path)
    if old is None or new is None:
        return None
    original = len(old)
    if original < int(cfg["min_original_lines"]):
        return None

    ns = numstat(path)
    if ns is None:
        return None
    added, deleted = ns
    if deleted < int(cfg["min_deleted_lines"]) or added < int(cfg["min_added_lines"]):
        return None

    delete_ratio = deleted / max(original, 1)
    churn_ratio = (added + deleted) / max(original, 1)
    similarity = difflib.SequenceMatcher(a=old, b=new, autojunk=False).ratio()

    major_replacement = delete_ratio >= float(cfg["major_delete_ratio"])
    low_similarity_churn = (
        churn_ratio >= float(cfg["rewrite_churn_ratio"])
        and similarity <= float(cfg["low_similarity_ratio"])
    )
    if not (major_replacement or low_similarity_churn):
        return None

    return {
        "path": path,
        "original_lines": original,
        "current_lines": len(new),
        "added": added,
        "deleted": deleted,
        "delete_ratio": delete_ratio,
        "churn_ratio": churn_ratio,
        "similarity": similarity,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect rewrite-like churn in existing tracked text files")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--warn-only", action="store_true")
    ap.add_argument("--path", action="append", default=[])
    args = ap.parse_args()

    if not git_ok():
        if not args.quiet:
            print("[minimal-diff] not a Git worktree; skipped")
        return 0

    cfg = load_policy()
    paths = {norm(p) for p in args.path} if args.path else task_touched_candidates(cfg)
    findings = [f for p in sorted(paths) if (f := suspicious(p, cfg)) is not None]

    if args.json:
        print(json.dumps({"checked_paths": len(paths), "findings": findings}, ensure_ascii=False, indent=2))
    elif findings:
        print("[minimal-diff:BLOCK] rewrite-like existing-file edits detected", file=sys.stderr)
        for f in findings:
            print(
                "  - {path}: +{added} -{deleted}, original={original_lines}, "
                "delete={delete_ratio:.0%}, similarity={similarity:.0%}".format(**f),
                file=sys.stderr,
            )
        print(
            "Re-edit only the required lines/blocks. Do not self-allowlist the file. "
            "A deliberate full rewrite needs a maintainer/user allowlist decision.",
            file=sys.stderr,
        )
    elif not args.quiet:
        print(f"[minimal-diff:PASS] checked {len(paths)} changed path(s)")

    if findings and not args.warn_only and str(cfg.get("mode", "fail")).lower() == "fail":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

MINIMAL_EDIT_PRETOOL = r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

MIN_EXISTING_LINES = 40
PROTECTED = (
    ".codex/harness/scripts/minimal_diff_guard.py",
    ".codex/harness/hooks/minimal_edit_pretool.py",
    ".codex/harness/minimal_edit_policy.json",
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


def git_root(cwd: Path) -> Path | None:
    cp = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return Path(cp.stdout.strip()).resolve() if cp.returncode == 0 else None


def all_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            out.extend(all_strings(value))
    elif isinstance(obj, list):
        for value in obj:
            out.extend(all_strings(value))
    return out


def extract_path(tool_input: dict[str, Any]) -> str | None:
    for key in ("file_path", "path", "filename", "file"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve(root: Path, raw: str) -> Path:
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def tracked(root: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    cp = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{rel}"], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return cp.returncode == 0


def line_count(path: Path) -> int:
    try:
        raw = path.read_bytes()
        if b"\x00" in raw[:8192]:
            return 0
        return len(raw.decode("utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def patch_text(tool_input: dict[str, Any]) -> str:
    joined = "\n".join(all_strings(tool_input))
    return joined if ("*** Update File:" in joined or "@@" in joined) else ""


def rewrite_like_patch(text: str, root: Path) -> str | None:
    blocks = re.split(r"(?=^\*\*\* Update File: )", text, flags=re.M)
    for block in blocks:
        m = re.match(r"^\*\*\* Update File:\s*(.+?)\s*$", block, flags=re.M)
        if not m:
            continue
        raw = m.group(1).strip()
        path = resolve(root, raw)
        if not path.exists() or not tracked(root, path):
            continue
        original = line_count(path)
        if original < MIN_EXISTING_LINES:
            continue
        deleted = sum(1 for line in block.splitlines() if line.startswith("-") and not line.startswith("---"))
        added = sum(1 for line in block.splitlines() if line.startswith("+") and not line.startswith("+++"))
        if deleted >= max(30, int(original * 0.60)) and added >= 15:
            return (
                f"{raw}: patch removes {deleted}/{original} existing lines and adds {added}. "
                "Preserve unchanged content and patch only the required lines/blocks."
            )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    joined = "\n".join(all_strings(tool_input)).lower()
    if tool_name in {"Write", "Edit", "apply_patch"} and any(p.lower() in joined for p in PROTECTED):
        return deny(
            "Adaptive Harness v6.10 blocked editing the minimal-diff guard/policy. "
            "Update guard infrastructure through the installer/maintainer path."
        )

    root = git_root(Path(payload.get("cwd") or Path.cwd()).resolve())
    if root is None:
        return 0

    if tool_name == "Write":
        raw = extract_path(tool_input)
        if raw:
            path = resolve(root, raw)
            if path.exists() and tracked(root, path):
                lines = line_count(path)
                if lines >= MIN_EXISTING_LINES:
                    return deny(
                        f"Adaptive Harness v6.10 blocked whole-file Write for existing tracked file "
                        f"{raw} ({lines} lines). Use Edit/apply_patch and modify only the necessary lines/blocks."
                    )
        return 0

    if tool_name == "apply_patch":
        text = patch_text(tool_input)
        if text:
            reason = rewrite_like_patch(text, root)
            if reason:
                return deny("Adaptive Harness v6.10 blocked rewrite-like apply_patch. " + reason)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

VERIFY_BLOCK = r'''# adaptive-codex-harness-v6.10-minimal-diff-preflight:begin
def _adaptive_harness_v610_minimal_diff_preflight() -> None:
    import subprocess as _subprocess
    import sys as _sys
    from pathlib import Path as _Path

    _root = _Path(__file__).resolve().parents[3]
    _guard = _root / ".codex" / "harness" / "scripts" / "minimal_diff_guard.py"
    if _guard.exists():
        _cp = _subprocess.run([_sys.executable, str(_guard), "--quiet"], cwd=_root)
        if _cp.returncode != 0:
            raise SystemExit(
                "Harness minimal-diff preflight failed; reduce rewrite-like edits before formal verification."
            )
_adaptive_harness_v610_minimal_diff_preflight()
# adaptive-codex-harness-v6.10-minimal-diff-preflight:end
'''


def find_project_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"Project root does not exist: {root}")
        return root

    candidates: list[Path] = []
    for start in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        candidates.extend([start, *start.parents])
    seen: set[Path] = set()
    for root in candidates:
        if root in seen:
            continue
        seen.add(root)
        if (root / ".codex" / "harness").is_dir():
            return root
    raise SystemExit("Harness project root not found. Run inside the project or use --target.")


def read_version(root: Path) -> str:
    path = root / ".codex" / "harness" / "VERSION"
    if not path.exists():
        raise SystemExit(".codex/harness/VERSION is missing; this updater requires an existing v6.x Harness.")
    return path.read_text(encoding="utf-8", errors="replace").strip()


def replace_managed_block(text: str, block: str) -> str:
    rx = re.compile(re.escape(MANAGED_BEGIN) + r".*?" + re.escape(MANAGED_END) + r"\n?", re.S)
    cleaned = rx.sub("", text).rstrip()
    return (cleaned + "\n\n" if cleaned else "") + block.rstrip() + "\n"


def inject_verify_block(text: str) -> str:
    begin = "# adaptive-codex-harness-v6.10-minimal-diff-preflight:begin"
    end = "# adaptive-codex-harness-v6.10-minimal-diff-preflight:end"
    text = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", text, flags=re.S)
    m = re.search(r"^from __future__ import annotations[ \\t]*$", text, flags=re.M)
    if m:
        pos = m.end()
        return text[:pos] + "\n\n" + VERIFY_BLOCK.rstrip() + "\n" + text[pos:].lstrip("\n")
    first_nl = text.find("\n")
    pos = first_nl + 1 if text.startswith("#!") and first_nl >= 0 else 0
    return text[:pos] + VERIFY_BLOCK.rstrip() + "\n" + text[pos:]


class Txn:
    def __init__(self, root: Path, dry_run: bool) -> None:
        self.root = root
        self.dry_run = dry_run
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup_root = root / ".harness" / "backups" / f"v6.10-{stamp}"
        self.originals: dict[Path, bytes | None] = {}
        self.modes: dict[Path, int | None] = {}
        self.changed: list[Path] = []

    def remember(self, path: Path) -> None:
        if path in self.originals:
            return
        if path.exists() and path.is_file():
            self.originals[path] = path.read_bytes()
            self.modes[path] = stat.S_IMODE(path.stat().st_mode)
        else:
            self.originals[path] = None
            self.modes[path] = None

    def backup(self, path: Path) -> None:
        if self.dry_run or not path.exists() or not path.is_file():
            return
        rel = path.relative_to(self.root)
        dst = self.backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)

    def write_text(self, path: Path, text: str, mode: int | None = None) -> bool:
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        if old == text:
            return False
        self.remember(path)
        self.changed.append(path)
        print(f"[{'DRY' if self.dry_run else 'WRITE'}] {path.relative_to(self.root)}")
        if self.dry_run:
            return True
        self.backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if mode is not None:
            path.chmod(mode)
        return True

    def write_json(self, path: Path, obj: Any) -> bool:
        return self.write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

    def rollback(self) -> None:
        if self.dry_run:
            return
        for path, data in reversed(list(self.originals.items())):
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
                print(f"[ROLLBACK WARN] {path}: {exc}", file=sys.stderr)


def patch_agents(root: Path, txn: Txn) -> None:
    path = root / "AGENTS.md"
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    txn.write_text(path, replace_managed_block(old, AGENTS_BLOCK))


def patch_skills(root: Path, txn: Txn) -> int:
    changed = 0
    for name in ("harness-develop", "harness-review", "harness-verify", "harness-debug"):
        path = root / ".agents" / "skills" / name / "SKILL.md"
        if not path.exists():
            continue
        old = path.read_text(encoding="utf-8", errors="replace")
        if txn.write_text(path, replace_managed_block(old, SKILL_BLOCK)):
            changed += 1
    return changed


def merge_hooks(root: Path, txn: Txn) -> None:
    path = root / ".codex" / "hooks.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"hooks": {}}
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError(".codex/hooks.json hooks must be an object")
    pre = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre, list):
        raise RuntimeError("hooks.PreToolUse must be an array")

    cleaned = []
    for entry in pre:
        if not isinstance(entry, dict):
            cleaned.append(entry)
            continue
        hs = entry.get("hooks")
        if isinstance(hs, list) and any(
            isinstance(h, dict) and "minimal_edit_pretool.py" in str(h.get("command", ""))
            for h in hs
        ):
            continue
        cleaned.append(entry)

    hook_path = root / ".codex" / "harness" / "hooks" / "minimal_edit_pretool.py"
    cleaned.append({
        "matcher": "^(Write|apply_patch|Edit)$",
        "hooks": [{
            "type": "command",
            "command": f"python3 {shlex.quote(str(hook_path))}",
            "timeout": 3,
            "statusMessage": "Checking minimal-diff edit policy",
        }],
    })
    hooks["PreToolUse"] = cleaned
    data["hooks"] = hooks
    txn.write_json(path, data)


def patch_verify(root: Path, txn: Txn) -> None:
    path = root / ".codex" / "harness" / "scripts" / "verify.py"
    if not path.exists():
        print("[INFO] verify.py not found; standalone minimal_diff_guard.py will still be installed")
        return
    old = path.read_text(encoding="utf-8", errors="replace")
    txn.write_text(path, inject_verify_block(old))


def write_files(root: Path, txn: Txn) -> None:
    txn.write_json(root / ".codex" / "harness" / "minimal_edit_policy.json", POLICY)
    txn.write_text(root / ".codex" / "harness" / "scripts" / "minimal_diff_guard.py", MINIMAL_DIFF_GUARD, 0o755)
    txn.write_text(root / ".codex" / "harness" / "hooks" / "minimal_edit_pretool.py", MINIMAL_EDIT_PRETOOL, 0o755)
    notes = """# Adaptive Codex Harness v6.10

Adds minimal-diff editing protection and concise, concrete bug explanation rules.

Manual guard:
```bash
python3 .codex/harness/scripts/minimal_diff_guard.py
```

Explanation example:
`現行コードは05:00を残業開始として扱うため、定時07:00・退勤08:00でも05:00〜08:00を3時間残業としてしまう。本来は07:00〜08:00の1時間。`

Only add another value/calculation when it explains a separate symptom.

After installing or changing `.codex/hooks.json`, restart Codex and review/trust project hooks if required.
"""
    txn.write_text(root / ".codex" / "harness" / "V6_10.md", notes)
    txn.write_text(root / ".codex" / "harness" / "VERSION", VERSION + "\n")


def self_check(root: Path) -> list[str]:
    problems: list[str] = []
    version = root / ".codex" / "harness" / "VERSION"
    if not version.exists() or version.read_text(encoding="utf-8", errors="replace").strip() != VERSION:
        problems.append(f"VERSION is not {VERSION}")

    for rel in (
        ".codex/harness/scripts/minimal_diff_guard.py",
        ".codex/harness/hooks/minimal_edit_pretool.py",
    ):
        path = root / rel
        if not path.exists():
            problems.append(f"missing {rel}")
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            problems.append(f"syntax error {rel}: {exc}")

    try:
        json.loads((root / ".codex" / "harness" / "minimal_edit_policy.json").read_text(encoding="utf-8"))
    except Exception as exc:
        problems.append(f"invalid minimal_edit_policy.json: {exc}")

    agents = root / "AGENTS.md"
    if not agents.exists() or "concise explanations" not in agents.read_text(encoding="utf-8", errors="replace"):
        problems.append("AGENTS.md v6.10 policy not installed")

    hooks = root / ".codex" / "hooks.json"
    try:
        raw = json.dumps(json.loads(hooks.read_text(encoding="utf-8")))
        if "minimal_edit_pretool.py" not in raw:
            problems.append("minimal-edit PreToolUse hook not installed")
    except Exception as exc:
        problems.append(f"invalid/missing .codex/hooks.json: {exc}")

    verify = root / ".codex" / "harness" / "scripts" / "verify.py"
    if verify.exists():
        text = verify.read_text(encoding="utf-8", errors="replace")
        if "adaptive-codex-harness-v6.10-minimal-diff-preflight:begin" not in text:
            problems.append("verify.py minimal-diff preflight not installed")
        try:
            ast.parse(text)
        except SyntaxError as exc:
            problems.append(f"verify.py syntax error: {exc}")

    guard = root / ".codex" / "harness" / "scripts" / "minimal_diff_guard.py"
    if guard.exists():
        cp = subprocess.run(
            [sys.executable, str(guard), "--json", "--warn-only"], cwd=root,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if cp.returncode != 0:
            problems.append(f"minimal_diff_guard.py execution failed: {cp.stderr.strip() or cp.stdout.strip()}")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6.x -> v6.10 updater")
    ap.add_argument("--target", help="Project root. Omit when running inside the project.")
    ap.add_argument("--dry-run", action="store_true", help="Show planned changes without writing files.")
    args = ap.parse_args()

    root = find_project_root(args.target)
    current = read_version(root)
    if not current.startswith("6."):
        raise SystemExit(f"Unsupported Harness VERSION: {current!r}; expected v6.x")

    print(f"Project root : {root}")
    print(f"Current      : {current}")
    print(f"Target       : {VERSION}")
    print(f"Mode         : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()
    print("v6.10 changes:")
    print("  - minimal-diff policy for existing files")
    print("  - PreToolUse guard for whole-file Write / rewrite-like apply_patch")
    print("  - Git-diff rewrite detector before verification")
    print("  - concise 1–3 sentence bug explanations with only necessary code values")
    print("  - existing hooks and prior v6.x safety files preserved")
    print()

    txn = Txn(root, args.dry_run)
    try:
        patch_agents(root, txn)
        print(f"[POLICY] relevant skill files updated: {patch_skills(root, txn)}")
        write_files(root, txn)
        merge_hooks(root, txn)
        patch_verify(root, txn)

        if args.dry_run:
            print(f"\nDRY-RUN complete: {len(txn.changed)} file(s) would change.")
            return 0

        problems = self_check(root)
        if problems:
            raise RuntimeError("Self-check failed:\n  - " + "\n  - ".join(problems))

        print(f"\nInstalled Adaptive Codex Harness {VERSION} delta.")
        print(f"Changed files: {len(txn.changed)}")
        print(f"Backup root : {txn.backup_root}")
        print("Restart Codex so the merged PreToolUse hook is reloaded/trusted.")
        return 0
    except Exception as exc:
        if not args.dry_run:
            print(f"[ERROR] {exc}", file=sys.stderr)
            print("[ROLLBACK] restoring installer-touched files", file=sys.stderr)
            txn.rollback()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
