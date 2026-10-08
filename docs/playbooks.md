# Playbooks

<!-- adaptive-codex-harness-v6.9-execution-diagnosis:begin -->
## Execution/result diagnosis (v6.9)

Use this flow when a command, container operation, PHP process, JavaScript request, job, migration, restore, or generated artifact has an unclear or failed result.

1. **Identify the exact run.** Confirm run/request/job ID where available, start time, command/operation, and the newest log. Never treat an old log path as the current run merely because it was printed again.
2. **Find the first causal failure.** Capture the original exit/status code and redact-safe stderr/exception/HTTP failure. Keep this separate from any later domain interpretation.
3. **Classify the terminal state.** Distinguish success, normal failure, timeout, user cancel, signal termination, and dependency/service failure.
4. **Separate progress from completion.** Docker `Creating`/`Created`, process start, queue dispatch, request send, modal/loading UI, and rollback start are not final success evidence.
5. **Compare requested and effective operation.** Record what the caller requested and what actually ran after wrapper/Compose/shell/environment/default resolution. Include execution user, cwd/Git root, relevant container, mounts, and write target. Redact secret-bearing values before recording.
6. **Check argument and shell boundaries.** Prefer argv/structured APIs. When a shell is unavoidable, verify quoting, `--` boundaries where applicable, working directory, variable expansion, leading hyphens, whitespace/newlines, globbing, and command substitution risks.
7. **Verify mutable preconditions at the write boundary.** For persistent changes, re-check critical DB/file/container/mount/source fingerprint/version/backup conditions immediately before mutation when practical; use locks, transactions, compare-and-swap/version columns, or equivalent concurrency controls where needed.
8. **Verify postconditions and recovery.** Confirm the intended final data/files/service state. If rollback/compensation ran, verify the rollback command completed and the restored state is correct; “rollback started” is not enough.
9. **Before retrying, improve observability.** Add only the smallest run ID, causal error, effective-operation, or postcondition evidence needed to distinguish the suspected causes. Do not broaden the design merely to gather more telemetry.

### Safety notes
- Redact passwords, tokens, cookies, Authorization headers, private keys, secret connection strings, and personal data before logs/chat/Git-managed artifacts.
- Prefer “configured/not configured”, hashes/fingerprints, counts, names of parameters/services, and error categories when raw values are unnecessary.
- Preserve enough non-secret context to diagnose the cause: exit/status code, error category, argument/parameter name, target service, and relevant run identifier.
- Ordinary one-off failures stay as implementation/debug notes. A one-off incident may become an automatic guard only when impact is severe and the dangerous condition can be detected narrowly with a fail-closed response.
<!-- adaptive-codex-harness-v6.9-execution-diagnosis:end -->

## Production monitor and workflow health

- Production Sheets has one writer: this repository's `main` Position Monitor, with job concurrency `position-monitor-production` and cancellation disabled. Branch and ordinary local executions are rejected before reading holdings. Do not impersonate GitHub Actions locally or run another repository against the same Sheets; Actions concurrency is repository scoped. Pause the monitor before manual status changes, and preserve `triggered_at`, `last_notified_at`, and the last verified `as_of_at`.
- `as_of_at` is the last verified price checkpoint. `incomplete` preserves the checkpoint and requires a later retry; it does not confirm no stop contact. Recovery rechecks the checkpoint session and subsequent closed sessions against daily OHLCV. A recovered stop is labelled historical and remains latched after prices recover. Minute history that the provider no longer retains needs private manual investigation; do not advance its checkpoint to silence the warning.
- The separate Reliability Watchdog checks main workflow success and the expected encrypted snapshot at 20:10 JST, with exchange holidays and two hours of scheduler grace. Forward requires a scheduled run because manual dispatch skips weekly-only processing. Delivered alert identities are stored in the Actions cache; cache eviction can cause a repeat alert. A platform-wide Actions outage also stops this watchdog: an independent scheduler may run `scripts/check_workflow_health.py` with read-only GitHub credentials, a private Slack webhook, a current snapshot checkout, and durable `--state` outside Actions.
- Slack timeout/500 is a failed notification, never recorded as delivered. Slack acceptance and Sheets status persistence are separate operations; after a status-write failure, reconcile the private notification and Sheets state before rerunning. Public logs retain stage, error type, row number, counts, and HTTP status; diagnose provider exception details through private channels rather than publishing holdings or credentials.
