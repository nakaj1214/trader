#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SELFTEST = SCRIPT_DIR / "selftest.py"


def main() -> int:
    print("Adaptive Codex Harness doctor -> v6 self-test\n")
    return subprocess.call([sys.executable, str(SELFTEST)])


if __name__ == "__main__":
    raise SystemExit(main())
