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
