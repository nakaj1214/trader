
<!-- adaptive-codex-harness-v6.6:begin -->
## Adaptive Codex Harness v6.6 — semantic investigation + fail-closed safety + bounded execution
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

### Semantic task interpretation
- Interpret documents by **content and user intent**, not by filename. Do not require per-file registration for task-like Markdown/text files.
- Headings or sections such as `質問`, `依頼`, `質問・依頼`, `TODO`, `未対応`, `確認事項`, `調査項目`, `課題`, `既知バグ`, `修正待ち`, `Open questions`, `Action items`, `Pending`, and `Known bugs` are unresolved-work candidates unless their surrounding context clearly marks them historical or completed.
- When the user asks to **確認する / 調べる / 状況を教える / 原因を見る / 対応状況を見る / verify / investigate / check status**, reading or restating the document is not completion. Extract the relevant unresolved items, then inspect the current source of truth needed to answer each item: implementation, routes, controllers/services/repositories/models, migrations/schema, configuration, scheduler/cron, views, tests, logs, or Git state/diff as appropriate.
- When the user explicitly asks only to **要約する / 一覧化する / 内容を読む / summarize / list**, a document-only answer is allowed.
- For an investigation item, prefer at least one concrete implementation/configuration evidence source before concluding. If the repository contains no evidence sufficient to decide, say that it is unresolved instead of converting the memo text into a factual answer.
- Treat `現行コード` / `現在のコード` as the checked-out working tree including relevant uncommitted changes unless the user names a branch, commit, or remote ref. Distinguish `main`, `origin/main`, and the working tree when that distinction can change the answer.
- Sections explicitly marked `対応済み`, `完了`, `Resolved`, `Done`, or equivalent are reference-only by default; inspect them only when needed to answer an active item or when the user asks for them.
- Use targeted evidence first. Do not scan the entire repository merely because a task queue exists; follow links/symbols from the active items and stop when enough evidence exists.
- Optional project metadata/front matter may override classification, but absence of metadata must never prevent semantic task recognition.
<!-- adaptive-codex-harness-v6.6:end -->

<!-- adaptive-codex-harness-v6.7-continuity:begin -->
## Adaptive Codex Harness v6.7 — conversation continuity and drift prevention

### Active-intent continuity
- Treat a follow-up user turn as continuing the nearest compatible unresolved user intent unless the user clearly starts a different task.
- Resolve omitted subjects, pronouns, shorthand, and phrases such as `それ`, `その方針`, `切り替えたら`, `確認したい`, `直して`, `続けて`, and equivalent wording against the nearest compatible user-established context before inventing a new target.
- Keep user-established target entities and constraints sticky across compatible follow-ups: named records/users/employees, IDs, categories, branches, files, dates, environments, requested modes, and explicit success criteria remain active until the user changes them, the task is completed, or they become incompatible with the new request.
- A user correction immediately overrides the conflicting part of the active context while preserving the non-conflicting remainder.

### No silent target substitution
- Never replace a user-established target with a sibling/example/convenient substitute merely because it is easier to test or inspect.
- Assistant-introduced examples and alternatives have lower priority than user-established targets and must not become the active target unless the user accepts them or the original target is impossible and the substitution is explicitly disclosed.
- Mentioning a comparison candidate does not itself switch the task target.

### Drift guard before actions
- Before a tool call, code change, DB operation, or concrete recommendation that uses a named target not present in the current user turn, verify that the target comes from the active conversation chain.
- If the contemplated action would change the target entity, date, branch, environment, operation, or success criterion relative to the active chain, first re-resolve the recent context. Do not silently proceed on a newly invented target.
- Classify the new turn mentally as one of:
  - `CONTINUE`: same objective; inherit target and constraints.
  - `REFINE`: user changes one or more parameters; preserve all non-conflicting context.
  - `SWITCH`: clearly different objective/target; drop only context that no longer applies.
- Prefer `CONTINUE` over `SWITCH` when the new turn is elliptical but compatible with the existing task.

