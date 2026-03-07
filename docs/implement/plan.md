## 実装計画: 個人投資家向けLLM分析モジュール（7種追加）

> proposal: `docs/implement/proposal_1.md`
> 作成日: 2026-03-07

---

### 目的

既存の投資銀行向け12種分析（DCF, Comps, M&A等）に加えて、
個人投資家向けの実用的な7種類のLLM駆動型分析機能を追加する。
既存の `Analyzer` ABC・`AnalysisRunner`・`templates.py` のパターンに従い、
最小限の基盤変更で新しい分析タイプを統合する。

### スコープ

- 含むもの:
  - 7種類の個人投資家向け分析テンプレート:
    1. Full Stock Analysis（総合分析・Buy/Hold/Sell判定）
    2. Stock Screener（スクリーニング基準生成）
    3. Earnings Report Analysis（決算レポート分析）
    4. Risk Assessment（ダウンサイドリスク評価）
    5. Stock Comparison（2銘柄のHead-to-Head比較）
    6. Portfolio Builder（ポートフォリオ構築提案）
    7. Entry Timing（エントリータイミング分析）
  - 各分析に対応するアナライザークラス
  - テンプレートの追加（`templates.py` に7種追加）
  - `AnalysisRunner` への登録
  - CLIコマンドの拡張（新しい分析タイプ対応）
  - 2銘柄比較に対応するための `AnalysisInput` モデル拡張
  - 戦略パラメータ（投資スタイル、金額、期間）のCLI/設定サポート
  - ユニットテスト

- 含まないもの:
  - 既存12種分析の変更（テンプレート内容・アナライザーロジック）
  - ダッシュボードUI変更（既存 `analysis.html` がそのまま対応可能）
  - Slack通知フォーマットの変更
  - 新しいデータプロバイダーの追加
  - リアルタイムデータストリーミング

### 影響範囲（変更/追加予定ファイル）

#### 新規作成

| ファイル | 役割 |
|---|---|
| `src/analysis/stock_analysis_analyzer.py` | 総合分析（Buy/Hold/Sell判定） |
| `src/analysis/stock_screener_analyzer.py` | スクリーニング基準生成 |
| `src/analysis/earnings_report_analyzer.py` | 決算レポート分析 |
| `src/analysis/risk_assessment_analyzer.py` | ダウンサイドリスク評価 |
| `src/analysis/stock_comparison_analyzer.py` | 2銘柄比較分析 |
| `src/analysis/portfolio_builder_analyzer.py` | ポートフォリオ構築提案 |
| `src/analysis/entry_timing_analyzer.py` | エントリータイミング分析 |
| `tests/test_analysis_retail_analyzers.py` | 7種アナライザーのユニットテスト |

#### 変更

| ファイル | 変更内容 |
|---|---|
| `src/analysis/templates.py` | 7種の `AnalysisTemplate` 定義を追加、`TEMPLATES` dict に登録 |
| `src/analysis/runner.py` | `_get_all_analyzers()` に7種を追加 |
| `src/core/models.py` | `AnalysisInput` に `comparison_data` と `params` フィールド追加（`from __future__ import annotations` による forward reference 解決確認含む） |
| `src/core/config.py` | `_VALID_ANALYSIS_TYPES` セットに7種追加: `stock_analysis`, `stock_screener`, `earnings_report`, `risk_assessment`, `stock_comparison`, `portfolio_builder`, `entry_timing` |
| `src/analysis/data_collector.py` | 2銘柄比較時の `collect_pair()` メソッド追加 |
| `src/cli.py` | `analyze` コマンドに `--compare`, `--style`, `--amount`, `--timeframe`, `--sector` オプション追加。カテゴリC（`stock_screener`, `portfolio_builder`）指定時は `--ticker` 省略可能にする分岐ロジック追加 |
| `config/default.yaml` | `enabled_analyses` リストに新しい分析タイプのコメント追加 |
| `tests/conftest.py` | `comparison_data` 付き `AnalysisInput` サンプル等の共通テストフィクスチャ追加 |

### 設計判断: 3つのカテゴリ分類

7種を以下の3カテゴリに分類し、それぞれのデータフローを設計する:

