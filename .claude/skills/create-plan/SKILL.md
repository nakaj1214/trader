---
name: create-plan
description: |
  Read docs/implement/proposal.md and create docs/implement/plan.md.
  Then run a Codex review loop until APPROVED or max iterations reached.
metadata:
  short-description: Proposal → Plan with Codex review loop
---

# Create Plan

`docs/implement/proposal.md` を読み込み、`docs/implement/plan.md` を作成する。
その後 Codex によるレビューループを回し、APPROVED になるまで plan.md を更新し続ける。

## Fixed Files

| File | Role |
|------|------|
| `docs/implement/proposal.md` | Input: User-written requirements (read-only) |
| `docs/implement/plan.md` | Output: Implementation plan (create/update by Claude) |
| `docs/implement/review.md` | Output: Codex review result (create/update by Codex) |

---

## Step 1: Read Proposal

Read `docs/implement/proposal.md`.

If the file does not exist, stop and tell the user:
> `docs/implement/proposal.md` が見つかりません。先にファイルを作成してください。

Send a Slack notification that the skill has started:

```bash
python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/notify-slack.py" \
  --title ":rocket: create-plan 開始" \
  --message "proposal.md を読み込み、実装計画の作成を開始します。"
```

---

## Step 2: Investigate Codebase (Claude)

Investigate the codebase based on the scope described in proposal.md:

- Related existing code (classes, functions, modules)
- Files likely to be affected
- Libraries and patterns already in use
- Existing tests relevant to the scope

Use this investigation to inform the plan in the next step.

---

## Step 3: Create plan.md (Claude)

Based on proposal.md, create `docs/implement/plan.md` using the format below.

```markdown
## 実装計画: {Title}

### 目的
{1-2 sentences from proposal}

### スコープ
- 含むもの: {list}
- 含まないもの: {list}

### 影響範囲（変更/追加予定ファイル）
- {file path}: {reason}

### 実装ステップ

#### Step 1: {Title}
- [ ] {Specific task}
- [ ] {Specific task}
**検証**: {Completion criteria}

#### Step 2: {Title}
...

### 例外・エラーハンドリング方針
{policy}

### テスト/検証方針
- 自動テスト: {command or N/A}
- 手動確認観点: {specific checklist}

### リスクと対策
1. リスク: {description} → 対策: {mitigation}
2. リスク: {description} → 対策: {mitigation}
3. リスク: {description} → 対策: {mitigation}

### 完了条件
- [ ] {Acceptance criterion}
```

---

## Step 4: Codex Review Loop

### Loop Settings

- Max iterations: **5**
- Terminate on: `APPROVED` in the last line of `docs/implement/review.md`
- Terminate on: max iterations reached → report to user and stop

### Each Iteration

**3-1. Launch Codex subagent (background)**

```
Task tool parameters:
- subagent_type: "general-purpose"
- run_in_background: false
- prompt: |
    Review the implementation plan.

    Steps:
    1. Read the file: docs/implement/plan.md
    2. Run Codex CLI:

    codex exec --model gpt-5.3-codex -c model_reasoning_effort="high" --sandbox workspace-write --full-auto "
    You are a senior engineer reviewing an implementation plan.
    Your ONLY allowed file operation is writing to docs/implement/review.md.
    Do NOT create, modify, or delete any other files.
    Read docs/implement/plan.md and write a structured review to docs/implement/review.md.

    Review checklist:
    1. Scope clarity - Is the purpose/non-purpose clear? Are there vague expressions?
    2. Completeness of affected files - Are all routes/validation/authorization/DB/frontend/config files listed?
    3. Implementation order - Are dependencies in the correct order?
    4. Test/verification specificity - Are test commands and manual check points concrete?
    5. Risks and mitigations - Are at least 3 risks listed with concrete mitigations?
    6. Completion criteria - Is the acceptance condition clear and measurable?

    Output format for docs/implement/review.md:
    # レビュー対象
    - docs/implement/plan.md

    # まず結論
    - 判定: (APPROVED / CHANGES_REQUIRED)
    - 要点（3〜5行）:

    # 必須修正（Blocking）
    - [ ]

    # 推奨（Non-blocking）
    - [ ]

    # 影響範囲の追加提案
    -

    # テスト追加/修正提案
    -

    # リスク再評価
    -

    # 次アクション
    -

    APPROVED or CHANGES_REQUIRED
    " 2>/dev/null

    3. Read docs/implement/review.md and return:
       - The verdict (APPROVED or CHANGES_REQUIRED)
       - Blocking issues (if any)
       - Non-blocking recommendations (if any)
```

**3-2. Read verdict from review.md**

Check the last non-empty line of `docs/implement/review.md`:
- `APPROVED` → go to Step 5 (done)
- `CHANGES_REQUIRED` → go to Step 3-3

**3-3. Update plan.md based on review (Claude)**

Read `docs/implement/review.md` and update `docs/implement/plan.md`:
- Fix all **Blocking** issues
- Apply **Non-blocking** recommendations if reasonable
- Do NOT change the overall structure unless required

Then go back to Step 3-1 (next iteration).

### Iteration Limit

If 5 iterations pass without `APPROVED`:

> ⚠️ レビューループが5回を超えました。`docs/implement/review.md` を確認し、手動で対応してください。

Send a Slack notification:

```bash
python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/notify-slack.py" \
  --title ":warning: create-plan レビュー上限到達" \
  --message "5回のレビューループで APPROVED になりませんでした。手動確認が必要です。\ndocs/implement/review.md を確認してください。"
```

Stop the loop and report remaining blocking issues to the user.

---

## Step 5: Done

Send a Slack notification that the plan is complete:

```bash
python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/notify-slack.py" \
  --title ":white_check_mark: create-plan 完了" \
  --message "実装計画が APPROVED されました（{N}回目で承認）。\n• docs/implement/plan.md\n• docs/implement/review.md"
```

Report to user (in Japanese):

```
## 計画作成完了

✅ Codex レビュー: APPROVED（{N}回目で承認）

### 作成ファイル
- docs/implement/plan.md
- docs/implement/review.md（最終レビュー）

### 次のステップ
実装を開始する場合は `/startproject` または実装タスクをお知らせください。
```

---

## Notes

- Codex is called via subagent to preserve main context window
- Codex cannot access Claude's file context — plan.md content must be passed explicitly in the prompt
- Claude has final authority; if Codex APPROVED but Claude sees a critical issue, Claude may request another iteration
- Max 5 iterations is a hard limit to prevent infinite loops
