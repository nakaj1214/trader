#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

SCRIPT_DIR = Path(__file__).resolve().parent
HARNESS_DIR = SCRIPT_DIR.parent
WORKSPACE_ROOT = HARNESS_DIR.parents[1]

REQUIRED_SKILLS = [
    "harness-bootstrap",
    "harness-debug",
    "harness-develop",
    "harness-review",
    "harness-verify",
    "maintain-project-knowledge",
]
REQUIRED_FILES = [
    "AGENTS.md",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/harness/VERSION",
    ".codex/harness/config.json",
    ".codex/harness/commands.json",
    ".codex/harness/architecture_rules.json",
    ".codex/harness/scripts/verify.py",
    ".codex/harness/scripts/output_guard.py",
    ".codex/harness/scripts/quiet_exec.py",
    ".codex/harness/scripts/change_inventory.py",
    ".codex/harness/scripts/test_inventory.py",
    ".codex/harness/scripts/architecture_check.py",
    ".codex/harness/scripts/telemetry_hook.py",
    ".codex/harness/scripts/telemetry_report.py",
    ".codex/harness/bin/codex-project",
    ".codex/rules/harness-safety.rules",
]


def read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
        return (v if isinstance(v, dict) else None), None
    except Exception as e:
        return None, str(e)


def run_git_root(path: Path) -> Path | None:
    try:
        out = subprocess.check_output(["git", "-C", str(path), "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True).strip()
        return Path(out).resolve() if out else None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6 self-test")
    ap.add_argument("--install-check", action="store_true", help="Used by installer; warnings do not fail installation")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    oks: list[str] = []

    def ok(msg: str) -> None: oks.append(msg)
    def err(msg: str) -> None: errors.append(msg)
    def warn(msg: str) -> None: warnings.append(msg)

    for rel in REQUIRED_FILES:
        p = WORKSPACE_ROOT / rel
        (ok if p.exists() else err)(f"required file: {rel}")

    version_path = HARNESS_DIR / "VERSION"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else ""
    if version == "6.0.0": ok("Harness version 6.0.0")
    else: err(f"Harness version mismatch: {version or 'missing'}")

    cfg, cfg_err = read_json(HARNESS_DIR / "config.json")
    if cfg_err or cfg is None:
        err(f"config.json parse: {cfg_err}")
        cfg = {}
    else:
        ok("config.json parse")
        if int(cfg.get("schema_version", 0)) >= 3: ok("config schema >= 3")
        else: err(f"config schema is {cfg.get('schema_version')}, expected >=3")
        meta = cfg.get("harness_meta", {}) if isinstance(cfg.get("harness_meta"), dict) else {}
        if meta.get("version") == "6.0.0": ok("harness_meta.version")
        else: err("harness_meta.version is not 6.0.0")
        tok = cfg.get("token_efficiency", {}) if isinstance(cfg.get("token_efficiency"), dict) else {}
        if tok.get("profile") == "adaptive_quality_v6": ok("adaptive_quality_v6 profile")
        else: err("token_efficiency.profile is not adaptive_quality_v6")

    for name in ("commands.json", "architecture_rules.json"):
        _, e = read_json(HARNESS_DIR / name)
        (err if e else ok)(f"{name} parse" + (f": {e}" if e else ""))

    installed_manifest, manifest_err = read_json(HARNESS_DIR / "installed-manifest.json")
    if manifest_err or installed_manifest is None:
        warn("installed-manifest.json missing or invalid; harness-owned drift cannot be checked")
    else:
        drift = []
        for rel, expected in installed_manifest.get("payload_sha256", {}).items():
            fp = WORKSPACE_ROOT / rel
            if not fp.is_file():
                drift.append(f"missing:{rel}")
                continue
            actual = hashlib.sha256(fp.read_bytes()).hexdigest()
            if actual != expected:
                drift.append(rel)
        if drift:
            # Install check treats this as an error; later deliberate local customizations only warn.
            (err if args.install_check else warn)("harness-owned file drift: " + ", ".join(drift[:8]))
        else:
            ok("harness-owned payload matches installed manifest")

    toml_path = WORKSPACE_ROOT / ".codex/config.toml"
    if tomllib is None:
        warn("tomllib unavailable; skipped config.toml parse")
    elif toml_path.exists():
        try:
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
            ok("config.toml parse")
            if data.get("model") == "gpt-5.6-sol": ok("model = gpt-5.6-sol")
            else: err(f"model is {data.get('model')!r}, expected gpt-5.6-sol")
            if data.get("model_reasoning_effort") == "high": ok("reasoning = high")
            else: err(f"reasoning is {data.get('model_reasoning_effort')!r}, expected high")
            agents = data.get("agents", {}) if isinstance(data.get("agents"), dict) else {}
            max_threads = int(agents.get("max_concurrent_threads_per_session", 99))
            if max_threads <= 2: ok("subagent concurrency <= 2")
            else: err(f"subagent concurrency={max_threads}, expected <=2")
        except Exception as e:
            err(f"config.toml parse: {e}")

    hooks, hooks_err = read_json(WORKSPACE_ROOT / ".codex/hooks.json")
    if hooks_err or hooks is None:
        err(f"hooks.json parse: {hooks_err}")
    else:
        ok("hooks.json parse")
        h = hooks.get("hooks", {}) if isinstance(hooks.get("hooks"), dict) else {}
        if "PostToolUse" in h and "SubagentStart" in h: ok("observability hooks installed")
        else: err("observability hooks missing")

    agents_path = WORKSPACE_ROOT / "AGENTS.md"
    if agents_path.exists():
        text = agents_path.read_text(encoding="utf-8", errors="replace")
        if len(text.splitlines()) > 220:
            warn(f"AGENTS.md is {len(text.splitlines())} lines; consider keeping it router-like")
        conflict_patterns = [
            r"Explorer\s*(?:→|->).*Planner\s*(?:→|->).*Worker",
            r"Planner/Explorer/Workerを(?:必ず|常に)",
        ]
        found = [p for p in conflict_patterns if re.search(p, text, re.I | re.S)]
        if found: err("AGENTS.md contains a legacy mandatory-agent-chain directive")
        else: ok("AGENTS.md has no known mandatory-agent-chain conflict")

    skills_root = WORKSPACE_ROOT / ".agents/skills"
    for skill in REQUIRED_SKILLS:
        p = skills_root / skill / "SKILL.md"
        if not p.exists():
            err(f"skill missing: {skill}")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---") and f"name: {skill}" in text[:600]: ok(f"skill metadata: {skill}")
        else: err(f"skill metadata invalid: {skill}")

    rules = WORKSPACE_ROOT / ".codex/rules/harness-safety.rules"
    if rules.exists():
        rt = rules.read_text(encoding="utf-8", errors="replace")
        if "prefix_rule(" in rt and 'decision = "prompt"' in rt: ok("safety rules basic structure")
        else: err("safety rules basic structure invalid")
        if rt.count("prefix_rule(") != rt.count("\n)"):
            warn("safety rules parentheses count is unusual; Codex will validate inline match cases at startup")

    launcher = WORKSPACE_ROOT / ".codex/harness/bin/codex-project"
    if launcher.exists():
        if os.access(launcher, os.X_OK): ok("codex-project launcher executable")
        else: err("codex-project launcher is not executable")

    layout = cfg.get("project_layout", {}) if isinstance(cfg, dict) else {}
    git_roots = []
    for rel in layout.get("git_roots", []) if isinstance(layout.get("git_roots", []), list) else []:
        p = (WORKSPACE_ROOT / str(rel)).resolve()
        if (p / ".git").exists(): git_roots.append(p)
    if (WORKSPACE_ROOT / ".git").exists(): git_roots.append(WORKSPACE_ROOT)
    if git_roots:
        ok("configured Git root detected")
        if all(p != WORKSPACE_ROOT for p in git_roots):
            warn("workspace root differs from Git root; start Codex from workspace root or use .codex/harness/bin/codex-project")
    else:
        err("no configured Git root detected")

    if shutil.which("codex") is None:
        warn("codex executable not found in PATH; launcher runtime not tested")

    if not args.quiet:
        for msg in oks: print(f"[OK] {msg}")
        for msg in warnings: print(f"[WARN] {msg}")
        for msg in errors: print(f"[FAIL] {msg}")
        print(f"\nSelf-test: {len(errors)} error(s), {len(warnings)} warning(s), {len(oks)} check(s) passed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
