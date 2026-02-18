# AI Stock Predictor

グローバル株式市場から成長候補銘柄をスクリーニングし、Prophet による来週株価予測・的中率追跡・Slack 通知を全自動で行うワークフローです。
GitHub Actions で毎週日曜日に自動実行されます。

## 機能概要

```
Step 1: スクリーニング   — S&P500 / NASDAQ100 からテクニカル指標でトップ N 銘柄を選出
Step 2: AI 価格予測      — Prophet で 5 営業日後の株価を予測（上昇銘柄のみ通過）
Step 3: スプレッドシート記録 — 予測結果を Google Sheets に追記
Step 4: 的中率追跡       — 前週予測の実績を評価し、的中率を算出
Step 5: Slack 通知       — 予測リストと先週の的中率をチャンネルへ投稿
```

## ディレクトリ構成

```
trader/
├── src/
│   ├── main.py        # オーケストレーター（全ステップを順次実行）
│   ├── screener.py    # Step 1: 銘柄スクリーニング
│   ├── predictor.py   # Step 2: Prophet による価格予測
│   ├── sheets.py      # Step 3/4: Google Sheets 読み書き
│   ├── tracker.py     # Step 4: 的中率追跡
│   ├── notifier.py    # Step 5: Slack 通知
│   ├── glossary.py    # 初心者向け用語解説
│   └── utils.py       # 設定読み込み等のユーティリティ
├── data/
│   ├── sp500.csv      # S&P500 銘柄リスト
│   ├── nasdaq100.csv  # NASDAQ100 銘柄リスト
│   └── nikkei225.csv  # 日経225 銘柄リスト（デフォルト無効）
├── tests/
│   ├── test_predictor.py
│   ├── test_screener.py
│   └── test_sheets_tracker.py
├── .github/workflows/
│   └── weekly_run.yml # GitHub Actions（毎週日曜 09:00 JST）
├── config.yaml        # スクリーニング・予測・通知の設定
├── .env.example       # 環境変数のサンプル
└── requirements.txt
```

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、各キーを設定します。

```bash
cp .env.example .env
```

| 変数名 | 説明 |
|--------|------|
| `OPENAI_API_KEY` | OpenAI API キー |
| `GOOGLE_CREDENTIALS_JSON` | Google サービスアカウント認証情報 JSON のパス |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

### 3. Google Sheets の準備

1. Google Cloud Console でサービスアカウントを作成し、Sheets API を有効化
2. 認証情報 JSON をダウンロードして `GOOGLE_CREDENTIALS_JSON` に設定
3. `config.yaml` の `spreadsheet_name` と同名のスプレッドシートをサービスアカウントと共有

## 設定（config.yaml）

```yaml
screening:
  markets: [sp500, nasdaq100]   # 対象市場
  top_n: 10                     # 選出上位数
  min_market_cap: 10_000_000_000  # 最低時価総額（100億ドル）
  lookback_days: 30             # テクニカル計算の参照期間
  weights:
    price_change_1m: 0.3        # 直近1ヶ月株価上昇率
    volume_trend:    0.2        # 出来高増加トレンド
    rsi_score:       0.25       # RSI スコア（30〜70 の中間帯が高評価）
    macd_signal:     0.25       # MACD シグナル

prediction:
  history_days: 90   # 予測に使う過去データ日数
  forecast_days: 5   # 予測する将来の営業日数（1週間）

openai:
  model: gpt-4o-mini   # 用語解説生成に使用

display:
  beginner_mode: true  # 初心者向け用語解説を Slack レポートに追加
```

## 手動実行

```bash
python -m src.main
```

## 自動実行（GitHub Actions）

`.github/workflows/weekly_run.yml` により、**毎週日曜 09:00 JST** に自動実行されます。
リポジトリ Settings > Secrets and variables > Actions に以下の Secrets を登録してください。

- `OPENAI_API_KEY`
- `GOOGLE_CREDENTIALS_JSON`
- `SLACK_WEBHOOK_URL`

手動実行は Actions タブから `workflow_dispatch` で行えます。

## テスト

```bash
pytest tests/
```

主なテストケース:

| ファイル | 内容 |
|---------|------|
| `test_screener.py` | スクリーニングロジック・時価総額フィルタ |
| `test_predictor.py` | Prophet 予測・営業日計算 |
| `test_sheets_tracker.py` | 的中率集計・評価不能除外・祝日対応 |

## 的中率の評価ロジック

- **評価日**: 予測日から **5 営業日後** の実取引日終値（yfinance の実データをカウント、祝日を自動スキップ）
- **判定**: 予測価格 > 現在価格 かつ 実績終値 > 現在価格 → 的中
- **「評価不能」**: 終値が取得できなかった銘柄。的中率の分母から除外される
- **最新週が全件「評価不能」**: その週を `hits=0 / total=0` として表示（過去週の値にならない）

## 技術スタック

| カテゴリ | ライブラリ |
|---------|-----------|
| データ取得 | yfinance |
| テクニカル指標 | ta |
| AI 予測 | Prophet |
| AI 補助（用語解説） | OpenAI API |
| スプレッドシート | gspread, google-auth |
| Slack 通知 | requests |
| 設定管理 | pyyaml, python-dotenv |
