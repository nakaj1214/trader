# GitHub / Cloudflare 設定手順書

このドキュメントは、以下の構成を前提にしています。

- GitHub Actions: `.github/workflows/weekly_run.yml`
- 静的ダッシュボード: `dashboard/`
- 生成データ: `dashboard/data/predictions.json`, `dashboard/data/accuracy.json`, `dashboard/data/stock_history.json`
- 配信先: Cloudflare Pages

## 1. GitHub 側で設定する項目

### 1.1 Actions が `git push` できる権限

1. GitHub リポジトリの `Settings` を開く
2. `Actions` > `General` を開く
3. `Workflow permissions` を `Read and write permissions` に設定
4. 保存

このプロジェクトの workflow は `dashboard/data/*.json` を自動コミットして `git push` するため、この権限が必要です。

### 1.2 Repository Secrets（Actions 用）

`Settings` > `Secrets and variables` > `Actions` > `New repository secret` で以下を登録します。

| Secret 名 | 必須 | 用途 |
|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | 必須 | Google Sheets 認証情報。GitHub では「JSON文字列そのもの」を入れる |
| `SLACK_WEBHOOK_URL` | `notifications.slack.enabled=true` の場合必須 | Slack 通知 |
| `LINE_CHANNEL_ACCESS_TOKEN` | `notifications.line.enabled=true` の場合必須 | LINE 通知 |
| `LINE_USER_ID` | `notifications.line.enabled=true` の場合必須 | LINE 通知先 |
| `OPENAI_API_KEY` | 任意 | 現行コードでは未使用（workflow には env 定義あり） |

注意点:

- `GOOGLE_CREDENTIALS_JSON` は、ローカルのようなファイルパスではなく、サービスアカウント JSON の中身を 1 つの Secret 値として登録します。
- Google Sheets 側で、サービスアカウントのメールアドレスに対象スプレッドシートへの編集権限を付与してください。

### 1.3 `.gitignore` と初回データ配置

`.gitignore` に以下が入っていることを確認します。

```gitignore
!dashboard/data/*.json
```

初回公開時に `dashboard/data/*.json` が存在しないと、Cloudflare Pages 上で表示エラーになります。最初に 3 ファイルをコミットしておきます。

1. ローカルで `python -m src.exporter` を実行
2. `dashboard/data/*.json` が生成されることを確認
3. 3 ファイルをコミットして `main` に push

### 1.4 Branch protection の確認

`main` に Branch protection を設定している場合、Actions からの push が拒否されることがあります。拒否される場合は次のいずれかで対応してください。

- Actions の更新コミットを許可する設定に変更する
- workflow を「直接 push」ではなく PR 作成方式に変更する

### 1.5 動作確認（手動実行）

1. `Actions` タブを開く
2. `Weekly Stock Analysis` を選択
3. `Run workflow` で `main` を手動実行
4. 成功後、`dashboard/data/*.json` の更新コミットが作成されることを確認

## 2. Cloudflare 側で設定する項目

### 2.1 Pages プロジェクト作成

1. Cloudflare Dashboard を開く
2. `Workers & Pages` > `Create` > `Pages` > `Connect to Git`
3. 対象 GitHub リポジトリを選択

### 2.2 Build 設定

Pages の Build 設定は以下にします。

- Framework preset: `None`
- Build command: 空欄（不要）
- Build output directory: `dashboard`
- Root directory: `/`（未指定でも可）
- Production branch: `main`

このプロジェクトは静的ファイル配信のみなので、Cloudflare Pages 側の環境変数は不要です。

### 2.3 Custom Domain（任意）

独自ドメインを使う場合:

1. Pages プロジェクトの `Custom domains` でドメイン追加
2. 指示に従って DNS レコードを設定

## 3. 運用フロー

1. 毎週日曜 UTC 00:00（JST 09:00）に GitHub Actions が実行
2. 分析と JSON 出力を実施
3. `dashboard/data/*.json` を自動コミット・push
4. Cloudflare Pages が自動デプロイ

## 4. 最終チェックリスト

- [ ] GitHub Actions 権限が `Read and write permissions`
- [ ] 必要な Secrets が登録済み
- [ ] `dashboard/data/*.json` が追跡対象（`.gitignore` 設定済み）
- [ ] `Weekly Stock Analysis` の手動実行が成功
- [ ] Cloudflare Pages の output directory が `dashboard`
- [ ] Pages 公開 URL で `index.html` / `accuracy.html` / `stock.html` が表示できる
