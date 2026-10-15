#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

VERSION = "6.14.0"
SUPPORTED_FROM = {(6, 13, 0), (6, 14, 0)}

V614_DOC = """# Adaptive Codex Harness v6.14

v6.14 adds a manual, behavior-based Harness evaluation loop without adding work to
ordinary application tasks.

Principles:
- Define the task contract and completion evidence before substantial work.
- Treat the latest user correction/review as authoritative for the current task.
- Reconcile actionable review findings into a plan instead of silently dropping them.
- Prefer the smallest edit and the smallest verification that proves the changed behavior.
- Turn reproducible Harness failures into eval scenarios before adding more permanent rules.
- Evaluate Harness policy/skill/hook changes in fresh Codex sessions with deterministic graders.
- Keep holdout scenarios out of routine tuning runs to reduce overfitting.
- Do not run Harness evals from normal Stop/verify hooks. Evals are explicit maintainer work only.
- Change one behavioral theme at a time when tuning Harness guidance, then re-run the relevant evals.

The eval runner uses fresh `codex exec --json --full-auto` invocations in isolated scratch
Git repositories. It records JSONL traces and applies deterministic checks to changed paths,
diff size, commands, file contents, and final-response claims.

Routine project verification remains proportional and unchanged from v6.13.
"""

AGENTS_BLOCK = """<!-- adaptive-codex-harness-v6.14:begin -->
## Adaptive Codex Harness v6.14 — task contract / empirical Harness tuning
- Before substantial work, keep a compact current-task contract: requested outcome, in-scope artifact/behavior, completion evidence, and explicit non-goals. The latest user correction/review overrides older conflicting assumptions.
- Stay on the current task. Do not switch to an adjacent unresolved topic merely because it appears in prior context, docs, or telemetry.
- When a review/checklist is an input to a plan, reconcile every actionable item: reflect it in the plan or explicitly mark why it is not applicable. Do not silently drop review requests.
- Preserve v6.13 proportional verification and minimal-edit behavior: prove changed behavior/direct risk only, and stop when sufficient evidence exists.
- Do not respond to a single Harness failure by stacking another global rule. First make the failure reproducible when practical, add/update a focused eval scenario, then change one behavioral theme at a time.
- Harness evals are maintainer-only and explicit. Run `$harness-eval` for changes to Harness instructions/skills/hooks/policies; do not run Harness evals for ordinary application changes and do not attach them to normal Stop/verify hooks.
- Use fresh-session traces and deterministic graders first. Use holdout scenarios only for final candidate checks, not while tuning against the visible core set.
<!-- adaptive-codex-harness-v6.14:end -->"""

HARNESS_EVAL_SKILL = """---
name: harness-eval
description: Evaluate changes to Adaptive Codex Harness instructions, skills, hooks, or policies with fresh Codex sessions and deterministic regression scenarios. Do not use for ordinary application changes.
---

# Harness eval

Use this only when the task changes Harness behavior itself, such as `AGENTS.md`,
`.agents/skills/`, `.codex/harness/`, hooks, policies, or installer-managed guidance.

## Default workflow

1. Run deterministic Harness self-checks first:
   `python3 .codex/harness/scripts/selftest.py`
2. Run the smallest relevant scenario while iterating:
   `python3 .codex/harness/scripts/harness_eval.py --scenario <id>`
3. After the candidate is coherent, run the visible core suite once:
   `python3 .codex/harness/scripts/harness_eval.py --suite core`
4. Before accepting a Harness release candidate, run the holdout set once:
   `python3 .codex/harness/scripts/harness_eval.py --suite core --include-holdout`
5. For a noisy or model-sensitive change, use `--repeats 3` and compare median score,
   critical-pass rate, command count, and changed-file count.
6. Inspect a failed trace/diff before changing instructions. Do not broaden rules merely
   to satisfy one ambiguous run.

## Tuning discipline

- One behavioral theme per tuning iteration.
- `[critical]` expectations are release-blocking for the scenario.
- Core scenarios are for iteration; holdout scenarios are for final candidate checks.
- Prefer deterministic graders over subjective judging.
- A failed command is not the same thing as the business/domain condition the command
  was intended to inspect.
- Keep the eval runner out of normal project verification and Stop hooks.

Artifacts are written below `.harness/runtime/evals/`.
"""

REQUIREMENTS = {
    "version": VERSION,
    "policy": {
        "execution": "manual_only",
        "fresh_session_per_run": True,
        "ordinary_project_tasks_run_evals": False,
        "holdout_during_routine_tuning": False,
        "one_behavioral_theme_per_tuning_iteration": True,
    },
    "requirements": [
        {
            "id": "task-current",
            "critical": True,
            "description": "Stay on the latest requested task and honor later corrections over older conflicting context.",
        },
        {
            "id": "review-plan-reconciliation",
            "critical": True,
            "description": "Every actionable review item is reflected in the plan or explicitly rejected with a reason.",
        },
        {
            "id": "minimal-edit",
            "critical": True,
            "description": "Local changes preserve unrelated existing content and avoid whole-file rewrite churn.",
        },
        {
            "id": "verification-proportionality",
            "critical": True,
            "description": "Verification is limited to changed behavior and concrete directly affected risk.",
        },
        {
            "id": "command-vs-condition",
            "critical": True,
            "description": "A command execution failure is not reported as the inspected business/domain condition.",
        },
        {
            "id": "bounded-work",
            "critical": False,
            "description": "Avoid command thrashing, unnecessary scans, and unrelated file changes.",
        },
    ],
}

