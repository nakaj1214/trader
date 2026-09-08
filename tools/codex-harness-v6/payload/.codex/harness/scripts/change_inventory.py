#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess
from pathlib import Path
HERE=Path(__file__).resolve(); HARNESS=HERE.parent.parent; WORKSPACE=HERE.parents[3]

def load_cfg():
    try: return json.loads((HARNESS/"config.json").read_text(encoding="utf-8"))
    except Exception: return {}

def run(cwd, *args):
    return subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.strip()

def main():
    cfg=load_cfg(); roots=cfg.get("project_layout",{}).get("git_roots",[]) or ["."]
    for rel in roots:
        root=(WORKSPACE/rel).resolve()
        if not (root/".git").exists(): continue
        print(f"Git root: {root.relative_to(WORKSPACE) if root != WORKSPACE else '.'}")
        status=run(root,"git","status","--short").splitlines()
        stat=run(root,"git","diff","--stat").splitlines()
        num=run(root,"git","diff","--numstat").splitlines()
        print(f"Changed/untracked entries: {len(status)}")
        for line in status[:20]: print(f"  {line}")
        if len(status)>20: print(f"  ... +{len(status)-20} more")
        adds=dels=files=0
        for line in num:
            parts=line.split("\t")
            if len(parts)>=3:
                files += 1
                if parts[0].isdigit(): adds += int(parts[0])
                if parts[1].isdigit(): dels += int(parts[1])
        print(f"Tracked diff: {files} files, +{adds}/-{dels}")
        if stat:
            print("Diff stat tail:")
            for line in stat[-8:]: print(f"  {line}")
    return 0
if __name__=="__main__": raise SystemExit(main())
