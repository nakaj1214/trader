#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".codex/harness/scripts"


def main() -> int:
    agents = ROOT / "AGENTS.md"
    skills = list((ROOT / ".agents/skills").glob("*/SKILL.md")) if (ROOT / ".agents/skills").exists() else []
    rules = list((ROOT / ".codex/rules").glob("*.rules")) if (ROOT / ".codex/rules").exists() else []
    print("Harness audit (manual, no application tests)")
    print(f"AGENTS.md: {len(agents.read_text(encoding='utf-8', errors='replace').splitlines()) if agents.exists() else 0} lines")
    print(f"Skills   : {len(skills)}")
    print(f"Rules    : {len(rules)}")
    rc = subprocess.call([sys.executable, str(SCRIPTS / "selftest.py"), "--quiet"])
    print(f"Self-test: {'PASS' if rc == 0 else 'FAIL'}")
    print("Use telemetry_report.py separately when you want execution-shape metrics.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
