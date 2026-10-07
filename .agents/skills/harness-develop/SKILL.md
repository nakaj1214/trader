---
name: harness-develop
description: Develop with GPT-5.6 Sol high while minimizing duplicated context, scope creep, repeated verification, and unnecessary artifacts. One parent agent by default; at most two narrowly scoped subagents only when materially faster.
---
# Harness Develop — Adaptive Execution Discipline

1. Keep GPT-5.6 Sol with high reasoning. Save usage by reducing duplicate reading and unnecessary model work, not model capability.
2. Start in the parent agent. Do not spawn planner/explorer/worker agents by default.
3. Define the requested scope before broad exploration. Do not fix adjacent issues, refactor unrelated code, rename/move files, or reformat unrelated areas. Report noteworthy out-of-scope findings instead.
4. Build a compact deterministic inventory first (`rg -l`, exact symbols/routes, `git diff --name-only`, `change_inventory.py`). If more than about 12 candidate files appear relevant, partition into workstreams before reading them all.
5. Read only task-relevant ranges. For large files, locate symbols first and read targeted ranges; do not repeatedly reread unchanged files without a new concrete question.
6. Delegate only when ALL are true: at least two substantial workstreams remain; scopes are independent and mostly non-overlapping; serial execution would be materially slow; each subagent has a narrow file/symbol boundary and concrete deliverable. Maximum two concurrent subagents; no nested delegation.
7. Subagents return compact findings (paths, symbols, mismatches, risks), not source dumps. Keep integration, cross-cutting decisions, implementation order, and final synthesis in the parent.
8. Prefer existing dependencies, helpers, abstractions, files, factories, and conventions. Add a dependency/new architectural layer/new file only when the requested behavior genuinely needs a new responsibility; do not scaffold speculatively.
9. Keep temporary audits, inventories, generated diagnostics, and raw logs under `.harness/runtime/`. Do not create tracked audit/report/plan files unless the user requested them or they are durable project knowledge.
10. Batch related edits before running targeted checks. Do not run a test/lint/build after every tiny file edit. Re-run a previously passing targeted check only when later edits can invalidate it.
11. During iteration use the smallest relevant deterministic check. Run registered full Harness verification once against the final diff unless later edits invalidate it.
12. Route potentially large command/search/diff output through `quiet_exec.py`, `verify.py`, or runtime files. Inspect `git diff --stat`/`--name-only` before a large full diff; inspect per-file hunks as needed.
13. Test creation is risk-based: extend the nearest coherent existing test by default; bug fixes get the smallest regression test; avoid duplicate behavior across layers and coverage-only tests.
14. Independent review is conditional. When the quality gate requires it, use `$harness-review`; do not launch a reviewer merely because several files changed.
15. Knowledge maintenance is advisory and durable-only. Routine fixes, transient audit notes, and one-off observations do not need new docs files.
16. If the same command/hypothesis fails twice without new evidence, stop repeating it. Summarize what is known and choose one narrower next check.
17. Respect `.codex/rules/` action guardrails; do not bypass approval by wrapping a destructive command differently. New dependencies require human approval.
18. Architecture checks are changed-file ratchets: treat advisory findings as evidence, not permission to repair unrelated legacy violations.
19. Use `task_state.py` only for genuinely long or multi-session work.
20. Keep plans/status concise and do not restate already-known findings.

### v6.5 writable layout / side-effect safety / bounded execution
- `.codex/` and `.agents/` are static configuration. Runtime/state/cache/report writes belong under project-root `.harness/`.
- For medium/high-risk work, run `python3 .codex/harness/scripts/task_scope.py begin` before edits and `... task_scope.py report` near closeout.
- Keep unrelated dirty files and unrelated existing failures untouched.
- Prefer the smallest coherent edit; do not expand scope merely to make a repository-wide gate green.
- Tests: existing relevant tests first, then extend an existing test file; new test file only for a material uncovered regression risk.
- **Before any Laravel/PHP test command, use `safe_test.py`.** It requires both DB isolation and side-effect isolation to pass.
- If either safety guard refuses a run, do not bypass or weaken it. Diagnose the isolation problem instead.
- Test-time external effects are default-deny/fake: outbound HTTP, real mail/notification, real queue/bus work, real filesystem/cloud disks, CUPS/printing, SMB/NAS writes, and stray child processes.
- Do not globally fake Laravel events by default; that can hide listener regressions. Keep listeners active while downstream external effects stay isolated. Use `Event::fake()` only in tests whose contract is event dispatch itself.
- Never use a test failure as justification to run migrations/wipes, DROP/TRUNCATE, destructive import/restore, recursive deletion, remote upload, printer submission, scheduler/worker commands, or persistent writes.
- Persistent/external mutations are user-supervised operations, not autonomous Harness verification. Prepare a bounded command + backup/recovery plan; do not execute the mutation yourself.
- Use targeted verification by default. Full verification is not an automatic closeout step.