**カテゴリA: 単一銘柄分析（既存パターン完全準拠）**
- Full Stock Analysis, Earnings Report, Risk Assessment, Entry Timing
- 既存の `Analyzer` ABC と `AnalysisInput` をそのまま使用
- データ収集: 既存 `AnalysisDataCollector.collect(ticker)` のみ

**カテゴリB: 2銘柄比較分析（モデル拡張必要）**
- Stock Comparison
- `AnalysisInput` に `comparison_data: AnalysisInput | None` フィールド追加
- データ収集: `AnalysisDataCollector.collect_pair(ticker_a, ticker_b)` 新設
- CLI: `--compare MSFT` オプションで比較対象を指定

**カテゴリC: 戦略パラメータ分析（パラメータ拡張必要）**
- Stock Screener, Portfolio Builder
- `AnalysisInput` に `params: dict[str, Any]` フィールド追加
- CLI: `--style growth`, `--amount 10000`, `--timeframe 5y` オプション
- 銘柄不要のケースにも対応（セクター/マーケット全体の分析）

### 実装ステップ

#### Step 1: 設定バリデーション・モデル拡張
- [ ] `src/core/config.py` の `_VALID_ANALYSIS_TYPES` セットに7種追加:
  ```python
  _VALID_ANALYSIS_TYPES = {
      "dcf", "comps", "financial_statement", "sensitivity",
      "ma", "lbo", "precedent", "ipo", "credit", "sotp",
      "operating_model", "ic_memo",
      # Retail investor analyses
      "stock_analysis", "stock_screener", "earnings_report",
      "risk_assessment", "stock_comparison", "portfolio_builder",
      "entry_timing",
  }
  ```
- [ ] `src/core/models.py` の `AnalysisInput` に2フィールド追加（`from __future__ import annotations` が既に使用されていることを確認し、自己参照型の forward reference を解決）:
  ```python
  comparison_data: AnalysisInput | None = None  # for stock comparison
  params: dict[str, Any] = Field(default_factory=dict)  # strategy parameters
  ```
  注意: `params` は `dict[str, Any]` とする（`dict[str, str]` だと数値パラメータの扱いが煩雑になるため）
- [ ] `AnalysisInput` の自己参照型が Pydantic v2 で正しく動作することを検証:
  - `model_dump()` / `model_validate()` の往復テスト
  - JSON シリアライズ/デシリアライズテスト
- [ ] `src/analysis/data_collector.py` に `collect_pair()` メソッド追加:
  ```python
  def collect_pair(self, ticker_a: str, ticker_b: str) -> AnalysisInput:
      primary = self.collect(ticker_a)
      comparison = self.collect(ticker_b)
      return AnalysisInput(
          **primary.model_dump(exclude={"comparison_data"}),
          comparison_data=comparison,
      )
  ```
  注意: `primary.__dict__` ではなく `primary.model_dump()` を使用（`frozen=True` Pydantic モデルとの互換性確保）
- [ ] ゲート条件: `pytest tests/ -v` で既存テスト全PASS確認

**検証**: `_VALID_ANALYSIS_TYPES` に19種が含まれること。`AnalysisConfig(enabled_analyses=["stock_analysis"])` が `ValueError` なくバリデーションされること。既存テストが全PASS（`AnalysisInput` の後方互換性確認）。`collect_pair("AAPL", "MSFT")` が両銘柄のデータを含む `AnalysisInput` を返すこと。`AnalysisInput.model_dump()` / `model_validate()` が `comparison_data` 付きで往復可能なこと。

