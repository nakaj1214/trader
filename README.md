# AI Stock Predictor

週次の株式スクリーニング、価格予測、実績追跡、通知、GUI用データ出力をまとめた Python プロジェクトです。
米国株（S&P500・NASDAQ100）と日本株（日経225）の両方に対応しています。

## 1. 現在の実装範囲

- 共通ユーティリティ: `src/utils.py`（設定・環境変数ロード）
- スクリーニング: `src/screener.py`（US株・日本株対応）
- 予測: `src/predictor.py`（Prophet）
- 実績追跡: `src/tracker.py`
- 予測補強: `src/enricher.py`（リスク指標・イベント・エビデンス・選出理由・ポジションサイジング）
- Google Sheets 記録: `src/sheets.py`
- 通知: `src/notifier.py`（Slack）+ `src/line_notifier.py`（LINE補助通知）
- GUIデータ出力: `src/exporter.py`（`dashboard/data/*.json`）
- 静的GUI: `dashboard/*.html`, `dashboard/us/`, `dashboard/jp/`, `dashboard/js/*.js`
- マクロ指標取得: `src/macro_fetcher.py`（FRED API）
- 日本株財務データ補完: `src/jquants_fetcher.py`（J-Quants API）
- US株ニュース・センチメント: `src/finnhub_fetcher.py`（Finnhub API）
- 財務データ最終フォールバック: `src/fmp_fetcher.py`（Financial Modeling Prep API）
- アノマリー統計検証: `src/alpha_survey.py`（アルファサーベイ）
- 株式用語ヘルプ: `src/glossary.py`（CLI検索・レポート埋め込み）
- バックテスト戦略比較: `src/baseline.py`
- 共通メタデータ生成: `src/meta.py`

注記:
- `config.yaml` に `openai` セクションはありますが、現行 `src` では OpenAI API を呼び出していません。
- `FRED_API_KEY` 環境変数がない場合は `macro.json` 生成をスキップします。
- 各外部 API（J-Quants・Finnhub・FMP）は API キー未設定時も degraded mode で動作し、該当データを `null` として継続します。

## 2. 実行フロー（`python -m src.main`）

1. 米国株スクリーニング（S&P500・NASDAQ100）
2. 日本株スクリーニング（nikkei225 が有効な場合、独立フロー）
3. AI価格予測（Prophet、上昇予測のみ採用）
4. 前週分の実績追跡と的中率計算
5. 予測結果の Sheets 追記
6. Slack 通知（必要に応じて LINE 補助通知）
7. ダッシュボード JSON 出力（リスク指標・エビデンス・選出理由・誤差分析・ポジションサイジングを含む）
8. アルファサーベイ（アノマリー統計検証 → `alpha_survey.json`）

## 3. ディレクトリ構成（主要部）

