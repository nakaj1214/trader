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

### v6.5 knowledge policy
- Project knowledge is not an automatic per-task closeout step.
- Promote only stable, repeated, evidenced patterns or explicit user decisions.
- Safety incidents that can cause persistent/external side effects may be promoted when the rule is general and mechanically enforceable.
- Do not turn one-off debugging observations, temporary failures, or task-local implementation details into durable rules.

<!-- adaptive-codex-harness-v6.9-execution-safety:begin -->
### v6.9 guard-promotion policy
- Do not generalize one ordinary incident into a new Skill, broad lint, or global rule. Prefer existing docs/tests/skills and wait for repeated, structurally similar failures.
- Exception: one incident may justify an automatic guard when impact is severe (persistent data destruction, unauthorized action, external mis-send, secret leakage, irrecoverable mutation) **and** the hazardous condition is mechanically identifiable with an acceptably narrow fail-closed check.
- Record the evidence for promotion: concrete incident/risk, detection condition, expected false-positive cost, fail-closed behavior, and why an existing guard/test cannot cover it.
<!-- adaptive-codex-harness-v6.9-execution-safety:end -->
