#!/usr/bin/env python3
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
