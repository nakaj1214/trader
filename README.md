# AI Stock Predictor

週次の株式スクリーニング、価格予測、実績追跡、通知、GUI用データ出力をまとめた Python プロジェクトです。

## 1. 現在の実装範囲

- スクリーニング: `src/screener.py`
- 予測: `src/predictor.py`（Prophet）
- 実績追跡: `src/tracker.py`
- 予測補強: `src/enricher.py`（リスク指標・イベント・エビデンス・選出理由・ポジションサイジング）
- Google Sheets 記録: `src/sheets.py`
- 通知: `src/notifier.py`（Slack）+ `src/line_notifier.py`（LINE補助通知）
- GUIデータ出力: `src/exporter.py`（`dashboard/data/*.json`）
- 静的GUI: `dashboard/*.html`, `dashboard/js/*.js`
- マクロ指標取得: `src/macro_fetcher.py`（FRED API）

注記:
- `config.yaml` に `openai` セクションはありますが、現行 `src` では OpenAI API を呼び出していません。
- `FRED_API_KEY` 環境変数がない場合は `macro.json` 生成をスキップします。

## 2. 実行フロー（`python -m src.main`）

1. 銘柄スクリーニング
2. 予測（上昇予測のみ採用）
3. 前週分の実績追跡と的中率計算
4. 予測結果の Sheets 追記
5. Slack 通知（必要に応じて LINE 補助通知）
6. ダッシュボード JSON 出力（リスク指標・エビデンス・選出理由・誤差分析・ポジションサイジングを含む）

## 3. ディレクトリ構成（主要部）

```text
trader-main/
  src/
    enricher.py        # 予測補強（リスク・イベント・エビデンス・選出理由・ポジションサイジング）
    exporter.py        # JSON出力（誤差分析・マクロ指標含む）
    macro_fetcher.py   # マクロ指標取得（FRED API）
    screener.py        # 銘柄スクリーニング
    predictor.py       # 価格予測
    tracker.py         # 実績追跡
    baseline.py        # 戦略比較・バックテスト品質開示
    ...
  dashboard/
    index.html         # 最新週サマリー（マクロバナー付き）
    accuracy.html      # 的中率推移 + 予測誤差分析 + バックテスト品質開示
    stock.html         # 銘柄詳細（リスク・エビデンス・選出理由・ポジションサイジング）
    simulator.html     # 投資シミュレータ
    js/
      macro.js         # マクロバナー描画
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
| `FRED_API_KEY` | FRED API（マクロ指標取得） | 任意。未設定時は `macro.json` 生成をスキップ |
| `OPENAI_API_KEY` | 将来拡張用 | 現行コードでは未使用 |

FRED API キーは [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) で無料取得できます。

## 6. 設定ファイル（`config.yaml`）

主要キー:

- `screening`: 市場、上位件数、時価総額フィルタ、テクニカル重み
- `prediction`: `history_days`, `forecast_days`
- `google_sheets`: `spreadsheet_name`, `worksheet_name`
- `slack.channel`: LINE文面にも反映されるチャンネル名
- `display.beginner_mode`: 用語メモの付与
- `notifications.slack.enabled`, `notifications.line.enabled`
- `line.enabled`（旧形式。`notifications.line.enabled` が優先）
- `guardrail`: `clip_pct`（上限クリップ）, `warn_pct`（警告しきい値）
- `sizing`: `vol_target_ann`（目標年率ボラ）, `max_weight_cap`（最大保有比率）, `stop_loss_multiplier`（損切り係数）
- `backtest`: `num_rules_tested`, `num_parameters_tuned`, `oos_start`, `min_rules_for_pbo`

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

- `http://localhost:8000/index.html` — 最新週サマリー（マクロバナー・リスク行・イベントバッジ付き）
- `http://localhost:8000/accuracy.html` — 的中率推移・銘柄ランキング・予測誤差分析・バックテスト品質開示
- `http://localhost:8000/stock.html?ticker=AAPL` — 銘柄詳細（リスク・エビデンス・選出理由・ポジションサイジング）
- `http://localhost:8000/simulator.html` — 投資シミュレータ

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
- `tests/test_enricher.py`（リスク指標・イベント・エビデンス・選出理由・誤差分析・ポジションサイジング）
- `tests/test_baseline.py`（戦略比較・バックテスト品質開示）
- `tests/test_macro_fetcher.py`（FRED API・マクロ指標・リスクオフ判定）

## 10. GitHub Actions

`.github/workflows/weekly_run.yml` で週次実行します。

- `src.main` 実行
- `src.exporter` 実行（`FRED_API_KEY` があれば `macro.json` も生成）
- `dashboard/data/*.json` のコミット・push

必要な Secrets:
- `GOOGLE_CREDENTIALS_JSON`
- `SLACK_WEBHOOK_URL`
- （LINE通知を使う場合）`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`
- （マクロ指標を使う場合）`FRED_API_KEY`
- （互換性維持）`OPENAI_API_KEY`

## 11. 実装フェーズ一覧

| フェーズ | 内容 | 主なファイル |
|---|---|---|
| Phase 1-3 | スクリーニング・予測・実績追跡 | `screener.py`, `predictor.py`, `tracker.py` |
| Phase 4 | リスク指標・イベント・エビデンス | `enricher.py` |
| Phase 5 | 予測ガードレール（clip/warn） | `enricher.py`, `guardrail` in config |
| Phase 6 | 戦略比較（AI/モメンタム/SPY） | `baseline.py`, `accuracy.html` |
| Phase 7 | 確率校正ダッシュボード | `exporter.py`, `accuracy.html` |
| Phase 8 | ポジションサイジング + 損切り規律 | `enricher.py`, `sizing` in config |
| Phase 9 | バックテスト品質開示 | `baseline.py`, `accuracy.html`, `backtest` in config |
| Phase 10 | マクロ指標統合（FRED） | `macro_fetcher.py`, `exporter.py`, `macro.js` |

## 12. ユーザー向けガイド

利用手順は `docs/guide/USER_GUIDE.md` を参照してください。
