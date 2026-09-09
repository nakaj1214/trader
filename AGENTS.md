


<!-- adaptive-codex-harness-v6.5:begin -->
## Adaptive Codex Harness v6.5 — fail-closed side-effect isolation + bounded execution
- Keep work scoped to the current user task. Pre-existing dirty-worktree changes/failures are non-blocking unless explicitly requested.
- Treat `.codex/` and `.agents/` as static read-only Harness configuration during Codex execution. Do not store mutable runtime/state/log/cache/report data there.
- All Harness-generated mutable data must live under project-root `.harness/`: transient execution data in `.harness/runtime/`, durable machine state in `.harness/state/`, caches in `.harness/cache/`, generated reports in `.harness/reports/`, and installer backups in `.harness/backups/`.
- Verification is risk-based: targeted checks by default; repository-wide/full gates only for broad/high-risk/release-sensitive work or when targeted checks are insufficient.
- Prefer existing tests, then extend an existing relevant test file. Create a new test file only for a material regression risk that existing coverage cannot reasonably validate. Never create tests merely to satisfy the Harness.
- **Tests must not reach persistent business infrastructure.** Laravel/PHP tests must pass both `test_db_guard.py` and `side_effect_guard.py` and should run through `safe_test.py`.
- Persistent DB access is forbidden during tests. Do not bypass, weaken, remove, or work around the SQLite-memory isolation guard.
- Outbound HTTP, real mail/notifications, real queues/jobs, real filesystem/cloud disks, printing/CUPS, SMB/NAS writes, and stray child processes are denied or faked during tests. If isolation cannot be proven, fail closed instead of falling back to the normal environment.
- Event dispatch is not globally faked because doing so can hide real integration regressions; listeners may run, but their external side-effect channels remain isolated. Tests that only assert dispatch may use `Event::fake()` locally.
- `Schema::drop*`, DROP/TRUNCATE, migrations/wipes, destructive imports/restores, recursive filesystem deletion, Docker volume deletion, force Git cleanup/reset, external HTTP writes, remote file transfer, printer submission, queue workers, and scheduler execution are not routine agent verification operations. Codex must not execute them autonomously against persistent resources.
- Read-only diagnostics are allowed when bounded: SELECT/SHOW/schema metadata, `migrate:status`, `route:list`, `lpstat`, and read-only remote listings. Interactive DB/SMB shells are denied because later input is not rechecked by `PreToolUse`.
- Independent reviewer is normally skipped for small/low-risk work. Use at most one reviewer for broad/high-risk changes (roughly >=5 task-touched files, >=200 task-diff lines, auth/permission/security, schema/migration/persistent-data risk, cross-component behavioral change, or explicit review request).
- Review and verification must inspect the current task diff, not every unrelated pre-existing change.
- Do not repeatedly run the same full gate, re-read unchanged large diffs, or open raw/full logs when bounded output is sufficient.
- Stop hooks are advisory; do not rely on a blocking Stop loop for correctness.
- Update durable project knowledge only for stable/repeated evidence or explicit user intent, not as automatic closeout for every task.
<!-- adaptive-codex-harness-v6.5:end -->
