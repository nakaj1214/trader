#!/usr/bin/env python3
from __future__ import annotations
import argparse, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

REQUIRED = {
    "APP_ENV": "testing",
    "DB_CONNECTION": "sqlite",
    "DB_DATABASE": ":memory:",
    # Standard Laravel MySQL fallback is deliberately made unreachable during tests.
    # This protects explicit DB::connection('mysql') calls even if application code uses them.
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "1",
    "DB_USERNAME": "__harness_test_blocked__",
    "DB_PASSWORD": "__harness_test_blocked__",
    "DB_URL": "",
}

DESTRUCTIVE_TEST_PATTERNS = (
    re.compile(r"Schema::\s*(?:connection\([^)]*\)\s*->\s*)?drop(?:IfExists)?\s*\(", re.I),
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I),
    re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?", re.I),
    re.compile(r"artisan\s+(?:migrate:fresh|migrate:refresh|migrate:reset|db:wipe)", re.I),
)

ABSOLUTE_DANGER_PATTERNS = (
    re.compile(r"\bDROP\s+DATABASE\b", re.I),
    re.compile(r"DB::(?:statement|unprepared)\s*\(\s*['\"]\s*DROP\s+DATABASE", re.I),
)

def laravel_root() -> Path | None:
    for p in (ROOT, ROOT / "src"):
        if (p / "artisan").is_file() and (p / "composer.json").is_file(): return p
    return None

def phpunit_file(app: Path) -> Path | None:
    for name in ("phpunit.xml", "phpunit.xml.dist"):
        p = app / name
        if p.exists(): return p
    return None

def env_map(xml_path: Path) -> dict[str, dict[str, str]]:
    tree = ET.parse(xml_path); root = tree.getroot(); out = {}
    for elem in root.iter("env"):
        name = elem.attrib.get("name")
        if name: out[name] = dict(elem.attrib)
    return out

def has_strong_testcase_guard(app: Path) -> bool:
    testcase = app / "tests" / "TestCase.php"
    trait = app / "tests" / "Concerns" / "HarnessSideEffectIsolation.php"
    if not testcase.exists():
        return False
    text = testcase.read_text(encoding="utf-8", errors="replace")
    combined = text
    if trait.exists():
        combined += "\n" + trait.read_text(encoding="utf-8", errors="replace")
    indicators = (
        ("app()->environment('testing')" in combined or 'app()->environment("testing")' in combined),
        ":memory:" in combined,
        "DB::purge" in combined,
        "database.connections" in combined,
        "HarnessSideEffectIsolation" in text,
        "harnessEnableSideEffectIsolation();" in text,
    )
    return all(indicators)

def scan_tests(app: Path) -> tuple[list[str], list[str]]:
    destructive, absolute = [], []
    base = app / "tests"
    if not base.exists(): return destructive, absolute
    for p in base.rglob("*.php"):
        try: text = p.read_text(encoding="utf-8", errors="replace")
        except OSError: continue
        rel = p.relative_to(app).as_posix()
        if any(rx.search(text) for rx in DESTRUCTIVE_TEST_PATTERNS): destructive.append(rel)
        if any(rx.search(text) for rx in ABSOLUTE_DANGER_PATTERNS): absolute.append(rel)
    return destructive, absolute

def audit(verbose: bool = True) -> int:
    app = laravel_root()
    if app is None:
        if verbose: print("[DB-GUARD] non-Laravel project: no Laravel DB preflight required")
        return 0
    xml_path = phpunit_file(app)
    if xml_path is None:
        print("[DB-GUARD:BLOCK] phpunit.xml/phpunit.xml.dist がありません。DB隔離を証明できないためLaravelテストを拒否します。", file=sys.stderr)
        return 2
    try: envs = env_map(xml_path)
    except Exception as exc:
        print(f"[DB-GUARD:BLOCK] {xml_path.name} を解析できません: {exc}", file=sys.stderr); return 2
    problems = []
    for name, value in REQUIRED.items():
        item = envs.get(name)
        if not item:
            problems.append(f"{name} が未定義")
            continue
        if item.get("value") != value: problems.append(f"{name}={item.get('value')!r} (required {value!r})")
        if item.get("force", "").lower() != "true": problems.append(f"{name} に force=\"true\" がない")
    for name, item in envs.items():
        if name.endswith("_DATABASE") and name != "DB_DATABASE":
            value = item.get("value", "")
            safe = value == ":memory:" or "test" in value.lower()
            if not safe: problems.append(f"{name}={value!r} はtesting専用DBと判定できない")
            if item.get("force", "").lower() != "true": problems.append(f"{name} に force=\"true\" がない")
    destructive, absolute = scan_tests(app)
    if absolute:
        problems.append("DROP DATABASE等の絶対破壊SQLを含むテスト: " + ", ".join(absolute[:8]))
    if destructive and not has_strong_testcase_guard(app):
        problems.append("DROP/TRUNCATE等を含むテストがあるが tests/TestCase.php の強制SQLite隔離ガードを確認できない: " + ", ".join(destructive[:8]))
    if problems:
        print("[DB-GUARD:BLOCK] LaravelテストDB隔離を証明できません。", file=sys.stderr)
        for p in problems: print(f"  - {p}", file=sys.stderr)
        print("ガードを弱めたり実DBへフォールバックせず、テスト設定を修正してください。", file=sys.stderr)
        return 2
    if verbose:
        print(f"[DB-GUARD:PASS] {app.relative_to(ROOT) if app != ROOT else '.'}: testing + sqlite + :memory: are forced")
        if destructive: print(f"[DB-GUARD] destructive fixture operations detected in {len(destructive)} test file(s); strong TestCase isolation guard confirmed")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Laravel test database isolation audit")
    ap.add_argument("--quiet", action="store_true"); args = ap.parse_args()
    return audit(not args.quiet)
if __name__ == "__main__": raise SystemExit(main())
