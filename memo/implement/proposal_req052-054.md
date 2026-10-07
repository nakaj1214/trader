# 実装要件書（REQ-052〜054: 日次 scan の耐性、四半期の業績の加速、業種の相対モメンタム）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の §4.1（四半期ごとの業績の加速）、REQ-022（業種の相対モメンタム）、および 2026-09-28・10-05 の日次 scan の失敗（`memo/local/tmp.md`）。
> 以前の要件書: REQ-001〜051 → それぞれ `proposal_req*.md`

## 背景

- **日次 scan の失敗:** 2026-09-28 と 10-05（どちらも月曜）の scan が `latest_coverage=0.0%` で失敗し、snapshot が欠けた。欠けた日は後から取り戻せない。価格は 99.6% 取得できているが、**期待日（10-05）を最新の足とする銘柄が 0 件**だった。原因は特定できていない（Yahoo が期待日より後の足を返した、期待日の足がまだ配信されていない、などの仮説がある）。失敗時のログに「最新日付の分布」が出ないため、次に失敗しても原因が分からない。
- **四半期の業績の加速:** 現在の特徴量は、直近の決算の累計値の前年比だけである。報告書 §4.1 は、**単独の四半期の成長率が前の四半期より加速したか**（Chordia & Shivakumar）を挙げている。
- **業種の相対モメンタム:** 業種コード（S33）は snapshot に記録済みだが、業種全体の動きに対する銘柄の相対的な強さは記録していない。

## 決定済みの事項

