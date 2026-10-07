## 実装計画: 市場区分別のベンチマークを、forward のレポートに併記する（REQ-058）

### 目的
グロース市場の小型株の超過リターンから、size 要因の差を見分けられるように、forward のレポートに市場区分別のベンチマーク（グロース → `2516.T`、プライム・スタンダード → `1306.T`）との超過リターンを**併記**する。既存のベンチマーク、レポートのキー、撤退判定は変えない。

### スコープ
- 含むもの: 市場とベンチマークの対応の定数、`2516.T` の取得（任意扱い）、売却ルールごとの `market_benchmark_excess`、`2516.T` の価格ハッシュ
- 含まないもの: 既存の `benchmark_excess` や取引ごとのキーの変更、撤退判定（kill criterion）の変更、学習側（`rebuild_inflection_learning.py`）と B1 の過去検証への適用、戦略・スコア・分類の変更、新しいファイル（テストを除く）

### 事前に確認した事実
- 価格の取得は `fetch_price_histories([*observed, BENCHMARK_TICKER], ..., required={BENCHMARK_TICKER})`。[forward_prices.py](../../src/data/forward_prices.py) は、`required` の欠損とは別に、**全取得対象の欠損率が `MAX_FAILURE_RATIO = 0.05` を超えると `RuntimeError` を送出する**。したがって、`2516.T` を同じ取得に加えて `required` から外すだけでは、`2516.T` の欠損でレポート生成が止まりうる（観測銘柄1件 + `1306.T` + `2516.T` で `2516.T` だけ欠損すると、欠損率 1/3 で失敗する。レビューで再現済み）。`2516.T` は、**既存の取得とは別の呼び出し**で取得する（Step 3）。既存の5%ガードは緩めない。
- ベンチマークは `fetched.total_return()` から `total_return.pop(BENCHMARK_TICKER)` で取り出し、`_build_group_report(signals, histories, split_histories, benchmark_history, signal_dates)` に1つだけ渡している。`paired_benchmark_returns` は、`BENCHMARK_TICKER` をラベルに固定している（ティッカーを引数にする必要がある）。
- 価格ハッシュは `_price_hashes` がティッカーごとに作り、`_changed_price_rows` が `old_hashes.get(ticker, {})` で比較する。新しいティッカーを足しても、既存のハッシュには影響しない。
- 取引（`TradeResult`）は市場を持たない。観測（`load_inflection_signals` の行）は `market`（`プライム`・`スタンダード`・`グロース`、`MktNm` の日本語名）を持つ。
- `2516.T` は、2026-10-07 に yfinance で取得できることを確認した（486日、出来高の中央値は約66万株）。**ETF の銘柄コードは、ユーザーが確認する [要確認]**。

### 影響範囲（変更/追加予定ファイル）
- [src/evaluation/inflection_forward.py](../../src/evaluation/inflection_forward.py): 市場とベンチマークの対応の定数、`paired_benchmark_returns` にティッカーの引数を追加（既定は `BENCHMARK_TICKER`）
- [src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py): `_build_group_report` と `_exit_strategy_report` に、市場別のベンチマークの履歴と、銘柄 → 市場の対応を任意の引数で渡し、`market_benchmark_excess` を加える
- [scripts/rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py): `2516.T` の取得、銘柄 → 市場の対応の作成、レポートへの受け渡し、価格ハッシュへの追加
- `tests/test_inflection_forward.py`（とレポートのテスト）: 既存ファイルに追記
- 変更しないもの: `inflection_live.py`、`inflection_learning.py`、`rebuild_inflection_learning.py`、`inflection_historical.py`、`inflection_backtest.py`

### 実装ステップ

#### Step 1: 市場別のベンチマークの定義と、ペアリング関数の拡張
- [ ] `inflection_forward.py` に、市場名 → ベンチマークのティッカーの対応の定数を追加する（`グロース` → `2516.T`、`プライム`・`スタンダード` → `1306.T`）。
- [ ] `paired_benchmark_returns` に、`benchmark_ticker`（既定は `BENCHMARK_TICKER`）の任意引数を追加し、出力の `benchmark_ticker` に使う。既存の呼び出しは、引数を省略して変わらない。
**検証**: 既存のテストが PASS し、既定の引数で出力が変わらない。

#### Step 2: レポートに `market_benchmark_excess` を追加
- [ ] `_exit_strategy_report` に、`market_benchmarks`（ティッカー → 履歴）と `ticker_markets`（銘柄 → 市場）の任意引数（既定は `None`）を追加する。`None` のときは、従来のキーだけを返す。
- [ ] 満期までの取引（`horizon_matured is True`）を、市場ごとに分け、その市場のベンチマークの履歴で `paired_benchmark_returns` を呼び、`summarize_benchmark_excess` で要約する。出力は `{市場名: {"benchmark_ticker": ..., **要約}}`。
- [ ] 市場に対応するベンチマークがない取引、対応するベンチマークの履歴がない場合は、その市場を対象外にし、理由（`"unavailable"` など）を出す。
- [ ] `_build_group_report` と、それを呼ぶ箇所で、引数を `_exit_strategy_report` まで渡す。既存のキーの順序と値は変えない。
**検証**: 受入条件 1、2、4。合成の価格で、グロースとプライムの超過リターンが手計算と一致する。

