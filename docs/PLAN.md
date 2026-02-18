# 自動AI株式分析 & 追跡ワークフロー - 計画書 v3

> 最終更新: 2026-02-18
> レビュー指摘(review.md) 8件反映済み

## 概要

グローバル市場データから成長株を自動スクリーニングし、AIで価格予測を行い、結果をGoogleスプレッドシートに記録・追跡するシステム。毎週日曜日に自動実行され、Slack Webhook経由で通知を行う。

**v2からの主な変更点**:
- [High #1] Slack方針を **Webhook-only** に統一。Slash Command/Bot関連を削除
- [High #2] Secrets一覧をWebhook構成に合わせて修正
- [Medium #3] OpenAIモデルを **config.yamlで切替可能**（デフォルト: gpt-4o-mini）に統一
- [Medium #4] 価格・性能データに **最終確認日** を追記
- [Medium #5] Prophetインストール手順を **検証済みバージョン付き** で記載
- [Medium #6] 判定基準を **対象市場の最終営業日終値** に固定
- [Low #7] Phase番号の飛びを修正（Phase 1→2→3の連続性を確保）
- [Low #8] 銘柄ユニバース取得方法を **静的リスト+補助API** に変更

---

## システム構成図

```
グローバル市場データ
       │
       ▼
┌─────────────────┐
│ ステップ1        │
│ 自動スクリーニング │ → 成長株トップ10を抽出
│                  │    銘柄リスト: 静的CSV + yfinance補助
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ステップ2        │    Phase 1: Prophet (時系列予測)
│ AI価格予測       │    Phase 2: + scikit-learn (アンサンブル)
│ (上昇のみ)       │    Phase 3: + OpenAI (ニュース分析・解説)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ステップ3        │
│ Googleスプレッド  │ → 日付/ティッカー/予測価格/ステータスを記録
│ シート自動記録    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ステップ4        │
│ 前週比較         │ → 先週の予測 vs 実績を比較、的中率を算出
│ (的中率追跡)     │    判定基準: 対象市場の最終営業日終値
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ステップ5        │
│ Slack通知        │ → Webhook-only で #stock-alerts に投稿
│ 毎週自動実行     │    初心者モード時は用語解説付き
└─────────────────┘

※ 毎週日曜日に繰り返し
```

---

## 技術スタック

| カテゴリ | 技術 | 理由 |
|---------|------|------|
| 言語 | Python 3.11+ | データ分析・ML系ライブラリが豊富 |
| 株式データ取得 | `yfinance` | 無料でグローバル市場データ取得可能 |
| 銘柄ユニバース | **静的CSVリスト** + yfinance補助 | [#8] 指数構成銘柄の直接取得に依存しない設計 |
| スクリーニング | `pandas` + `ta` (テクニカル分析) | 柔軟なフィルタリング |
| AI価格予測(主) | `prophet` (Meta) | 無料・初心者でも扱いやすい時系列予測 |
| AI価格予測(補助) | OpenAI API (**config.yamlで切替**) | デフォルト: gpt-4o-mini。用語解説・要約生成 |
| スプレッドシート | Google Sheets API (`gspread`) | 自動記録・閲覧共有が容易 |
| 通知 | **Slack Incoming Webhook** | [#1] Webhook-onlyに統一。シンプルで矛盾なし |
| スケジューラ | GitHub Actions | 毎週日曜の自動実行 |
| 設定管理 | `.env` + `config.yaml` | APIキー等の安全管理 |

---

## 設計判断の根拠

### 1. Slack方針: Webhook-only [#1 #2 解決]

**決定**: Incoming Webhook のみ使用。Bot/Slash Commandは採用しない。

**理由**:
- Webhook-onlyなら `SLACK_WEBHOOK_URL` だけで完結し、認証設計が単純
- Bot Token / Signing Secret が不要になり、Secrets管理が簡素化
- サーバー常駐が不要（GitHub Actionsのバッチ実行のみ）

**ヘルプ機能への影響**:
- ~~Slackで `/stock-help RSI` と入力して回答~~ → 採用しない
- 代替: レポート本文に用語解説を埋め込む（`beginner_mode`）
- 代替: CLI `python -m src.glossary RSI` でローカル検索

### 2. OpenAIモデル: config.yamlで切替可能 [#3 解決]

**決定**: デフォルト `gpt-4o-mini`。config.yamlの `openai.model` で変更可能。

```yaml
# config.yaml
openai:
  model: "gpt-4o-mini"   # "gpt-4o" 等に変更可能
```

**コスト試算** (最終確認日: 2026-02-18):

| モデル | 入力単価 | 出力単価 | 週コスト | 月コスト | 年コスト |
|--------|---------|---------|---------|---------|---------|
| gpt-4o-mini | $0.15/1Mトークン | $0.60/1Mトークン | $0.006 | $0.024 | $0.31 |
| gpt-4o | $2.50/1Mトークン | $10.00/1Mトークン | $0.10 | $0.40 | $5.20 |

> ※ 想定: 週10リクエスト、入力2000トークン/出力500トークン
> ※ 価格出典: https://openai.com/api/pricing/ (最終確認: 2026-02-18)
> ※ `docs/stock_prediction_comparison.md` はGPT-4o前提の参考資料であり、本計画の採用モデルとは異なる

### 3. 判定基準時刻の明確化 [#6 解決]

**決定**: 全ての価格判定は **対象市場の最終営業日終値 (Close)** を使用する。

| 対象市場 | 取得タイミング | 基準 |
|---------|--------------|------|
| 米国 (NYSE/NASDAQ) | 金曜 16:00 ET 終値 | 日曜実行時に前営業日(金曜)の終値を取得 |
| 日本 (TSE) | 金曜 15:00 JST 終値 | 同上 |

- 祝日等で金曜が休場の場合、直前の営業日終値を使用
- `yfinance` の `Close` 列を使用（`Adj Close` ではなく）

### 4. 銘柄ユニバースの取得方法 [#8 解決]

**決定**: 静的CSVリスト を主、yfinance を補助とする。

**理由**: `yfinance` で指数構成銘柄を直接取得するAPIは不安定で、将来的に変更される可能性がある。

```
data/
├── sp500.csv       # S&P500構成銘柄 (ティッカー一覧)
├── nasdaq100.csv   # NASDAQ100構成銘柄
└── nikkei225.csv   # 日経225構成銘柄
```

- 銘柄リストは手動またはスクリプトで定期更新（四半期ごと推奨）
- `config.yaml` でどの市場を対象にするか設定可能

```yaml
# config.yaml
screening:
  markets:
    - "sp500"
    - "nasdaq100"
    # - "nikkei225"  # 必要に応じて有効化
```

---

## ディレクトリ構成

```
trader/
├── docs/
│   ├── PLAN.md                      # 本計画書
│   └── stock_prediction_comparison.md  # 予測手法比較（参考資料）
├── requirements.txt                 # Python依存パッケージ (バージョン固定)
├── config.yaml                      # スクリーニング条件・設定
├── .env.example                     # 環境変数テンプレート
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── main.py              # メインオーケストレーター
│   ├── screener.py          # ステップ1: 自動スクリーニング
│   ├── predictor.py         # ステップ2: AI価格予測 (Prophet → scikit-learn → OpenAI)
│   ├── sheets.py            # ステップ3: Googleスプレッドシート連携
│   ├── tracker.py           # ステップ4: 的中率追跡
│   ├── notifier.py          # ステップ5: Slack Webhook通知
│   ├── glossary.py          # 株式用語ヘルプ (CLIツール + レポート埋め込み)
│   └── utils.py             # 共通ユーティリティ
│
├── data/
│   ├── glossary.yaml        # 株式用語集データ
│   ├── sp500.csv            # S&P500構成銘柄リスト
│   ├── nasdaq100.csv        # NASDAQ100構成銘柄リスト
│   └── nikkei225.csv        # 日経225構成銘柄リスト
│
├── .github/
│   └── workflows/
│       └── weekly_run.yml   # GitHub Actions 定期実行
│
└── img/
    └── plan.jpg
```

---

## 各ステップ詳細設計

### ステップ1: 自動スクリーニング (`screener.py`)

**目的**: グローバル市場から成長ポテンシャルの高い銘柄トップ10を抽出

**処理フロー**:
1. `data/*.csv` から対象市場の銘柄ティッカーリストを読み込む [#8]
2. `yfinance` で各銘柄の直近データを取得（株価、出来高、時価総額等）
3. `ta` ライブラリでテクニカル指標を算出
4. スクリーニング条件でフィルタリング:
   - 直近1ヶ月の株価上昇率
   - 出来高増加トレンド
   - 時価総額フィルタ（小型株除外等）
   - RSI・MACD等のテクニカル指標
5. スコアリングしてトップ10を返却

**入力**: config.yamlのスクリーニング条件 + data/*.csv
**出力**: 成長株トップ10のリスト（ティッカー、現在株価、各種指標）

---

### ステップ2: AI価格予測 (`predictor.py`)

**目的**: トップ10銘柄について来週の株価を予測し、上昇予測のみ抽出

**段階的アプローチ** [#7 修正: Phase 1→2→3 の連続性を確保]:

#### Phase 1: Prophet (初期実装)
```python
from prophet import Prophet

model = Prophet()
model.fit(stock_history_df)       # 過去90日の株価データ
forecast = model.predict(future)  # 来週の予測
```
1. 各銘柄の過去90日の株価データを取得
2. Prophetで時系列予測を実行
3. 予測上昇率を算出、上昇予測の銘柄のみフィルタリング
4. 信頼区間も出力（Prophetが自動算出）

#### Phase 2: + scikit-learn / XGBoost (精度改善)
- テクニカル指標を特徴量としたXGBoostモデルを追加
- ProphetとXGBoostの予測をアンサンブル（加重平均）
- バックテストで重み配分を最適化

#### Phase 3: + OpenAI API (解説・分析補助)
- ニュースセンチメント分析でProphetの予測を補正
- 「なぜ上昇/下落が見込まれるか」の解説を自然言語で生成
- モデルは `config.yaml` の `openai.model` で指定（デフォルト: gpt-4o-mini）

**入力**: ステップ1の成長株トップ10
**出力**: 上昇予測銘柄リスト（ティッカー、現在価格、予測価格、予測上昇率、信頼区間）

---

### ステップ3: Googleスプレッドシート自動記録 (`sheets.py`)

**目的**: 予測結果をGoogleスプレッドシートに自動記録

**記録データ構造**:
| 日付 | ティッカー | 現在価格 | 予測価格 | 予測上昇率 | 信頼区間 | 翌週実績価格 | 的中 | ステータス |
|------|-----------|---------|---------|-----------|---------|-------------|------|----------|
| 2026-02-22 | AAPL | 250.00 | 265.00 | +6.0% | ±3.2% | (翌週記入) | (翌週判定) | 予測済み |

**処理フロー**:
1. Google Sheets API (gspread) で認証
2. 予測データを新しい行として追記
3. 前週の「翌週実績価格」列を対象市場の最終営業日終値で更新
4. 的中判定（予測方向が合っていたか）を自動記入

**必要な準備**:
- Google Cloud Projectの作成
- Sheets API有効化
- サービスアカウント作成・JSONキー取得

---

### ステップ4: 前週比較・的中率追跡 (`tracker.py`)

**目的**: 先週の予測と実績を比較し、的中率を計算

**判定基準** [#6]:
- **実績価格**: 対象市場の最終営業日終値 (Close) を使用
- 米国市場: 金曜 16:00 ET 終値
- 日本市場: 金曜 15:00 JST 終値
- 休場日の場合、直前の営業日終値を使用

**処理フロー**:
1. スプレッドシートから前週の予測データを取得
2. 各銘柄の最終営業日終値を取得（実績価格）
3. 予測 vs 実績を比較:
   - 上昇予測 → 実際に上昇 → 的中
   - 上昇予測 → 実際に下落 → 外れ
4. 全体的中率を算出（直近4週/累計）
5. スプレッドシートの実績列を更新

**出力**: 的中率サマリー（今週/4週平均/累計）

---

### ステップ5: Slack通知 (`notifier.py`) [#1 Webhook-only]

**目的**: 分析結果を Slack の #stock-alerts チャンネルにWebhookで通知

**方式**: Incoming Webhook のみ（Bot/Slash Commandは使用しない）

**通知例**:
```
━━━━━━━━━━━━━━━━━━━━━━━━
📊 週間AI株式予測レポート (2026-02-22)
━━━━━━━━━━━━━━━━━━━━━━━━

【今週の上昇予測銘柄】
1. AAPL: $250.00 → $265.00 (予測 +6.0%, 信頼区間 ±3.2%)
2. MSFT: $420.00 → $438.00 (予測 +4.3%, 信頼区間 ±2.8%)

【先週の的中率】(判定: 最終営業日終値基準)
的中: 6/8銘柄 (75.0%)
累計的中率: 71.2% (過去12週)

📋 詳細: [スプレッドシートリンク]
```

**beginner_mode有効時の追加情報**:
```
💡 用語メモ:
・予測上昇率 = AIが予測する来週の値上がり幅(%)
・信頼区間 = 予測のブレ幅。小さいほど予測に自信あり
・RSI = 70以上で買われすぎ、30以下で売られすぎのサイン

📖 今週のワンポイント:
  RSI(相対力指数)とは、一定期間の値上がり・値下がりの
  勢いを0〜100で表した指標です。
```

---

### ヘルプ機能 (`glossary.py`) [#1 Webhook-only対応版]

**目的**: 株知識ゼロのユーザーでも安心して使えるサポート機能

**提供方法** (Webhook-onlyのため、Slack上の対話機能は無し):

| 機能 | 説明 | 利用方法 |
|------|------|---------|
| レポート内用語解説 | 通知に専門用語の解説を自動付与 | `config.yaml` で `beginner_mode: true` |
| CLI用語検索 | ターミナルで用語を検索 | `python -m src.glossary RSI` |
| 用語集データ | glossary.yamlに定義 | 手動追加・編集可能 |

**glossary.yaml の例**:
```yaml
terms:
  RSI:
    short: "70以上=買われすぎ、30以下=売られすぎ"
    detail: "Relative Strength Index（相対力指数）。一定期間の値上がり幅と
             値下がり幅から算出。70を超えると過熱感あり、30を下回ると
             売られすぎと判断される。"
  MACD:
    short: "トレンドの方向と強さを示す指標"
    detail: "Moving Average Convergence Divergence。短期と長期の移動平均の差。
             シグナルラインとの交差が売買サインとなる。"
  PER:
    short: "株価の割安/割高を測る指標。低い=割安"
    detail: "Price Earnings Ratio（株価収益率）。株価÷1株あたり利益で算出。
             業種平均と比較して低ければ割安と判断される。"
  出来高:
    short: "一定期間に売買された株数"
    detail: "出来高が多い=その銘柄への注目度が高い。急増は大きな値動きの
             前兆になることがある。"
  時価総額:
    short: "会社全体の株式の合計価値"
    detail: "株価×発行済株式数で算出。大型株(時価総額が大きい)は安定的、
             小型株は値動きが激しい傾向がある。"
```

---

## 自動実行 (GitHub Actions)

```yaml
# .github/workflows/weekly_run.yml
name: Weekly Stock Analysis
on:
  schedule:
    - cron: '0 0 * * 0'  # 毎週日曜 UTC 00:00 (JST 09:00)
  workflow_dispatch:        # 手動実行も可能
```

**Secrets設定** [#2 Webhook-only構成に合わせて修正]:

| Secret名 | 用途 | 必須 |
|----------|------|------|
| `OPENAI_API_KEY` | 用語解説・補助分析 (Phase 3) | Phase 3以降 |
| `GOOGLE_CREDENTIALS_JSON` | Sheets API認証 | 必須 |
| `SLACK_WEBHOOK_URL` | Slack通知 | 必須 |

> ~~`SLACK_BOT_TOKEN`~~ / ~~`SLACK_SIGNING_SECRET`~~ → Webhook-onlyのため不要

---

## コスト見積もり

> 最終確認日: 2026-02-18 [#4]
> 次回見直し: 2026-05-18（四半期ごと）

| 項目 | 月額コスト | 備考 |
|------|-----------|------|
| OpenAI API (デフォルト: gpt-4o-mini) | ~$0.024 (約3円) | config.yamlで変更可能 |
| Google Cloud (Sheets API) | $0 | 無料枠内 |
| Slack (Incoming Webhook) | $0 | 無料プラン（90日履歴制限） |
| GitHub Actions | $0 | 無料枠内（月2000分） |
| yfinance / Prophet / ta | $0 | 全て無料 |
| **合計** | **~$0.024/月 (約3円)** | |

---

## 依存パッケージとバージョン [#5]

> 最終確認日: 2026-02-18

```txt
# requirements.txt
# Pythonバージョン要件(>=3.11)は runtime / pyproject.toml 側で管理

# データ取得・分析
yfinance>=0.2.36
pandas>=2.2.0
ta>=0.11.0

# AI予測
prophet>=1.1.5
# ※ prophet は内部で cmdstanpy を使用。pystan は不要。
# ※ インストール: pip install prophet (cmdstanpyが自動インストールされる)

# Phase 2 (将来追加)
# scikit-learn>=1.4.0
# xgboost>=2.0.0

# OpenAI
openai>=1.12.0

# Google Sheets
gspread>=6.0.0
google-auth>=2.28.0

# Slack通知
requests>=2.31.0

# 設定管理
pyyaml>=6.0.1
python-dotenv>=1.0.1
```

**Prophetインストール手順** [#5]:
```bash
# 推奨: Python 3.11 環境
pip install prophet
# ※ pystan の個別インストールは不要（prophet 1.1.5+ は cmdstanpy ベース）
# ※ Windows: Visual C++ Build Tools が必要な場合あり
# ※ 問題が発生した場合: conda install -c conda-forge prophet
```

---

## 実装順序（フェーズ分け）

### フェーズ1: 基盤構築 (Day 1)
- [ ] プロジェクトセットアップ（Python環境、依存パッケージ）
- [ ] config.yaml の設計・作成（OpenAIモデル切替含む）
- [ ] .env.example / .gitignore 作成
- [ ] data/*.csv 銘柄リスト作成 [#8]
- [ ] data/glossary.yaml (株式用語集) 作成

### フェーズ2: データ取得 & スクリーニング (Day 2-3)
- [ ] `screener.py` 実装（静的CSVから銘柄読み込み）
- [ ] `ta` ライブラリでテクニカル指標算出
- [ ] スクリーニング条件のチューニング
- [ ] 動作確認

### フェーズ3: AI価格予測 - Prophet [Phase 1] (Day 4-5)
- [ ] `predictor.py` 実装（Prophet方式）
- [ ] バックテスト実装（過去データで精度検証）
- [ ] 動作確認

### フェーズ4: スプレッドシート連携 (Day 6)
- [ ] Google Cloud Project セットアップ
- [ ] `sheets.py` 実装
- [ ] 記録・更新ロジックの動作確認

### フェーズ5: 通知 & ヘルプ (Day 7-8)
- [ ] `notifier.py` 実装（Slack Incoming Webhook）
- [ ] `glossary.py` 実装（CLI用語検索 + レポート埋め込み）
- [ ] beginner_mode の動作確認

### フェーズ6: 自動化 & 統合 (Day 9-10)
- [ ] `main.py` オーケストレーター実装
- [ ] `tracker.py` 実装（最終営業日終値ベースの判定 [#6]）
- [ ] GitHub Actions ワークフロー設定
- [ ] エンドツーエンドテスト
- [ ] 本番運用開始

### フェーズ7: 改善 (将来)
- [ ] [Phase 2] scikit-learn (XGBoost) によるアンサンブル予測の追加
- [ ] [Phase 3] OpenAI APIによるニュース分析・解説生成の追加
- [ ] コスト・価格データの四半期見直し [#4]
- [ ] 銘柄リスト (data/*.csv) の四半期更新 [#8]

---

## 必要なアカウント・APIキー

| サービス | 用途 | 費用 | 取得方法 |
|---------|------|------|---------|
| OpenAI API | ヘルプ機能・補助分析 | ~$0.024/月 | https://platform.openai.com/ |
| Google Cloud | スプレッドシート連携 | 無料 | https://console.cloud.google.com/ |
| Slack Webhook | 通知 | 無料 | ワークスペース設定 > App > Incoming Webhook |

---

## リスクと対策

| リスク | 対策 |
|-------|------|
| yfinance レート制限 | リクエスト間隔の制御、キャッシュ活用 |
| 株価データの欠損 | エラーハンドリング、欠損銘柄はスキップ |
| Prophet予測精度が低い | バックテストで継続評価、Phase 2でXGBoost追加 |
| Slack無料プランの90日制限 | 長期データはGoogle Sheetsに保存 |
| API費用の増加 | デフォルトgpt-4o-mini、config.yamlで管理 |
| 銘柄リストの陳腐化 [#8] | 四半期ごとにdata/*.csvを更新 |
| 価格・性能前提の陳腐化 [#4] | 四半期ごとにコスト見積もりを見直し |
| 休場日の判定ズレ [#6] | 最終営業日終値を使用、祝日カレンダー考慮 |

---

## 定期メンテナンスタスク [#4]

| タスク | 頻度 | 対象 |
|-------|------|------|
| OpenAI API価格の確認 | 四半期 | docs/PLAN.md コスト見積もり |
| 銘柄リスト更新 | 四半期 | data/*.csv |
| Prophet/依存パッケージ更新 | 四半期 | requirements.txt |
| 的中率トレンド確認 | 月次 | Google Sheets |

---

## 免責事項

本システムはAIによる株価予測の実験・学習目的で構築するものであり、投資助言を提供するものではありません。実際の投資判断は自己責任で行ってください。
