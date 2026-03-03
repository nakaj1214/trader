## 実装計画: Trader プロジェクト ゼロベース再設計

> proposal: `docs/implement/proposal.md`
> 作成日: 2026-03-03

---

### 目的

現行の Trader プロジェクト（週次株式スクリーニング・Prophet予測・Google Sheets永続化・静的HTMLダッシュボード）を
ゼロから再設計し、拡張性・保守性・予測精度・開発体験を根本的に改善する。
Perplexity Finance 等の新規データソース統合も視野に入れた、プラグイン型アーキテクチャへ移行する。

### スコープ

- 含むもの:
  - アーキテクチャ全体の再設計（モジュール分割、依存関係整理）
  - データパイプラインの非同期化・並列化
  - SQLite → PostgreSQL 移行可能な永続化レイヤー導入（Google Sheets依存脱却）
  - 予測モデルのプラグイン化（Prophet + LightGBM/XGBoost アンサンブル）
  - フロントエンドの近代化（React or Svelte + Vite）
  - データソースのプラグイン型統合基盤（Perplexity Sonar API 含む）
  - テスト基盤の強化（統合テスト追加、カバレッジ80%以上）
  - CI/CD パイプラインの改善

- 含まないもの:
  - リアルタイムトレーディング機能（デイトレ・HFT）
  - 有料データベンダー（Bloomberg Terminal 等）との統合
  - モバイルアプリ開発
  - Google Sheets データの完全自動マイグレーション（`scripts/migrate_sheets_to_db.py` で半自動対応、手動確認が必要）
  - Perplexity Finance Web UIのスクレイピング（ToS 違反）

### 影響範囲（変更/追加予定ファイル）

#### 新規ディレクトリ構成（`trader/` 配下を全面再構成）

```
trader/
├── pyproject.toml                    # パッケージ管理（requirements.txt 廃止）
├── config/
│   ├── default.yaml                  # デフォルト設定
│   ├── production.yaml               # 本番オーバーライド
│   └── test.yaml                     # テスト用設定
├── src/
│   ├── __init__.py
│   ├── cli.py                        # CLIエントリポイント（Typer）
│   ├── orchestrator.py               # パイプライン実行制御
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py                 # Pydantic データモデル（Prediction, Stock, etc.）
│   │   ├── config.py                 # 設定ロード・バリデーション（utils.py 統合）
│   │   ├── meta.py                   # 実行メタ情報（git hash, config hash）
│   │   ├── glossary.py               # 用語解説辞書（beginner_mode 連動）
│   │   └── exceptions.py             # カスタム例外定義
│   ├── data/
│   │   ├── __init__.py
│   │   ├── providers/                # データソースプラグイン
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # DataProvider ABC
│   │   │   ├── yfinance_provider.py  # yfinance（価格・財務）
│   │   │   ├── jquants_provider.py   # J-Quants（JP株）
│   │   │   ├── finnhub_provider.py   # Finnhub（センチメント）
│   │   │   ├── fmp_provider.py       # FMP（財務フォールバック）
│   │   │   ├── fred_provider.py      # FRED（マクロ指標）
│   │   │   └── perplexity_provider.py # Perplexity Sonar（AIニュース要約）
│   │   └── repository.py            # DB永続化レイヤー（SQLAlchemy）
│   ├── screening/
│   │   ├── __init__.py
│   │   ├── universe.py               # ユニバース定義（銘柄リスト管理）
│   │   ├── filters.py                # フィルタチェーン（時価総額、流動性、GC等）
│   │   ├── indicators.py             # テクニカル指標計算
│   │   └── scorer.py                 # スコアリング（重み付き合成スコア）
│   ├── prediction/
│   │   ├── __init__.py
│   │   ├── base.py                   # PredictionModel ABC
│   │   ├── prophet_model.py          # Prophet モデル
│   │   ├── lightgbm_model.py         # LightGBM モデル
│   │   ├── ensemble.py               # アンサンブル制御
│   │   └── calibrator.py             # 確率キャリブレーション（Platt Scaling）
│   ├── enrichment/
│   │   ├── __init__.py
│   │   ├── base.py                   # Enricher ABC
│   │   ├── risk_enricher.py          # リスク指標（vol, beta, drawdown）
│   │   ├── event_enricher.py         # イベント検出（決算、配当）
│   │   ├── evidence_enricher.py      # ファクター分析（momentum, value, quality）
│   │   ├── sentiment_enricher.py     # ニュースセンチメント
│   │   └── sizing_enricher.py        # ポジションサイジング
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── tracker.py                # 的中率追跡
│   │   ├── backtest.py               # 戦略比較バックテスト（baseline.py 統合）
│   │   ├── walkforward.py            # ウォークフォワード評価
│   │   ├── alpha_survey.py           # アノマリー統計検証
│   │   └── calibration_metrics.py    # Brier Score, ECE 等
│   ├── notification/
│   │   ├── __init__.py
│   │   ├── base.py                   # Notifier ABC
│   │   ├── slack_notifier.py         # Slack通知
│   │   ├── line_notifier.py          # LINE通知
│   │   └── chart_builder.py          # チャート画像生成（matplotlib）
│   └── export/
│       ├── __init__.py
│       ├── json_exporter.py          # ダッシュボードJSON出力
│       └── sheets_exporter.py        # Google Sheets出力（後方互換）
├── dashboard/                        # フロントエンド（Svelte + Vite）
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.svelte
│   │   ├── routes/
│   │   ├── components/
│   │   ├── stores/
│   │   └── lib/
│   ├── static/
│   │   └── _headers                  # Cloudflare Pages キャッシュ制御（現行 dashboard/_headers を移植）
│   └── public/
│       └── data/                     # ビルド後JSONデータ配置先
├── tests/
│   ├── unit/                         # ユニットテスト
│   ├── integration/                  # 統合テスト
│   └── conftest.py                   # 共通フィクスチャ
├── scripts/
│   └── migrate_sheets_to_db.py      # Google Sheets → SQLite 移行スクリプト
├── data/
│   ├── universes/                    # 銘柄リストCSV
│   ├── glossary.yaml                # 株式用語定義（現行位置を維持）
│   └── migrations/                   # DBマイグレーション（Alembic）
└── .github/
    └── workflows/
        ├── weekly_run.yml            # 週次実行
        ├── test.yml                  # PRテスト
        └── deploy_dashboard.yml      # ダッシュボードデプロイ
```