SCENARIOS: dict[str, dict[str, Any]] = {
    "median-review-to-plan": {
        "id": "median-review-to-plan",
        "suite": "core",
        "kind": "median",
        "requirements": ["review-plan-reconciliation", "task-current", "bounded-work"],
        "prompt": (
            "review.md の指摘を plan.md に反映してください。実装はしないでください。"
            "review.md の actionable な指摘を漏れなく反映し、無関係なファイルは変更しないでください。"
        ),
        "files": {
            "review.md": (
                "# Review\n\n"
                "- 境界値 05:00 の扱いを計画に明記する。\n"
                "- timezone は Asia/Tokyo 固定前提を計画に明記する。\n"
                "- 検証は対象テストだけに限定し、全テストは既定にしない。\n"
            ),
            "plan.md": (
                "# Plan\n\n"
                "1. overtime calculation を修正する。\n"
                "2. テストする。\n"
            ),
            "app.py": "def calculate(value):\n    return value\n",
        },
        "expect": {
            "changed_paths_exact": ["plan.md"],
            "required_file_contains": {
                "plan.md": ["05:00", "Asia/Tokyo", "対象テスト"],
            },
            "commands": {"max_count": 10},
        },
    },
    "edge-minimal-edit": {
        "id": "edge-minimal-edit",
        "suite": "core",
        "kind": "edge",
        "requirements": ["minimal-edit", "bounded-work"],
        "prompt": (
            "settings.py の REQUEST_TIMEOUT = 30 を 45 に変更してください。"
            "それ以外の設定・コメント・並び順は変えないでください。"
        ),
        "files": {
            "settings.py": (
                "# application settings\n"
                "REQUEST_TIMEOUT = 30\n"
                + "".join(f"SETTING_{i:03d} = {i}\n" for i in range(1, 101))
            ),
        },
        "expect": {
            "changed_paths_exact": ["settings.py"],
            "required_file_contains": {"settings.py": ["REQUEST_TIMEOUT = 45"]},
            "diff_limits": {"settings.py": {"max_added": 2, "max_deleted": 2}},
            "commands": {"max_count": 8},
        },
    },
    "edge-verification-scope": {
        "id": "edge-verification-scope",
        "suite": "core",
        "kind": "edge",
        "requirements": ["verification-proportionality", "bounded-work"],
        "prompt": (
            "calculator.py の round_total だけを、小数点以下2桁ではなく1桁に丸めるよう変更してください。"
            "必要な最小検証だけ行い、無関係なテストや全テストは実行しないでください。"
        ),
        "files": {
            "calculator.py": "def round_total(value):\n    return round(value, 2)\n",
            "tests/test_calculator.py": (
                "import unittest\nfrom calculator import round_total\n\n"
                "class TestCalculator(unittest.TestCase):\n"
                "    def test_round_total(self):\n"
                "        self.assertEqual(round_total(1.26), 1.3)\n\n"
                "if __name__ == '__main__': unittest.main()\n"
            ),
            "tests/test_unrelated.py": (
                "import unittest\n\n"
                "class TestUnrelated(unittest.TestCase):\n"
                "    def test_unrelated(self): self.assertTrue(True)\n"
            ),
        },
        "expect": {
            "changed_paths_exact": ["calculator.py"],
            "required_file_contains": {"calculator.py": ["round(value, 1)"]},
            "commands": {
                "max_count": 12,
                "forbidden_regex": [
                    r"(?i)(^|\s)(pytest|py\.test)\s*(?:$|[;&|])",
                    r"(?i)python(?:3)?\s+-m\s+unittest\s+discover\b",
                    r"(?i)(npm|pnpm|yarn)\s+test\b",
                ],
            },
        },
    },
    "edge-context-continuity": {
        "id": "edge-context-continuity",
        "suite": "core",
        "kind": "edge",
        "requirements": ["task-current", "bounded-work"],
        "prompt": (
            "task_context.md に書かれている前の決定の続きとして、module_a.py の TODO だけ実装してください。"
            "module_b.py は別件なので触らないでください。"
        ),
        "files": {
            "task_context.md": (
                "# Current task\n"
                "module_a.py の normalize_name は前後空白だけ除去する。"
                "大文字小文字変換や module_b.py の変更はしない。\n"
            ),
            "module_a.py": "def normalize_name(value):\n    # TODO\n    return value\n",
            "module_b.py": "def normalize_code(value):\n    return value.upper()\n",
        },
        "expect": {
            "changed_paths_exact": ["module_a.py"],
            "required_file_contains": {"module_a.py": [".strip()"]},
            "commands": {"max_count": 10},
        },
    },
    "edge-command-failure-classification": {
        "id": "edge-command-failure-classification",
        "suite": "core",
        "kind": "edge",
        "requirements": ["command-vs-condition", "bounded-work"],
        "prompt": (
            "python3 check_state.py を実行して作業ツリーの状態を判定し、結果を簡潔に説明してください。"
            "ファイル変更は不要です。コマンド自体の失敗と、dirty/clean の判定結果を混同しないでください。"
        ),
        "files": {
            "check_state.py": (
                "import sys\n"
                "print('permission denied: cannot inspect git status', file=sys.stderr)\n"
                "raise SystemExit(2)\n"
            ),
            "README.md": (
                "check_state.py exit codes: 0=clean, 1=dirty, 2=inspection command failed; state is unknown.\n"
            ),
        },
        "expect": {
            "changed_paths_exact": [],
            "commands": {
                "required_regex": [r"(?i)python3?\s+check_state\.py"],
                "max_count": 8,
            },
            "final_response": {
                "required_any_regex": [
                    r"(?i)permission denied",
                    r"判定(?:でき|不能|不可)",
                    r"コマンド.*失敗",
                    r"状態.*不明",
                    r"unknown",
                ],
                "forbidden_regex": [
                    r"未コミット変更(?:が|は)あ(?:る|ります)",
                    r"(?i)worktree is dirty",
                ],
            },
        },
    },
    "holdout-doc-only-no-tests": {
        "id": "holdout-doc-only-no-tests",
        "suite": "holdout",
        "kind": "holdout",
        "requirements": ["verification-proportionality", "task-current", "bounded-work"],
        "prompt": (
            "README.md の `Timeout: 30 seconds` を `Timeout: 45 seconds` に訂正してください。"
            "コード変更やテスト実行は不要です。"
        ),
        "files": {
            "README.md": "# Settings\n\nTimeout: 30 seconds\n",
            "app.py": "TIMEOUT = 45\n",
            "tests/test_app.py": "def test_timeout():\n    assert True\n",
        },
        "expect": {
            "changed_paths_exact": ["README.md"],
            "required_file_contains": {"README.md": ["Timeout: 45 seconds"]},
            "commands": {
                "max_count": 6,
                "forbidden_regex": [
                    r"(?i)\b(pytest|phpunit|pest)\b",
                    r"(?i)python(?:3)?\s+-m\s+unittest\b",
                    r"(?i)(npm|pnpm|yarn)\s+test\b",
                ],
            },
        },
    },
}