#### Step 2: テンプレート追加（7種）
- [ ] `src/analysis/templates.py` に以下の7テンプレートを追加:
  - `STOCK_ANALYSIS`: 総合分析テンプレート
    - system_prompt: "You are a senior Wall Street analyst..."
    - user_prompt: revenue growth, profit margins, debt levels, competitive position, valuation → Buy/Hold/Sell
  - `STOCK_SCREENER`: スクリーニング基準テンプレート
    - system_prompt: "You are a quantitative investment strategist..."
    - user_prompt: {style} stocks, metrics, ratios, thresholds for {sector/market}
  - `EARNINGS_REPORT`: 決算分析テンプレート
    - system_prompt: "You are a senior equity research analyst..."
    - user_prompt: beat/miss expectations, management signals, investment case impact
  - `RISK_ASSESSMENT`: リスク評価テンプレート
    - system_prompt: "You are a risk management specialist..."
    - user_prompt: industry threats, competitive risks, balance sheet, macro exposure, worst-case
  - `STOCK_COMPARISON`: 銘柄比較テンプレート
    - system_prompt: "You are a portfolio strategist..."
    - user_prompt: valuation, growth, financial health, moat comparison → stronger buy
  - `PORTFOLIO_BUILDER`: ポートフォリオ構築テンプレート
    - system_prompt: "You are a certified financial planner..."
    - user_prompt: {amount}, {style}, {timeframe} → diversified portfolio with allocation %
  - `ENTRY_TIMING`: エントリータイミングテンプレート
    - system_prompt: "You are a technical analysis expert..."
    - user_prompt: current valuation, price action, support levels → buy now/wait/target price
- [ ] `TEMPLATES` dict に7種を追加

**検証**: 全19テンプレート（既存12 + 新規7）が `TEMPLATES` dict に登録され、`{financials_summary}` プレースホルダーが正しく展開されること。

#### Step 3: カテゴリA アナライザー実装（4種）
- [ ] `stock_analysis_analyzer.py`:
  - name: `"stock_analysis"`
  - required_data_fields: `["revenue", "ebitda", "netIncome", "totalDebt"]`
  - テンプレート: `STOCK_ANALYSIS`
- [ ] `earnings_report_analyzer.py`:
  - name: `"earnings_report"`
  - required_data_fields: `["revenue", "netIncome", "income_stmt"]`
  - テンプレート: `EARNINGS_REPORT`
- [ ] `risk_assessment_analyzer.py`:
  - name: `"risk_assessment"`
  - required_data_fields: `["totalDebt", "revenue", "beta"]`
  - テンプレート: `RISK_ASSESSMENT`
- [ ] `entry_timing_analyzer.py`:
  - name: `"entry_timing"`
  - required_data_fields: `["revenue", "trailingPE"]`
  - テンプレート: `ENTRY_TIMING`

**検証**: 各アナライザーが既存 `ConcreteAnalyzer` テストパターンに準拠し、モックLLMで `AnalysisResult` を返すこと。

#### Step 4: カテゴリB アナライザー実装（1種）
- [ ] `stock_comparison_analyzer.py`:
  - name: `"stock_comparison"`
  - required_data_fields: `["revenue", "ebitda"]`
  - `_user_prompt()` をオーバーライドし、`data.comparison_data` がある場合は両銘柄の financials_summary を含める
  - `_format_comparison_summary()` ヘルパーメソッド追加: 2銘柄のデータを並列表示
  - `_validate_input()` をオーバーライドし、`comparison_data` が `None` の場合は `ValueError` raise

**検証**: `comparison_data` 付き `AnalysisInput` で2銘柄の情報がプロンプトに含まれること。`comparison_data=None` で明確なエラーメッセージが出ること。

#### Step 5: カテゴリC アナライザー実装（2種）
- [ ] `stock_screener_analyzer.py`:
  - name: `"stock_screener"`
  - required_data_fields: `[]`（銘柄なしでも動作可能）
  - `_user_prompt()` で `data.params` から `style`, `sector`, `market` を取得しテンプレートに注入
  - デフォルト: style=`"growth"`, sector=`"all"`, market=`"US"`
- [ ] `portfolio_builder_analyzer.py`:
  - name: `"portfolio_builder"`
  - required_data_fields: `[]`（銘柄なしでも動作可能）
  - `_user_prompt()` で `data.params` から `amount`, `style`, `timeframe`, `num_stocks` を取得
  - デフォルト: amount=`"$10,000"`, style=`"growth"`, timeframe=`"5 years"`, num_stocks=`"10"`

**検証**: `params` 未指定時にデフォルト値で動作すること。カスタム `params` が正しくテンプレートに反映されること。

