---
name: maintain-project-knowledge
description: Record only verified durable project knowledge that will materially reduce future work. Prefer updating an existing record; avoid creating routine per-task evidence/audit files.
---
# Maintain project knowledge — durable-only

1. Read `docs/index.md` and exact task-related records only; never sweep all `docs/`.
2. Skip Knowledge writes for routine fixes, transient failures, one-off audit findings, implementation narration, or information already obvious from code/tests.
3. Prefer updating an existing relevant record over creating a new file. Create a new record only for a durable decision/pattern/handover that future sessions genuinely need.
4. Keep evidence concise and link to code/tests/commands; never copy large logs/source excerpts.
5. Promotion: repeated/approved invariant -> pattern/rule; recurring deterministic failure -> test/lint/script; unfinished long-running work -> one compact handover.
6. Do not create an audit report, exec plan, evidence file, and pattern for the same fact.
7. If nothing durable was learned, make no Knowledge change.