#### 主要な変更理由

- `src/enricher.py`（920行）→ `src/enrichment/` に5ファイル分割: 単一責任原則違反の解消
- `src/exporter.py`（701行）→ `src/export/` + `src/evaluation/`: 責務分離
- `src/screener.py`（383行）→ `src/screening/` に4ファイル分割: フィルタ・指標・スコアリングの独立
- `dashboard/js/accuracy.js`（610行）+ 他JSファイル群 → Svelte コンポーネント群: Vanilla JS の保守性向上
- Google Sheets 永続化 → SQLite/PostgreSQL: SPOF排除、クエリ性能向上
- `requirements.txt` → `pyproject.toml`: 依存管理の近代化（uv 使用、pip フォールバック対応）

#### 現行モジュール移行マッピング

| 現行ファイル | 移行先 | 方針 |
|---|---|---|
| `src/screener.py` | `src/screening/` (4ファイル) | 分割移植 |
| `src/predictor.py` | `src/prediction/prophet_model.py` | 移植 |
| `src/tracker.py` | `src/evaluation/tracker.py` | 移植 |
| `src/sheets.py` | `src/export/sheets_exporter.py` | 移植（後方互換） |
| `src/notifier.py` | `src/notification/slack_notifier.py` | 移植 |
| `src/exporter.py` | `src/export/json_exporter.py` + `src/orchestrator.py` | 分割（エクスポート責務とオーケストレーション責務を分離） |
| `src/enricher.py` | `src/enrichment/` (5ファイル) | 分割移植 |
| `src/jquants_fetcher.py` | `src/data/providers/jquants_provider.py` | 移植 |
| `src/finnhub_fetcher.py` | `src/data/providers/finnhub_provider.py` | 移植 |
| `src/fmp_fetcher.py` | `src/data/providers/fmp_provider.py` | 移植 |
| `src/macro_fetcher.py` | `src/data/providers/fred_provider.py` + `src/export/json_exporter.py` | FRED取得ロジックはprovider、`macro.json`出力はexporter |
| `src/line_notifier.py` | `src/notification/line_notifier.py` | 移植 |
| `src/alpha_survey.py` | `src/evaluation/alpha_survey.py` | 移植（evaluationドメイン） |
| `src/baseline.py` | `src/evaluation/backtest.py` | 統合移植（3戦略比較ロジック） |
| `src/walkforward.py` | `src/evaluation/walkforward.py` | 移植 |
| `src/chart_builder.py` | `src/notification/chart_builder.py` | 移植（Slack通知チャート生成） |
| `src/meta.py` | `src/core/meta.py` | 移植（実行メタ情報はcore基盤） |
| `src/utils.py` | `src/core/config.py` | 統合（`load_config()`, `get_env()` → Pydantic Settings、`ROOT_DIR` → config定数） |
| `src/glossary.py` | `src/core/glossary.py` | 移植（`beginner_mode` 連動の用語辞書） |
| `src/main.py` | `src/orchestrator.py` + `src/cli.py` | 分割（実行制御とCLIインターフェース） |

