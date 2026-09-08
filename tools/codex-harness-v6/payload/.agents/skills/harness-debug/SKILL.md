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
