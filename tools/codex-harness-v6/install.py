#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent
PAYLOAD_ROOT = PACKAGE_ROOT / "payload"
VERSION = "6.0.0"
CONFIG_SCHEMA = 3


def looks_like_project(p: Path) -> bool:
    return (
        (p / ".codex/harness/config.json").is_file()
        and (p / ".agents/skills").is_dir()
        and (p / "AGENTS.md").is_file()
    )


def find_project(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not looks_like_project(p):
            raise SystemExit(f"Adaptive Codex Harnessが見つかりません: {p}")
        return p
    seen: set[Path] = set()
    for base in (PACKAGE_ROOT, Path.cwd().resolve()):
        for p in (base, *base.parents):
            if p in seen:
                continue
            seen.add(p)
            if looks_like_project(p):
                return p
    raise SystemExit("Project rootを自動検出できません。project/tools/ 配下へ展開するか --target を指定してください。")


def load_json(path: Path, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def detect_previous_version(project: Path) -> str:
    vp = project / ".codex/harness/VERSION"
    if vp.exists():
        v = vp.read_text(encoding="utf-8", errors="replace").strip()
        if v:
            return v
    cfg = load_json(project / ".codex/harness/config.json", {})
    meta = cfg.get("harness_meta", {}) if isinstance(cfg, dict) else {}
    if isinstance(meta, dict) and meta.get("version"):
        return str(meta["version"])
    profile = ((cfg.get("token_efficiency") or {}).get("profile") if isinstance(cfg, dict) else None)
    if profile:
        m = re.search(r"v(\d+)", str(profile))
        if m:
            return f"v{m.group(1)}-profile"
    return f"legacy-schema-{cfg.get('schema_version', '?') if isinstance(cfg, dict) else '?'}"


class Transaction:
    def __init__(self, project: Path, backup_root: Path, dry_run: bool):
        self.project = project
        self.backup_root = backup_root
        self.dry_run = dry_run
        self.entries: list[dict[str, Any]] = []
        self.seen: set[str] = set()

    def backup(self, path: Path) -> None:
        rel = path.relative_to(self.project).as_posix()
        if rel in self.seen:
            return
        self.seen.add(rel)
        existed = path.exists()
        self.entries.append({"path": rel, "existed": existed})
        if self.dry_run or not existed:
            return
        dst = self.backup_root / "files" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(path, dst)

    def save_manifest(self) -> None:
        if self.dry_run:
            return
        self.backup_root.mkdir(parents=True, exist_ok=True)
        write_json(self.backup_root / "manifest.json", {
            "harness_version": VERSION,
            "created_at": time.time(),
            "project": str(self.project),
            "entries": self.entries,
        })

    def rollback(self) -> None:
        if self.dry_run:
            return
        for entry in reversed(self.entries):
            rel = entry["path"]
            target = self.project / rel
            backup = self.backup_root / "files" / rel
            try:
                if entry["existed"]:
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if backup.is_dir():
                        shutil.copytree(backup, target, dirs_exist_ok=True)
                    elif backup.exists():
                        shutil.copy2(backup, target)
                else:
                    if target.is_dir():
                        shutil.rmtree(target)
                    elif target.exists():
                        target.unlink()
            except Exception as e:
                print(f"[ROLLBACK WARN] {rel}: {e}", file=sys.stderr)


def validate_package() -> None:
    required = [
        PAYLOAD_ROOT / ".codex/harness/VERSION",
        PAYLOAD_ROOT / ".codex/harness/scripts/selftest.py",
        PAYLOAD_ROOT / ".codex/harness/scripts/verify.py",
        PAYLOAD_ROOT / ".codex/rules/harness-safety.rules",
        PAYLOAD_ROOT / ".agents/skills/harness-develop/SKILL.md",
    ]
    missing = [str(p.relative_to(PACKAGE_ROOT)) for p in required if not p.exists()]
    if missing:
        raise SystemExit("v6 package is incomplete: " + ", ".join(missing))
    for p in PAYLOAD_ROOT.rglob("*.py"):
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except Exception as e:
            raise SystemExit(f"Python syntax error in package {p}: {e}")
    manifest_path = PACKAGE_ROOT / "package_manifest.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path, {})
        expected = manifest.get("payload_sha256", {}) if isinstance(manifest, dict) else {}
        for rel, digest in expected.items():
            fp = PAYLOAD_ROOT / rel
            if not fp.is_file():
                raise SystemExit(f"Package manifest file missing: payload/{rel}")
            actual = hashlib.sha256(fp.read_bytes()).hexdigest()
            if actual != digest:
                raise SystemExit(f"Package integrity mismatch: payload/{rel}")


def copy_payload(project: Path, tx: Transaction) -> list[str]:
    changed: list[str] = []
    preserve_if_exists = {
        ".codex/harness/architecture_rules.json",
    }
    for src in sorted(PAYLOAD_ROOT.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(PAYLOAD_ROOT).as_posix()
        dst = project / rel
        if rel in preserve_if_exists and dst.exists():
            continue
        tx.backup(dst)
        changed.append(rel)
        if tx.dry_run:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if dst.suffix == ".py" or rel.endswith("codex-project"):
            dst.chmod(dst.stat().st_mode | 0o111)
    return changed


def patch_architecture_rules(project: Path, tx: Transaction) -> list[str]:
    p = project / ".codex/harness/architecture_rules.json"
    if not p.exists():
        return ["architecture_rules.json created from v6 default"]
    cfg = load_json(p, {})
    if not isinstance(cfg, dict):
        cfg = {}
    before = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    cfg.setdefault("schema_version", 1)
    cfg.setdefault("mode", "advisory")
    cfg.setdefault("rules", [])
    after = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    if before != after:
        tx.backup(p)
        if not tx.dry_run:
            write_json(p, cfg)
        return ["existing architecture rules preserved and schema defaults added"]
    return ["existing architecture rules preserved unchanged"]


def patch_harness_config(project: Path, tx: Transaction, previous: str) -> list[str]:
    p = project / ".codex/harness/config.json"
    tx.backup(p)
    cfg = load_json(p, {})
    if not isinstance(cfg, dict):
        cfg = {}
    cfg["schema_version"] = max(int(cfg.get("schema_version", 0) or 0), CONFIG_SCHEMA)
    cfg["harness_meta"] = {
        "name": "adaptive-codex-harness",
        "version": VERSION,
        "config_schema": CONFIG_SCHEMA,
        "profile": "adaptive_quality_v6",
        "migrated_from": previous,
        "feature_modes": {
            "self_test": "enforce_on_install",
            "version_migration": "enforce",
            "action_guardrails": "destructive_prompt",
            "root_validation": "warn_and_launcher",
            "architecture_check": "advisory_ratcheting",
            "common_verification_gate": "enforce",
            "skill_eval": "manual",
            "task_state": "large_or_multisession_only",
            "observability": "local_metrics_only",
            "subagent_isolation": "conditional_read_only_first",
            "harness_audit": "manual",
        },
    }

    tok = cfg.setdefault("token_efficiency", {})
    tok["enabled"] = True
    tok["profile"] = "adaptive_quality_v6"
    tok["execution"] = {
        "model_policy": "sol_high_fixed",
        "single_agent_default": True,
        "subagents": "conditional",
        "max_parallel_subagents": 2,
        "delegation_requires_independent_scopes": True,
        "prefer_read_only_subagents": True,
        "avoid_duplicate_context": True,
        "prefer_local_deterministic_tools": True,
        "capture_large_command_output": True,
        "targeted_checks_during_iteration": True,
        "final_full_verification_once": True,
        "knowledge_update": "advisory_durable_only",
    }
    tok["delegation_policy"] = {
        "all_conditions_required": [
            "two_or_more_substantial_workstreams_remain",
            "scopes_independent_and_mostly_non_overlapping",
            "serial_execution_materially_slow",
            "narrow_scope_and_concrete_deliverable",
        ],
        "max_depth": 1,
        "max_parallel": 2,
        "read_only_for_investigation": True,
    }
    tok["context_policy"] = {
        "scope_expansion": "evidence_only",
        "candidate_files_partition_threshold": 12,
        "large_file_targeted_read_lines": 400,
        "avoid_reread_unchanged_files": True,
        "large_diff_inventory_first": True,
        "diff_first_then_hunks": True,
        "broad_search_requires_bounded_output": True,
    }
    tok["artifact_policy"] = {
        "temporary_root": ".codex/harness/runtime",
        "tracked_audit_reports": "user_requested_or_durable_only",
        "prefer_update_existing_docs": True,
        "avoid_per_task_report_files": True,
        "avoid_speculative_scaffolding": True,
    }
    tok["change_policy"] = {
        "scope_creep": "report_not_fix",
        "unrelated_refactor": False,
        "unrelated_formatting": False,
        "rename_move_without_need": False,
        "prefer_existing_dependencies": True,
        "new_dependency_requires_human_approval": True,
        "new_file_requires_new_responsibility": True,
    }
    tok["verification"] = {
        "success_max_lines": 4,
        "failure_max_lines": 100,
        "detail_max_lines": 250,
        "tail_scan_bytes": 1572864,
        "retain_success_logs": False,
        "retain_failed_logs": True,
        "failed_log_retention_runs": 8,
        "targeted_checks_after_logical_batch": True,
        "avoid_repeating_valid_pass": True,
        "architecture_ratchet_in_final_gate": True,
    }
    tok["review_policy"] = {
        "diff_first": True,
        "inventory_first": True,
        "no_repository_wide_audit": True,
        "expand_context_on_concrete_risk_only": True,
        "reuse_valid_verification_stamp": True,
        "single_reviewer_pass_is_final": True,
    }
    tok["failure_policy"] = {
        "repeat_same_command_without_new_evidence": False,
        "unproductive_attempts_before_resynthesis": 2,
        "broaden_scope_only_with_evidence": True,
    }
    tok["bootstrap_policy"] = {
        "routine_per_task": False,
        "run_when": ["initial_install", "commands_uninitialized", "material_environment_or_layout_change"],
        "doctor_after_harness_or_environment_change_only": True,
    }
    tok["test_policy"] = {
        "strategy": "risk_based_minimal_regression",
        "new_test_file_default": "avoid_prefer_existing_coherent_home",
        "prefer_existing_related_test": True,
        "bug_fix_minimal_regression": True,
        "avoid_cross_layer_duplicate_behavior": True,
        "avoid_coverage_only_tests": True,
        "legacy_parity_use_datasets_for_related_cases": True,
        "audit_only_no_speculative_test_creation": True,
        "reuse_factories_fixtures_helpers": True,
        "new_test_file_soft_limit_per_workstream": 1,
        "new_test_file_soft_limit_per_task": 3,
        "soft_limit_requires_explicit_risk_justification": True,
    }
    cfg["root_policy"] = {
        "workspace_root": ".",
        "split_workspace_git_root_supported": True,
        "preferred_launch": ".codex/harness/bin/codex-project",
        "do_not_modify_user_global_config": True,
    }
    cfg["observability"] = {
        "enabled": True,
        "storage": ".codex/harness/runtime/telemetry",
        "store_command_text": False,
        "store_tool_output": False,
        "mode": "local_metrics_only",
    }
    cfg["architecture"] = {
        "rules_file": ".codex/harness/architecture_rules.json",
        "default_mode": "advisory",
        "scope": "changed_files",
        "ratchet": True,
    }
    cfg["task_state"] = {
        "enabled": True,
        "automatic": False,
        "use_for": "genuinely_long_or_multi_session_work_only",
        "storage": ".codex/harness/runtime/task-state",
    }

    gate = cfg.setdefault("quality_gate", {})
    gate["enabled"] = True
    gate["require_verification"] = True
    gate["require_independent_review"] = True
    nt = gate.setdefault("nontrivial", {})
    nt["changed_files"] = max(int(nt.get("changed_files", 2) or 2), 8)
    nt["changed_lines"] = max(int(nt.get("changed_lines", 25) or 25), 200)
    gate["max_stop_blocks_per_diff"] = 1
    gate.setdefault("verification_exempt_globs", ["docs/**", "memo/**", "**/*.md"])
    cfg.setdefault("knowledge", {})["stop_checkpoint"] = "advisory"

    if not tx.dry_run:
        write_json(p, cfg)
    return ["config schema -> v6", "Sol/high + conditional max-2 agents retained", "v6 feature modes + observability/root/architecture policies added"]


def patch_commands(project: Path, tx: Transaction) -> list[str]:
    p = project / ".codex/harness/commands.json"
    if not p.exists():
        return ["commands.json missing: preserved as missing; bootstrap required"]
    cfg = load_json(p, {})
    if not isinstance(cfg, dict):
        return ["commands.json invalid: self-test will fail"]
    tx.backup(p)
    for item in cfg.get("commands", []):
        if not isinstance(item, dict):
            continue
        cmd = str(item.get("command", "")).strip()
        name = str(item.get("name", cmd)).casefold()
        if cmd in {"docker compose config", "docker-compose config"}:
            item["command"] = cmd + " --quiet"
            cmd = item["command"]
        out = item.setdefault("output", {})
        if not isinstance(out, dict):
            out = {}; item["output"] = out
        out["success_lines"] = 0 if "compose config" in (name + " " + cmd.casefold()) else min(int(out.get("success_lines", 4) or 4), 4)
        out["failure_lines"] = min(int(out.get("failure_lines", 100) or 100), 100)
        out["detail_lines"] = min(int(out.get("detail_lines", 250) or 250), 250)
    if not tx.dry_run:
        write_json(p, cfg)
    return ["project-specific verification commands preserved; output budgets capped"]


def replace_section_key(text: str, section: str, key: str, value: str) -> str:
    sec = re.compile(rf"(?ms)^\[{re.escape(section)}\]\s*\n(.*?)(?=^\[|\Z)")
    m = sec.search(text)
    if not m:
        return text.rstrip() + f"\n\n[{section}]\n{key} = {value}\n"
    block = m.group(0)
    kr = re.compile(rf"(?m)^{re.escape(key)}\s*=\s*.*$")
    new = kr.sub(f"{key} = {value}", block, count=1) if kr.search(block) else block.replace(f"[{section}]\n", f"[{section}]\n{key} = {value}\n", 1)
    return text[:m.start()] + new + text[m.end():]


def set_top(text: str, key: str, value: str) -> str:
    m = re.search(r"(?m)^\[", text)
    end = m.start() if m else len(text)
    head, tail = text[:end], text[end:]
    pat = re.compile(rf"(?m)^{re.escape(key)}\s*=\s*.*$")
    head = pat.sub(f"{key} = {value}", head, count=1) if pat.search(head) else head.rstrip() + f"\n{key} = {value}\n"
    return head + tail


def patch_toml(project: Path, tx: Transaction) -> list[str]:
    p = project / ".codex/config.toml"
    if not p.exists():
        return ["config.toml missing: self-test will fail"]
    tx.backup(p)
    text = p.read_text(encoding="utf-8")
    text = set_top(text, "model", '"gpt-5.6-sol"')
    text = set_top(text, "model_reasoning_effort", '"high"')
    text = replace_section_key(text, "features", "multi_agent", "true")
    text = replace_section_key(text, "features", "hooks", "true")
    text = replace_section_key(text, "agents", "enabled", "true")
    text = replace_section_key(text, "agents", "max_concurrent_threads_per_session", "2")
    text = replace_section_key(text, "agents", "max_depth", "1")
    # Intentionally do not set project_root_markers here. A project-local setting cannot
    # safely fix every split workspace/git-root layout; v6 ships a root launcher instead.
    if not tx.dry_run:
        p.write_text(text, encoding="utf-8")
    return ["Codex model fixed to gpt-5.6-sol/high", "hooks enabled; max 2 subagents / depth 1", "project_root_markers intentionally untouched"]


def _hook_command(script: str) -> str:
    return f"/bin/sh -c 'd=$PWD; while [ \"$d\" != / ]; do p=\"$d/.codex/harness/scripts/{script}\"; if [ -f \"$p\" ]; then exec /usr/bin/python3 \"$p\"; fi; d=${{d%/*}}; [ -n \"$d\" ] || d=/; done; exit 0'"


def patch_hooks(project: Path, tx: Transaction) -> list[str]:
    p = project / ".codex/hooks.json"
    tx.backup(p)
    root = load_json(p, {"description": "Adaptive Codex Harness hooks", "hooks": {}})
    if not isinstance(root, dict):
        root = {"description": "Adaptive Codex Harness hooks", "hooks": {}}
    hooks = root.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}; root["hooks"] = hooks

    telemetry_cmd = _hook_command("telemetry_hook.py")

    def add(event: str, matcher: str | None = None, *, async_: bool = True, timeout: int = 3) -> None:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            groups = []; hooks[event] = groups
        for g in groups:
            if not isinstance(g, dict):
                continue
            for h in g.get("hooks", []) if isinstance(g.get("hooks"), list) else []:
                if isinstance(h, dict) and "telemetry_hook.py" in str(h.get("command", "")):
                    if matcher == g.get("matcher") or (matcher is None and not g.get("matcher")):
                        return
        group: dict[str, Any] = {"hooks": [{"type": "command", "command": telemetry_cmd, "timeout": timeout, "async": async_}]}
        if matcher:
            group["matcher"] = matcher
        groups.append(group)

    add("SessionStart", "startup|resume|clear|compact", async_=True)
    add("PostToolUse", "Bash|apply_patch|Agent", async_=True)
    add("SubagentStart", None, async_=True)
    add("SubagentStop", None, async_=True)
    add("SessionEnd", None, async_=True)
    root["description"] = "Adaptive Codex Harness v6 lifecycle, quality gate, and low-content local observability."
    if not tx.dry_run:
        write_json(p, root)
    return ["existing hooks preserved", "low-content asynchronous observability hooks added"]


def replace_md_section(text: str, heading: str, body: str) -> str:
    pat = re.compile(rf"(?ms)^## {re.escape(heading)}\s*\n.*?(?=^## |\Z)")
    replacement = f"## {heading}\n\n{body.strip()}\n\n"
    if pat.search(text):
        return pat.sub(replacement, text, count=1)
    return text.rstrip() + "\n\n" + replacement


def remove_md_sections(text: str, heads: list[str]) -> str:
    for h in heads:
        text = re.sub(rf"(?ms)^## {re.escape(h)}\s*\n.*?(?=^## |\Z)", "", text)
    return text


def patch_agents_md(project: Path, tx: Transaction) -> list[str]:
    p = project / "AGENTS.md"
    if not p.exists():
        return ["AGENTS.md missing: self-test will fail"]
    tx.backup(p)
    text = p.read_text(encoding="utf-8")
    text = remove_md_sections(text, [
        "Token-efficient execution", "Minimum-token execution", "Adaptive token-efficient execution",
        "Adaptive execution discipline", "Harness v6 runtime rules",
    ])
    text = replace_md_section(text, "Default agent loop", """
通常はGPT-5.6 Sol + highの親Agent 1つで進める。Planner/Explorer/Workerを自動分割しない。

- 2つ以上の独立した大きなworkstreamがあり、範囲がほぼ重ならず、逐次処理が明らかに遅い場合だけ最大2 Subagentを使う。調査はread-onlyを優先し、入れ子は禁止。
- 調査は小さいinventoryから始め、必要なファイル/シンボルだけ読む。12ファイル超が候補ならworkstreamへ分割する。
- 親Agentが統合・実装順・最終判断を保持し、Subagentはコード全文ではなく短い根拠付き結果を返す。
""")
    text = replace_md_section(text, "Verification", """
- 正式入口は `python3 .codex/harness/scripts/verify.py`。Architecture Ratchetも同じ最終Gateに含む。
- 実装途中は影響範囲の最小チェックを論理的な変更単位ごとに行い、同じPASSを無意味に再実行しない。
- 成功raw logは読まない。失敗は `--detail` → 必要時のみ `--raw`。
- 最終diffでregistered verificationを原則1回実行し、その後の編集で無効化された場合だけ再実行する。
""")
    text = replace_md_section(text, "Review", """
Reviewerはquality gateが要求する高リスク/大規模な最終diffだけに使用する。`change_inventory.py` → changed files → changed hunksの順で確認し、具体的リスクがある場合だけ周辺コードへ広げる。repository-wide再監査、既に有効なVerificationの全再実行、PASS後の追加Reviewerは禁止する。
""")
    text = text.rstrip() + """

## Harness v6 runtime rules

- 依頼外の修正・refactor・format・renameは原則行わず、必要なら報告する。
- 新規依存は人間の承認対象。既存のhelper/file/test/factoryを優先し、新規Test.phpは明確に別責務の場合だけ作る。
- 大量出力は `quiet_exec.py` / `verify.py` / runtime fileへ退避する。一時audit/report/logは `.codex/harness/runtime/` に置く。
- 破壊的・外部書き込み操作は `.codex/rules/` のGuardrailに従う。Guardrailを回避しない。
- Architecture rulesは既存違反の一括修正ではなく、changed-file ratchetとして使う。初期はadvisory。
- `doctor.py` / Self TestはHarness・環境変更時に使い、通常の小変更ごとには実行しない。
- 長期・複数セッション作業だけ `task_state.py` を使う。通常タスクで状態ファイルを作らない。
- Knowledgeは永続価値がある場合だけ更新する。毎タスクのaudit/plan/evidenceファイルを乱造しない。
"""
    if not tx.dry_run:
        p.write_text(text, encoding="utf-8")
    return ["legacy saver appendices removed", "agent/verification/review sections normalized for v6", "concise v6 runtime rules installed"]


def patch_gitignore(project: Path, tx: Transaction) -> list[str]:
    # Only relevant when the workspace itself is a Git root. In split-root layouts,
    # .codex/runtime is already outside the application Git repository.
    if not (project / ".git").exists():
        return ["workspace is not Git root; no root .gitignore change needed"]
    p = project / ".gitignore"
    old = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    marker_start = "# >>> adaptive-codex-harness-v6 >>>"
    marker_end = "# <<< adaptive-codex-harness-v6 <<<"
    body = f"{marker_start}\n.codex/harness/runtime/\n.codex-harness-backup/\n{marker_end}"
    pat = re.compile(re.escape(marker_start) + r".*?" + re.escape(marker_end), re.S)
    new = pat.sub(body, old) if pat.search(old) else old.rstrip() + ("\n\n" if old.strip() else "") + body + "\n"
    if new != old:
        tx.backup(p)
        if not tx.dry_run:
            p.write_text(new, encoding="utf-8")
    return ["runtime/backup paths ignored in workspace Git root"]


def write_installed_manifest(project: Path, tx: Transaction) -> None:
    source = load_json(PACKAGE_ROOT / "package_manifest.json", {})
    hashes = source.get("payload_sha256", {}) if isinstance(source, dict) else {}
    # architecture_rules.json is project-owned after initial creation and is intentionally excluded.
    hashes = {k: v for k, v in hashes.items() if k != ".codex/harness/architecture_rules.json"}
    p = project / ".codex/harness/installed-manifest.json"
    tx.backup(p)
    if not tx.dry_run:
        write_json(p, {"version": VERSION, "payload_sha256": hashes})


def record_install_history(project: Path, previous: str) -> None:
    p = project / ".codex/harness/runtime/install-history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "from": previous, "to": VERSION}, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_selftest(project: Path) -> int:
    script = project / ".codex/harness/scripts/selftest.py"
    return subprocess.call([sys.executable, str(script), "--install-check"], cwd=project)


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive Codex Harness v6 transactional upgrader")
    ap.add_argument("--target", help="Project/workspace root. Usually auto-detected when this package is under project/tools/.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-rollback", action="store_true", help="Debug only: keep changes if post-install self-test fails")
    args = ap.parse_args()

    validate_package()
    project = find_project(args.target)
    previous = detect_previous_version(project)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = project / ".codex-harness-backup" / f"v6-{stamp}"
    tx = Transaction(project, backup_root, args.dry_run)

    print(f"Project    : {project}")
    print(f"From       : {previous}")
    print(f"To         : {VERSION}")
    print("Model      : gpt-5.6-sol")
    print("Reasoning  : high")
    print("Agents     : 1 default / max 2 conditional")
    print("Architecture: advisory ratchet")
    print("Telemetry  : local metrics only (no command/output text)")
    print(f"Backup     : {backup_root}")
    print(f"Dry-run    : {'yes' if args.dry_run else 'no'}\n")

    notes: list[str] = []
    try:
        changed = copy_payload(project, tx)
        notes += patch_architecture_rules(project, tx)
        notes += patch_harness_config(project, tx, previous)
        notes += patch_commands(project, tx)
        notes += patch_toml(project, tx)
        notes += patch_hooks(project, tx)
        notes += patch_agents_md(project, tx)
        notes += patch_gitignore(project, tx)
        write_installed_manifest(project, tx)
        tx.save_manifest()

        print("Installed/updated:")
        for rel in changed:
            print(f"  - {rel}")
        print("\nMigration/policy:")
        for n in notes:
            print(f"  - {n}")

        if args.dry_run:
            print("\nDry-run only. No files were changed.")
            return 0

        print("\nRunning v6 self-test...")
        rc = run_selftest(project)
        if rc != 0:
            raise RuntimeError(f"v6 self-test failed (exit={rc})")
        record_install_history(project, previous)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        if not args.dry_run and not args.no_rollback:
            print("Self-test/install failed; rolling back touched files...", file=sys.stderr)
            tx.rollback()
            print(f"Rollback completed. Backup retained at: {backup_root}", file=sys.stderr)
        elif not args.dry_run:
            tx.save_manifest()
            print(f"Changes retained because --no-rollback was specified. Backup: {backup_root}", file=sys.stderr)
        return 1

    print("\nAdaptive Codex Harness v6 installed successfully.")
    print("Restart Codex after installation.")
    print("Recommended checks:")
    print("  python3 .codex/harness/scripts/doctor.py")
    print("  python3 .codex/harness/scripts/verify.py --list")
    print("  python3 .codex/harness/scripts/telemetry_report.py --days 7")
    print("\nIf workspace root and Git root differ, launch Codex with:")
    print("  ./.codex/harness/bin/codex-project")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