#### Step 6: ランナー・CLI統合
- [ ] `src/analysis/runner.py` の `_get_all_analyzers()` に7種を追加:
  ```python
  from src.analysis.stock_analysis_analyzer import StockAnalysisAnalyzer
  from src.analysis.stock_screener_analyzer import StockScreenerAnalyzer
  from src.analysis.earnings_report_analyzer import EarningsReportAnalyzer
  from src.analysis.risk_assessment_analyzer import RiskAssessmentAnalyzer
  from src.analysis.stock_comparison_analyzer import StockComparisonAnalyzer
  from src.analysis.portfolio_builder_analyzer import PortfolioBuilderAnalyzer
  from src.analysis.entry_timing_analyzer import EntryTimingAnalyzer
  ```
- [ ] `AnalysisRunner.run_single()` を拡張: `stock_comparison` タイプの場合は `collect_pair()` を使用
- [ ] `src/cli.py` の `analyze` コマンドに以下のオプション追加:
  - `--compare TEXT`: 比較対象銘柄（`stock_comparison` タイプ用）
  - `--style TEXT`: 投資スタイル（growth/dividend/value）
  - `--amount TEXT`: 投資金額
  - `--timeframe TEXT`: 投資期間
  - `--sector TEXT`: 対象セクター
- [ ] CLI の `--ticker` 必須チェック（L192-195）をカテゴリC対応に修正:
  ```python
  TICKER_OPTIONAL_TYPES = {"stock_screener", "portfolio_builder"}
  tickers = [t.strip() for t in ticker.split(",") if t.strip()] if ticker else []
  if not tickers:
      if types and all(t in TICKER_OPTIONAL_TYPES for t in types):
          tickers = ["MARKET"]  # dummy ticker for strategy analyses
      else:
          typer.echo("No tickers specified. Use --ticker AAPL,MSFT")
          raise typer.Exit(code=1)
  ```
  これにより `--ticker` 未指定 + `--type stock_screener` が正常動作し、他のタイプでは従来通りエラーになる
- [ ] CLI内で新オプションを `AnalysisInput.params` に変換するロジック追加
- [ ] `stock_comparison` タイプで `--compare` 未指定時の明確なエラーメッセージ追加

**検証**:
- `trader analyze --ticker AAPL --type stock_analysis` で総合分析が実行されること
- `trader analyze --ticker AAPL --type stock_comparison --compare MSFT` で比較分析が実行されること
- `trader analyze --type stock_screener --style growth --sector technology` でスクリーニング基準が生成されること
- `trader analyze --type portfolio_builder --amount 50000 --style conservative --timeframe 10y` でポートフォリオが提案されること

#### Step 7: テスト
- [ ] `tests/test_analysis_retail_analyzers.py` に以下のテストを実装:
  - 各7種アナライザーの `name` プロパティテスト
  - 各7種アナライザーの `required_data_fields` テスト
  - カテゴリA（4種）: モックLLMで `analyze()` が `AnalysisResult` を返すこと
  - カテゴリB: `comparison_data` 付きで2銘柄のサマリーがプロンプトに含まれること
  - カテゴリB: `comparison_data=None` で適切なエラーが出ること
  - カテゴリC: `params` 未指定でデフォルト値が使われること
  - カテゴリC: カスタム `params` がプロンプトに反映されること
- [ ] `tests/test_analysis_data_collector.py` に `collect_pair()` のテスト追加
- [ ] `tests/test_analysis_runner.py` に `stock_comparison` の特殊ルーティングテスト追加
- [ ] 既存テスト全PASS確認: `pytest tests/ -v`
- [ ] Lint: `ruff check src/analysis/`

**検証**: 全テストPASS。新規テストカバレッジ80%以上。既存テストに影響なし。

### 例外・エラーハンドリング方針

