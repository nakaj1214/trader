---
name: harness-review
description: Perform a bounded independent review only when the Harness quality gate requires it. Review the final diff first and expand to minimal adjacent context only when a concrete risk requires it.
---
# Harness Review — Diff-first bounded review

1. Run only when the quality gate marks the final diff high-risk/large, or the user explicitly requests independent review.
2. Start with `.codex/harness/scripts/change_inventory.py`, `git diff --stat`, changed filenames, and changed hunks. Do not begin with a repository-wide audit or broad Knowledge reread.
3. Review priorities: correctness/regression, security boundary, data integrity/destructive behavior, misleading/missing regression tests, then unnecessary complexity.
4. Expand from a changed hunk only to the directly affected interface/caller/callee/test/schema needed to validate a concrete concern. Avoid broad adjacent-code exploration without evidence.
5. Do not re-run the full test suite merely to review; rely on the current valid verification stamp unless a finding requires a specific targeted check.
6. Do not request speculative refactors or style cleanup unrelated to correctness/risk.
7. If PASS, stop with `VERDICT: PASS`; do not launch another reviewer. If FAIL, list only blocking findings with exact paths/symbols and concise evidence.
8. After blocking fixes, rerun only invalidated targeted checks plus final Harness verification as required, then one final bounded review.
