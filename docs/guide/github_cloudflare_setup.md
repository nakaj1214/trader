# GitHub / Cloudflare 設定手順（最新版）

この手順は、現行のプロジェクト実装を基準にしています。

- Workflow: `.github/workflows/weekly_run.yml`
- 静的サイト: `dashboard/`
- 生成データ: `dashboard/data/predictions.json`, `dashboard/data/accuracy.json`, `dashboard/data/stock_history.json`
- 配信先: Cloudflare Pages

## 1. 事前確認（現行実装）

- Workflow は `python -m src.main` と `python -m src.exporter` を実行します。
- Workflow は `dashboard/data/*.json` をコミットして `main` に push します。
- `.gitignore` には `!dashboard/data/*.json` が必要です（現行リポジトリでは設定済み）。
- `dashboard/js/*.js` は `data/*.json` を `fetch()` して表示します。

## 2. GitHub 側で設定する項目

### 2.1 Actions 権限

1. `Settings` > `Actions` > `General`
2. `Workflow permissions` を `Read and write permissions` に設定

理由:
- 現行 Workflow は `git push` を実行するため、書き込み権限が必要です。

### 2.2 Repository Secrets（Actions）

`Settings` > `Secrets and variables` > `Actions` で以下を登録します。

| Secret | 必須 | 用途 |
|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | 必須 | Google Sheets 認証（サービスアカウント JSON） |
| `SLACK_WEBHOOK_URL` | `notifications.slack.enabled=true` の場合必須（現行は true） | Slack 通知 |
| `LINE_CHANNEL_ACCESS_TOKEN` | `notifications.line.enabled=true` の場合のみ | LINE 通知 |
| `LINE_USER_ID` | `notifications.line.enabled=true` の場合のみ | LINE 通知先 |
| `OPENAI_API_KEY` | 任意 | 現行コードでは未使用だが Workflow で env 注入あり |

`GOOGLE_CREDENTIALS_JSON` の登録ルール:
- GitHub Secrets にはファイルパスではなく、サービスアカウント JSON の中身を文字列で登録します。

### 2.3 Branch protection の確認

`main` に保護ルールがある場合、Workflow の push が拒否されることがあります。

- Actions からの更新コミットを許可する
- もしくは運用方針として Workflow の push を PR 方式に変更する

## 3. 初回データ作成と push

Cloudflare Pages 初回公開時に `dashboard/data/*.json` がないと画面でデータが出ません。

1. ローカルで `python -m src.exporter` を実行
2. `dashboard/data/*.json` の 3 ファイルを確認
3. 3 ファイルをコミットして `main` に push

## 4. Workflow 手動実行で動作確認

1. `Actions` タブを開く
2. `Weekly Stock Analysis` を選択
3. `Run workflow` で `main` を手動実行
4. 実行完了後に `dashboard/data/*.json` の更新コミットが push されることを確認

補足:
- スケジュール実行は `cron: '0 0 * * 0'`（毎週日曜 UTC 00:00 / JST 09:00）です。

## 5. Cloudflare Pages 側で設定する項目

### 5.1 Pages プロジェクト作成

1. Cloudflare Dashboard で `Workers & Pages` を開く
2. `Create` > `Pages` > `Connect to Git`
3. 対象 GitHub リポジトリを接続

### 5.2 Build 設定（現行構成）

- Framework preset: `None`
- Build command: 空欄
- Build output directory: `dashboard`
- Production branch: `main`

補足:
- 現行は静的配信のみのため、Cloudflare Pages 側の環境変数は不要です。

### 5.3 カスタムドメイン（任意）

1. Pages プロジェクトの `Custom domains` でドメインを追加
2. 表示される指示に従って DNS を設定

## 6. 運用フロー

1. GitHub Actions が分析とデータ出力を実行
2. `dashboard/data/*.json` を自動コミットして push
3. Cloudflare Pages が自動デプロイ
4. `index.html` / `accuracy.html` / `stock.html` で最新データを表示

## 7. チェックリスト

- [ ] `Settings > Actions > General > Workflow permissions` が `Read and write permissions`
- [ ] `GOOGLE_CREDENTIALS_JSON` が登録済み
- [ ] （現行設定に合わせて）`SLACK_WEBHOOK_URL` が登録済み
- [ ] （LINE を有効化する場合のみ）`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID` が登録済み
- [ ] `dashboard/data/predictions.json`, `dashboard/data/accuracy.json`, `dashboard/data/stock_history.json` が存在
- [ ] `Weekly Stock Analysis` の手動実行が成功
- [ ] Cloudflare Pages の `Build output directory` が `dashboard`