RUBRIC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "scenario_id": {"type": "string"},
        "critical_pass": {"type": "boolean"},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "pass": {"type": "boolean"},
                    "critical": {"type": "boolean"},
                    "notes": {"type": "string"},
                },
                "required": ["id", "pass", "critical", "notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scenario_id", "critical_pass", "score", "checks"],
    "additionalProperties": False,
}

HARNESS_EVAL_RUNNER = r"""#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HARNESS_DIR = ROOT / ".codex" / "harness"
EVAL_ROOT = HARNESS_DIR / "evals"
SCENARIO_ROOT = EVAL_ROOT / "scenarios"
RUNTIME_ROOT = ROOT / ".harness" / "runtime" / "evals"

IGNORED_STATUS = (
    ".harness/**",
    ".codex/harness/runtime/**",
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
)

def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")

def ignored(path: str) -> bool:
    p = norm(path)
    return any(fnmatch.fnmatch(p, pat) for pat in IGNORED_STATUS)

def run(cmd: list[str], cwd: Path, *, timeout: int | None = None, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )

def git(root: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], root, timeout=timeout)

def select_scenarios(ids: list[str], suite: str, include_holdout: bool) -> list[dict[str, Any]]:
    all_items = [load_json(p) for p in sorted(SCENARIO_ROOT.glob("*.json"))]
    all_items = [x for x in all_items if x.get("id")]
    if ids:
        by_id = {str(x["id"]): x for x in all_items}
        missing = [x for x in ids if x not in by_id]
        if missing:
            raise SystemExit("unknown scenario(s): " + ", ".join(missing))
        return [by_id[x] for x in ids]
    selected = [x for x in all_items if x.get("suite") == suite]
    if include_holdout:
        selected += [x for x in all_items if x.get("suite") == "holdout" and x not in selected]
    return selected

def copytree_filtered(src: Path, dst: Path, *, exclude: tuple[str, ...] = ()) -> None:
    if not src.exists():
        return
    def ignore(base: str, names: list[str]) -> set[str]:
        base_path = Path(base)
        rel_base = base_path.relative_to(src).as_posix() if base_path != src else ""
        ignored_names = set()
        for name in names:
            rel = f"{rel_base}/{name}".lstrip("/")
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat) for pat in exclude):
                ignored_names.add(name)
        return ignored_names
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)

def patch_scratch_config(workspace: Path) -> None:
    path = workspace / ".codex" / "harness" / "config.json"
    data = load_json(path)
    layout = data.setdefault("project_layout", {})
    if isinstance(layout, dict):
        layout["git_roots"] = ["."]
        layout["application_root"] = "."
        layout["knowledge_root"] = "docs"
    gate = data.setdefault("quality_gate", {})
    if isinstance(gate, dict):
        # Scenarios grade behavior directly. Disable ordinary project Stop gating so
        # project-specific verification commands cannot contaminate scratch evals.
        gate["enabled"] = False
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def create_workspace(scenario: dict[str, Any], workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=False)
    shutil.copy2(ROOT / "AGENTS.md", workspace / "AGENTS.md")
    (workspace / ".codex").mkdir(parents=True, exist_ok=True)

    for rel in (".codex/config.toml", ".codex/hooks.json"):
        src = ROOT / rel
        if src.is_file():
            dst = workspace / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Exclude eval definitions/runner so the tested agent cannot read the answer key.
    copytree_filtered(
        ROOT / ".codex" / "harness",
        workspace / ".codex" / "harness",
        exclude=(
            "evals",
            "evals/**",
            "scripts/harness_eval.py",
            "installed-manifest.json",
            "V6_14.md",
        ),
    )
    copytree_filtered(ROOT / ".codex" / "rules", workspace / ".codex" / "rules")
    copytree_filtered(
        ROOT / ".agents" / "skills",
        workspace / ".agents" / "skills",
        exclude=("harness-eval", "harness-eval/**"),
    )

    (workspace / "docs").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "index.md").write_text(
        "# Eval fixture docs\n\nNo additional project documents are required for this scenario.\n",
        encoding="utf-8",
    )
    patch_scratch_config(workspace)

    files = scenario.get("files", {})
    if not isinstance(files, dict):
        raise RuntimeError("scenario files must be an object")
    for rel, content in files.items():
        path = workspace / norm(str(rel))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")

    cp = git(workspace, "init", "-q")
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or "git init failed")
    git(workspace, "config", "user.email", "harness-eval@example.invalid")
    git(workspace, "config", "user.name", "Harness Eval")
    cp = git(workspace, "add", "-A")
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or "git add failed")
    cp = git(workspace, "commit", "-qm", "eval baseline")
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or "git commit failed")

def parse_jsonl(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events

def command_strings(events: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = item.get("command")
        if isinstance(command, str):
            commands.append(command)
    return commands

def collect_text(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            out.extend(collect_text(value))
    elif isinstance(obj, list):
        for value in obj:
            out.extend(collect_text(value))
    return out

# def final_response(events: list[dict[str, Any]], stdout: str) -> str:
#     candidates: list[str] = []
#     for event in events:
#         if event.get("type") != "item.completed":
#             continue
#         item = event.get("item")
#         if not isinstance(item, dict):
#             continue
#         if item.get("type") in {"agent_message", "message"}:
#             candidates.extend(collect_text(item))
#     if candidates:
#         return "\n".join(candidates[-4:])
#     return stdout[-8000:]

def final_response(events: list[dict[str, Any]], stdout: str) -> str:
    response = ""
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"agent_message", "message"}:
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                response = text
    if response:
        return response
    return stdout[-8000:]

def status_paths(workspace: Path) -> list[str]:
    cp = git(workspace, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if cp.returncode != 0:
        return ["<git-status-failed>"]
    chunks = cp.stdout.split("\0")
    paths: set[str] = set()
    i = 0
    while i < len(chunks):
        item = chunks[i]
        if not item:
            i += 1
            continue
        if len(item) >= 4:
            code, raw = item[:2], item[3:]
            p = norm(raw)
            if not ignored(p):
                paths.add(p)
            if (code.startswith("R") or code.startswith("C")) and i + 1 < len(chunks) and chunks[i + 1]:
                old = norm(chunks[i + 1])
                if not ignored(old):
                    paths.add(old)
                i += 1
        i += 1
    return sorted(paths)

def numstat(workspace: Path) -> dict[str, tuple[int, int]]:
    cp = git(workspace, "diff", "--numstat", "HEAD")
    result: dict[str, tuple[int, int]] = {}
    if cp.returncode != 0:
        return result
    for line in cp.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, p = parts[0], parts[1], norm(parts[2])
        if ignored(p) or a == "-" or d == "-":
            continue
        try:
            result[p] = (int(a), int(d))
        except ValueError:
            pass
    return result

def add_check(checks: list[dict[str, Any]], cid: str, passed: bool, notes: str, critical: bool = True) -> None:
    checks.append({"id": cid, "pass": bool(passed), "critical": critical, "notes": notes})

def grade(scenario: dict[str, Any], workspace: Path, events: list[dict[str, Any]], stdout: str, exit_code: int) -> dict[str, Any]:
    expect = scenario.get("expect", {})
    checks: list[dict[str, Any]] = []
    changed = status_paths(workspace)
    stats = numstat(workspace)
    commands = command_strings(events)
    response = final_response(events, stdout)

    add_check(checks, "codex-exit", exit_code == 0, f"exit={exit_code}", critical=True)

    if "changed_paths_exact" in expect:
        wanted = sorted(norm(str(x)) for x in expect.get("changed_paths_exact", []))
        add_check(checks, "changed-paths", changed == wanted, f"actual={changed}; expected={wanted}")

    required = expect.get("required_file_contains", {})
    if isinstance(required, dict):
        for rel, needles in required.items():
            path = workspace / norm(str(rel))
            text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            values = [str(x) for x in needles] if isinstance(needles, list) else [str(needles)]
            missing = [x for x in values if x not in text]
            add_check(checks, f"contains:{rel}", not missing, "missing=" + repr(missing) if missing else "ok")

    limits = expect.get("diff_limits", {})
    if isinstance(limits, dict):
        for rel, cfg in limits.items():
            a, d = stats.get(norm(str(rel)), (0, 0))
            max_a = int(cfg.get("max_added", 10**9))
            max_d = int(cfg.get("max_deleted", 10**9))
            add_check(
                checks,
                f"diff:{rel}",
                a <= max_a and d <= max_d,
                f"+{a}/-{d}; limits +{max_a}/-{max_d}",
            )

    command_cfg = expect.get("commands", {})
    if isinstance(command_cfg, dict):
        max_count = command_cfg.get("max_count")
        if max_count is not None:
            add_check(checks, "command-count", len(commands) <= int(max_count), f"{len(commands)} <= {max_count}", critical=False)
        blob = "\n".join(commands)
        for idx, pattern in enumerate(command_cfg.get("required_regex", []) or []):
            ok = re.search(str(pattern), blob) is not None
            add_check(checks, f"command-required-{idx+1}", ok, str(pattern))
        for idx, pattern in enumerate(command_cfg.get("forbidden_regex", []) or []):
            hit = re.search(str(pattern), blob) is not None
            add_check(checks, f"command-forbidden-{idx+1}", not hit, str(pattern))

    response_cfg = expect.get("final_response", {})
    if isinstance(response_cfg, dict):
        required_any = response_cfg.get("required_any_regex", []) or []
        if required_any:
            matched = [p for p in required_any if re.search(str(p), response)]
            add_check(checks, "response-required-any", bool(matched), f"matched={matched}")
        for idx, pattern in enumerate(response_cfg.get("forbidden_regex", []) or []):
            hit = re.search(str(pattern), response) is not None
            add_check(checks, f"response-forbidden-{idx+1}", not hit, str(pattern))

    critical_pass = all(c["pass"] for c in checks if c["critical"])
    score = round(100 * sum(1 for c in checks if c["pass"]) / max(len(checks), 1))
    return {
        "scenario_id": scenario["id"],
        "kind": scenario.get("kind", "unknown"),
        "requirements": scenario.get("requirements", []),
        "critical_pass": critical_pass,
        "score": score,
        "checks": checks,
        "metrics": {
            "command_count": len(commands),
            "changed_file_count": len(changed),
            "changed_paths": changed,
        },
        "final_response_excerpt": response[-3000:],
    }

def save_diff(workspace: Path, path: Path) -> None:
    cp = git(workspace, "diff", "--no-ext-diff", "HEAD", timeout=30)
    path.write_text(cp.stdout + (("\n[stderr]\n" + cp.stderr) if cp.stderr else ""), encoding="utf-8")

def execute_one(scenario: dict[str, Any], run_dir: Path, repeat: int, timeout: int, keep_workspace: bool) -> dict[str, Any]:
    case_dir = run_dir / f"{scenario['id']}-r{repeat}"
    case_dir.mkdir(parents=True, exist_ok=False)
    workspace = case_dir / "workspace"
    create_workspace(scenario, workspace)

    prompt = str(scenario.get("prompt", "")).strip()
    # cmd = ["codex", "exec", "--json", "--full-auto", prompt]
    cmd = [
        "codex",
        "-a", "never",
        "-s", "workspace-write",
        "exec",
        "--json",
        prompt,
    ]
    started = time.time()
    try:
        cp = run(cmd, workspace, timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        cp = subprocess.CompletedProcess(cmd, 124, stdout=stdout, stderr=stderr)
        timed_out = True
    elapsed = round(time.time() - started, 3)

    (case_dir / "trace.jsonl").write_text(cp.stdout or "", encoding="utf-8")
    (case_dir / "stderr.log").write_text(cp.stderr or "", encoding="utf-8")
    save_diff(workspace, case_dir / "diff.patch")

    events = parse_jsonl(cp.stdout or "")
    result = grade(scenario, workspace, events, cp.stdout or "", cp.returncode)
    result["repeat"] = repeat
    result["elapsed_seconds"] = elapsed
    result["timed_out"] = timed_out
    (case_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not keep_workspace:
        shutil.rmtree(workspace, ignore_errors=True)
    return result

def validate_scenario(data: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    for key in ("id", "suite", "kind", "prompt", "files", "expect"):
        if key not in data:
            errors.append(f"{path.name}: missing {key}")
    if data.get("suite") not in {"core", "holdout"}:
        errors.append(f"{path.name}: suite must be core/holdout")
    if not isinstance(data.get("files"), dict):
        errors.append(f"{path.name}: files must be object")
    if not isinstance(data.get("expect"), dict):
        errors.append(f"{path.name}: expect must be object")
    return errors

def self_test() -> int:
    errors: list[str] = []
    req = load_json(EVAL_ROOT / "requirements.json")
    if req.get("version") != "6.14.0":
        errors.append("requirements version is not 6.14.0")
    paths = sorted(SCENARIO_ROOT.glob("*.json"))
    if not paths:
        errors.append("no eval scenarios")
    ids: set[str] = set()
    suites: set[str] = set()
    for path in paths:
        data = load_json(path)
        errors.extend(validate_scenario(data, path))
        sid = str(data.get("id", ""))
        if sid in ids:
            errors.append(f"duplicate scenario id: {sid}")
        ids.add(sid)
        suites.add(str(data.get("suite", "")))
    if "core" not in suites or "holdout" not in suites:
        errors.append("core and holdout suites are both required")
    if errors:
        for e in errors:
            print("[ERROR]", e)
        return 1
    print(f"harness eval self-test: PASS ({len(paths)} scenarios)")
    return 0

def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result["scenario_id"]), []).append(result)

    scenario_summary = {}
    for sid, rows in sorted(grouped.items()):
        scores = [int(r["score"]) for r in rows]
        commands = [int(r.get("metrics", {}).get("command_count", 0)) for r in rows]
        changed = [int(r.get("metrics", {}).get("changed_file_count", 0)) for r in rows]
        scenario_summary[sid] = {
            "runs": len(rows),
            "critical_pass_rate": sum(1 for r in rows if r["critical_pass"]) / len(rows),
            "median_score": statistics.median(scores),
            "median_command_count": statistics.median(commands),
            "median_changed_file_count": statistics.median(changed),
        }

    return {
        "version": "6.14.0",
        "scenario_count": len(grouped),
        "run_count": len(results),
        "critical_pass": all(r["critical_pass"] for r in results),
        "critical_pass_rate": (
            sum(1 for r in results if r["critical_pass"]) / len(results) if results else 0.0
        ),
        "median_score": statistics.median([int(r["score"]) for r in results]) if results else 0,
        "scenarios": scenario_summary,
    }

def print_summary(summary: dict[str, Any]) -> None:
    state = "PASS" if summary.get("critical_pass") else "FAIL"
    print(
        f"Harness eval: {state}; runs={summary.get('run_count', 0)}; "
        f"critical-pass-rate={summary.get('critical_pass_rate', 0):.0%}; "
        f"median-score={summary.get('median_score', 0)}"
    )
    for sid, row in summary.get("scenarios", {}).items():
        print(
            f"  {sid}: critical={row['critical_pass_rate']:.0%}, "
            f"median-score={row['median_score']}, commands={row['median_command_count']}, "
            f"changed-files={row['median_changed_file_count']}"
        )

def main() -> int:
    ap = argparse.ArgumentParser(description="Fresh-session deterministic evals for Adaptive Codex Harness")
    ap.add_argument("--scenario", action="append", default=[], help="Run only this scenario id (repeatable)")
    ap.add_argument("--suite", default="core", choices=["core", "holdout"])
    ap.add_argument("--include-holdout", action="store_true", help="Add holdout scenarios to the selected suite")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=300, help="Per Codex run timeout in seconds")
    ap.add_argument("--keep-workspaces", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    scenarios = select_scenarios(args.scenario, args.suite, args.include_holdout)
    if args.list:
        for s in scenarios:
            print(f"{s['id']}\t{s.get('suite')}\t{s.get('kind')}\t{','.join(s.get('requirements', []))}")
        return 0

    if not scenarios:
        print("No scenarios selected.", file=sys.stderr)
        return 2
    if args.repeats < 1 or args.repeats > 10:
        print("--repeats must be between 1 and 10", file=sys.stderr)
        return 2
    if shutil.which("codex") is None:
        print("codex executable not found in PATH", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = RUNTIME_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []

    print(f"Harness eval run: {run_id}")
    print(f"Scenarios: {len(scenarios)} x repeats {args.repeats}")
    for scenario in scenarios:
        for repeat in range(1, args.repeats + 1):
            print(f"==> {scenario['id']} [{repeat}/{args.repeats}]")
            result = execute_one(scenario, run_dir, repeat, args.timeout, args.keep_workspaces)
            results.append(result)
            print(
                f"    {'PASS' if result['critical_pass'] else 'FAIL'} "
                f"score={result['score']} commands={result['metrics']['command_count']} "
                f"changed={result['metrics']['changed_file_count']}"
            )

    summary = summarize(results)
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(summary)
    print(f"Artifacts: {run_dir.relative_to(ROOT)}")
    return 0 if summary["critical_pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
"""

