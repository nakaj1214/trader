#!/usr/bin/env python3
from __future__ import annotations
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve()
WORKSPACE = HERE.parents[3]
CANDIDATES = [WORKSPACE / "src" / "tests", WORKSPACE / "tests"]

def git_changed() -> set[str]:
    for cwd in (WORKSPACE / "src", WORKSPACE):
        if (cwd / ".git").exists():
            cp = subprocess.run(["git", "status", "--short"], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            out=set()
            for line in cp.stdout.splitlines():
                if len(line)>=4:
                    out.add(line[3:].strip().split(" -> ")[-1])
            return out
    return set()

def main() -> int:
    root = next((p for p in CANDIDATES if p.is_dir()), None)
    if not root:
        print("Tests: no tests directory detected")
        return 0
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".php", ".py", ".js", ".ts", ".tsx"}]
    rows=[]
    total=0
    for p in files:
        try: n=sum(1 for _ in p.open("r", encoding="utf-8", errors="ignore"))
        except OSError: continue
        total += n; rows.append((n,p))
    changed=git_changed()
    print(f"Tests: {len(rows)} files / {total} lines")
    changed_tests=[]
    for _,p in rows:
        rel_ws=p.relative_to(WORKSPACE).as_posix()
        rel_src=p.relative_to(WORKSPACE/"src").as_posix() if (WORKSPACE/"src") in p.parents else rel_ws
        if rel_ws in changed or rel_src in changed:
            changed_tests.append(rel_ws)
    print(f"Changed test files: {len(changed_tests)}")
    for rel in sorted(changed_tests)[:12]: print(f"  {rel}")
    if len(changed_tests)>12: print(f"  ... +{len(changed_tests)-12} more")
    print("Largest:")
    for n,p in sorted(rows, reverse=True)[:5]: print(f"  {n:5d}  {p.relative_to(WORKSPACE).as_posix()}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
