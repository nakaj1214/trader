---
name: harness-verify
description: Deterministic verification with progressive log disclosure and minimal reruns. Keep raw output outside model context and verify only what can be invalidated by the current edits until final verification.
---
# Harness Verify — Adaptive Execution Discipline

1. Use `python3 .codex/harness/scripts/verify.py` as the single registered Human/Codex/CI gate instead of verbose raw commands. The changed-file Architecture Ratchet is included there.
2. During editing use the smallest affected test/lint/static check at logical checkpoints, not after every tiny edit.
3. Do not rerun an unchanged passing targeted check unless later edits can invalidate it.
4. Run the full registered profile once against the final diff; rerun only if subsequent edits invalidate the stamp.
5. PASS summaries are sufficient. Never inspect successful raw logs.
6. On failure use `--detail` first, then one named failing check; use `--raw` only when bounded detail is insufficient.
7. Do not spawn a Tester subagent for routine verification.

### v6.4 verification policy
1. Start from task-touched files / task scope, not the whole dirty worktree.
2. Before any Laravel/PHP test, run through `python3 .codex/harness/scripts/safe_test.py --shell '<original test command>'`.
3. `safe_test.py` requires `test_db_guard.py` and `side_effect_guard.py` to pass before launching the test process.
4. If isolation cannot be proven, fail closed. Never fall back to the container's normal DB, network, mail, queue, storage, print, or remote-share environment.
5. Small/low-risk: diff check + directly relevant tests/checks.
6. Moderate: add lint/format for task-touched files and the relevant regression group.
7. Broad/high-risk/release-sensitive: full gate may be appropriate, but unrelated pre-existing failures stay non-blocking.
8. Do not create new test files just to satisfy verification. Prefer existing coverage or extending an existing test.
9. Do not re-run an unchanged full gate repeatedly. After a small edit, re-run only invalidated checks unless final risk justifies a full pass.
10. Use bounded detail first; raw/full logs only when bounded detail cannot diagnose the failure.