class InstallError(RuntimeError):
    pass


@dataclass
class Plan:
    target: Path
    writes: dict[Path, bytes] = field(default_factory=dict)
    chmods: dict[Path, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def stage_text(self, rel: str, text: str) -> None:
        path = self.target / rel
        data = text.encode("utf-8")
        current = path.read_bytes() if path.is_file() else None
        if current != data:
            self.writes[path] = data

    def staged_or_disk(self, rel: str) -> bytes:
        path = self.target / rel
        if path in self.writes:
            return self.writes[path]
        if not path.is_file():
            raise InstallError(f"manifest target is missing: {rel}")
        return path.read_bytes()


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", text)
    if not match:
        raise InstallError(f"invalid Harness VERSION: {text!r}")
    return tuple(int(x) for x in match.groups())  # type: ignore[return-value]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InstallError(f"cannot read {path}: {exc}") from exc


def require_files(target: Path, rels: Iterable[str]) -> None:
    missing = [rel for rel in rels if not (target / rel).is_file()]
    if missing:
        raise InstallError("required file(s) missing: " + ", ".join(missing))


def validate_manifest(target: Path, expected_version: str) -> dict[str, Any]:
    manifest_path = target / ".codex/harness/installed-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise InstallError(f"installed-manifest.json is invalid: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != expected_version:
        raise InstallError(
            f"target VERSION expects installed manifest {expected_version}, "
            f"found {manifest.get('version') if isinstance(manifest, dict) else type(manifest).__name__}"
        )
    payload = manifest.get("payload_sha256")
    if not isinstance(payload, dict) or not payload:
        raise InstallError(f"{expected_version} installed manifest has no payload hashes")
    drift: list[str] = []
    for rel, expected in payload.items():
        path = target / str(rel)
        if not path.is_file() or sha256_file(path) != str(expected):
            drift.append(str(rel))
    if drift:
        raise InstallError(
            f"Existing {expected_version} Harness-owned drift detected: " + ", ".join(drift[:12])
        )
    return manifest


def upsert_managed_block(text: str, block: str, names: Iterable[str]) -> str:
    for name in names:
        begin = f"<!-- adaptive-codex-harness-{name}:begin -->"
        end = f"<!-- adaptive-codex-harness-{name}:end -->"
        if begin in text or end in text:
            if text.count(begin) != 1 or text.count(end) != 1:
                raise InstallError(f"malformed managed block {name}")
            start = text.index(begin)
            finish = text.index(end, start) + len(end)
            out = text[:start] + block + text[finish:]
            return out if out.endswith("\n") else out + "\n"
    base = text.rstrip()
    return (base + "\n\n" + block + "\n") if base else block + "\n"


def patch_config(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception as exc:
        raise InstallError(f"config.json is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("config.json root must be an object")
    meta = data.setdefault("harness_meta", {})
    if not isinstance(meta, dict):
        raise InstallError("config.harness_meta must be an object")
    meta["version"] = VERSION
    data["harness_eval"] = {
        "mode": "manual",
        "runner": ".codex/harness/scripts/harness_eval.py",
        "scenario_root": ".codex/harness/evals/scenarios",
        "runtime_root": ".harness/runtime/evals",
        "default_suite": "core",
        "default_repeats": 1,
        "ordinary_project_tasks": "disabled",
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def patch_minimal_policy(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception as exc:
        raise InstallError(f"minimal_edit_policy.json is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("minimal_edit_policy root must be an object")
    data["version"] = VERSION
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def patch_hooks(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception as exc:
        raise InstallError(f"hooks.json is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("hooks.json root must be an object")
    data["description"] = (
        "Adaptive Codex Harness v6.14 lifecycle, safety, proportional verification, "
        "task continuity, and manual empirical Harness evaluation."
    )
    blob = json.dumps(data, ensure_ascii=False)
    if "harness_eval.py" in blob:
        raise InstallError("harness_eval.py must remain manual-only and must not be registered in hooks.json")
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def patch_agents(text: str) -> str:
    return upsert_managed_block(text, AGENTS_BLOCK, ("v6.14", "v6.13", "v6.12", "v6.11", "v6.10"))


def patch_selftest(text: str) -> str:
    if "6.13.0" not in text and "6.14.0" not in text:
        raise InstallError("selftest.py does not contain a recognized v6.13/v6.14 version check")
    text = text.replace("6.13.0", "6.14.0")

    if '"harness-eval",' not in text:
        anchor = '    "harness-verify",\n'
        if anchor not in text:
            raise InstallError("selftest.py REQUIRED_SKILLS anchor not found")
        text = text.replace(anchor, anchor + '    "harness-eval",\n', 1)

    required = [
        ".codex/harness/scripts/harness_eval.py",
        ".codex/harness/evals/requirements.json",
        ".codex/harness/evals/rubric.schema.json",
        ".codex/harness/evals/scenarios/median-review-to-plan.json",
        ".codex/harness/evals/scenarios/edge-minimal-edit.json",
        ".codex/harness/evals/scenarios/edge-verification-scope.json",
        ".codex/harness/evals/scenarios/edge-context-continuity.json",
        ".codex/harness/evals/scenarios/edge-command-failure-classification.json",
        ".codex/harness/evals/scenarios/holdout-doc-only-no-tests.json",
    ]
    anchor = '    ".codex/harness/scripts/minimal_diff_guard.py",\n'
    if anchor not in text:
        raise InstallError("selftest.py REQUIRED_FILES anchor not found")
    additions = "".join(f'    "{rel}",\n' for rel in required if f'"{rel}"' not in text)
    if additions:
        text = text.replace(anchor, anchor + additions, 1)

    marker = "# adaptive-codex-harness-v6.14-eval-selftest:begin"
    if marker not in text:
        insertion_anchor = '    py_files = list((HARNESS_DIR / "scripts").glob("*.py")) + list((HARNESS_DIR / "hooks").glob("*.py"))\n'
        if insertion_anchor not in text:
            raise InstallError("selftest.py Python syntax anchor not found")
        block = (
            '    # adaptive-codex-harness-v6.14-eval-selftest:begin\n'
            '    eval_runner = SCRIPT_DIR / "harness_eval.py"\n'
            '    if eval_runner.exists():\n'
            '        cp = subprocess.run(\n'
            '            [sys.executable, str(eval_runner), "--self-test"],\n'
            '            cwd=WORKSPACE_ROOT,\n'
            '            text=True,\n'
            '            stdout=subprocess.PIPE,\n'
            '            stderr=subprocess.STDOUT,\n'
            '            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},\n'
            '            timeout=15,\n'
            '        )\n'
            '        if cp.returncode == 0:\n'
            '            ok("Harness eval definitions self-test")\n'
            '        else:\n'
            '            err("Harness eval definitions self-test failed: " + cp.stdout.strip()[-1200:])\n'
            '    # adaptive-codex-harness-v6.14-eval-selftest:end\n'
        )
        text = text.replace(insertion_anchor, block + insertion_anchor, 1)
    return text


def patch_minimal_edit_pretool(text: str) -> str:
    text = text.replace("Adaptive Harness v6.13", "Adaptive Harness v6.14")
    additions = (
        '    ".codex/harness/scripts/harness_eval.py",\n'
        '    ".codex/harness/evals/",\n'
        '    ".agents/skills/harness-eval/",\n'
    )
    if '".codex/harness/evals/"' not in text:
        anchor = '    ".codex/harness/minimal_edit_policy.json",\n'
        if anchor not in text:
            raise InstallError("minimal_edit_pretool.py PROTECTED anchor not found")
        text = text.replace(anchor, anchor + additions, 1)
    return text


def patch_pre_tool_safety(text: str) -> str:
    additions = (
        '    ".codex/harness/scripts/harness_eval.py",\n'
        '    ".codex/harness/evals/",\n'
        '    ".agents/skills/harness-eval/",\n'
    )
    if '".codex/harness/evals/"' not in text:
        anchor = '    ".codex/harness/scripts/verify.py",\n'
        if anchor not in text:
            raise InstallError("pre_tool_safety.py PROTECTED_PATHS anchor not found")
        text = text.replace(anchor, anchor + additions, 1)
    return text


def eval_file_payloads() -> dict[str, str]:
    payloads = {
        ".codex/harness/evals/requirements.json": json.dumps(REQUIREMENTS, ensure_ascii=False, indent=2) + "\n",
        ".codex/harness/evals/rubric.schema.json": json.dumps(RUBRIC_SCHEMA, ensure_ascii=False, indent=2) + "\n",
        ".codex/harness/scripts/harness_eval.py": HARNESS_EVAL_RUNNER,
        ".agents/skills/harness-eval/SKILL.md": HARNESS_EVAL_SKILL,
    }
    for sid, scenario in SCENARIOS.items():
        payloads[f".codex/harness/evals/scenarios/{sid}.json"] = (
            json.dumps(scenario, ensure_ascii=False, indent=2) + "\n"
        )
    return payloads


def manifest_text(plan: Plan, previous_manifest: dict[str, Any]) -> str:
    old_payload = previous_manifest.get("payload_sha256", {})
    if not isinstance(old_payload, dict):
        raise InstallError("previous manifest payload is invalid")
    rels = {str(rel) for rel in old_payload}

    for path in plan.writes:
        rel = path.relative_to(plan.target).as_posix()
        if rel.startswith(".codex/harness/") or rel.startswith(".agents/skills/"):
            rels.add(rel)

    explicit_new = set(eval_file_payloads()) | {".codex/harness/V6_14.md"}
    rels.update(explicit_new)
    rels.discard("AGENTS.md")
    rels.discard(".codex/harness/config.json")
    rels.discard(".codex/harness/commands.json")
    rels.discard(".codex/harness/architecture_rules.json")
    rels.discard(".codex/harness/installed-manifest.json")

    payload: dict[str, str] = {}
    for rel in sorted(rels):
        path = plan.target / rel
        if path in plan.writes:
            payload[rel] = sha256_bytes(plan.writes[path])
        elif path.is_file():
            payload[rel] = sha256_file(path)
        elif rel in explicit_new:
            raise InstallError(f"new manifest target was not staged: {rel}")
        else:
            raise InstallError(f"existing manifest target disappeared: {rel}")
    return json.dumps({"version": VERSION, "payload_sha256": payload}, ensure_ascii=False, indent=2) + "\n"


def build_plan(target: Path) -> Plan:
    required = [
        "AGENTS.md",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/harness/VERSION",
        ".codex/harness/config.json",
        ".codex/harness/installed-manifest.json",
        ".codex/harness/minimal_edit_policy.json",
        ".codex/harness/hooks/pre_tool_safety.py",
        ".codex/harness/hooks/minimal_edit_pretool.py",
        ".codex/harness/scripts/selftest.py",
    ]
    require_files(target, required)

    current = parse_version(load_text(target / ".codex/harness/VERSION"))
    if current not in SUPPORTED_FROM:
        raise InstallError(f"supported source versions are 6.13.0/6.14.0, found {current}")

    expected_manifest_version = "6.13.0" if current == (6, 13, 0) else VERSION
    previous_manifest = validate_manifest(target, expected_manifest_version)

    plan = Plan(target=target)
    plan.stage_text(".codex/harness/VERSION", VERSION + "\n")
    plan.stage_text(".codex/harness/V6_14.md", V614_DOC)
    plan.stage_text(".codex/harness/config.json", patch_config(load_text(target / ".codex/harness/config.json")))
    plan.stage_text(
        ".codex/harness/minimal_edit_policy.json",
        patch_minimal_policy(load_text(target / ".codex/harness/minimal_edit_policy.json")),
    )
    plan.stage_text(".codex/hooks.json", patch_hooks(load_text(target / ".codex/hooks.json")))
    plan.stage_text("AGENTS.md", patch_agents(load_text(target / "AGENTS.md")))
    plan.stage_text(
        ".codex/harness/scripts/selftest.py",
        patch_selftest(load_text(target / ".codex/harness/scripts/selftest.py")),
    )
    plan.stage_text(
        ".codex/harness/hooks/minimal_edit_pretool.py",
        patch_minimal_edit_pretool(load_text(target / ".codex/harness/hooks/minimal_edit_pretool.py")),
    )
    plan.stage_text(
        ".codex/harness/hooks/pre_tool_safety.py",
        patch_pre_tool_safety(load_text(target / ".codex/harness/hooks/pre_tool_safety.py")),
    )

    for rel, content in eval_file_payloads().items():
        plan.stage_text(rel, content)

    runner = target / ".codex/harness/scripts/harness_eval.py"
    current_mode = (runner.stat().st_mode & 0o7777) if runner.exists() else 0o644
    desired_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if current_mode != desired_mode:
        plan.chmods[runner] = desired_mode

    plan.stage_text(
        ".codex/harness/installed-manifest.json",
        manifest_text(plan, previous_manifest),
    )
    return plan


def rel_to_target(target: Path, path: Path) -> Path:
    try:
        return path.relative_to(target)
    except ValueError as exc:
        raise InstallError(f"path escapes target: {path}") from exc


def atomic_write(path: Path, data: bytes, mode: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.v614-", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode if mode is not None else 0o644)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def run_checked(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    cp = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if cp.returncode != 0:
        raise InstallError(f"check failed ({' '.join(cmd)}):\n{cp.stdout.rstrip()}")
    return cp.stdout


def run_checks(target: Path) -> None:
    for base in (target / ".codex/harness/scripts", target / ".codex/harness/hooks"):
        for path in base.glob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    for rel in (
        ".codex/harness/config.json",
        ".codex/harness/commands.json",
        ".codex/harness/architecture_rules.json",
        ".codex/harness/minimal_edit_policy.json",
        ".codex/harness/installed-manifest.json",
        ".codex/harness/evals/requirements.json",
        ".codex/harness/evals/rubric.schema.json",
        ".codex/hooks.json",
    ):
        path = target / rel
        if path.is_file():
            json.loads(path.read_text(encoding="utf-8"))

    for path in (target / ".codex/harness/evals/scenarios").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))

    try:
        import tomllib
        tomllib.loads((target / ".codex/config.toml").read_text(encoding="utf-8"))
    except ImportError:
        pass
    except Exception as exc:
        raise InstallError(f"config.toml parse failed: {exc}") from exc

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run_checked(
        [sys.executable, str(target / ".codex/harness/scripts/harness_eval.py"), "--self-test"],
        target,
        env,
    )
    run_checked(
        [sys.executable, str(target / ".codex/harness/scripts/selftest.py"), "--install-check", "--quiet"],
        target,
        env,
    )


def backup_path(backup_root: Path, target: Path, path: Path) -> Path:
    return backup_root / rel_to_target(target, path)


def copy_to_backup(backup_root: Path, target: Path, path: Path) -> None:
    dest = backup_path(backup_root, target, path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, dest, copy_function=shutil.copy2)
    else:
        shutil.copy2(path, dest)


def restore_from_backup(backup_root: Path, target: Path, path: Path) -> None:
    src = backup_path(backup_root, target, path)
    if not src.exists():
        return
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, path, copy_function=shutil.copy2)
    else:
        shutil.copy2(src, path)


def apply_plan(plan: Plan, dry_run: bool) -> int:
    target = plan.target
    writes = sorted(plan.writes)
    chmods = sorted(plan.chmods)
    changed = bool(writes or chmods)

    print(f"Adaptive Codex Harness v6.14 target: {target}")
    for note in plan.notes:
        print(f"  NOTE {note}")
    if not changed:
        print("No changes required; Harness is already at the v6.14 target state.")
        return 0

    prefix = "WOULD " if dry_run else ""
    for path in writes:
        print(f"  {prefix}UPDATE {rel_to_target(target, path)}")
    for path in chmods:
        print(f"  {prefix}CHMOD +x {rel_to_target(target, path)}")
    if dry_run:
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = target / ".harness/backups" / f"v6.14-{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    existed: set[Path] = set()

    try:
        for path in sorted(set(writes) | set(chmods)):
            if path.exists():
                copy_to_backup(backup_root, target, path)
                existed.add(path)

        for path, data in plan.writes.items():
            mode = (path.stat().st_mode & 0o7777) if path.exists() else None
            atomic_write(path, data, mode)

        for path, mode in plan.chmods.items():
            if path.exists():
                os.chmod(path, mode)

        run_checks(target)

        history = target / ".harness/state/install-history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(),
            "to": VERSION,
            "backup": str(backup_root.relative_to(target)),
            "changed_files": len(writes),
            "theme": "manual empirical harness evals",
        }
        with history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    except Exception:
        for path in reversed(writes):
            src = backup_path(backup_root, target, path)
            if src.exists():
                restore_from_backup(backup_root, target, path)
            elif path not in existed and path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        for path in chmods:
            src = backup_path(backup_root, target, path)
            if src.exists():
                shutil.copy2(src, path)
            elif path not in existed and path.exists():
                path.unlink()
        raise

    print(f"Installed Harness {VERSION}")
    print(f"Backup: {backup_root.relative_to(target)}")
    print("Post-install deterministic selftest: PASS")
    print("Harness evals were NOT run automatically.")
    print("Manual core eval: python3 .codex/harness/scripts/harness_eval.py --suite core")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adaptive Codex Harness v6.13 -> v6.14 empirical-eval installer"
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Harness workspace root (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without writing",
    )
    args = parser.parse_args()
    target = Path(args.target).expanduser().resolve()

    try:
        return apply_plan(build_plan(target), args.dry_run)
    except InstallError as exc:
        print(f"[install_v6_14:ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"[install_v6_14:ERROR] unexpected failure: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
