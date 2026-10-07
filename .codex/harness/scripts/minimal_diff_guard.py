#!/usr/bin/env python3
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