- **戦略・スコア・分類・候補の選定は変えない。** `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）は変えない。snapshot に足すのは `features`（辞書）の項目だけである（REQ-050 と同じ方式）。
- **新しい項目は過去の snapshot にない。** 読む側は項目がなくても動くこと。
- 戦略に影響する項目（A7 の減衰、A8-a・b、相場環境による切り替え、売却ルールの採用、B5）は、B1 の標本が不足しているため保留する（2026-10-07 ユーザー確認）。

## 事実確認（2026-10-07、実データ）

- J-Quants の `CurPerType` は**累計**である。1Q は3か月、2Q は6か月、3Q は9か月、FY/4Q は12か月の期間を持つ（`.data/jquants/fins/2026-05-15.json.gz` の全行で確認）。単独の四半期の値は、同じ会計年度（`CurFYEn`）の1つ前の累計との差で作る。
- `expected_tse_session_date` は JST の日付から正しく期待日を求めている（10-06 01:21 JST の起動でも期待日は 10-05）。つまり、期待日の計算の誤りではない。

---

## 要件一覧

### REQ-052: 日次 scan が、期待日より後の足と配信遅れで失敗しないようにし、失敗時に原因を残す

- **画面**: 日次 scan のログ、Slack の失敗通知
- **対象ファイル**: [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`scan_japan_inflection`、`PriceDataRetryExhausted`）、[scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（失敗通知の本文）、`tests/test_inflection_live.py`、`tests/test_shadow_health.py`
- **Before（現状）**:
  - 銘柄の最新の足が期待日と一致する割合（`latest_coverage`）だけを見る。期待日**より後**の日付の足があると、その銘柄は「古い」と数えられる。
  - 失敗時の `DATA_HEALTH_RETRY` のログと Slack の通知に、最新日付の分布がない（成功時のレポートにだけある）。
- **After（期待）**:
  - 価格の取得後（再試行で取り直した分も含む）、**期待日より後の日付の足を捨ててから**、`latest_coverage` の判定と特徴量の計算を行う。期待日は「確定しているはずの最新の営業日」なので、それより後の足は完成した足ではない。
  - `DATA_HEALTH_RETRY` のログと、`PriceDataRetryExhausted` の詳細（Slack の失敗通知）に、**最新日付の分布**（上位の日付と件数。例: `2026-10-02:3200,2026-10-06:480`）と、期待日より後の足を捨てた銘柄数を加える。日付と件数だけで、銘柄名は出さない。
  - 既存のゲートの閾値、再試行の待ち時間と回数は変えない。
- **受入条件**:
  1. 全銘柄の最新の足が期待日の翌営業日である合成データで、足を捨てた後に `latest_coverage` が 100% になり、scan が成功する（捨てた後の最新の足は期待日）。
  2. 期待日より後の足を捨てても、期待日以前の足の値は変わらない。特徴量は、期待日以前の足だけから計算される。
  3. 最新の足が期待日より**前**の日付（配信遅れ）の合成データでは、従来どおり失敗し、失敗の詳細に最新日付の分布が含まれる。
  4. `DATA_HEALTH_RETRY` のログに、最新日付の分布が含まれる。ログと通知に銘柄名を含まない。
  5. 既存の scan のテストが PASS する。
- **備考**: 10-05 の失敗の**原因はまだ仮説**である。この要件は、仮説が当たっていれば失敗を防ぎ、外れていても次の失敗の原因を特定できるようにするものである。9-28 と 10-05 の snapshot の補完は含めない。

### REQ-053: 四半期ごとの業績の加速を snapshot の特徴量に記録する（§4.1）

- **画面**: なし（snapshot の `features`）
- **対象ファイル**: [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`_fundamental_features`、`FEATURE_DEFAULTS`、`_evaluate_candidate`）、`tests/test_inflection_live.py`
- **Before（現状）**: `features` の成長率は、直近の決算の累計値と、前年の同じ種類の累計値の比較だけである。単独の四半期の値と、その加速はない。
- **After（期待）**: `features` に、次の項目を追加する（すべて**スコアには使わない**）。計算できなければ `None`。
  - `quarterly_sales_growth_yoy_pct`: 直近の単独の四半期の売上の前年同期比（%）
  - `quarterly_op_growth_yoy_pct`: 同、営業利益（前年同期が正のときだけ計算する。既存の `operating_profit_growth_yoy_pct` と同じ扱い）
  - `quarterly_sales_growth_accel_pctpt`: 直近の四半期の売上の前年同期比 − 1つ前の四半期の前年同期比（パーセントポイント）
  - `quarterly_op_growth_accel_pctpt`: 同、営業利益
  - 単独の四半期の値: 1Q は 1Q の累計そのもの、2Q・3Q は累計 − 同じ会計年度の1つ前の累計、4Q は FY の累計 − 3Q の累計。前年同期の値も同じ方法で作る。
  - 必要な行（同じ会計年度の1つ前の累計、前年の対応する期）がなければ `None`。連結・単体や会計基準の違う行を混ぜない（既存の行の選び方に合わせる）。
  - 判定日より後に開示された行は使わない（point-in-time）。B1 の過去検証の `reconstruct_scan` も同じ関数を通るので、過去の日付でも同じ項目が計算される。
- **受入条件**:
  1. 手計算できる合成の累計の行（1Q〜FY の2年分）で、単独の四半期の値、前年同期比、加速が期待どおりになる。
  2. 2Q・3Q・4Q（FY）の各期で、累計から単独の値が正しく作られる。1つ前の累計がない場合は `None` になる。
  3. 前年同期が 0 または負の営業利益のとき、営業利益の成長率と加速が `None` になる（0 除算と符号の誤りがない）。
  4. 新しい項目を足しても、スコア、分類、`candidates`、`classification_counts` が変わらない。
  5. `validate_report`、forward の loader、learning の loader が、新しい項目がある snapshot と、ない snapshot の両方を読める。
  6. 実データ（`.data/jquants/fins`）で、新しい項目が計算できる割合（取得率）が分かる（B1 の評価の `yoy_coverage_by_month` と同様に、実装の確認として一度だけ測る。測定結果は memo に記録する）。
- **備考**: 累計値の意味は上の「事実確認」で確認済み。取得率が低い場合は、必要な過去の行数（warmup）の問題なので、結果を報告して判断を仰ぐ。

### REQ-054: 業種の相対モメンタムを snapshot の特徴量に記録する（REQ-022）

- **画面**: なし（snapshot の `features`）
- **対象ファイル**: [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`select_and_evaluate`、`_evaluate_candidate`、`FEATURE_DEFAULTS`）、`tests/test_inflection_live.py`
- **Before（現状）**: 業種コード（S33）は記録されているが、業種全体の動きに対する相対的な強さはない。
- **After（期待）**: `features` に、次の項目を追加する（すべて**スコアには使わない**）。計算できなければ `None`。
  - `sector33_return_20d_pct`、`sector33_return_60d_pct`: 同じ S33 の、価格特徴量が計算できた全銘柄（流動性で絞る前の全体）の、20日・60日リターンの**中央値**
  - `relative_return_20d_vs_sector_pct`、`relative_return_60d_vs_sector_pct`: 銘柄のリターン − 業種の中央値（パーセントポイント）
  - 業種の銘柄数が少ない場合（5銘柄未満）は、中央値の値は `None`（ノイズを避ける）。業種コードがない銘柄も `None`。
  - 業種の中央値は、`select_and_evaluate` が受け取った `prices` と `ticker_meta` だけから作る。B1 の `reconstruct_scan` も同じ関数を通るので、過去の日付でも計算される。
- **受入条件**:
  1. 業種が複数ある合成データで、業種ごとの中央値と、銘柄の相対値が期待どおりになる。
  2. 業種の銘柄数が5未満のとき、4項目が `None` になる。業種コードがない銘柄も `None` になる。
  3. 判定日より後の価格を変えても、計算された値が変わらない（先読みしない）。
  4. 新しい項目を足しても、スコア、分類、`candidates`、`classification_counts` が変わらない。
  5. `validate_report`、forward の loader、learning の loader が、新しい項目がある snapshot と、ない snapshot の両方を読める。

---

## 繰り返し失敗している要件

なし。（REQ-052 は、同じ種類の失敗が2回起きているが、原因の修正を試みたのは初めてである。）

---

## 完了済み・保留中

### 完了済み
- REQ-048〜051（候補の見える化、Slack のダイジェスト、診断用の特徴量、欠損営業日の検出）: コミット済み・push 済み
- B1 の過去検証（取得・評価）: 結果は [historical_backtest_2026-10-06.md](../analysis/historical_backtest_2026-10-06.md)。標本不足で判定不能

### 保留中（今回のスコープ外）
- **9-28・10-05 の snapshot の補完。** 過去の価格から作り直す機能は含めない。
- **戦略に影響する項目**（A7 の減衰、A8-a・b、相場環境による切り替え、売却ルールの採用、B5）。forward の標本が溜まってから判断する。
- **A8-d（市場ごとのベンチマーク）、B6（TDnet・EDINET・信用残など追加データ）、決算日・過熱の警告。** 調査が先である。
- **新しい特徴量のスコアへの採用。** 記録だけを行う。採用は、forward で効果を確認してからである。
