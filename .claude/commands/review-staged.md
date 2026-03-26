staging/ の skill/hook 候補を確認し、承認または却下する。

## 実行手順

### 1. MANIFEST の読み込み

`.claude/staging/STAGING-MANIFEST.json` を Read で読み込む。

- ファイルが存在しない場合: 「[review-staged] MANIFEST が見つかりません。`/materialize` を先に実行してください」と通知して終了
- `status: "pending_review"` のエントリをフィルタ
- pending_review がなければ「[review-staged] レビュー待ちの候補はありません」と通知して終了

### 2. QUEUE との整合チェック

`.claude/docs/memory/AUTO-MATERIALIZE-QUEUE.jsonl` を読み、MANIFEST の各エントリに対応する QUEUE エントリの `status` を確認する。
- QUEUE 側が `staged` でない場合は警告を出す（処理は続行）

### 3. 各候補のレビュー

各 `pending_review` エントリについて:

#### a. ファイル内容の表示
- skill の場合: `SKILL.md` と `INSTRUCTIONS.md` を Read で表示
- hook の場合: Python スクリプトを Read で表示

#### b. ユーザーへの確認
AskUserQuestion で以下を提示:
- **「承認して配置する」** — 安全ゲートを通過後に正式ディレクトリへ配置
- **「skill-creator で改善してから配置する」** — staging パスを伝えて終了
- **「却下して削除する」** — staging から削除

### 4. 承認フロー

#### 安全ゲート（validate_before_deploy）

**hook の場合:**
1. `python3 -m py_compile {script}` で Python 構文チェック
2. スクリプト内に `sys.exit` or `exit(` が存在するか確認
3. スクリプト内に `sys.stdin` or `json.load` が存在するか確認（PostToolUse hook の場合）

**skill の場合:**
1. `SKILL.md` が存在し、YAML フロントマター (`---`) で始まるか
2. フロントマター内に `name:` フィールドがあるか
3. `INSTRUCTIONS.md` が存在するか
4. `evaluations/evals.json` が存在するか

いずれか1つでも失敗したら配置を中止し、エラーをユーザーに報告する。

#### 配置処理（deploy_item）

**skill の場合:**
1. `.claude/staging/{name}/` → `.claude/skills/{name}/` にコピー
2. `python3 .claude/meta/generate-registry.py` を実行して registry 更新

**hook の場合:**
1. スクリプトを `.claude/hooks/` にコピー
2. `settings.json` のバックアップを取得
3. `settings.json` の該当 hooks セクションにエントリ追加

#### ロールバック

配置途中で例外が発生した場合:
- skill: `.claude/skills/{name}/` を削除
- hook: コピーしたスクリプトを削除、`settings.json` をバックアップから復元

#### ステータス更新

配置成功後:
1. STAGING-MANIFEST.json の status を `"approved"` に更新
2. AUTO-MATERIALIZE-QUEUE.jsonl の対応エントリを `"approved"` に更新
3. `.claude/staging/{name}/` を削除（クリーンアップ）

### 5. 却下フロー

1. `.claude/staging/{name}/` を削除
2. STAGING-MANIFEST.json の status を `"rejected"` に更新
3. AUTO-MATERIALIZE-QUEUE.jsonl の対応エントリを `"rejected"` に更新

### 6. 改善フロー

1. staging パスをユーザーに伝える: `.claude/staging/{name}/`
2. 「`/skill-creator` でこのディレクトリのファイルを改善してから、再度 `/review-staged` を実行してください」と案内
3. MANIFEST の status は `"pending_review"` のまま維持

## エラーハンドリング

| エラー | 対処 |
|--------|------|
| MANIFEST 不在 | `[review-staged] FILE_NOT_FOUND: STAGING-MANIFEST.json が見つかりません → /materialize を実行してください` |
| pending_review なし | `[review-staged] EMPTY_INPUT: レビュー待ちの候補はありません` |
| 安全ゲート失敗 | `[review-staged] VALIDATION_FAILED: {エラー詳細} → 配置を中止しました` |
| 配置失敗 | `[review-staged] DEPLOY_FAILED: {エラー詳細} → ロールバックを実行しました` |
| QUEUE 不整合 | 警告を表示して処理続行 |
