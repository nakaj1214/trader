#!/usr/bin/env python3
from __future__ import annotations


# adaptive-codex-harness-v6.4-side-effect-preflight:begin
# Fail closed before formal verification can launch any Laravel test command.
def _adaptive_harness_v64_preflight() -> None:
    import subprocess as _subprocess
    import sys as _sys
    from pathlib import Path as _Path

    _root = _Path(__file__).resolve().parents[3]
    for _name in ("test_db_guard.py", "side_effect_guard.py"):
        _guard = _root / ".codex" / "harness" / "scripts" / _name
        if _guard.exists():
            _cp = _subprocess.run([_sys.executable, str(_guard), "--quiet"], cwd=_root)
            if _cp.returncode != 0:
                raise SystemExit(f"Harness safety preflight failed in {_name}; verification aborted before tests.")
_adaptive_harness_v64_preflight()
# adaptive-codex-harness-v6.4-side-effect-preflight:end

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from common import WORKSPACE_ROOT, COMMANDS_PATH, RUNTIME_DIR, config, load_json, repo_state_hash
from output_guard import prune_failed_logs, read_detail, run_guarded

VERIFY_ROOT = RUNTIME_DIR / "verification"
LATEST_PATH = VERIFY_ROOT / "latest.json"


def _selected_commands(cfg: dict, profile: str) -> list[dict]:
    return [
        c for c in cfg.get("commands", [])
        if c.get("enabled", True) and profile in c.get("profiles", ["quick", "full"])
    ]


def _load_latest() -> dict:
    return load_json(LATEST_PATH, {})


def _show_previous(name_filter: str | None, raw: bool) -> int:
    latest = _load_latest()
    if not latest:
        print("No previous verification log is available.")
        return 2

    token_cfg = config().get("token_efficiency", {})
    verification_cfg = token_cfg.get("verification", {}) if isinstance(token_cfg, dict) else {}
    detail_max = int(verification_cfg.get("detail_max_lines", 400))
    scan_bytes = int(verification_cfg.get("tail_scan_bytes", 2 * 1024 * 1024))

    matched = 0
    for result in latest.get("results", []):
        name = str(result.get("name", ""))
        if name_filter and name_filter.casefold() not in name.casefold():
            continue
        rel = result.get("log_path")
        if not rel:
            continue
        log_path = RUNTIME_DIR / rel
        if not log_path.exists():
            continue
        matched += 1
        print(f"\n==> {'RAW' if raw else 'DETAIL'}: {name}")
        lines = read_detail(log_path, detail_max, scan_bytes, raw=raw)
        if raw:
            for line in lines:
                print(line)
        else:
            for line in lines[:detail_max]:
                print(line)
            if len(lines) >= detail_max:
                print(f"... detail capped at {detail_max} lines; use --raw only if still necessary")

    if matched == 0:
        print("No retained failed log matched. Successful command logs are discarded by default.")
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Token-efficient harness verification")
    ap.add_argument("--profile", default="quick", choices=["quick", "full"])
    ap.add_argument("--list", action="store_true")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--detail", nargs="?", const="", metavar="NAME", help="Show a bounded excerpt from the latest retained failed log without rerunning tests")
    group.add_argument("--raw", nargs="?", const="", metavar="NAME", help="Show the full latest retained failed log without rerunning tests")
    args = ap.parse_args()

    if args.detail is not None:
        return _show_previous(args.detail or None, raw=False)
    if args.raw is not None:
        return _show_previous(args.raw or None, raw=True)

    command_cfg = load_json(COMMANDS_PATH, {"status": "uninitialized", "commands": []})
    commands = _selected_commands(command_cfg, args.profile)
    if args.list:
        print(json.dumps(commands, ensure_ascii=False, indent=2))
        return 0
    if command_cfg.get("status") != "ready" or not commands:
        print("Harness verification commands are not initialized. Run `$harness-bootstrap` and confirm real project commands.")
        return 2

    harness_cfg = config()

    # Architecture ratchet is part of the same human/Codex/CI gate.
    # Default mode is advisory and an empty rule set is a no-op.
    arch_script = Path(__file__).resolve().parent / "architecture_check.py"
    if arch_script.exists():
        arch = subprocess.run([sys.executable, str(arch_script), "--json"], cwd=WORKSPACE_ROOT, text=True, capture_output=True)
        try:
            payload = json.loads((arch.stdout or "{}").strip() or "{}")
        except Exception:
            payload = {}
        findings = payload.get("findings", []) if isinstance(payload, dict) else []
        mode = payload.get("mode", "advisory") if isinstance(payload, dict) else "advisory"
        if findings:
            print(f"[{'FAIL' if arch.returncode else 'WARN'}] Architecture ratchet ({len(findings)} finding(s), mode={mode})")
            for f in findings[:8]:
                print(f"  {f.get('path')}:{f.get('line','?')} [{f.get('rule','?')}] {f.get('message','')}")
            if len(findings) > 8:
                print(f"  ... {len(findings)-8} more; run architecture_check.py for details")
        elif mode != "off":
            print(f"[PASS] Architecture ratchet ({mode})")
        if arch.returncode != 0:
            print("==> Harness verification: FAIL (architecture gate)")
            return 1
    token_cfg = harness_cfg.get("token_efficiency", {})
    verification_cfg = token_cfg.get("verification", {}) if isinstance(token_cfg, dict) else {}
    keep_runs = int(verification_cfg.get("failed_log_retention_runs", 12))

    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = VERIFY_ROOT / run_id
    results: list[dict] = []
    required_pass = True

    print(f"==> Harness verification [{args.profile}] ({len(commands)} checks)")
    for item in commands:
        cmd = item.get("command")
        name = item.get("name", cmd)
        required = item.get("required", True)
        timeout = int(item.get("timeout_seconds", 900))
        cwd = WORKSPACE_ROOT / item.get("cwd", ".")

        result = run_guarded(
            name=name,
            command=cmd,
            cwd=cwd,
            timeout=timeout,
            item=item,
            token_cfg=token_cfg,
            run_dir=run_dir,
        )
        result["required"] = required
        results.append(result)
        passed = bool(result["passed"])
        required_pass = required_pass and (passed or not required)

        state = "PASS" if passed else "FAIL"
        print(f"[{state}] {name} ({result['elapsed_seconds']}s, exit={result['exit_code']})")
        for line in result.get("excerpt", []):
            print(f"  {line}")
        if not passed and result.get("log_path"):
            print(f"  retained log: .codex/harness/runtime/{result['log_path']}")
            print(f"  more detail: python3 .codex/harness/scripts/verify.py --detail \"{name}\"")

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    VERIFY_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = {
        "state_hash": repo_state_hash(harness_cfg),
        "passed": required_pass,
        "profile": args.profile,
        "timestamp": time.time(),
        "results": results,
    }
    (RUNTIME_DIR / "verify-stamp.json").write_text(json.dumps(stamp, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_PATH.write_text(json.dumps(stamp, ensure_ascii=False, indent=2), encoding="utf-8")
    prune_failed_logs(VERIFY_ROOT, keep_runs)

    print(f"==> Harness verification: {'PASS' if required_pass else 'FAIL'}")
    if not required_pass:
        print("Use --detail first. Use --raw only if the bounded detail is insufficient.")
    return 0 if required_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
