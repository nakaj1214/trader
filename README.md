# AI Stock Predictor

週次の株式スクリーニング、価格予測、実績追跡、通知、ダッシュボード用データ出力をまとめた Python プロジェクトです。
米国株（S&P500・NASDAQ100）と日本株（日経225）に対応しています。

## 1. アーキテクチャ

```text
trader/
  src/
    cli.py                # Typer CLI エントリーポイント
    orchestrator.py       # パイプラインオーケストレーター
    core/                 # 設定・モデル・メタデータ・例外
    screening/            # 銘柄スクリーニング（US/JP対応）
    prediction/           # 価格予測（Prophet + LightGBM アンサンブル）
    evaluation/           # 実績追跡・バックテスト・ウォークフォワード・アルファサーベイ
    enrichment/           # リスク指標・イベント・エビデンス・センチメント・ポジションサイジング
    export/               # JSON/Sheets エクスポーター
    notification/         # Slack/LINE 通知
    analysis/             # LLM 駆動の財務分析
    data/                 # データリポジトリ・外部プロバイダー
  config/
    default.yaml          # デフォルト設定
  dashboard/              # 静的 GUI（HTML/JS/CSS）
  dashboard-v2/           # 次世代ダッシュボード（SvelteKit）
  data/                   # 銘柄リスト CSV・用語辞書
  tests/                  # テストスイート
  .github/workflows/
    weekly_run_v2.yml     # 週次パイプライン実行
    deploy_dashboard.yml  # Cloudflare Pages デプロイ
    test.yml              # CI テスト・lint
```

## 2. 実行フロー（`python -m src.cli run`）

1. 米国株スクリーニング（S&P500・NASDAQ100）
2. 日本株スクリーニング（nikkei225）
3. 価格予測（Prophet + LightGBM アンサンブル）
4. 前週分の実績追跡と的中率計算
5. DB / Google Sheets への記録
6. 予測補強（リスク・イベント・エビデンス・センチメント・ポジションサイジング）
7. Slack / LINE 通知
8. ダッシュボード JSON 出力
9. ウォークフォワード・アルファサーベイ・マクロ指標エクスポート

## 3. セットアップ

```bash
cd trader
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e ".[dev]"
```

ML 機能（Prophet / LightGBM）を使う場合:

```bash
pip install -e ".[dev,ml]"
```

## 4. 環境変数

`.env.example` をコピーして `.env` を作成します。

| 変数 | 用途 | 必須条件 |
|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | Google Sheets 認証 | Sheets 記録時は必須 |
| `SLACK_WEBHOOK_URL` | Slack 通知 | Slack 通知有効時は必須 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE 通知 | LINE 通知有効時のみ |
| `LINE_USER_ID` | LINE 送信先 | LINE 通知有効時のみ |
| `FRED_API_KEY` | マクロ指標取得（FRED API） | 任意 |
| `JQUANTS_API_KEY` | 日本株財務データ（J-Quants API） | 任意 |
| `FINNHUB_API_KEY` | US株ニュース・センチメント | 任意 |
| `FMP_API_KEY` | 財務データフォールバック | 任意 |
| `OPENAI_API_KEY` | LLM 分析（analysis コマンド） | analysis 使用時のみ |

## 5. 設定ファイル（`config/default.yaml`）

主要セクション:

- `screening`: 市場・上位件数・フィルタ・スコアリング重み
- `prediction`: history_days / forecast_days / Prophet / LightGBM パラメータ
- `evaluation`: バックテスト・ウォークフォワード設定
- `enrichment`: リスク・イベント・エビデンス・センチメント・サイジング
- `export`: JSON 出力パス
- `notification`: Slack / LINE 設定
- `providers`: 外部 API 設定（FRED / J-Quants / Finnhub / FMP）
- `analysis`: LLM 分析設定

## 6. コマンド

```bash
# 全体パイプライン実行
python -m src.cli run --market all

# スクリーニングのみ
python -m src.cli screen --market us

# 予測のみ（スクリーニング含む）
python -m src.cli predict --market us

# ダッシュボード JSON 再生成
python -m src.cli export

# LLM 財務分析
python -m src.cli analyze --ticker AAPL,MSFT --type dcf

# バージョン表示
python -m src.cli version
```

## 7. テスト

```bash
python -m pytest tests/
```

主なテスト:

- `tests/test_config.py` — 設定ロード・バリデーション
- `tests/test_orchestrator.py` — パイプラインオーケストレーター
- `tests/test_screening_new.py` — スクリーニング
- `tests/test_prediction_new.py` — 予測
- `tests/test_evaluation.py` — 実績追跡・バックテスト
- `tests/test_json_exporter.py` — JSON エクスポーター
- `tests/test_repository.py` — データリポジトリ
- `tests/test_analysis_*.py` — LLM 分析モジュール
- `tests/test_dashboard_html.py` — ダッシュボード HTML 構造

## 8. GitHub Actions

### weekly_run_v2.yml（週次実行 — 毎週日曜 JST 09:00）

1. `python -m src.cli run --market all` 実行
2. `dashboard/data/*.json` をコミット・push

### deploy_dashboard.yml（ダッシュボードデプロイ）

- `dashboard-v2` をビルドし Cloudflare Pages へデプロイ
- `dashboard/data/*.json` を静的アセットとして配信

### test.yml（CI）

- ruff lint
- pytest（カバレッジ 80% 目標）

必要な GitHub Secrets:

- `GOOGLE_CREDENTIALS_JSON`
- `SLACK_WEBHOOK_URL`
- （任意）`FRED_API_KEY`, `JQUANTS_API_KEY`, `FINNHUB_API_KEY`, `FMP_API_KEY`

## 9. ユーザーガイド

利用手順は `docs/guide/USER_GUIDE.md` を参照してください。
