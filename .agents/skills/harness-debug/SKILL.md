---
name: harness-debug
description: Debug with GPT-5.6 Sol high and bounded context. Prefer one reproducible failure path and one evidence-backed hypothesis at a time; avoid broad rescans and repeated commands.
---
# Harness Debug — Adaptive Execution Discipline

1. Start with the smallest reproducible failure and exact error/symbol/route search.
2. Read the failing path and nearest callers/callees only; broaden scope only when evidence points outward.
3. Keep one evidence-backed hypothesis at a time for one failure path. Do not ask multiple agents to inspect the same failure.
4. Use a second subagent only for a genuinely independent failure in non-overlapping code where serial diagnosis would be materially slow. Maximum two; no nested delegation.
5. Capture verbose output with `quiet_exec.py` or runtime files. Expose only bounded error neighborhoods first.
6. Prefer targeted reproduction during iteration. Do not rerun the same unchanged failing command repeatedly; after two unproductive attempts, synthesize evidence and choose a narrower discriminating check.
7. Avoid opportunistic refactors while debugging. Make the smallest root-cause fix that preserves project conventions.
8. Run final registered verification once after the fix; use `--detail` before `--raw` on failure.
9. Reviewer and Knowledge updates remain conditional, not automatic.

### v6.5 debug safety
- Harness-generated debug logs/state belong under `.harness/`; do not write runtime data below `.codex/` or `.agents/`.
- Prefer read-only diagnostics. Persistent/external mutation is not diagnosis.
- Do not run tests until both DB and side-effect guards pass. Do not assume `phpunit.xml` wins over populated container environment unless `force="true"` is verified.
- For HTTP, mail, queue, storage/NAS/S3, printer/CUPS, external processes, scheduler/worker, and remote-transfer problems, inspect configuration/logs/read-only status first. Do not send a real probe that creates, updates, deletes, prints, emails, uploads, or queues work merely to reproduce an issue.
- Interactive DB or SMB shells are denied because later input is not rechecked by `PreToolUse`; use bounded non-interactive read-only commands.
- If a missing table/data/file issue is found, first determine whether it is drift, accidental deletion, wrong connection/path, or pre-existing state. Do not reconstruct/restore persistent state without explicit user supervision.

### v6.6 investigation semantics
- A bug/TODO/question memo is a hypothesis/work queue, not a source of truth about current behavior.
- For `確認`, `調査`, `状況`, or equivalent requests, validate the memo against current code/config/schema/scheduler/tests/Git state before reporting status.
- Do not report the memo's wording itself as the finding. Report `confirmed`, `already fixed`, `partially fixed`, `not reproducible from code`, or `insufficient evidence`, with the smallest useful evidence trail.
- Inspect uncommitted task-relevant changes before concluding that a known bug still exists.

### v6.7 conversation continuity
- Debug follow-ups inherit the active reproduction target and expected behavior unless the user changes them.
- Never replace the active target with a different example to make diagnosis easier. Additional examples are secondary evidence only.
- When the user asks what happens "if it is switched/changed" after naming a specific target earlier, test or reason about that specific target unless the new turn explicitly changes it.
- A correction from the user overrides the conflicting debug assumption immediately; retain the remaining context.

<!-- adaptive-codex-harness-v6.9-execution-safety:begin -->
### v6.9 execution-diagnosis policy
- Identify the exact/latest run before interpreting logs; retain the first causal failure and exit/status code.
- Keep execution/runtime failure distinct from business-condition mismatch.
- Distinguish success, timeout, user cancel, signal termination, dependency failure, and normal failure.
- Compare requested operation with the effective operation after wrappers, environment injection, cwd/user/container/mount/default resolution.
- Redact secrets and personal data before surfacing command/env/stderr/HTTP context; keep non-secret diagnostic evidence such as error category, exit code, parameter name, service, and run ID.
- Treat progress messages as non-terminal; verify final state and any rollback/cleanup result.
<!-- adaptive-codex-harness-v6.9-execution-safety:end -->

<!-- adaptive-codex-harness-v6.10:begin -->
### v6.10 minimal edits / explanation clarity
- Preserve unchanged existing content; use targeted patches instead of whole-file regeneration.
- Run `python3 .codex/harness/scripts/minimal_diff_guard.py` before expensive/final verification.
- Explain bugs briefly: normally 1–3 sentences.
- Include only the concrete code value/boundary or calculation needed to understand the cause.
- Do not mechanically enumerate every internal step or repeat the same fact in multiple forms.
<!-- adaptive-codex-harness-v6.10:end -->
