# セットアップチェックリスト（シークレット・手動設定）

> 新しい環境やリポジトリに本システムをデプロイする際に必要な手動設定の一覧。
> コードに埋め込めないシークレット類はすべてここで管理する。

---

## 1. GitHub Secrets（必須）

GitHub リポジトリの **Settings → Secrets and variables → Actions → New repository secret** から登録する。

| シークレット名 | 必須 | 用途 | 取得方法 |
|---|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | **必須** | Google Sheets 読み書き認証（サービスアカウント JSON の中身をそのまま貼り付け） | GCP コンソール → IAM → サービスアカウント → キーを作成 → JSON |
| `SLACK_WEBHOOK_URL` | **必須** | 週次レポートの Slack 通知 | Slack App 管理画面 → Incoming Webhooks → URL をコピー |
| `JQUANTS_API_KEY` | **必須**（JP 株機能を使う場合） | 日本株 PBR/ROE・配当データ取得（J-Quants V2） | [jpx-jquants.com](https://jpx-jquants.com/) でアカウント登録後に発行 |
| `FINNHUB_API_KEY` | **必須**（US 株センチメントを使う場合） | US 株ニュース・センチメント取得 | [finnhub.io/register](https://finnhub.io/register) で無料登録後に発行 |
| `FMP_API_KEY` | **必須**（財務データフォールバックを使う場合） | グローバル財務データ補完（250 req/日） | [financialmodelingprep.com](https://site.financialmodelingprep.com/) で無料登録後に発行 |
| `FRED_API_KEY` | 任意 | マクロ指標（政策金利・イールドカーブ・VIX）取得。未設定時は macro.json をスキップ | [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `LINE_CHANNEL_ACCESS_TOKEN` | 任意 | LINE で Slack 確認リマインドを送る。`config.yaml: notifications.line.enabled: true` と合わせて設定 | LINE Developers コンソール → チャンネル → Messaging API |
| `LINE_USER_ID` | 任意 | LINE 通知の送信先ユーザー ID（`LINE_CHANNEL_ACCESS_TOKEN` とセット） | LINE Developers → チャンネル → ユーザー ID |

> **注意:** `GOOGLE_CREDENTIALS_JSON` にはファイルパスではなく **JSON 文字列そのもの**を貼り付けること。
> `credentials.json` の中身を全選択コピーしてシークレット値に貼り付ける。

---

## 2. Cloudflare Pages 手動設定

Cloudflare ダッシュボードから以下を設定する（現状 `wrangler.toml` なし・GUI 設定のみ）。

| 設定項目 | 設定値 | 備考 |
|---|---|---|
| Framework preset | なし（Static HTML） | ビルドコマンド不要 |
| Build output directory | `dashboard` | リポジトリルートからの相対パス |
| Root directory | （空欄） | リポジトリルートを使用 |
| 対象ブランチ | `main` | `main` への push で自動デプロイ |
| Production branch | `main` | |

> **確認事項:** Cloudflare Pages が `dashboard/_headers` を認識しているか、デプロイ後に
> ブラウザの DevTools → Network で `/data/predictions.json` の
> `Cache-Control: no-store` ヘッダーを確認すること。

---

## 3. Google Sheets 初期設定

| 設定項目 | 値 | 備考 |
|---|---|---|
| スプレッドシート名 | `trade` | `config.yaml: google_sheets.spreadsheet_name` と一致させること |
| ワークシート名 | `predictions` | `config.yaml: google_sheets.worksheet_name` と一致させること |
| サービスアカウントへの共有 | 編集者権限で共有 | GCP で発行したサービスアカウントのメールアドレスをスプレッドシートの共有設定に追加 |

---

## 4. config.yaml で切り替える設定

コードは変更不要。`config.yaml` の値を変えることで動作を切り替える。

| キー | デフォルト | 変更が必要なケース |
|---|---|---|
| `jquants.enabled` | `true` | J-Quants を使わない場合は `false` に変更（`JQUANTS_API_KEY` 未設定でも degraded mode で続行するが、明示的に無効化を推奨） |
| `finnhub.enabled` | `true` | Finnhub を使わない場合は `false` |
| `fmp.enabled` | `true` | FMP を使わない場合は `false` |
| `notifications.line.enabled` | `false` | LINE 通知を有効にする場合は `true`（`LINE_CHANNEL_ACCESS_TOKEN` + `LINE_USER_ID` のシークレット登録も必要） |
| `screening.markets` | `[sp500, nasdaq100, nikkei225]` | JP 株を外す場合は `nikkei225` を削除 |
| `prophet.uncertainty_samples` | `1000` | CI が timeout する場合は `500` 等に下げて実行時間を短縮 |

---

## 5. ローカル開発用 .env

`.env.example` をコピーして `.env` を作成する（`.gitignore` 対象のためコミット禁止）。

```bash
cp .env.example .env
# .env を編集して実際のキーを入力
```

`.env` に設定するキー一覧:

```
GOOGLE_CREDENTIALS_JSON=path/to/credentials.json  # または JSON 文字列
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
JQUANTS_API_KEY=...
FINNHUB_API_KEY=...
FMP_API_KEY=...
FRED_API_KEY=...               # 任意
LINE_CHANNEL_ACCESS_TOKEN=...  # 任意
LINE_USER_ID=...               # 任意
```

---

## 6. 初回デプロイ確認チェックリスト

- [✓] GitHub Secrets に必須項目（`GOOGLE_CREDENTIALS_JSON`, `SLACK_WEBHOOK_URL`）が登録されている
- [ ] 使用する API に対応するシークレット（`JQUANTS_API_KEY` 等）が登録されている
- [✓] Google Sheets の `trade` スプレッドシートがサービスアカウントに共有されている
- [ ] Cloudflare Pages の Build output directory が `dashboard` に設定されている
- [ ] デプロイ後、`/data/predictions.json` の Response Header に `Cache-Control: no-store` が含まれている
- [ ] GitHub Actions を手動実行（`workflow_dispatch`）して全ステップが成功することを確認
- [ ] Slack に通知が届くことを確認