```text
trader/
  src/
    utils.py           # 共通ユーティリティ（設定・環境変数）
    meta.py            # 共通メタデータ生成
    glossary.py        # 株式用語ヘルプ（CLI検索・レポート埋め込み）
    screener.py        # 銘柄スクリーニング（US・JP対応）
    predictor.py       # 価格予測（Prophet）
    tracker.py         # 実績追跡
    enricher.py        # 予測補強（リスク・イベント・エビデンス・選出理由・ポジションサイジング）
    baseline.py        # 戦略比較・バックテスト品質開示
    exporter.py        # JSON出力（誤差分析・マクロ指標含む）
    macro_fetcher.py   # マクロ指標取得（FRED API）
    jquants_fetcher.py # 日本株財務データ（J-Quants API）
    finnhub_fetcher.py # US株ニュース・センチメント（Finnhub API）
    fmp_fetcher.py     # 財務データ最終フォールバック（FMP API）
    alpha_survey.py    # アノマリー統計検証（アルファサーベイ）
    sheets.py          # Google Sheets 記録
    notifier.py        # Slack 通知
    line_notifier.py   # LINE 通知
    main.py            # オーケストレーター
  dashboard/
    index.html         # 最新週サマリー（マクロバナー付き）
    accuracy.html      # 的中率推移 + 予測誤差分析 + バックテスト品質開示
    stock.html         # 銘柄詳細（リスク・エビデンス・選出理由・ポジションサイジング）
    simulator.html     # 投資シミュレータ
    us/                # US株専用ダッシュボード（index / accuracy / stock）
    jp/                # 日本株専用ダッシュボード（index / accuracy / stock）
    js/
      app.js           # 共通アプリロジック
      index.js         # インデックス共通
      index_us.js      # US株インデックス描画
      index_jp.js      # 日本株インデックス描画
      accuracy.js      # 的中率・誤差グラフ
      stock.js         # 銘柄詳細
      macro.js         # マクロバナー描画
      simulator.js     # シミュレータロジック
    css/
    data/
      predictions.json
      accuracy.json
      stock_history.json
      alpha_survey.json
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
cd trader
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
| `JQUANTS_API_KEY` | J-Quants API（日本株財務データ、V2） | 任意。未設定時は V1 フォールバックまたは degraded mode |
| `JQUANTS_MAIL_ADDRESS` | J-Quants 認証メール（V1フォールバック） | `JQUANTS_API_KEY` 未設定時のみ参照 |
| `JQUANTS_PASSWORD` | J-Quants 認証パスワード（V1フォールバック） | `JQUANTS_API_KEY` 未設定時のみ参照 |
| `FINNHUB_API_KEY` | Finnhub API（US株ニュース・センチメント） | 任意。未設定時は `news_sentiment: null` |
| `FMP_API_KEY` | Financial Modeling Prep API（財務データフォールバック） | 任意。未設定時は FMP 補完をスキップ |
| `OPENAI_API_KEY` | 将来拡張用 | 現行コードでは未使用 |

FRED API キーは [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) で無料取得できます。

## 6. 設定ファイル（`config.yaml`）

主要キー:

- `screening`: 市場（`sp500` / `nasdaq100` / `nikkei225`）、上位件数、時価総額フィルタ、テクニカル重み
- `screening.min_avg_dollar_volume_us`: US株 日次平均売買代金下限（ドル建て）
- `screening.min_avg_dollar_volume_jp`: JP株 日次平均売買代金下限（円建て）
- `screening.exclude_days_to_earnings`: 決算 N 日前の JP 銘柄を警告（0で無効）
- `prediction`: `history_days`, `forecast_days`
- `prophet`: `interval_width`, `changepoint_prior_scale`, `uncertainty_samples`
- `google_sheets`: `spreadsheet_name`, `worksheet_name`
- `slack.channel`: LINE文面にも反映されるチャンネル名
- `display.beginner_mode`: 用語メモの付与
- `notifications.slack.enabled`, `notifications.line.enabled`
- `line.enabled`（旧形式。`notifications.line.enabled` が優先）
- `guardrail`: `clip_pct`（上限クリップ）, `warn_pct`（警告しきい値）
- `sizing`: `vol_target_ann`（目標年率ボラ）, `max_weight_cap`（最大保有比率）, `stop_loss_multiplier`（損切り係数）
- `backtest`: `num_rules_tested`, `num_parameters_tuned`, `oos_start`, `min_rules_for_pbo`
- `jquants.enabled`: J-Quants API の有効/無効
- `finnhub.enabled`: Finnhub API の有効/無効
- `fmp.enabled`: FMP API の有効/無効

## 7. 実行コマンド

全体実行:

```bash
python -m src.main
```

GUI用 JSON だけ再生成:

```bash
python -m src.exporter
```

用語検索（CLI）:

```bash
python -m src.glossary RSI
```

## 8. ダッシュボード確認

```bash
python -m src.exporter
cd dashboard
python -m http.server 8000
```

### 共通ページ
- `http://localhost:8000/index.html` — 最新週サマリー（マクロバナー・リスク行・イベントバッジ付き）
- `http://localhost:8000/accuracy.html` — 的中率推移・銘柄ランキング・予測誤差分析・バックテスト品質開示
- `http://localhost:8000/stock.html?ticker=AAPL` — 銘柄詳細（リスク・エビデンス・選出理由・ポジションサイジング）
- `http://localhost:8000/simulator.html` — 投資シミュレータ