#### 静的データ移行

| 現行ファイル | 移行先 | 方針 |
|---|---|---|
| `data/sp500.csv` | `data/universes/sp500.csv` | ディレクトリ移動 |
| `data/nasdaq100.csv` | `data/universes/nasdaq100.csv` | ディレクトリ移動 |
| `data/nikkei225.csv` | `data/universes/nikkei225.csv` | ディレクトリ移動 |
| `data/glossary.yaml` | `data/glossary.yaml` | 配置維持（`src/core/glossary.py` から参照） |
| `config.yaml` | `config/default.yaml` | 構造再編（下記マッピング参照） |
| `Dockerfile` | `Dockerfile` | 維持（`uv` ベースに更新） |
| `docker-compose.yml` | `docker-compose.yml` | 維持（DB追加等を反映） |
| `dashboard/_headers` | `dashboard/static/_headers` | Cloudflare Pages キャッシュ制御ヘッダー（SvelteKit static ディレクトリに移動） |

#### `config.yaml` → `config/default.yaml` 設定キー対応表

> 現行キーは `config.yaml` の実態（2026-03-03 時点）に基づく。新規追加キーは末尾に別表で記載。

| 現行キー | 新設計キー | 備考 |
|---|---|---|
| `screening.markets` | `screening.markets` | 維持 |
| `screening.top_n` | `screening.top_n` | 維持 |
| `screening.min_market_cap` | `screening.filters.market_cap.min` | フィルタ配下に階層化 |
| `screening.min_avg_dollar_volume_us` | `screening.filters.liquidity.min_dollar_volume_us` | フィルタ配下に階層化（US株用） |
| `screening.min_avg_dollar_volume_jp` | `screening.filters.liquidity.min_dollar_volume_jp` | フィルタ配下に階層化（JP株用） |
| `screening.exclude_days_to_earnings` | `screening.filters.earnings_exclusion.days` | フィルタ配下に階層化 |
| `screening.lookback_days` | `screening.lookback_days` | 維持 |
| `screening.use_golden_cross_filter` | `screening.filters.golden_cross.enabled` | フィルタ配下に階層化 |
| `screening.weights.*` | `screening.scoring.weights.*` | scoring配下に移動 |
| `prediction.history_days` | `prediction.history_days` | 維持 |
| `prediction.forecast_days` | `prediction.forecast_days` | 維持 |
| `prophet.interval_width` | `prediction.prophet.interval_width` | prediction配下に統合 |
| `prophet.changepoint_prior_scale` | `prediction.prophet.changepoint_prior_scale` | prediction配下に統合 |
| `prophet.uncertainty_samples` | `prediction.prophet.uncertainty_samples` | prediction配下に統合 |
| `guardrail.clip_pct` | `prediction.guardrail.clip_pct` | prediction配下に移動 |
| `guardrail.warn_pct` | `prediction.guardrail.warn_pct` | prediction配下に移動 |
| `openai.*` | 削除 | 現行コードで未使用のため削除 |
| `google_sheets.spreadsheet_name` | `export.google_sheets.spreadsheet_name` | export配下に移動 |
| `google_sheets.worksheet_name` | `export.google_sheets.worksheet_name` | export配下に移動 |
| `slack.channel` | `notification.slack.channel` | notification配下に移動 |
| `display.beginner_mode` | `notification.beginner_mode` | notification配下に移動 |
| `line.enabled` | `notification.line.enabled` | notification配下に移動 |
| `notifications.slack.enabled` | `notification.slack.enabled` | notification配下に統合 |
| `notifications.line.enabled` | `notification.line.enabled` | notification配下に統合 |
| `notifications.slack_chart` | `notification.slack.chart_enabled` | notification.slack配下に統合 |
| `notifications.chart_lookback_days` | `notification.chart.lookback_days` | notification.chart配下に統合 |
| `notifications.slack_channel_id` | `notification.slack.channel_id` | notification.slack配下に統合 |
| `sizing.vol_target_ann` | `enrichment.sizing.vol_target_ann` | enrichment配下に移動 |
| `sizing.max_weight_cap` | `enrichment.sizing.max_weight_cap` | enrichment配下に移動 |
| `sizing.stop_loss_multiplier` | `enrichment.sizing.stop_loss_multiplier` | enrichment配下に移動 |
| `backtest.num_rules_tested` | `evaluation.backtest.num_rules_tested` | evaluation配下に移動 |
| `backtest.num_parameters_tuned` | `evaluation.backtest.num_parameters_tuned` | evaluation配下に移動 |
| `backtest.oos_start` | `evaluation.backtest.oos_start` | evaluation配下に移動 |
| `backtest.min_rules_for_pbo` | `evaluation.backtest.min_rules_for_pbo` | evaluation配下に移動 |
| `walkforward.train_weeks` | `evaluation.walkforward.train_weeks` | evaluation配下に移動 |
| `walkforward.test_weeks` | `evaluation.walkforward.test_weeks` | evaluation配下に移動 |
| `walkforward.min_train_weeks` | `evaluation.walkforward.min_train_weeks` | evaluation配下に移動 |
| `jquants.enabled` | `providers.jquants.enabled` | providers配下に統合 |
| `finnhub.enabled` | `providers.finnhub.enabled` | providers配下に統合 |
| `fmp.enabled` | `providers.fmp.enabled` | providers配下に統合 |
| `price_column` | `data.price_column` | data配下に移動 |

