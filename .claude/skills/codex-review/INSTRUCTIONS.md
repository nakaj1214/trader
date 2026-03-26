# Codex Review — 詳細手順

## 入力パラメータ

呼び出し側がスキル起動時に指定する。ユーザーのメッセージまたはスキル引数から解析する。

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|---------|------|
| `target_file` | Yes | — | レビュー対象のファイルパス |
| `review_file` | No | `{target_file dir}/review.md` | レビュー結果の出力パス |
| `max_iterations` | No | 5 | レビューループの最大反復回数 |
| `checklist` | No | (組み込みデフォルト) | カスタムレビューチェックリスト — インラインテキストまたは `.md` ファイルパス |
| `slack_notify` | No | true | Slack 通知を送信するか |

---

## Step 1: 初期化

1. `target_file` の存在を確認する。存在しない場合はユーザーに通知して停止:
   > `{target_file}` が見つかりません。ファイルパスを確認してください。

2. `review_file` のデフォルトを解決する:
   - 未指定の場合は `target_file` と同じディレクトリにファイル名 `review.md` を使用
   - 例: `docs/design.md` → `docs/review.md`

3. `checklist` を解決する:
   - ファイルパス（`.md` で終わる）が指定された場合、そのファイルを読み取って内容を使用
   - インラインテキストが指定された場合、そのまま使用
   - 未指定の場合は、以下の **デフォルトチェックリスト** を使用

4. `slack_notify` が true の場合、開始通知を送信:

```bash
python3 .claude/hooks/notify-slack.py \
  --title ":mag: codex-review 開始" \
  --message "対象: {target_file}\nレビューループを開始します。"
```

---

## Step 2: レビューループ

最大 `max_iterations` 回繰り返す。

### 2-1. Codex MCP ツールによるレビュー実行

**重要: Codex は MCP サーバー経由で呼び出す（`codex exec` Bash 実行は廃止）。**

`.mcp.json` に登録された `codex` MCP サーバーの `codex` ツールを使用する。

ToolSearch で `mcp__codex__codex` を検索・ロードしてから、以下のパラメータで呼び出す:

```
ツール: mcp__codex__codex
パラメータ:
  prompt: |
    You are a senior engineer reviewing a document.
    Read {target_file} and provide a structured review.

    Review checklist:
    {resolved_checklist}

    Output format:
    # レビュー対象
    - {target_file}

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

  model: "gpt-5.4"
  base-instructions: "You are a code review assistant. Focus only on the review task given. Do not read project instruction files. Only review what is specified in the prompt."
  sandbox: "read-only"
  approval-policy: "on-request"
```

**`base-instructions` が最重要パラメータ。** これにより `.codex/instructions.md` や `.claude/CLAUDE.md` の自動読み込みをオーバーライドし、タイムアウトを防止する。

### 2-2. レビュー結果の保存と判定確認

1. MCP ツールのレスポンス（`content` フィールド）を `{review_file}` に Write ツールで書き込む
2. レスポンス内容から判定を確認:
   - `APPROVED` → Step 3（完了）へ
   - `CHANGES_REQUIRED` → 2-3 へ

`slack_notify` が true の場合、通知を送信:

```bash
python3 .claude/hooks/notify-slack.py \
  --title ":mag: codex-review レビュー結果 (#{iteration}回目)" \
  --message "判定: {verdict}\n{blocking issues summary, if any}"
```

### 2-3. 対象ファイルの修正（Claude）

`{review_file}` を読み取り、`{target_file}` を更新する:
- すべての **Blocking** 問題を修正
- 妥当であれば **Non-blocking** 推奨事項も適用
- 必要でない限り全体の構造は変更しない

`slack_notify` が true の場合、通知を送信:

```bash
python3 .claude/hooks/notify-slack.py \
  --title ":pencil2: codex-review 修正完了 (#{iteration}回目)" \
  --message "レビュー指摘に基づき {target_file} を更新しました。次のレビューを開始します。"
```

2-1 に戻る（次のイテレーション）。

### イテレーション上限

`max_iterations` に達しても `APPROVED` にならない場合:

**Claude は自分で APPROVED 判定を行ってはならない。**
ユーザーに以下を報告し、判断を仰ぐこと:

1. 残っている blocking issues の一覧
2. これまでの修正履歴の要約
3. 次のアクションの選択肢を提示:
   - blocking issues を手動で解決してから再実行
   - 現状のまま APPROVED として進める（ユーザーの明示的な承認が必要）
   - prompt.md を見直して要件を修正する

> :warning: レビューループが{max_iterations}回を超えました。以下の blocking issues が残っています。

`slack_notify` が true の場合:

```bash
python3 .claude/hooks/notify-slack.py \
  --title ":warning: codex-review レビュー上限到達" \
  --message "{max_iterations}回のレビューループで APPROVED になりませんでした。ユーザー判断が必要です。\n{review_file} を確認してください。"
```

ループを停止し、**ユーザーの判断を待つ**。自動的に進めてはならない。

---

## Step 3: 完了

`slack_notify` が true の場合:

```bash
python3 .claude/hooks/notify-slack.py \
  --title ":white_check_mark: codex-review 完了" \
  --message "{target_file} が APPROVED されました（{N}回目で承認）。\n• {target_file}\n• {review_file}"
```

ユーザーに報告（日本語で）:

```
## Codex レビュー完了

✅ 判定: APPROVED（{N}回目で承認）

### ファイル
- {target_file}（レビュー対象）
- {review_file}（レビュー結果）

### 次のステップ
必要に応じて次の作業をお知らせください。
```

---

## デフォルトチェックリスト

`checklist` パラメータが未指定の場合に使用:

```
1. スコープの明確さ - 目的/非目的は明確か？曖昧な表現はないか？
2. 完全性 - 影響するファイル/コンポーネント/ルート/バリデーション/認可/DB/フロントエンド/設定がすべて列挙されているか？
3. 実装順序 - 依存関係が正しい順序になっているか？
4. テスト/検証の具体性 - テストコマンドと手動確認ポイントは具体的か？
5. リスクと軽減策 - 少なくとも3つのリスクが具体的な軽減策と共に記載されているか？
6. 完了基準 - 受け入れ条件は明確で測定可能か？
```

---

## 注意事項

- **Codex は MCP ツール `mcp__codex__codex` で呼び出す**（`codex exec` Bash 実行は廃止）
- **`base-instructions` パラメータ必須** — これがないと Codex が `.codex/instructions.md` や `.claude/CLAUDE.md` を自動読み込みし、コンテキストを圧迫してタイムアウトする
- MCP ツールのレスポンスは `content` フィールドに文字列で返される。これを Claude が `{review_file}` に Write ツールで保存する
- **Claude は APPROVED / CHANGES_REQUIRED の判定を自分で行ってはならない。** 判定は Codex のみが行う。Codex が APPROVED を出さずにループ上限に達した場合は、ユーザーに報告して判断を仰ぐこと
- max_iterations の制限は無限ループを防ぐためのハードキャップ
