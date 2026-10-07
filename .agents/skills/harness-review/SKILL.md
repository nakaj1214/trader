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

### v6.5 reviewer policy
- Reviewer is normally skipped for small/low-risk changes.
- Spawn at most one bounded independent reviewer when the current task is broad/high-risk: roughly >=5 task-touched files, >=200 task-diff lines, auth/permission/security, schema/migration/persistent-data behavior, material cross-component behavior, or explicit review request.
- Review only the current-task diff. Pre-existing dirty changes are context only when necessary and are not findings to fix.
- When tests or integration code changed, explicitly check that tests cannot reach persistent DBs, external HTTP, real mail/notification channels, real queues, real disks/NAS/S3, printers/CUPS, scheduler/workers, or uncontrolled child processes.
- Do not repeatedly poll a reviewer or spawn replacement reviewers. If a reviewer cannot complete, report that once instead of starting a loop.
- A review PASS is invalidated only by later edits relevant to the reviewed scope, not by unrelated pre-existing worktree changes.

<!-- adaptive-codex-harness-v6.8.1-plan-scope-skill:begin -->
### v6.8.1 review-convergence + Blocking Qualification policy
Review for implementability and requirement coverage, not maximal detail.

Before recording **each** Blocking finding, run this qualification gate and record the matching reason:
- B1 requirement conflict prevents choosing implementation direction;
- B2 required dependency/data/interface is missing and prevents implementation;
- B3 planned approach would materially corrupt protected data or break a required existing path;
- B4 an acceptance condition cannot be met;
- B5 unresolved scope/integration boundary materially changes the implementation approach.

If none of B1-B5 applies, Blocking is forbidden. Classify as:
- Implementation note: actionable detail that can be resolved during implementation/verification; or
- Future/out-of-scope: valid concern intentionally deferred.

Important classification examples:
- wrong test command/service name -> Implementation note unless acceptance becomes impossible;
- Harness doctor/version-label mismatch -> Implementation note unless it prevents required verification entirely;
- test runner incompatibility such as a disabled runtime function -> Implementation note when the guard can be repaired without changing the product plan;
- optional DB hardening / alternative locking strategy -> Implementation note unless current plan risks protected data;
- future Phase design -> Future/out-of-scope, not Blocking.

Round behavior:
- Round 1: discover findings comprehensively, but qualify every blocker before writing it.
- Round 2+: verify previous blockers; new blocker categories require prior-fix causation or new evidence of data loss/build impossibility/acceptance impossibility.
- Do not promote implementation notes into plan requirements on later rounds.
- If Plan Ready passes, write READY and stop expanding review.md.
<!-- adaptive-codex-harness-v6.8.1-plan-scope-skill:end -->

<!-- adaptive-codex-harness-v6.10:begin -->
### v6.10 minimal edits / explanation clarity
- Preserve unchanged existing content; use targeted patches instead of whole-file regeneration.
- Run `python3 .codex/harness/scripts/minimal_diff_guard.py` before expensive/final verification.
- Explain bugs briefly: normally 1–3 sentences.
- Include only the concrete code value/boundary or calculation needed to understand the cause.
- Do not mechanically enumerate every internal step or repeat the same fact in multiple forms.
<!-- adaptive-codex-harness-v6.10:end -->