#### 新規追加キー（現行 `config.yaml` に存在しないもの）

| 新設計キー | デフォルト値 | 備考 |
|---|---|---|
| `prediction.model` | `"prophet"` | `"prophet"` / `"lightgbm"` / `"ensemble"` |
| `prediction.ensemble.weights` | `{prophet: 0.4, lightgbm: 0.6}` | アンサンブル時の重み |
| `providers.fred.enabled` | `false` | FRED マクロ指標取得 |
| `providers.perplexity.enabled` | `false` | Perplexity Sonar API |
| `providers.perplexity.model` | `"sonar"` | `sonar` / `sonar-pro` |
| `providers.perplexity.max_tickers` | `5` | API コスト制限 |

### 実装ステップ

#### Step 1: プロジェクト基盤構築

- [ ] `pyproject.toml` 作成（PEP 621 準拠、uv / pip 両対応）
  - `[project.dependencies]` (core): `yfinance`, `pandas`, `ta`, `matplotlib`, `pydantic>=2.0`, `sqlalchemy>=2.0`, `alembic`, `gspread`, `google-auth`, `requests`, `pyyaml`, `python-dotenv`, `typer`, `structlog`, `tenacity`, `cachetools`
  - `[project.optional-dependencies.ml]`: `prophet`, `lightgbm`, `scikit-learn`
  - `[project.optional-dependencies.dev]`: `pytest`, `pytest-cov`, `mypy`, `ruff`, `black`, `isort`, `pre-commit`
- [ ] `src/core/models.py` 作成（Pydantic v2 データモデル定義）
  - `Stock`, `Prediction`, `Enrichment`, `TrackingResult`, `BacktestResult`
- [ ] `src/core/config.py` 作成（Pydantic Settings + YAML マージ）
  - `config/default.yaml`, `config/production.yaml`, `config/test.yaml`
- [ ] `src/core/exceptions.py` 作成（`DataProviderError`, `PredictionError`, `ConfigError`）
- [ ] `src/core/meta.py` 移植（`build_run_meta()`, `build_common_meta()`, `save_config_snapshot()`）
- [ ] `src/core/glossary.py` 移植（`data/glossary.yaml` 読み込み、`beginner_mode` 連動の用語辞書）
- [ ] `src/cli.py` 作成（Typer CLI: `run`, `screen`, `predict`, `export` サブコマンド）
- [ ] ロガー設定（structlog: JSON構造化ログ）

**検証**: `uv run python -m src.cli --help` でサブコマンド一覧が表示されること

#### Step 2: データプロバイダー基盤

- [ ] `src/data/providers/base.py` 作成（`DataProvider` ABC）
  - 共通インターフェース: `fetch_price()`, `fetch_info()`, `is_available()`, `cache_key()`
  - セッション内メモリキャッシュ（`functools.lru_cache` or `cachetools.TTLCache`）
  - APIキー未設定時の degraded mode（`is_available() → False` で skip）
  - リトライ（`tenacity` ライブラリ: 指数バックオフ、最大3回）
- [ ] `src/data/providers/yfinance_provider.py` 移植
  - バッチ取得（50銘柄/バッチ）維持
  - Phase A では同期実装。Phase B 以降で `asyncio` + `aiohttp` による非同期化を検討
- [ ] `src/data/providers/jquants_provider.py` 移植
- [ ] `src/data/providers/finnhub_provider.py` 移植
- [ ] `src/data/providers/fmp_provider.py` 移植
- [ ] `src/data/providers/fred_provider.py` 移植
- [ ] `src/data/providers/perplexity_provider.py` 新規作成
  - Perplexity Sonar API (`sonar` / `sonar-pro` モデル)
  - AIニュース要約 + センチメント分類（bullish/neutral/bearish）

**検証**: 各プロバイダーの `is_available()` が環境変数に応じて正しく動作すること

