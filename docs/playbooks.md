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
- Monitor schedules are 09:20 / 12:50 / 15:35 / 15:50 JST on weekdays, with main-only manual dispatch. The final check waits for the provider's delayed closing bar. `--dry-run` suppresses Slack, but still writes Sheets and still requires the production writer guard.
- One monitor run shares a ticker's daily history and current minute bars, and one lazily opened Sheets connection. Purchase-date split adjustments, pending-session recovery, stop decisions and mutable bar copies remain position-specific. These are run-scoped values, not a persistent cache; the next run fetches again.
- `as_of_at` is the last verified price checkpoint. `incomplete` preserves the checkpoint and requires a later retry; it does not confirm no stop contact. Recovery rechecks the checkpoint session and subsequent closed sessions against daily OHLCV. A recovered stop is labelled historical and remains latched after prices recover. A pending session older than 30 days is beyond the provider's 1-minute retention and can never be replayed, so it is judged on its daily bar: `low <= max(prior high-water, day's high) * (1 - stop%)` is a necessary condition for any touch, so a daily low above that level proves no contact, while a lower one is reported once as `recovered_daily_possible_touch` (the intraday order is unknown, so it can be a false alarm). Sessions within 30 days stay `incomplete` until their minute bars return; the checkpoint is not advanced for them.
- The separate Reliability Watchdog checks main workflow success and the expected encrypted snapshot at 20:10 JST, with exchange holidays and two hours of scheduler grace. Forward requires a scheduled run because manual dispatch skips weekly-only processing. Delivered alert identities are stored in the Actions cache; cache eviction can cause a repeat alert. A platform-wide Actions outage also stops this watchdog: an independent scheduler may run `scripts/check_workflow_health.py` with read-only GitHub credentials, a private Slack webhook, a current snapshot checkout, and durable `--state` outside Actions.
- Slack timeout/500 is a failed notification, never recorded as delivered. Slack acceptance and Sheets status persistence are separate operations; after a status-write failure, reconcile the private notification and Sheets state before rerunning. Public logs retain stage, error type, row number, counts, and HTTP status; diagnose provider exception details through private channels rather than publishing holdings or credentials.
# Stage 4B reliability boundaries

The daily digest records `pending` or `succeeded` by market date in
`dashboard/data/inflection/digest_state.json`. A pending day is retried by the next normal run;
`workflow_dispatch` with `resend_digest=true` forces a retry. Delivery is best-effort, not exactly
once: a runner stop after Slack accepts a message but before the state is pushed can duplicate it,
and Slack acceptance does not prove end-user delivery.

A `pending` mark is written before a new day's snapshot, so a stop after that never leaves a snapshot whose digest is lost. If `digest_state.json` cannot be read or written (corrupt JSON, an unknown value, a read-only file), the scan still saves and commits the snapshot, withholds the digest (sending it untracked could repeat it tomorrow) and never rewrites the file. The run page shows a `Daily digest not sent` warning annotation, the log prints `digest=failed:digest-state-invalid` (or `-unwritable`) and, when a webhook is set, one fixed-text Slack alert is sent per run until it is fixed. Repair the file (or delete it: a day without a mark is treated as a legacy snapshot and not re-sent) and use `resend_digest=true` if the day's digest is still owed. A plain Slack failure is annotated too but sends no second message over the same channel.

Provider diagnostics expose only a category (`timeout`, `rate_limit`, `server_error`, `protocol`,
`empty`, `invalid_ohlcv`, `validation`, `auth`, or `unexpected`), status, retry count, and aggregate
count. Never add tickers, URLs, response bodies, credentials, or raw exception messages to public
workflow output. `unexpected` errors are propagated instead of being converted to missing data.

Snapshot and latest are saved before digest delivery; the workflow commits/pushes afterwards.
An existing snapshot without notification state is not sent by normal runs. A missing webhook
keeps a pending day retryable. Explicit resend uses the new scan report, which may differ from
the immutable snapshot. Initial notification-state write failure fails the run; Slack send
failure is best-effort. Investigate a successful Slack send followed by state-save or push failure
privately before manual resend, because the next run can send a duplicate.

Snapshot, latest and evaluation files use same-directory temporary files followed by atomic
publication. Immutable snapshots cannot be overwritten, even by competing creation attempts.
Atomicity is per file: snapshot/latest and report/summary pairs are not a transaction and can
represent different generations after an interrupted run.

## Setup and implementation status

- Use Python 3.11 or later and `uv==0.9.21`; `uv sync --frozen --extra dev` installs from `uv.lock`.
  Workflows use SHA-pinned Actions and frozen dependency installation. Forward PRs, including forks,
  run tests without decryption secrets; schedule/manual runs decrypt snapshots, and only scheduled
  runs rebuild learning and push encrypted price hashes. No workflow uses `pull_request_target`.
- Export environment variables yourself; CLIs do not load `.env` automatically. The scan requires
  `JQUANTS_API_KEY` and a separate, stable `SNAPSHOT_ENCRYPTION_KEY` (no API-key fallback). Slack
  digest/failure delivery requires `SLACK_WEBHOOK_URL`; monitor Sheets requires
  `GOOGLE_CREDENTIALS_JSON` and `GOOGLE_SHEET_ID`, plus Slack unless using `--dry-run`.
- `JQUANTS_PLAN` accepts free/light/standard/premium. `JQUANTS_DATA_DELAY_WEEKS` must be a
  non-negative integer, at least 12 for free; defaults are 12 for free and 0 otherwise. Invalid
  configuration fails rather than being coerced. The scan workflow currently declares free/12;
  this declaration does not prove API availability at a historical cutoff.
- EDINET fetching, diagnostic features in live snapshots and learning factors are implemented
  and covered with fake/unit tests. Live acquisition is conditional on `EDINET_API_KEY`, and
  unavailable data stays missing. Issuer mapping and API metadata were checked in the 2026-10-07
  probe record. Historical integration remains deferred because erased filings prevent strict
  reconstruction. Production acquisition and end-to-end notification delivery were not reverified
  in Stage 4C; code integration is not evidence of production delivery.
