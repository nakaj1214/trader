#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

REQUIRED_ENV = {
    "APP_ENV": "testing",
    "MAIL_MAILER": "array",
    "MAIL_HOST": "127.0.0.1",
    "MAIL_PORT": "1",
    "QUEUE_CONNECTION": "sync",
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "FILESYSTEM_DISK": "local",
    "BROADCAST_CONNECTION": "log",
    "BROADCAST_DRIVER": "log",
    "CUPS_SERVER": "127.0.0.1:1",
    "HTTP_PROXY": "http://127.0.0.1:1",
    "HTTPS_PROXY": "http://127.0.0.1:1",
    "ALL_PROXY": "http://127.0.0.1:1",
    "NO_PROXY": "",
    "AWS_ACCESS_KEY_ID": "__harness_test_blocked__",
    "AWS_SECRET_ACCESS_KEY": "__harness_test_blocked__",
    "AWS_SESSION_TOKEN": "__harness_test_blocked__",
    "AWS_EC2_METADATA_DISABLED": "true",
    "REDIS_HOST": "127.0.0.1",
    "REDIS_PORT": "1",
    "MEMCACHED_HOST": "127.0.0.1",
    "MEMCACHED_PORT": "1",
}

TRAIT_REQUIRED = (
    "database.connections",
    "DB::purge",
    ":memory:",
    "Http::preventStrayRequests",
    "Mail::fake",
    "Notification::fake",
    "Queue::fake",
    "Bus::fake",
    "Storage::fake",
    "useStoragePath",
    "preventStrayProcesses",
    "Intentionally do NOT call Event::fake",
)

LOW_LEVEL_TEST_SIDE_EFFECTS = (
    ("native filesystem deletion", re.compile(r"\b(?:unlink|rmdir)\s*\(", re.I)),
    ("native filesystem write/move", re.compile(r"\b(?:file_put_contents|touch|rename|copy|move_uploaded_file|mkdir)\s*\(", re.I)),
    ("native fopen write mode", re.compile(r"\bfopen\s*\([^,]+,\s*['\"](?:w|a|x|c)[+bte]*['\"]", re.I)),
    ("Illuminate File mutation", re.compile(r"\bFile::(?:delete|deleteDirectory|cleanDirectory|put|append|prepend|move|copy|makeDirectory|moveDirectory|copyDirectory)\s*\(", re.I)),
    ("dynamic Laravel storage construction", re.compile(r"\bStorage::build\s*\(", re.I)),
    ("raw process execution", re.compile(r"\b(?:shell_exec|exec|system|passthru|proc_open|popen)\s*\(", re.I)),
    ("raw curl execution", re.compile(r"\bcurl_(?:exec|multi_exec)\s*\(", re.I)),
    ("raw socket connection", re.compile(r"\b(?:fsockopen|pfsockopen|stream_socket_client)\s*\(", re.I)),
)

SAFE_PATH_HINTS = (
    "sys_get_temp_dir", "tempnam(", "storage_path(", "Storage::fake", "fake(",
)
ALLOW_MARKER = "@harness-side-effect-allow"

WEAKENING_PATTERNS = (
    re.compile(r"Http::allowStrayRequests\s*\(", re.I),
    re.compile(r"Process::allowStrayProcesses\s*\(", re.I),
)

def laravel_root() -> Path | None:
    for p in (ROOT, ROOT / "src"):
        if (p / "artisan").is_file() and (p / "composer.json").is_file():
            return p
    return None

def phpunit_file(app: Path) -> Path | None:
    for name in ("phpunit.xml", "phpunit.xml.dist"):
        p = app / name
        if p.exists():
            return p
    return None

def env_map(xml_path: Path) -> dict[str, dict[str, str]]:
    tree = ET.parse(xml_path)
    out: dict[str, dict[str, str]] = {}
    for elem in tree.getroot().iter("env"):
        name = elem.attrib.get("name")
        if name:
            out[name] = dict(elem.attrib)
    return out

def scan_low_level_tests(app: Path) -> list[str]:
    problems: list[str] = []
    test_root = app / "tests"
    if not test_root.exists():
        return problems
    for path in test_root.rglob("*.php"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if ALLOW_MARKER in text:
            continue
        rel = path.relative_to(app).as_posix()
        if rel.lower() == "tests/concerns/harnesssideeffectisolation.php":
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(rx.search(line) for rx in WEAKENING_PATTERNS):
                problems.append(f"{rel}:{line_no}: side-effect isolation weakening call")
                continue
            for label, rx in LOW_LEVEL_TEST_SIDE_EFFECTS:
                if not rx.search(line):
                    continue
                if any(hint.lower() in line.lower() for hint in SAFE_PATH_HINTS):
                    continue
                problems.append(f"{rel}:{line_no}: {label} bypasses Laravel fakes")
    return problems

def audit(verbose: bool = True) -> int:
    app = laravel_root()
    if app is None:
        if verbose:
            print("[SIDE-EFFECT-GUARD] non-Laravel project: no Laravel side-effect preflight required")
        return 0

    problems: list[str] = []
    xml = phpunit_file(app)
    if xml is None:
        problems.append("phpunit.xml/phpunit.xml.dist がないためtesting副作用隔離を証明できない")
    else:
        try:
            envs = env_map(xml)
        except Exception as exc:
            problems.append(f"{xml.name} parse error: {exc}")
            envs = {}
        for name, value in REQUIRED_ENV.items():
            item = envs.get(name)
            if item is None:
                problems.append(f"{name} が未定義")
                continue
            if item.get("value", "") != value:
                problems.append(f"{name}={item.get('value')!r} (required {value!r})")
            if item.get("force", "").lower() != "true":
                problems.append(f"{name} に force=\"true\" がない")

    testcase = app / "tests" / "TestCase.php"
    trait = app / "tests" / "Concerns" / "HarnessSideEffectIsolation.php"
    if not testcase.exists():
        problems.append("tests/TestCase.php がない")
    else:
        t = testcase.read_text(encoding="utf-8", errors="replace")
        if "HarnessSideEffectIsolation" not in t or "harnessEnableSideEffectIsolation();" not in t:
            problems.append("tests/TestCase.php に HarnessSideEffectIsolation が組み込まれていない")
    if not trait.exists():
        problems.append("tests/Concerns/HarnessSideEffectIsolation.php がない")
    else:
        tt = trait.read_text(encoding="utf-8", errors="replace")
        for marker in TRAIT_REQUIRED:
            if marker not in tt:
                problems.append(f"HarnessSideEffectIsolation trait missing: {marker}")

    problems.extend(scan_low_level_tests(app))

    if problems:
        print("[SIDE-EFFECT-GUARD:BLOCK] テストの実環境副作用隔離を証明できません。", file=sys.stderr)
        for p in problems[:40]:
            print(f"  - {p}", file=sys.stderr)
        if len(problems) > 40:
            print(f"  - ... and {len(problems) - 40} more", file=sys.stderr)
        print("ガードを弱めず、fake / temp storage / mock へ置き換えてください。", file=sys.stderr)
        return 2

    if verbose:
        print("[SIDE-EFFECT-GUARD:PASS] HTTP/mail/notification/queue/storage/process isolation is installed")
        print("[SIDE-EFFECT-GUARD] Laravel events stay active; downstream side effects remain isolated")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Laravel test side-effect isolation audit")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    return audit(not args.quiet)

if __name__ == "__main__":
    raise SystemExit(main())