#### Step 3: 永続化レイヤー（SQLite + SQLAlchemy）

- [ ] `src/data/repository.py` 作成（SQLAlchemy 2.0 + SQLite）
  - テーブル: `predictions`, `tracking_results`, `enrichments`, `backtest_results`
  - `PredictionRepository`: CRUD + 週次集計クエリ
  - `TrackingRepository`: 的中率計算クエリ
  - マイグレーション基盤: Alembic 初期設定
- [ ] `data/migrations/` ディレクトリ作成（Alembic 設定）
- [ ] Google Sheets エクスポーター残置（`src/export/sheets_exporter.py`）
  - 後方互換: 新DBから Google Sheets への一方向同期オプション
- [ ] `scripts/migrate_sheets_to_db.py` 作成（Google Sheets → SQLite データ移行）
  - Google Sheets の全レコードを取得し、SQLite の `predictions` / `tracking_results` テーブルに投入
  - 冪等実行可能（同一日付+ティッカーの重複レコードは skip）
  - ドライランモード: `--dry-run` で移行対象件数のみ表示

**検証**: `alembic upgrade head` でテーブル作成、`PredictionRepository.save()` → `.find_by_date()` が往復できること。`scripts/migrate_sheets_to_db.py --dry-run` で対象件数が表示されること

#### Step 4: スクリーニングモジュール分割

- [ ] 既存 `data/*.csv` を `data/universes/` へ移設
  - `data/sp500.csv` → `data/universes/sp500.csv`
  - `data/nasdaq100.csv` → `data/universes/nasdaq100.csv`
  - `data/nikkei225.csv` → `data/universes/nikkei225.csv`
- [ ] `src/screening/universe.py` 作成
  - `data/universes/*.csv` から銘柄リストロード
  - US（S&P500, NASDAQ100）、JP（日経225）ユニバース
- [ ] `src/screening/filters.py` 作成（フィルタチェーンパターン）
  - `MarketCapFilter`, `LiquidityFilter`, `GoldenCrossFilter`
  - `FilterChain.apply(stocks) → filtered_stocks`（config.yaml で有効/無効制御）
- [ ] `src/screening/indicators.py` 作成
  - 各テクニカル指標を独立関数として実装（`ta` ライブラリ活用）
  - `calc_rsi()`, `calc_macd()`, `calc_bollinger()`, `calc_adx()`, `calc_52w_high()`
- [ ] `src/screening/scorer.py` 作成
  - 重み付きスコアリング（config.yaml の `weights` セクション参照）
  - 上位 N 銘柄選出

**検証**: 現行 `screener.py` と同一入力で同一出力が得られること（回帰テスト）

#### Step 5: 予測モデルのプラグイン化

- [ ] `src/prediction/base.py` 作成（`PredictionModel` ABC）
  - 共通インターフェース: `train()`, `predict()`, `confidence_interval()`
- [ ] `src/prediction/prophet_model.py` 移植
  - ±30% クリップ維持、±20% 警告フラグ
- [ ] `src/prediction/lightgbm_model.py` 新規作成
  - 特徴量: テクニカル指標 + ファンダメンタルズ（screener 出力を再利用）
  - ターゲット: 5営業日後リターン
  - TimeSeriesSplit によるクロスバリデーション
- [ ] `src/prediction/ensemble.py` 作成
  - Prophet + LightGBM の加重平均（デフォルト: 0.4 / 0.6）
  - 設定で単一モデル使用も可能
- [ ] `src/prediction/calibrator.py` 作成
  - Platt Scaling による `prob_up` のキャリブレーション
  - `prob_up_calibrated` フィールドの実装（現行は常に `null`）

**検証**: `PredictionModel` を差し替え可能であること。Prophet 単体の結果が現行と一致すること

#### Step 6: エンリッチメントモジュール分割

- [ ] `src/enrichment/base.py` 作成（`Enricher` ABC）
  - `enrich(stock: Stock, prediction: Prediction) → Enrichment`
- [ ] `src/enrichment/risk_enricher.py` 作成
  - `vol_20d_ann`, `vol_60d_ann`, `beta`, `max_drawdown_1y`
- [ ] `src/enrichment/event_enricher.py` 作成
  - 決算日、配当落ち日検出（J-Quants 決算カレンダー含む）
  - 決算禁則期間警告（Phase 24 相当）
- [ ] `src/enrichment/evidence_enricher.py` 作成
  - `momentum_z`, `value_z`, `quality_z`, `low_risk_z`, `composite`
- [ ] `src/enrichment/sentiment_enricher.py` 作成
  - Finnhub ニュースセンチメント + Perplexity AI要約の統合