1. **比較対象銘柄の未指定**: `stock_comparison` タイプで `--compare` 未指定 → CLIレベルで明確なエラーメッセージ表示、分析実行しない
2. **パラメータ不正**: `--style` に不正値 → 許容値（growth/dividend/value）をエラーメッセージに含めて表示
3. **銘柄データ取得失敗**: 比較分析でどちらかの銘柄データが取得できない場合 → `DataCollectionError` raise、両方のデータが揃った場合のみ分析実行
4. **LLM API障害**: 既存のリトライ・フォールバックポリシーに準拠（tenacity 3回、個別失敗はスキップ）
5. **戦略パラメータ型分析で銘柄未指定**: `stock_screener` と `portfolio_builder` は銘柄なしでも動作可能。CLIで `--ticker` 未指定の場合はダミー入力（ticker="MARKET", company_name="Market Overview"）を生成

### テスト/検証方針

- 自動テスト: `pytest tests/test_analysis_retail_analyzers.py tests/test_analysis_data_collector.py tests/test_analysis_runner.py -v`
- Lint: `ruff check src/analysis/`
- 手動確認観点:
  - [ ] `trader analyze --ticker AAPL --type stock_analysis` が Buy/Hold/Sell の明確な判定を含む結果を返すこと
  - [ ] `trader analyze --ticker AAPL --type stock_comparison --compare MSFT` が両銘柄を比較した結果を返すこと
  - [ ] `trader analyze --type stock_screener --style dividend` が配当株向けのスクリーニング基準を返すこと
  - [ ] `trader analyze --type portfolio_builder --amount 100000 --timeframe 10y` がポートフォリオ構成を返すこと
  - [ ] 既存12種分析が影響を受けずに動作すること（`--type dcf` が従来通り動作）
  - [ ] `--type all` で19種全分析が実行可能なこと

### リスクと対策

1. リスク: `AnalysisInput` モデル変更による既存12種アナライザーへの影響 → 対策: 新フィールドはすべて Optional/デフォルト値付き（`comparison_data: AnalysisInput | None = None`, `params: dict[str, Any] = Field(default_factory=dict)`）。既存アナライザーは新フィールドを参照しないため影響なし。既存テスト全PASS確認を必須ステップとする

2. リスク: `stock_comparison` の `collect_pair()` が2銘柄分のAPIコールを発行し、レート制限に抵触 → 対策: `collect_pair()` は順次（非並列）で2回 `collect()` を呼び出す。既存の `AnalysisRunner` の `max_concurrent` 制限が全体の同時リクエスト数を制御するため、追加の制御は不要

3. リスク: `stock_screener` / `portfolio_builder` が銘柄不要のため、既存の銘柄ベースのデータフロー（`collect(ticker)` → `analyze(data)` → `export(result)`）と合わない → 対策: ダミー入力（ticker="MARKET"）を生成し、既存フローに乗せる。エクスポート時はティッカーとして "MARKET" を使用

4. リスク: 7種追加によるテンプレート管理の複雑化（`templates.py` が19テンプレートで肥大化） → 対策: テンプレートは `AnalysisTemplate` frozen dataclass で統一されており、追加は定数宣言のみ。Step 2 完了時にファイル行数を確認し、800行超過の場合は即座に `templates_retail.py` へファイル分割を実施

5. リスク: `_VALID_ANALYSIS_TYPES` への新タイプ未追加による `ConfigError`（YAML設定で新タイプを `enabled_analyses` に追加した時点で即座にバリデーションエラー） → 対策: Step 1 の最初のタスクとして `_VALID_ANALYSIS_TYPES` 更新を実施。ゲート条件として `AnalysisConfig(enabled_analyses=["stock_analysis"])` のバリデーション成功を確認してから次ステップに進む

### 完了条件

- [ ] 7種類の個人投資家向け分析テンプレートが全て実装され、`Analyzer` ABCに準拠していること
- [ ] `TEMPLATES` dict に19種（既存12 + 新規7）が登録されていること
- [ ] `_get_all_analyzers()` が19種のアナライザーを返すこと
- [ ] 2銘柄比較分析（`stock_comparison`）が `--compare` オプションで動作すること
- [ ] 戦略パラメータ分析（`stock_screener`, `portfolio_builder`）が銘柄なしでも動作すること
- [ ] 既存12種分析が影響を受けずに動作すること（既存テスト全PASS）
- [ ] 新規テストカバレッジ80%以上
- [ ] `ruff check src/analysis/` がエラー0
