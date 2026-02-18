# AI Stock Predictor

週次の株式スクリーニング、価格予測、実績追跡、通知、GUI用データ出力をまとめた Python プロジェクトです。

## 1. 現在の実装範囲

- スクリーニング: `src/screener.py`
- 予測: `src/predictor.py`（Prophet）
- 実績追跡: `src/tracker.py`
- Google Sheets 記録: `src/sheets.py`
- 通知: `src/notifier.py`（Slack）+ `src/line_notifier.py`（LINE補助通知）
- GUIデータ出力: `src/exporter.py`（`dashboard/data/*.json`）
- 静的GUI: `dashboard/*.html`, `dashboard/js/*.js`

注記:
- `config.yaml` に `openai` セクションはありますが、現行 `src` では OpenAI API を呼び出していません。

## 2. 実行フロー（`python -m src.main`）

1. 銘柄スクリーニング
2. 予測（上昇予測のみ採用）
3. 前週分の実績追跡と的中率計算
4. 予測結果の Sheets 追記
5. Slack 通知（必要に応じて LINE 補助通知）
6. ダッシュボード JSON 出力

## 3. ディレクトリ構成（主要部）

```text
trader-main/
  src/
  dashboard/
    index.html
    accuracy.html
    stock.html
    js/
    css/
  data/
    sp500.csv
    nasdaq100.csv
    nikkei225.csv
    glossary.yaml
  tests/
  .github/workflows/weekly_run.yml
  config.yaml
  .env.example
```

## 4. セットアップ（開発者向け）

```bash
cd trader-main
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

テスト実行する場合は追加で:

```bash
pip install pytest
```

## 5. 環境変数

`.env.example` をコピーして `.env` を作成します。

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

| 変数 | 用途 | 必須条件 |
|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | Google Sheets 認証（ファイルパス or JSON文字列） | `src.main` / `src.exporter` 実行時は必須 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook | `notifications.slack.enabled=true` の場合必須 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API | LINE通知有効時のみ必須 |
| `LINE_USER_ID` | LINE送信先ユーザーID | LINE通知有効時のみ必須 |
| `OPENAI_API_KEY` | 将来拡張用 | 現行コードでは未使用 |

## 6. 設定ファイル（`config.yaml`）

主要キー:

- `screening`: 市場、上位件数、時価総額フィルタ、テクニカル重み
- `prediction`: `history_days`, `forecast_days`
- `google_sheets`: `spreadsheet_name`, `worksheet_name`
- `slack.channel`: LINE文面にも反映されるチャンネル名
- `display.beginner_mode`: 用語メモの付与
- `notifications.slack.enabled`, `notifications.line.enabled`
- `line.enabled`（旧形式。`notifications.line.enabled` が優先）

## 7. 実行コマンド

全体実行:

```bash
python -m src.main
```

GUI用 JSON だけ再生成:

```bash
python -m src.exporter
```

## 8. ダッシュボード確認

```bash
python -m src.exporter
cd dashboard
python -m http.server 8000
```

- `http://localhost:8000/index.html`
- `http://localhost:8000/accuracy.html`
- `http://localhost:8000/stock.html?ticker=AAPL`

## 9. テスト

```bash
python -m pytest tests/
```

主なテスト対象:
- `tests/test_screener.py`
- `tests/test_predictor.py`
- `tests/test_sheets_tracker.py`
- `tests/test_notifier.py`
- `tests/test_line_notifier.py`
- `tests/test_exporter.py`

## 10. GitHub Actions

`.github/workflows/weekly_run.yml` で週次実行します。

- `src.main` 実行
- `src.exporter` 実行
- `dashboard/data/*.json` のコミット・push

必要な Secrets:
- `GOOGLE_CREDENTIALS_JSON`
- `SLACK_WEBHOOK_URL`
- （LINE通知を使う場合）`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`
- （互換性維持）`OPENAI_API_KEY`

## 11. ユーザー向けガイド

利用手順は `docs/current/USER_GUIDE.md` を参照してください。