### US株専用
- `http://localhost:8000/us/index.html` — US株サマリー
- `http://localhost:8000/us/accuracy.html` — US株的中率
- `http://localhost:8000/us/stock.html?ticker=AAPL` — US株銘柄詳細

### 日本株専用
- `http://localhost:8000/jp/index.html` — 日本株サマリー
- `http://localhost:8000/jp/accuracy.html` — 日本株的中率
- `http://localhost:8000/jp/stock.html?ticker=7203.T` — 日本株銘柄詳細

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
- `tests/test_jquants_fetcher.py`（J-Quants API・日本株財務データ）
- `tests/test_finnhub_fetcher.py`（Finnhub API・ニュース・センチメント）
- `tests/test_fmp_fetcher.py`（FMP API・財務データフォールバック）
- `tests/test_alpha_survey.py`（アノマリー統計検証）
- `tests/test_dashboard_html.py`（ダッシュボードHTML構造）

## 10. GitHub Actions

`.github/workflows/weekly_run.yml` で週次実行します（毎週日曜 JST 09:00）。

- `src.main` 実行（米国株・日本株スクリーニング → 予測 → 追跡 → 通知 → エクスポート → アルファサーベイ）
- `src.exporter` 実行（`FRED_API_KEY` があれば `macro.json` も生成）
- `dashboard/data/*.json` のコミット・push

必要な Secrets:
- `GOOGLE_CREDENTIALS_JSON`
- `SLACK_WEBHOOK_URL`
- （LINE通知を使う場合）`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`
- （マクロ指標を使う場合）`FRED_API_KEY`
- （日本株財務データを使う場合）`JQUANTS_API_KEY` または `JQUANTS_MAIL_ADDRESS` + `JQUANTS_PASSWORD`
- （US株センチメントを使う場合）`FINNHUB_API_KEY`
- （財務データフォールバックを使う場合）`FMP_API_KEY`
- （互換性維持）`OPENAI_API_KEY`

## 11. 実装フェーズ一覧

| フェーズ | 内容 | 主なファイル |
|---|---|---|
| Phase 1–3 | スクリーニング・予測・実績追跡 | `screener.py`, `predictor.py`, `tracker.py` |
| Phase 4 | リスク指標・イベント・エビデンス | `enricher.py` |
| Phase 5 | 予測ガードレール（clip/warn） | `enricher.py`, `guardrail` in config |
| Phase 6 | 戦略比較（AI/モメンタム/SPY） | `baseline.py`, `accuracy.html` |
| Phase 7 | 確率校正ダッシュボード | `exporter.py`, `accuracy.html` |
| Phase 8 | ポジションサイジング + 損切り規律 | `enricher.py`, `sizing` in config |
| Phase 9 | バックテスト品質開示 | `baseline.py`, `accuracy.html`, `backtest` in config |
| Phase 10 | マクロ指標統合（FRED） | `macro_fetcher.py`, `exporter.py`, `macro.js` |
| Phase 11 | アルファサーベイ（アノマリー統計検証） | `alpha_survey.py`, `alpha_survey.json` |
| Phase 13 | 52週高値モメンタムスコア | `screener.py`, `fifty2w_score` in config |
| Phase 15 | 日本株スクリーニング独立フロー | `screener.py`, `main.py`, `jp/` dashboard |
| Phase 17 | J-Quants API（日本株財務データ補完） | `jquants_fetcher.py`, `jquants` in config |
| Phase 18 | Finnhub ニュース・センチメント（US株） | `finnhub_fetcher.py`, `finnhub` in config |
| Phase 19 | FMP グローバル財務データフォールバック | `fmp_fetcher.py`, `fmp` in config |
| Phase 23 | 売買代金フィルタ（US/JP別） | `screener.py`, `min_avg_dollar_volume_*` in config |
| Phase 24 | 決算 N 日前警告（JP株） | `screener.py`, `exclude_days_to_earnings` in config |
| Phase 25 | Prophet パラメータ設定 | `predictor.py`, `prophet` in config |

## 12. ユーザー向けガイド

利用手順は `docs/guide/USER_GUIDE.md` を参照してください。
