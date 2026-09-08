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
9. Keep temporary audits, inventories, generated diagnostics, and raw logs under `.codex/harness/runtime/`. Do not create tracked audit/report/plan files unless the user requested them or they are durable project knowledge.
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
