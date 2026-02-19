# GitHub / Cloudflare 設定手順（現行プロジェクト構成）

## 1. 前提（現行コードから見た要件）
- `src/exporter.py` が `dashboard/data/*.json` を生成する
- `dashboard/js/app.js` が `data/*.json` を fetch して表示する
- `.github/workflows/weekly_run.yml` が `dashboard/data/*.json` を `git add` して push する

## 2. 最初に必要な修正（重要）
現状の `.gitignore` では `*.json` が無視され、`dashboard/data/*.json` が追跡対象にならない。

### 修正内容
- `.gitignore` に以下を追加:

```gitignore
!dashboard/data/*.json
```

## 3. GitHub 側で設定すべき項目

### 3.1 Repository Secrets and variables > Actions
以下を登録する:

- `GOOGLE_CREDENTIALS_JSON`（必須）
- `SLACK_WEBHOOK_URL`（`notifications.slack.enabled=true` のため実質必須）
- `LINE_CHANNEL_ACCESS_TOKEN`（LINE通知を使う場合）
- `LINE_USER_ID`（LINE通知を使う場合）
- `OPENAI_API_KEY`（現行コードでは未使用だが workflow で env 注入あり）

### 3.2 Actions 権限
- `Settings > Actions > General > Workflow permissions` を `Read and write permissions` に設定
- 理由: workflow が `git push` するため

### 3.3 Branch 保護設定
- `main` に保護ルールがある場合は、Actions からの更新コミットを許可する

## 4. GitHub 側の作業手順
1. `.gitignore` を修正して `!dashboard/data/*.json` を追加
2. `dashboard/data/` を作成
3. 初回データ生成を実行:
   - `python -m src.exporter`
4. 生成された `dashboard/data/*.json` をコミットして push
5. GitHub Secrets を登録
6. `Actions > Weekly Stock Analysis` を `workflow_dispatch` で手動実行
7. 実行後に `dashboard/data/*.json` の更新コミットが push されることを確認

## 5. Cloudflare 側で設定すべき項目（Pages）

### 5.1 Pages プロジェクト作成
1. Cloudflare Dashboard で `Workers & Pages` を開く
2. `Create` > `Pages` > `Connect to Git`
3. GitHub の対象リポジトリを接続

### 5.2 Build 設定
- Framework preset: `None`
- Build command: （空欄）
- Build output directory: `dashboard`
- Production branch: `main`（運用ブランチに合わせる）

### 5.3 環境変数
- 現在は静的配信のみのため Cloudflare Pages 側の環境変数は不要

### 5.4 カスタムドメイン（任意）
- `Custom domains` で追加
- DNS を Cloudflare 管理に寄せると設定しやすい

## 6. 運用フロー
1. GitHub Actions（週次/手動）が分析と JSON 出力を実行
2. `dashboard/data/*.json` が commit/push される
3. Cloudflare Pages が該当コミットを自動デプロイ
4. ダッシュボードが最新 JSON を読み込んで表示する

## 7. 確認チェックリスト
- [ ] `.gitignore` に `!dashboard/data/*.json` が入っている
- [ ] `dashboard/data` に `predictions.json`, `accuracy.json`, `stock_history.json` がある
- [ ] GitHub Secrets が登録済み
- [ ] Workflow の手動実行が成功する
- [ ] Actions が `main` へ更新コミットを push できる
- [ ] Cloudflare Pages の output directory が `dashboard` になっている