#### Step 3: forward の再構築スクリプトの変更
- [ ] `rebuild_inflection_forward_validation.py` で、既存の `fetch_price_histories([*observed, BENCHMARK_TICKER], ...)` の呼び出しは**変更しない**（取得対象に `2516.T` を加えない。5%ガードと `required` の挙動を維持する）。`2516.T` は、**別の `fetch_price_histories([市場別ベンチマークのティッカー], ..., required={そのティッカー})` の呼び出し**で取得し、その呼び出しの `RuntimeError`（取得失敗）だけを捕捉する。失敗した場合は、`market_benchmarks` を空にして、失敗の理由を `market_benchmark_excess` の `None` の理由に渡す。捕捉の範囲は、この追加ETFの呼び出しだけにする（既存の取得の例外を握りつぶさない）。追加の呼び出しは、`cache_path` を共有するかどうかを、`_load_cache` / `_save_cache` の挙動を読んで決める（共有で既存のキャッシュを壊す、または失われる恐れがあれば、`cache_path=None` にして毎回取得する。取得は1銘柄で、負担は小さい）。
- [ ] 観測（`all_observations`）から、シグナル日ごとの銘柄 → 市場の対応を作る。取引は `signal_date` と `ticker` を持つので、同じ銘柄が複数の日にある場合は、シグナル日の観測の市場を使う [取引から市場を引くキーは、実装時に決める]。
- [ ] `total_return.pop(BENCHMARK_TICKER)` と同様に、`2516.T` を `histories` から取り除き、`market_benchmarks` に入れる。取り除かないと、候補の銘柄と一緒に評価されてしまう。
- [ ] 価格ハッシュに、`2516.T` を加える（`_legacy_hash_starts` と `_price_hashes` に、`1306.T` と同じ扱い）。
**検証**: 受入条件 3、5。`2516.T` が取得できない場合にレポートが生成される。テストでは、既存の `FakeDownload` で、観測銘柄と `1306.T` は成功し、`2516.T` だけ欠損する場合に、レポートが生成され、`market_benchmark_excess` が理由つきの `None` になることを確認する。また、既存の取得で観測銘柄の欠損が5%を超える場合は、従来どおり失敗することも確認する（ガードを緩めていない確認）。

#### Step 4: 回帰と最終確認
- [ ] 既存のキーと値が変わらないことを、変更前後の出力の比較で確認する（`market_benchmark_excess` を除いて同一）。
- [ ] ruff、mypy（CI の対象のファイル）、`pytest tests/ -q`（カバレッジ 80% 以上）。
- [ ] 実データで、`rebuild_inflection_forward_validation.py` を一度実行して、`market_benchmark_excess` が出ることを確認する（外部の取得が必要。実行はユーザーの確認後。標本が少なければ、空の要約でもよい）。
**検証**: 完了条件の全項目。

### 例外・エラーハンドリング方針
- `2516.T` の取得失敗は、レポートの生成を止めない（市場別の併記を理由つきの `None` にする）。既存の取得の5%ガード、`required`（`1306.T`）の失敗判定、既存の取得の例外は、変更も握りつぶしもしない。`2516.T` だけを別の呼び出しにして、その呼び出しの失敗だけを捕捉する。`1306.T` の取得失敗は、従来どおり失敗する（撤退判定の基準だから）。
- 市場が対応表にない取引は、市場別の併記の対象外にし、既存の `benchmark_excess` には従来どおり含める。
- 市場別のベンチマークの計算の失敗が、既存のレポートのキーに影響しないようにする（追加のキーだけが欠ける）。

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/test_inflection_forward.py -q`（対象）、最後に `.venv/bin/python -m pytest tests/ -q`。`ruff check src scripts tests`、CI と同じ対象の `mypy --ignore-missing-imports`。
- 受入条件のテストが、実装の誤りを検出できることを、一時的にバグを入れて確認する（例: 市場とベンチマークの対応を入れ替える、`1306.T` を全市場に使う）。
- 手動確認観点: `market_benchmark_excess` の各市場の `benchmark_ticker` が、対応表どおりである。

### リスクと対策
1. リスク: `2516.T` が、グロース250連動の ETF ではない（銘柄コードの誤り） → 対策: 実装の前に、ユーザーが銘柄を確認する（[要確認]）。対応表は定数 1 行なので、変更は容易。
2. リスク: 取引から市場を引くキーが曖昧で、市場の取り違えが起きる → 対策: シグナル日と銘柄の組で観測の市場を引く。テストで、市場が混在する合成データを使う。
3. リスク: ベンチマークを追加すると、`histories` に混入して、候補として評価される → 対策: `1306.T` と同じく、取得結果から取り除く（ステップ3）。テストで、`histories` に `2516.T` が残らないことを確認する。
4. リスク: ベンチマークの取得が増えて、実行時間が延びる → 対策: 1銘柄の追加だけで、影響は小さい。
5. リスク: 追加のキーが、forward のレポートを読む側（learning や Slack のダイジェスト）を壊す → 対策: 追加のキーだけで、既存のキーは変えない。読む側が、未知のキーを要求しないことを、既存のテストで確認する。

### 完了条件
- [ ] REQ-058 の受入条件 1〜6 が、テストで確認されている
- [ ] 既存の `benchmark_excess`、取引ごとのキー、撤退判定が変わらない
- [ ] `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）が変わっていない
- [ ] ruff、mypy、`pytest tests/ -q` が PASS（カバレッジ 80% 以上）
- [ ] ETF の銘柄コード（`2516.T`）を、ユーザーが確認している
