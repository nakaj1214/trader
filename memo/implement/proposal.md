# 実装要件書（REQ-058: 市場区分別のベンチマークを、forward のレポートに併記する）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の A8-d。
> 以前の要件書: REQ-001〜057 → それぞれ `proposal_req*.md`

## 背景

- forward のレポートは、全銘柄を共通のベンチマーク `1306.T`（TOPIX 連動 ETF）と比べている。**グロース市場の小型株の超過リターンには、size 要因の差（小型株が TOPIX に対して持つ構造的な差）が混入する**。戦略の良し悪しと、市場区分の差を、区別できない。
- 候補の `market` は、snapshot の各候補に記録済み（`プライム`、`スタンダード`、`グロース`）。

## 決定済みの事項

- **戦略・スコア・分類・候補の選定は変えない。** `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）は変えない。
- **既存のベンチマーク（`1306.T`）の結果、レポートのキーと値は変えない。** 市場別のベンチマークは**併記**であり、置き換えではない。撤退判定（B1 の kill criterion）も、現行の `1306.T` のままである。
- グロースのベンチマークは、`2516.T`（グロース市場250指数連動の ETF とされる）を使う。**ETF の銘柄コードは、実装前にユーザーが確認する**（[要確認]）。yfinance で取得できることは、2026-10-07 に確認済み（2年分の日足、出来高の中央値は約66万株）。
- プライムとスタンダードは `1306.T`（TOPIX）のままとする。

## 事実確認（2026-10-07）

- `2516.T`: 取得できる履歴は 2024-10-07〜（486日）。`1306.T`: 同 487日。
- 候補の `market` は、J-Quants の `MktNm`（日本語の名前）である。市場コードの `Mkt` ではない。
- 価格の改ざん検知（`price_hashes`）は、ティッカーごとに記録する構造で、新しいティッカーを足しても既存のハッシュに影響しない。

---

## 要件一覧

### REQ-058: 市場区分別のベンチマークの超過リターンを、forward のレポートに併記する

- **画面**: forward のレポート（`inflection_forward_validation_summary.json`）
- **対象ファイル**:
  - [src/evaluation/inflection_forward.py](../../src/evaluation/inflection_forward.py)（ベンチマークの定義、`paired_benchmark_returns`）
  - [src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py)（`_exit_strategy_report`、`_build_group_report`）
  - [scripts/rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)（価格の取得、ベンチマークの受け渡し、価格ハッシュ）
  - テスト: `tests/test_inflection_forward.py`、`tests/test_inflection_report.py`（あれば）
- **Before（現状）**: 各取引の超過リターンは、全銘柄で `1306.T` と比べる。市場区分ごとの比較はない。
- **After（期待）**:
  - 市場区分とベンチマークの対応を定数で定義する（`グロース` → `2516.T`、`プライム`・`スタンダード` → `1306.T`）。対応がない市場（`その他` など）は、市場別の併記の対象外とする。
  - forward の価格取得で、`2516.T` も取得する。**`2516.T` が取得できなくても、レポートは生成する**（市場別の併記を `None` と理由にする。既存の `1306.T` は従来どおり必須）。
  - 各売却ルールのレポート（`_exit_strategy_report`）に、`market_benchmark_excess`（追加のキー）を加える。**市場区分ごと**に、その市場のベンチマークとの超過リターンの要約（既存の `summarize_benchmark_excess` と同じ形）を出す。対象は、満期までの取引（matured）。
  - 各市場の要約に、使ったベンチマークのティッカーを含める。
  - 既存のキー（`benchmark_excess`、取引ごとの `benchmark_*`、`excess_return_pct` など）は変更しない。
  - 市場区分は、取引の銘柄の候補の `market` から求める（銘柄 → 市場の対応は、観測から作る）。同じ銘柄で市場が途中で変わった場合は、その取引のシグナル日の観測の市場を使う。
  - `2516.T` の価格ハッシュを、既存の仕組みで記録する。
- **受入条件**:
  1. グロースの取引は `2516.T`、プライムの取引は `1306.T` との超過リターンが、`market_benchmark_excess` に出る（合成の価格で、手計算の値と一致する）。
  2. 既存の `benchmark_excess`、取引ごとの `benchmark_*`、`excess_return_pct`、`regime_*` などのキーと値が、変更前と同じである。
  3. `2516.T` の価格が取得できないとき、レポートは生成され、`market_benchmark_excess` は理由つきの `None` になる。`1306.T` が取得できないときは、従来どおり失敗する。
  4. 市場が `その他` などの対応がない取引は、`market_benchmark_excess` の対象外になり、例外にならない。
  5. 価格ハッシュに `2516.T` が加わり、既存のティッカーのハッシュが変わらない。
  6. 既存の forward のテストが PASS する。
- **備考**:
  - 学習側（`rebuild_inflection_learning.py`）の超過リターンは、今回の対象外（`1306.T` のまま）。必要になれば別の要件にする。
  - B1 の過去検証（`inflection_historical.py`）も対象外。J-Quants の過去データのキャッシュに `2516` の日足があるかは未確認（`bars` は全銘柄の日足なので、ある可能性が高い）。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- REQ-048〜057（候補の見える化、診断用の特徴量、日次 scan の耐性、learning への接続、過熱警告、DSR）: コミット済み（`941cbbb`）、未 push

### 保留中（今回のスコープ外）
- **決算発表日の警告。** J-Quants の client に決算発表予定日のエンドポイントがない。取得方法の調査が先。
- **B6（TDnet・EDINET・信用残）。** 調査が先。
- **戦略に影響する項目**（A7 の減衰、A8-a・b、相場環境による切り替え、売却ルールの採用、B5）。forward の標本が溜まってから。
- **学習側・B1 の市場別ベンチマーク。** 今回は forward のみ。
