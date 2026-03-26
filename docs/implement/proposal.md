# 実装要件書

> このファイルは create-plan の入力です。
> 各要件は「具体的な Before/After」「対象ファイル」「受入条件」を含めてください。

---

## 要件一覧

### REQ-001: .claude/.env の平文 Slack トークンを安全な管理方法に移行する

- **画面**: なし（CLI / フック基盤）
- **対象ファイル**:
  - `.claude/.env` — トークン格納元（削除対象）
  - `.claude/hooks/lib/env.py` — トークン読み込みロジック（3層フォールバック: os.environ → .claude/.env → settings.json[env]）
  - `.claude/settings.json` — env セクション（移行先候補）
  - `.claude/hooks/slack/slack_approval.py` — BOT_TOKEN, CHANNEL_ID, APPROVER_USER_ID 使用
  - `.claude/hooks/slack/notify-slack.py` — BOT_TOKEN, CHANNEL_ID, APPROVER_USER_ID, WEBHOOK_URL 使用
  - `.claude/hooks/slack/slack_socket_daemon.py` — APP_TOKEN, BOT_TOKEN, APPROVER_USER_ID 使用
  - `.claude/hooks/slack/edit-approval.py` — BOT_TOKEN, CHANNEL_ID, APPROVER_USER_ID 使用
  - `.claude/hooks/slack/stop-notify.py` — BOT_TOKEN, CHANNEL_ID, WEBHOOK_URL 使用
- **Before（現状）**: `.claude/.env` に 4 つの Slack トークン（`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_APPROVER_USER_ID`）が平文でハードコードされている。`.gitignore` で Git 追跡外だが、ローカルディスク上に生トークンが露出している
- **After（期待）**: `.claude/.env` ファイルを削除し、トークンは OS 環境変数（推奨）または `.claude/settings.json` の `env` セクションで管理する。既存の `env.py` の 3 層フォールバック機構はそのまま活用し、フックスクリプトの変更は不要とする
- **受入条件**:
  1. `.claude/.env` ファイルが削除されている
  2. `.claude/.env.example` に必要な変数名のみ（値なし）を記載したテンプレートが存在する
  3. `env.py` の 3 層フォールバックが引き続き動作する（os.environ → settings.json[env] にフォールバック）
  4. セットアップ手順ドキュメントが更新されている
- **備考**:
  - `env.py` の 3 層フォールバック（os.environ → .claude/.env → settings.json[env]）は変更不要。.env を消せば自動的に次の層にフォールバックする
  - `settings.json` が `.gitignore` に含まれているか実装時に確認が必要
  - フックスクリプト自体の変更は不要（env.py 経由で間接的に読み込んでいるため）

### REQ-002: トークンローテーション手順を文書化する

- **画面**: なし（ドキュメント）
- **対象ファイル**:
  - `docs/setup/secrets_checklist.md`（既存、更新）
- **Before（現状）**: Slack トークンのローテーション（再発行）手順が文書化されていない
- **After（期待）**: `docs/setup/secrets_checklist.md` に Slack Bot Token (`xoxb-`) と App Token (`xapp-`) の再発行手順、および新トークンのプロジェクトへの反映手順が記載されている
- **受入条件**:
  1. Bot Token (`xoxb-`) の再発行手順が記載されている
  2. App Token (`xapp-`) の再発行手順が記載されている
  3. 新トークンの反映先（OS 環境変数 or settings.json）が明記されている
- **備考**: 実際のローテーション作業はユーザーが Slack 管理画面で手動実施する。ドキュメントは手順のガイドのみ

---

## 繰り返し失敗している要件

> 該当なし

---

## 完了済み・保留中

### 完了済み
- なし

### 保留中（今回のスコープ外）
- なし
