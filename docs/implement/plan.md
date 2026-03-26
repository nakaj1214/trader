## 実装計画: Slack トークンの平文保存を解消する

> proposal: `docs/implement/proposal.md`
> 作成日: 2026-03-26

---

### 目的

`.claude/.env` に平文で保存されている Slack トークンを削除し、OS 環境変数または `settings.json` の `env` セクションで管理する方式に移行する。既存フックの動作を維持しつつ、セキュリティリスクを解消する。

### スコープ

- 含むもの:
  - `.claude/.env` の削除
  - `.claude/.env.example` テンプレートの作成
  - セットアップ手順の更新（`docs/setup/secrets_checklist.md`）
  - トークンローテーション手順の文書化

- 含まないもの:
  - `env.py` のロジック変更（既存の 3 層フォールバックをそのまま活用）
  - フックスクリプトの変更（env.py 経由で間接的に読み込んでいるため不要）
  - `settings.json` の構造変更（既存の `env` セクション読み込みロジックをそのまま活用）
  - 実際のトークンローテーション作業（ユーザーが手動で実施）

### 影響範囲（変更/追加予定ファイル）

| ファイル | 変更内容 |
|---------|---------|
| `.claude/.env` | 削除（archive/ にバックアップ後） |
| `.claude/.env.example` | 新規作成: 必要な変数名のテンプレート |
| `docs/setup/secrets_checklist.md` | 更新: Slack トークンのローテーション手順と反映先を追記 |

### 実装ステップ

#### Step 1: .env.example テンプレートを作成

- [ ] `.claude/.env.example` を作成。変数名のみ記載し、値は空またはプレースホルダーにする:
  ```
  # Slack Integration
  SLACK_BOT_TOKEN=xoxb-your-bot-token
  SLACK_APP_TOKEN=xapp-your-app-token
  SLACK_CHANNEL_ID=C0YOUR_CHANNEL
  SLACK_APPROVER_USER_ID=U0YOUR_USER_ID
  ```

**検証**: ファイルに実際のトークン値が含まれていないこと

#### Step 2: .claude/.env を archive/ にバックアップし削除

- [ ] `archive/` ディレクトリが存在しない場合は作成
- [ ] `.claude/.env` を `archive/.claude-env-backup-2026-03-26` にコピー
- [ ] `.claude/.env` を削除
- [ ] `archive/` が `.gitignore` に含まれていることを確認

**検証**: `.claude/.env` が存在しないこと。バックアップが `archive/` に存在すること

#### Step 3: env.py のフォールバック動作を確認

- [ ] `.claude/.env` 削除後、`env.py` の `get()` 関数が `settings.json[env]` にフォールバックすることを確認
- [ ] テスト方法: Python で直接確認
  ```bash
  python3 -c "import sys; sys.path.insert(0, '.claude/hooks'); from lib.env import get; print('BOT_TOKEN:', bool(get('SLACK_BOT_TOKEN'))); print('CHANNEL_ID:', bool(get('SLACK_CHANNEL_ID')))"
  ```
- [ ] トークンが OS 環境変数にも `settings.json[env]` にも設定されていない場合は空文字列が返ることを確認（フックの fail-safe が働く）

**検証**: `env.py` がエラーなく動作し、フォールバックチェーンが正しく機能すること

#### Step 4: トークンローテーション手順を文書化

- [ ] `docs/setup/secrets_checklist.md` に以下のセクションを追記:
  - Slack Bot Token (`xoxb-`) の再発行手順（Slack App 管理画面 → OAuth & Permissions → Reinstall）
  - Slack App Token (`xapp-`) の再発行手順（Slack App 管理画面 → Basic Information → App-Level Tokens）
  - 新トークンの反映方法:
    1. OS 環境変数に設定する方法（推奨）
    2. `.claude/settings.json` の `env` セクションに追記する方法（代替）
  - 動作確認方法

**検証**: 手順が具体的かつ再現可能であること

### 例外・エラーハンドリング方針

- `.claude/.env` 削除後にフックがトークンを取得できない場合: `env.py` は空文字列を返し、各フックスクリプトの fail-safe（exit 0 or exit 2）が機能する。新たなエラーハンドリングは不要
- `archive/` ディレクトリが既に存在する場合: そのまま使用（上書きしない）

### テスト/検証方針

- 自動テスト: N/A（設定ファイルの移行のため）
- 手動確認観点:
  - [ ] `.claude/.env` が削除されていること
  - [ ] `.claude/.env.example` にテンプレートが存在すること
  - [ ] `env.py` の `get()` が `.env` なしで正常動作すること
  - [ ] `docs/setup/secrets_checklist.md` にローテーション手順が記載されていること
  - [ ] `archive/` にバックアップが存在すること

### リスクと対策

1. リスク: `.env` 削除後にフックが動作しなくなる → 対策: `env.py` の 3 層フォールバックにより、OS 環境変数または `settings.json[env]` から自動取得。削除前に Step 3 でフォールバック動作を確認する

2. リスク: バックアップ先 `archive/` が Git に含まれてトークンが漏洩する → 対策: `archive/` が `.gitignore` に含まれていることを Step 2 で確認。含まれていなければ追加する

3. リスク: ユーザーが新しいトークン設定方法を理解できない → 対策: Step 4 で具体的な手順を文書化。OS 環境変数と settings.json の両方の方法を記載する

### 完了条件

- [ ] `.claude/.env` が削除されている
- [ ] `.claude/.env.example` が作成されている（値なしテンプレート）
- [ ] `archive/` にバックアップが存在する
- [ ] `env.py` の 3 層フォールバックが `.env` なしで正常動作する
- [ ] `docs/setup/secrets_checklist.md` にローテーション手順が記載されている
- [ ] `archive/` が `.gitignore` に含まれている