### Confirmation discipline
- Do not ask the user to repeat or reconfirm a target already established in the active conversation merely because the latest message omits it.
- Preserve normal safety/destructive-action confirmation requirements. Conversation continuity never authorizes an otherwise disallowed or confirmation-gated action.
- When ambiguity genuinely remains between two still-active user-established targets, state the competing interpretations briefly rather than choosing an unrelated third option.

### Scope and persistence
- Use the nearest relevant conversation chain, not the entire historical session. Do not resurrect stale targets from unrelated older topics.
- Do not create or update repository files solely to store conversational state. The continuity anchor is conversational unless the user explicitly asks for durable task state.
- Keep the continuity check lightweight; it must not trigger broad repository scans or repeated document reads.
<!-- adaptive-codex-harness-v6.7-continuity:end -->

<!-- adaptive-codex-harness-v6.8.1-plan-scope:begin -->
## Adaptive Codex Harness v6.8.1 — Plan Scope Guard + Blocking Qualification

The planning/review goal is **implementation-ready**, not exhaustive design.

### Plan purpose
A plan decides only:
- what requirement is being implemented;
- what is in/out of scope;
- which files/components are affected sufficiently to start implementation;
- implementation order and integration boundaries;
- data-protection/backward-compatibility constraints that materially affect the approach;
- acceptance and targeted verification criteria.

Do not expand plan.md into a code-level implementation specification. Finished code/SQL, DB-driver branch code, private-method internals, complete column lists, sentinel constants, speculative recovery mechanisms, and detailed future-phase design belong to implementation notes unless an acceptance-critical compatibility constraint requires them.

### Mandatory Blocking Qualification Gate
**Before writing any finding as Blocking, explicitly test it against the five conditions below.**
A finding may be Blocking only when at least one answer is YES:
1. Do requirements conflict so implementation direction cannot be chosen?
2. Is a required dependency/data source/interface missing so the requirement cannot be implemented?
3. Would the planned approach materially corrupt/overwrite protected data or break a required existing path?
4. Is an acceptance condition impossible to meet with the current plan?
5. Is an unresolved scope/integration boundary large enough to materially change the implementation approach?

If all five answers are NO, the finding **MUST NOT** be classified Blocking. Put it in Implementation notes or Future/out-of-scope instead.

Operational/tooling observations are not planning blockers by default. Examples include an incorrect test command, service/container name, Harness doctor warning/version-label mismatch, test runner incompatibility, or a verification command that needs adjustment. They become Blocking only if they satisfy one of the five conditions above—e.g. acceptance truly cannot be verified or the implementation direction itself must change.

Hardening ideas, future-proofing, optional DB constraints, hypothetical edge cases, architecture preferences, and details discoverable safely during implementation are non-blocking unless the five-condition gate says otherwise.

### Scope guard
- Requirements/proposal are the scope authority. Do not create scope merely because a reviewer can imagine a safer, cleaner, more generic, or future-proof design.
- A new model/service/repository/migration/table/abstraction not requested or clearly implied by the requirements needs an acceptance-condition reason or existing-code evidence proving necessity.
- Items explicitly future/out-of-scope get only: item name, defer reason, target phase. Do not design their files, algorithms, tests, or data flow now.
- Prefer implementation-time decisions for details that can be settled safely by reading the touched code during implementation.

### Review convergence
- Round 1: discover and classify findings, but every proposed blocker must pass the Blocking Qualification Gate first.
- Round 2+: verify prior blockers. A new Blocking category is allowed only if caused by the previous fix or newly evidenced data loss, build impossibility, or acceptance impossibility.
- Later rounds do not restart design review at finer granularity.
- New non-blocking observations go to Implementation notes and do not force another planning round.

### Plan Ready gate
Declare READY and stop expanding the plan when all are true:
1. target requirements are identified;
2. in/out scope boundaries are explicit;
3. affected files/components are identified sufficiently to start implementation;
4. DB/schema direction is known if needed;
5. legacy/new integration boundary is known;
6. protected-data/backward-compatibility constraints are known;
7. acceptance conditions have a verification strategy.

Once READY, missing implementation-level detail is not a reason to return to Blocking.