### v6.6 semantic investigation policy
- Treat task-like sections in project documents as work queues by meaning, not by filename. New memo/checklist files do not need Harness registration.
- If the user asks to check/investigate/status-review items in such a section, first extract the active items and then inspect the implementation/configuration/test/Git evidence needed for each one. Do not finish by paraphrasing the queue.
- If the user asks only for a summary/list/read-through, stay document-only unless implementation evidence is necessary to explain ambiguity.
- `current code` means the checked-out working tree, including relevant uncommitted changes, unless a branch/ref is explicitly named.
- Prefer bounded, directly relevant evidence. One concrete source is usually enough to establish a simple item; use more only where the behavior spans components or evidence conflicts.

### v6.7 conversation continuity
- On follow-up implementation requests, inherit the nearest compatible user-established objective, target entities, dates, branch/environment, and success criteria.
- Do not swap the requested target for an easier example or sibling case. If a substitute is technically necessary, disclose it before using it and keep it separate from the requested target.
- Before editing or executing against an entity not named in the latest turn, verify it is the active target from the recent conversation chain.
- Interpret elliptical follow-ups as CONTINUE by default; parameter changes are REFINE; only a clear incompatible request is SWITCH.

<!-- adaptive-codex-harness-v6.8-plan-scope-skill:begin -->
### v6.8 plan-scope policy
Before finalizing plan.md:
1. Map each plan step to an explicit requirement/acceptance condition.
2. Remove detailed design for anything marked Phase 2/3/later or otherwise out of scope; retain only defer reason + target phase.
3. Move code-level discoveries (sentinel values, exact private method implementation, SQL/driver branches, complete column enumerations) out of plan.md unless they are required to explain an acceptance-critical compatibility constraint.
4. Challenge every newly proposed artifact not named or implied by the requirements: keep it only if acceptance requires it or existing-code evidence makes it necessary.
5. Apply the Plan Ready gate. If it passes, finish the plan rather than searching for more design detail.
6. Run `.codex/harness/scripts/plan_scope_guard.py <plan-path> [--proposal <proposal-path>]` when available. WARN findings are advisory cleanup prompts, not automatic blockers.
<!-- adaptive-codex-harness-v6.8-plan-scope-skill:end -->

<!-- adaptive-codex-harness-v6.9-execution-safety:begin -->
### v6.9 implementation-safety policy
- For time-varying production-like data, validate structural invariants (keys, mappings, references, versions) instead of unbound total-count literals.
- Prefer isolated copies/worktrees/temporary artifacts when historical code or destructive experiments would otherwise rewrite the active worktree.
- Verify that the real execution user can read/write generated files, caches, build outputs, mounts, and target paths.
- Prefer structured argv/process APIs over shell-string concatenation. When shell use is unavoidable, preserve safe argument boundaries and explicit working directory; do not interpolate untrusted external input directly into shell commands.
- Persistent updates must re-check critical mutable conditions near the write boundary; use transactions, locks, version checks, idempotency, or compensation when partial success/concurrency matters.
- Preserve causal exceptions when translating them into domain-facing messages, while redacting secret/personal values from logs and surfaced diagnostics.
<!-- adaptive-codex-harness-v6.9-execution-safety:end -->

<!-- adaptive-codex-harness-v6.10:begin -->
### v6.10 minimal edits / explanation clarity
- Preserve unchanged existing content; use targeted patches instead of whole-file regeneration.
- Run `python3 .codex/harness/scripts/minimal_diff_guard.py` before expensive/final verification.
- Explain bugs briefly: normally 1–3 sentences.
- Include only the concrete code value/boundary or calculation needed to understand the cause.
- Do not mechanically enumerate every internal step or repeat the same fact in multiple forms.
<!-- adaptive-codex-harness-v6.10:end -->
