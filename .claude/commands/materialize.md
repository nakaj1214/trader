memory/ の提案から skills/hooks のドラフトを staging/ に生成する。

## 実行手順

### 1. キューの読み込み

`.claude/docs/memory/AUTO-MATERIALIZE-QUEUE.jsonl` を Read で読み込む。

- ファイルが存在しない場合: 「[materialize] キューファイルが見つかりません。`/learn-edits` でパターン分析を実行してください」と通知して終了
- `status: "pending"` のエントリをフィルタ
- pending がなければ「[materialize] 未処理の提案はありません」と通知して終了

### 2. 冪等性チェック

各 pending エントリについて `source` フィールドをキーとして重複チェックする:
- 同じ `source` で `status` が `staged` / `approved` / `rejected` のエントリが既にあればスキップ

### 3. 各エントリの処理

各 pending エントリについて:

#### a. ソースファイルの読み込み
- `source` フィールドのファイルを `.claude/docs/memory/` から Read で読み込む
- ファイルが存在しない場合はスキップし、警告を表示

#### b. ドラフト生成
Task (general-purpose) で以下を依頼:

**skill の場合** (`type: "edit-patterns"` or `type: "skill-suggestions"`):
- パターンファイルから最も価値の高い候補を1つ選択
- 以下のファイルを生成:
  - `SKILL.md` — 最小フロントマター (`name`, `description`, `allowed-tools`)
  - `INSTRUCTIONS.md` — 詳細な実行手順
  - `evaluations/evals.json` — 基本テストケース (2-3件)
- 既存の `.claude/registry/skills.yaml` と照合し、重複する場合はスキップ

**hook の場合**:
- Python スクリプトを生成
- `settings.json` に追加する hook エントリの JSON を生成
- 既存の hook ファイル名と照合し、重複する場合はスキップ

**feedback-pattern の場合** (`type: "feedback-pattern"`):
- `category` と `suggested_action` フィールドを読み取る
- `.claude/docs/feedback-log.md` から該当カテゴリの全エントリを抽出
- `suggested_action` に基づいてドラフトを生成:
  - Rule → `.claude/staging/{name}.md` (ルールファイル)
  - Hook → `.claude/staging/{name}/` (Python スクリプト + settings.json エントリ)
  - Skill → `.claude/staging/{name}/` (SKILL.md + INSTRUCTIONS.md + evals.json)
  - MCP → `.claude/staging/{name}/` (MCP 設定 JSON)

#### c. staging/ に配置
- `.claude/staging/{name}/` にファイルを配置
- ディレクトリが既に存在する場合は上書き警告を表示

#### d. STAGING-MANIFEST.json の更新
- `.claude/staging/STAGING-MANIFEST.json` にエントリ追加:
```json
{
  "name": "{name}",
  "type": "skill" | "hook",
  "source": "{source filename}",
  "status": "pending_review",
  "created_at": "{ISO8601}"
}
```

#### e. QUEUE のステータス更新
- 該当エントリの `status` を `"staged"` に更新
- **更新順序**: staging 配置 → MANIFEST 追加 → QUEUE 更新（最後に更新し、失敗時は pending のまま）

### 4. サマリー報告

処理結果をユーザーに表示:
- 「N 件の候補を staging/ に配置しました」
- 各候補の名前と種別を一覧表示
- 「`/review-staged` で確認・承認してください」と案内
- スキップした件数があればその理由も表示

## エラーハンドリング

| エラー | 対処 |
|--------|------|
| QUEUE ファイル不在 | `[materialize] FILE_NOT_FOUND: キューファイルが見つかりません → /learn-edits を実行してください` |
| pending エントリなし | `[materialize] EMPTY_INPUT: 未処理の提案はありません` |
| source ファイル不在 | 警告を出してスキップ、他のエントリは処理続行 |
| Task 失敗 | QUEUE を pending のまま残す（次回再試行可能） |
| staging 配置失敗 | staging/{name}/ を削除してスキップ |