- [ ] `src/enrichment/sizing_enricher.py` 作成
  - ボラティリティベースのポジションサイジング + 損切り水準

**検証**: `enricher.py`（920行）と同等のデータを出力すること

#### Step 7: 評価・追跡モジュール

- [ ] `src/evaluation/tracker.py` 移植
  - DB（SQLite）から予測レコード取得 → 実績価格取得 → 的中判定 → DB更新
- [ ] `src/evaluation/backtest.py` 移植（現行 `baseline.py` を統合）
  - AI vs モメンタム vs SPY 3戦略比較
  - CAGR, 最大ドローダウン, Sharpe 比算出
- [ ] `src/evaluation/walkforward.py` 移植
  - train_weeks / test_weeks 分割評価
- [ ] `src/evaluation/alpha_survey.py` 移植
  - アノマリー統計検証（現行の `insufficient_data` プレースホルダーを実装に置換）
  - `dashboard/data/alpha_survey.json` 出力
- [ ] `src/evaluation/calibration_metrics.py` 作成
  - Brier Score, Log-loss, ECE を実計算（プレースホルダー置換）

**検証**: 既存の `comparison.json`, `walkforward.json` と同等のデータが出力されること

#### Step 8: 通知・エクスポートモジュール

- [ ] `src/notification/chart_builder.py` 移植（matplotlib チャート画像生成）
- [ ] `src/notification/slack_notifier.py` 移植
  - Webhook テキスト送信 + Bot Token チャート画像 upload（`chart_builder.py` を利用）
- [ ] `src/notification/line_notifier.py` 移植
- [ ] `src/export/json_exporter.py` 移植
  - **移行期間（Phase A〜C）**: `dashboard/data/` に出力（現行互換を維持）
  - **Phase C 完了後（Svelte 本番稼働後）**: `dashboard/data/` への出力を停止し `dashboard/public/data/` のみに切り替え
  - JSON atomic write（`.tmp` → `rename`）を維持
- [ ] `src/export/sheets_exporter.py` 移植（後方互換オプション）

**検証**: Slack 通知の mock テスト通過、JSON出力が現行スキーマと互換であること

#### Step 9: オーケストレーター

- [ ] `src/orchestrator.py` 作成
  - パイプライン定義: Screen → Predict → Track → Enrich → Export → Notify
  - 各ステップの成功/失敗を独立管理（1ステップの失敗で全体が止まらない）
  - JP株パイプラインの独立実行（US失敗時もJPは続行、逆も同様）
  - 実行メタデータ記録（git hash, config hash, タイムスタンプ）
  - structlog による構造化ログ出力

**検証**: `python -m src.cli run` で全パイプラインが実行され、`dashboard/data/` に JSON が出力されること（移行期間中は現行パスを使用）

#### Step 10: フロントエンド近代化（Svelte + Vite）

- [ ] `dashboard/` を Svelte + Vite + TypeScript で再構築
  - SvelteKit（SSG モード）で Cloudflare Pages デプロイ互換
- [ ] コンポーネント設計:
  - `MarketSelector` - US/JP 市場選択
  - `PredictionTable` - 予測一覧テーブル（ソート・フィルタ付き）
  - `AccuracyChart` - 的中率推移グラフ（Chart.js）
  - `StockDetail` - 銘柄詳細（リスク指標・エビデンス・サイジング）
  - `StrategyComparison` - 3戦略比較チャート
  - `MacroBanner` - マクロ指標バナー
  - `InvestmentSimulator` - 投資シミュレータ
- [ ] レスポンシブデザイン（Tailwind CSS）
- [ ] ダークモード対応
- [ ] `dashboard/public/data/*.json` を静的にロード（API不要）
  - Svelte ビルド時に `dashboard/data/` から `dashboard/public/data/` へコピーするビルドスクリプトを用意
  - Phase C 完了後は `json_exporter.py` の出力先を `dashboard/public/data/` に切り替え、コピー不要にする
- [ ] コンポーネントテスト（Vitest + Testing Library）
  - 各コンポーネントの描画テスト
  - JSON データロード・表示の正常系テスト
- [ ] Cloudflare Pages デプロイ設定の更新
  - 現行: Framework preset なし（Static HTML）、Build output directory = `dashboard`、ビルドコマンドなし
  - 新設計: Framework preset = SvelteKit、Build output directory = `dashboard/build`（SvelteKit SSG 出力先）、ビルドコマンド = `cd dashboard && npm run build`
  - `dashboard/_headers` を Svelte の `static/_headers` に移植（Cloudflare Pages のキャッシュ制御を維持）
  - `/legacy/` パスに現行 HTML/JS ダッシュボードを配置（リスク3 の対策）

