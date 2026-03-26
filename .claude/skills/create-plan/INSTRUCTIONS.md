# Create Plan — 詳細手順

## Fixed Files

| File | Role |
|------|------|
| `docs/implement/proposal.md` | Input: User-written requirements (read-only) |
| `docs/implement/plan.md` | Output: Implementation plan (create/update by Claude) |
| `docs/implement/review.md` | Output: Codex review result (create/update by Codex) |

---

## Step 0-pre: 調査型タスク判定

proposal.md を読み、課題が**調査型**（原因不明のバグ・動作不良）かを判定する:

- 「〜が動かない」「〜が表示されない」「アラートが出る」「原因不明」などのキーワード
- 修正方針が「まず原因を調べる」になっている

**調査型と判定した場合**: ユーザーに以下を提案して確認を取る:
> この課題は原因不明のバグです。Codex レビューループで計画を磨くより、verify-before-fix で証拠を集めて直接修正する方が速い可能性があります。
> 1. verify-before-fix で進める（推奨）— plan 作成と Codex レビューをスキップ
> 2. 通常の create-plan で進める

ユーザーが「1」を選んだ場合: plan.md に「verify-before-fix による調査 → 最小修正」の簡易テンプレートを生成し、Codex レビュー（Step 4）をスキップして完了する。

**実装型と判定した場合**: 通常通り Step 0 に進む。

---

## Step 0: Proposal Quality Gate（前提チェック）

**plan 作成の前に、必ず `proposal-quality-gate` スキルの INSTRUCTIONS.md を読み、品質チェックを実行すること。**

品質チェックの結果:
- **PASS** → Step 1 に進む
- **FAIL** → proposal.md のリライトを実施し、ユーザー承認後に Step 1 に進む

詳細: [proposal-quality-gate INSTRUCTIONS.md](../proposal-quality-gate/INSTRUCTIONS.md)

---

## Step 1: Read Proposal

Read `docs/implement/proposal.md`.

If the file does not exist, stop and tell the user:
> `docs/implement/proposal.md` が見つかりません。先にファイルを作成してください。

Send a Slack notification that the skill has started:

```bash
python3 .claude/hooks/notify-slack.py \
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

Invoke the `codex-review` skill with the following parameters:

- **target_file**: `docs/implement/plan.md`
- **review_file**: `docs/implement/review.md`
- **max_iterations**: 5
- **checklist**: (use default — the built-in checklist covers implementation plan review)
- **slack_notify**: true

The `codex-review` skill handles the full review loop:
Codex reviews → Claude fixes blocking issues → repeat until APPROVED or max iterations.

See [codex-review INSTRUCTIONS](../codex-review/INSTRUCTIONS.md) for detailed loop behavior.

---

## Step 5: Done

Send a Slack notification that the plan is complete:

```bash
python3 .claude/hooks/notify-slack.py \
  --title ":white_check_mark: create-plan 完了" \
  --message "実装計画が APPROVED されました（{N}回目で承認）。\n• docs/implement/plan.md\n• docs/implement/review.md"
```

### 5回以内で APPROVED → 自動実装

Codex レビューが **5回以内（max_iterations 以内）で APPROVED** された場合:

1. ユーザーに以下を報告する:

```
## 計画作成完了 → 自動実装開始

✅ Codex レビュー: APPROVED（{N}回目で承認）

### 作成ファイル
- docs/implement/plan.md
- docs/implement/review.md（最終レビュー）

⚡ 5回以内で承認されたため、implement-plans を自動実行します。
```

2. **`implement-plans` スキルを自動的に発火する。** ユーザーの追加指示を待たずに実行を開始すること。

### APPROVED にならなかった場合

5回のループで APPROVED にならなかった場合は、自動実装を行わない。
ユーザーに残っている blocking issues を提示して次のアクションを確認する:

```
## 計画作成 — レビュー未承認

⚠️ Codex レビュー: 5回のループで APPROVED に至りませんでした。

### 残っている問題
- {blocking issue 1}
- {blocking issue 2}

### 作成ファイル
- docs/implement/plan.md
- docs/implement/review.md（最終レビュー）

### 次のステップ
手動で修正するか、再度レビューを実行するかお知らせください。
```

---

## Notes

- **Codex は MCP ツール `mcp__codex__codex` で呼び出す**（`codex exec` Bash 実行は廃止 — instruction 自動読み込みによるタイムアウトを回避するため）
- **`base-instructions` パラメータ必須** — これがないと Codex がプロジェクトの instruction ファイルを読み込み、コンテキストを圧迫してタイムアウトする
- **Claude は APPROVED 判定を自分で行ってはならない。** Codex が APPROVED を出さなかった場合、ユーザーに状況を報告して判断を仰ぐこと
- Max 5 iterations is a hard limit to prevent infinite loops
- 5回のループで APPROVED にならなかった場合、Claude が勝手に APPROVED とせず、残っている blocking issues をユーザーに提示して次のアクションを確認すること