### Conversation continuity
This block is additive to prior Harness rules. Preserve v6.7 continuity/investigation behavior and v6.5 safety behavior. Do not pivot from the user's active task into Harness maintenance unless requested.
<!-- adaptive-codex-harness-v6.8.1-plan-scope:end -->

<!-- adaptive-codex-harness-v6.9-execution-evidence:begin -->
## Adaptive Codex Harness v6.9 — Execution Evidence & Runtime Safety

Apply these rules across Shell, PHP, JavaScript, containers, jobs, and migration/restore work:

1. **Separate execution failure from business-condition mismatch.** Preserve the causal error class and exit/status code. Do not turn command/network/runtime failure into a domain message such as “dirty worktree”, “validation failed”, or “not found”.
2. **Prove completion with final evidence.** Creating/Started/sent/loading messages are progress only. Success requires the final exit/status plus the expected postcondition. Distinguish timeout, user cancel, signal termination, dependency failure, and normal command failure.
3. **Verify changing data structurally.** Prefer keys, mappings, referential integrity, versions, and other invariants over snapshot-specific total counts unless the snapshot and expected count are explicitly bound together.
4. **Verify execution context when it can change behavior.** Confirm the relevant run ID/time, requested vs effective operation, execution user, working/Git root, container, mount, and write target. Re-check critical mutable preconditions immediately before persistent changes when practical.
5. **Keep command boundaries and diagnostics safe.** Prefer structured argv over shell string concatenation; redact secrets, credentials, auth headers/cookies, private keys, and personal data before logs/chat/Git output. A single severe persistent-data, authorization, external-send, or secret-leak incident may justify a narrowly targeted fail-closed guard when the hazardous condition is mechanically identifiable.

Detailed diagnosis belongs in `docs/playbooks.md` and existing Harness skills. Do not create a new Skill or broad lint rule from a one-off ordinary failure.
<!-- adaptive-codex-harness-v6.9-execution-evidence:end -->

<!-- adaptive-codex-harness-v6.10:begin -->
## Adaptive Codex Harness v6.10 — minimal-diff editing + concise explanations

### Existing-file editing
- Existing files must be edited with the smallest coherent diff. Preserve unchanged lines and blocks instead of deleting and regenerating them.
- Prefer `apply_patch` / targeted Edit operations for existing tracked files.
- Do not use whole-file `Write`, delete-and-recreate, `cat > file`, `tee file`, `Path.write_text()`-style regeneration, or equivalent replacement merely because rewriting is easier.
- A one-line change should normally produce a one-line-scale diff. A section change should normally touch only that section.
- Full-file replacement is allowed only when the task itself explicitly requires a full rewrite, the file is generated/lock/output content, or preserving the old structure is not meaningful.
- Before expensive/final verification, run `python3 .codex/harness/scripts/minimal_diff_guard.py`.
- If the guard reports rewrite-like churn, reduce the edit to the required lines/blocks. Do not self-allowlist a file to make an agent edit pass.

### User-facing bug / behavior explanations
- Explain the cause in the shortest form that still lets the user understand it.
- Avoid abstract-only wording. Include only the concrete code value or boundary needed to understand the cause.
- Prefer 1–3 short sentences. Do not mechanically list every input, branch, calculation, expected result, and impact when some are obvious.
- For calculations, show only the key comparison or interval. Example: `現行コードは05:00を残業開始として扱うため、定時07:00・退勤08:00でも05:00〜08:00を3時間残業としてしまう。本来は07:00〜08:00の1時間。`
- Add another calculation only when it explains a separate symptom. Example: `深夜残業も05:00 - 07:00 = -2時間になる。`
- Do not repeat the same fact in different wording or add implementation detail that is not needed for the user's decision.

### Guard ownership
- Do not weaken, bypass, edit, or allowlist `.codex/harness/scripts/minimal_diff_guard.py`, `.codex/harness/hooks/minimal_edit_pretool.py`, or `.codex/harness/minimal_edit_policy.json` merely to pass a task. Harness guard changes are installer/maintainer work.
<!-- adaptive-codex-harness-v6.10:end -->
