#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WRITABLE_ROOT = ROOT / ".harness"
RUNTIME_ROOT = WRITABLE_ROOT / "runtime"
STATE_ROOT = WRITABLE_ROOT / "state"
CACHE_ROOT = WRITABLE_ROOT / "cache"
REPORTS_ROOT = WRITABLE_ROOT / "reports"
BACKUPS_ROOT = WRITABLE_ROOT / "backups"


def ensure_layout() -> None:
    for path in (WRITABLE_ROOT, RUNTIME_ROOT, STATE_ROOT, CACHE_ROOT, REPORTS_ROOT, BACKUPS_ROOT):
        path.mkdir(parents=True, exist_ok=True)