**検証**: `npm run build` が成功し、`dashboard/build/` が Cloudflare Pages 互換の静的ファイルであること。`npm run test` が全PASS。デプロイ後に `/data/predictions.json` の `Cache-Control: no-store` ヘッダーが維持されていること

#### Step 11: テスト基盤強化

- [ ] `tests/unit/` に各モジュールのユニットテスト移植・追加
  - データプロバイダー: 各6テスト以上（正常系、APIキー未設定、HTTPエラー、タイムアウト、キャッシュ、JSONパース失敗）
  - スクリーニング: フィルタ・指標・スコアリング各テスト
  - 予測: Prophet/LightGBM/アンサンブル各テスト
  - エンリッチメント: 各エンリッチャーのテスト
- [ ] `tests/integration/` 作成
  - パイプライン統合テスト（モック外部API、実DB）
  - DB永続化の往復テスト
- [ ] `tests/conftest.py` 作成（共通フィクスチャ: モックプロバイダー、テストDB）
- [ ] `tests/e2e/` 作成
  - CLI からの全パイプライン実行テスト（モック外部API、実DB）
  - `python -m src.cli run --config config/test.yaml` の正常完了を確認
- [ ] カバレッジ設定（`pytest-cov`, 80%以上の閾値）
- [ ] 回帰テスト用スナップショット基盤
  - 現行 `main.py` の出力 JSON を `tests/snapshots/` に保存
  - 新 `orchestrator.py` の出力と diff 比較するスクリプト: `scripts/regression_diff.py`
- [ ] Alembic マイグレーション往復テスト
  - `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` の正常完了

**検証**: `pytest tests/ -v --cov=src --cov-fail-under=80` が全 PASS

#### Step 12: CI/CD 改善

- [ ] `.github/workflows/test.yml` 作成
  - PR 時: lint（ruff）+ type check（mypy）+ pytest
- [ ] `.github/workflows/weekly_run_v2.yml` 新規作成（旧 `weekly_run.yml` は Phase C 完了まで維持）
  - `uv run python -m src.cli run` に変更（`pip` フォールバック付き）
  - テスト → 本体実行 → ダッシュボードビルド → デプロイ
  - JSON 出力先: 移行期間中は `dashboard/data/` を commit 対象（現行互換）。Phase C 完了後に `dashboard/public/data/` へ切り替え
- [ ] `.github/workflows/deploy_dashboard.yml` 作成
  - Svelte ビルド → Cloudflare Pages デプロイ（`wrangler pages deploy` または Cloudflare Pages の Git 連携を継続利用）
  - 現行は Cloudflare Pages が `main` push で自動デプロイ（GUI 設定のみ、`wrangler.toml` なし）。Svelte 移行後も同方式を維持するか、`wrangler.toml` + GitHub Actions からの明示的デプロイに切り替えるか選択
- [ ] pre-commit hooks 設定（ruff, mypy, black, isort）

**検証**: GitHub Actions でテスト・ビルド・デプロイが通ること

### 例外・エラーハンドリング方針

- **データプロバイダー障害**: 各プロバイダーは `is_available()` で可用性を事前チェック。障害時は `DataProviderError` を raise せず `None` / `{}` を返す degraded mode を維持。ログに `structlog.warning` で記録
- **予測モデル障害**: 個別銘柄の予測失敗はスキップし、他銘柄の処理を継続。アンサンブルの1モデルが失敗した場合は残モデルのみで予測
- **DB障害**: SQLite はローカルファイルのため障害リスクは低い。書き込み失敗時は `PersistenceError` を raise し、パイプライン続行（Google Sheets フォールバック）
- **パイプラインステップ障害**: 各ステップは独立実行。Screen 失敗時は前週の予測を使って Track/Export は実行可能
- **外部API レート制限**: `tenacity` による指数バックオフリトライ（最大3回、初回2秒、最大30秒）
- **設定エラー**: 起動時に Pydantic で全設定をバリデーション。不正値は即エラー（サイレント無視しない）

### テスト/検証方針

- 自動テスト: `pytest tests/ -v --cov=src --cov-fail-under=80`
- 型チェック: `mypy src/ --strict`
- リント: `ruff check src/ tests/`
- フロントエンドビルド: `cd dashboard && npm run build`
- 手動確認観点:
  - [ ] 全 API キー未設定でアプリが正常起動し degraded mode で動作すること
  - [ ] `config/default.yaml` のデフォルト設定のみで最小実行が完了すること
  - [ ] US株・JP株それぞれ独立でパイプライン実行できること
  - [ ] 予測モデルの差し替え（Prophet 単体 ↔ アンサンブル）が config 変更のみで可能なこと
  - [ ] ダッシュボードが Cloudflare Pages で正常表示されること
  - [ ] 既存の Google Sheets データと新 DB の整合性が取れること
  - [ ] 移行期間中は `dashboard/data/*.json` に出力され、現行ダッシュボードで表示可能であること
  - [ ] Phase C 完了後は `dashboard/public/data/*.json` に出力が切り替わり、Svelte ダッシュボードで表示可能であること

