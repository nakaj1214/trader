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

### v6.4 debug safety
- Prefer read-only diagnostics. Persistent/external mutation is not diagnosis.
- Do not run tests until both DB and side-effect guards pass. Do not assume `phpunit.xml` wins over populated container environment unless `force="true"` is verified.
- For HTTP, mail, queue, storage/NAS/S3, printer/CUPS, external processes, scheduler/worker, and remote-transfer problems, inspect configuration/logs/read-only status first. Do not send a real probe that creates, updates, deletes, prints, emails, uploads, or queues work merely to reproduce an issue.
- Interactive DB or SMB shells are denied because later input is not rechecked by `PreToolUse`; use bounded non-interactive read-only commands.
- If a missing table/data/file issue is found, first determine whether it is drift, accidental deletion, wrong connection/path, or pre-existing state. Do not reconstruct/restore persistent state without explicit user supervision.