### リスクと対策

1. リスク: 再設計の規模が大きく、全体完了までに長期間を要する → 対策: Step 1-4（基盤+スクリーニング）を Phase A、Step 5-8（予測+エンリッチ+通知）を Phase B、Step 9-12（オーケストレーター+フロントエンド+CI）を Phase C として段階リリース。各フェーズ終了時に既存システムと並行稼働で検証する

2. リスク: LightGBM モデルの訓練データが不足（現行は数十週分の予測実績のみ）→ 対策: 初期は Prophet 単体をデフォルトとし、LightGBM は十分な実績データ（52週以上）が蓄積された後にアンサンブルへ移行。`config.yaml` の `prediction.model` で切り替え可能に設計

3. リスク: フロントエンド Svelte 移行で既存ダッシュボードが一時的に利用不能になる → 対策: JSON スキーマの後方互換を維持し、Svelte 版完成まで現行 HTML/JS ダッシュボードを併存。`/legacy/` パスで旧版にアクセス可能に設定

4. リスク: Google Sheets → SQLite 移行で過去データが失われる → 対策: Google Sheets からの一括エクスポートスクリプト（`scripts/migrate_sheets_to_db.py`）を用意。移行後も `sheets_exporter.py` で Google Sheets への一方向同期を維持

5. リスク: Perplexity Sonar API の有料コストが想定以上に膨らむ → 対策: `max_tickers` 制限（デフォルト5）と `enabled: false` デフォルトを維持。API レスポンスのセッション内キャッシュで重複呼び出し防止。コスト監視を structlog で記録

6. リスク: 920行の `enricher.py` 分割時にロジック欠落や挙動変更が発生する → 対策: 分割前に現行出力のスナップショットを取得し、分割後の出力と diff で完全一致を確認する回帰テストを実装

7. リスク: 現行テスト（16ファイル）が `from src.xxx import ...` のインポートパスに依存しており、ディレクトリ再構成で全テストが壊れる → 対策: Step 1 で `src/__init__.py` にインポート互換レイヤー（re-export）を一時的に用意し、段階的に新パスへ移行。CI で既存テストの PASS を各ステップで確認

8. リスク: CI/CD の移行ギャップ。現行 `weekly_run.yml` が `python -m src.main` を実行しており、移行中にCIが壊れる → 対策: 新CIワークフローは `weekly_run_v2.yml` として並行作成し、旧ワークフローは Phase C 完了まで維持。最終切り替え時に旧ワークフロー削除

9. リスク: `uv` は比較的新しいツールであり、GitHub Actions や Windows での互換性問題がある可能性 → 対策: `pyproject.toml` は PEP 621 準拠で記述し `pip install .` でもインストール可能。CI では `uv` 失敗時に `pip` フォールバック手順を用意

10. リスク: SQLite のファイルベースDB制限により並列ワーカーからの同時書き込みでロックが発生する可能性 → 対策: Write-Ahead Logging (WAL) モードを有効化（`PRAGMA journal_mode=WAL`）。現行は単一プロセス実行のため実害は低いが、長期的な PostgreSQL 移行パスを維持

### 完了条件

- [ ] `pyproject.toml` でプロジェクトが管理され、`uv run python -m src.cli run` で全パイプラインが実行される
- [ ] データプロバイダーがプラグイン型（`DataProvider` ABC）で統一され、新規ソース追加が1ファイルで完結する
- [ ] SQLite による永続化が動作し、Google Sheets 依存が解消されている（後方互換エクスポートは維持）
- [ ] 予測モデルが `config.yaml` の設定変更のみで差し替え可能（Prophet / LightGBM / アンサンブル）
- [ ] `prob_up_calibrated` が Platt Scaling で実計算される（`null` でない）
- [ ] `enricher.py` が5つ以下のモジュールに分割され、各ファイルが400行以下
- [ ] フロントエンドが Svelte + Vite で構築され、Cloudflare Pages にデプロイ可能
- [ ] `pytest tests/ -v --cov=src --cov-fail-under=80` が全 PASS
- [ ] `mypy src/ --strict` がエラー0
- [ ] CI/CD で PR テスト・週次実行・ダッシュボードデプロイが自動化されている
- [ ] 現行ダッシュボードの JSON スキーマと後方互換が維持されている
