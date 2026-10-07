## 実装計画: 日次 scan の耐性、四半期の業績の加速、業種の相対モメンタム（REQ-052〜054）

### 目的
日次 scan が期待日より後の足で失敗しないようにし、失敗時に原因を残す（REQ-052）。あわせて、スコアに使わない診断用の特徴量（四半期の加速、業種の相対モメンタム）を snapshot の `features` に記録し始める（REQ-053・054）。戦略・スコア・分類・候補の選定は変えない。

### スコープ
- 含むもの:
  - 期待日より後の足の除去と、失敗時の最新日付の分布の出力（ログ、`PriceDataRetryExhausted`、Slack の失敗通知）
  - `features` への特徴量の追加: 四半期の4項目（REQ-053）、業種の4項目（REQ-054）
  - 実データでの取得率の測定と memo への記録（REQ-053 の受入条件 6）
- 含まないもの:
  - `STRATEGY_VERSION`、`REPORT_SCHEMA_VERSION`、スコア、分類、候補の選定の変更
  - 9-28・10-05 の snapshot の補完
  - 新しい特徴量のスコアへの採用、戦略に影響する項目（A7 の減衰、A8-a・b、相場環境、売却ルール、B5）
  - schema の変更、新しい abstraction・ファイル（テストを除く）

### 事前に確認した事実
- `CurPerType` は累計（1Q=3か月、2Q=6か月、3Q=9か月、FY/4Q=12か月）。単独の四半期は同じ `CurFYEn` の1つ前の累計との差で作る。
- `expected_tse_session_date` は JST の日付から期待日を求めており、誤りはない（変更しない）。
- 失敗の詳細は `PriceDataRetryExhausted.details` → [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)`main` が `GITHUB_OUTPUT` に書き出す → [.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml) の Slack の本文が、キーを**明示的に列挙**している。したがって、`details` に足すだけでは Slack に出ない。workflow の本文も変更が必要。
- B1 の過去検証の財務の行は `FINS_FIELDS`（`CurPerType`、`CurFYEn`、`Sales`、`OP` などを含む。`CurPerSt`・`CurPerEn` は含まない）。四半期の計算は `CurPerType`・`CurFYEn`・`Sales`・`OP`・`DocType` だけで作れるので、`FINS_FIELDS` は変更しない。
- 業種の中央値は、`select_and_evaluate` の最初のループ（全銘柄の `_technical_features` を計算する場所）で、全銘柄の技術特徴量が揃う。ここから作れる。

### 影響範囲（変更/追加予定ファイル）
- [src/screening/inflection_live.py](../../src/screening/inflection_live.py): 足の除去、最新日付の分布、四半期の特徴量、業種の特徴量、`FEATURE_DEFAULTS`
- [.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml): Slack の失敗通知に最新日付の分布を追加（1行）
- `tests/test_inflection_live.py`、`tests/test_shadow_health.py`: 受入条件のテスト（既存ファイルに追記）
- `memo/analysis/`: 取得率の測定結果（REQ-053 の受入条件 6）
- 変更しないもの: `scripts/run_inflection_shadow.py`（`details` を汎用に書き出すため）、`inflection_historical.py`、forward・learning の loader（新しい項目は `features` に足すだけで、読む側は項目を要求しない。受入条件のテストで確認する）

### 実装ステップ

#### Step 1: REQ-052 期待日より後の足の除去と失敗時の診断
- [ ] `inflection_live.py` に、価格辞書の各 DataFrame から**期待日より後の行を除く**関数を追加する（小さな内部関数。除いた銘柄数を返す）。
- [ ] `scan_japan_inflection` の価格取得のループで、最初の取得と、再試行で取り直した後（`prices.update(...)` の直後）の**両方**で、`latest_dates` を求める前に適用する。ループの後の `latest_dates` の再計算にも、除去済みの `prices` が使われることを確認する。
- [ ] 最新日付の分布（`Counter` の上位5件を `日付:件数` の文字列にしたもの）を作り、`DATA_HEALTH_RETRY` のログと `PriceDataRetryExhausted.details`（キー `latest_dates`、除去した銘柄数のキー `dropped_future_bars`）に加える。成功時のレポートの既存の `latest_date_histogram` と同じ集計方法にする。
- [ ] [.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml) の Slack の失敗通知の本文に `latest_dates=...` と `dropped_future_bars=...` の行を足す。
- [ ] 閾値、再試行の待ち時間と回数、`expected_tse_session_date` は変更しない。
**検証**: 受入条件 1〜5。翌営業日の足を持つ合成データで成功し、配信遅れの合成データで失敗し、詳細に分布が入る。

#### Step 2: REQ-054 業種の相対モメンタム
- [ ] `select_and_evaluate` の最初のループで、技術特徴量が計算できた全銘柄について、S33 ごとに `return_20d_pct`・`return_60d_pct` の値を集める。
- [ ] 銘柄数が5以上の業種だけ、中央値（標準ライブラリの `statistics.median`）を求める。`_evaluate_candidate` に、業種ごとの中央値の辞書を任意の引数（既定は空）として渡す。`_evaluate_candidate` の他の呼び出し元（あれば）は、引数を省略しても動くこと。
- [ ] `FEATURE_DEFAULTS` に4項目（`sector33_return_20d_pct`、`sector33_return_60d_pct`、`relative_return_20d_vs_sector_pct`、`relative_return_60d_vs_sector_pct`）を追加し、`source` に値を入れる。業種コードがない、業種の銘柄数が5未満、銘柄のリターンが `None` のときは `None`。
- [ ] スコア・分類の計算に使われないこと（`source` から `features` への書き出しだけ）を確認する。
**検証**: 受入条件 1〜5（REQ-054）。

#### Step 3: REQ-053 四半期の業績の加速
- [ ] `inflection_live.py` に、財務の行（`actual_rows`）から**単独の四半期の値**を作る内部関数を追加する。
  - 対象の行: `_has_actual_financials` が真で、`CurPerType` が `1Q`・`2Q`・`3Q`・`FY`/`4Q` のもの。決算の `DocType` の連結・単体・IFRS を混ぜない（最新の行の `DocType` の系統に合わせる）。`EarnForecastRevision` のような予想修正の行は、`Sales`・`OP` が空なので `_has_actual_financials` で除かれる。
  - 同じ `CurPerType`・`CurFYEn` の行が複数ある場合（訂正）は、開示の新しい行を使う（`_row_sort_key` の順）。
  - 単独の値 = その期の累計 − 同じ `CurFYEn` の1つ前の期の累計（1Q は累計そのもの）。1つ前の累計がなければ `None`。
- [ ] 直近の四半期（最新の `actual_rows` の期）と、前年の同じ期（`CurFYEn` が1年前、同じ `CurPerType`）の単独の値から、売上・営業利益の前年同期比を求める。営業利益は、前年同期が正のときだけ計算する（既存の `operating_profit_growth_yoy_pct` と同じ扱い）。
- [ ] 1つ前の四半期（直近の期の1つ前）の前年同期比も同じ方法で求め、差を `*_accel_pctpt` にする。
- [ ] `_fundamental_features` の戻り値に4項目（`quarterly_sales_growth_yoy_pct`、`quarterly_op_growth_yoy_pct`、`quarterly_sales_growth_accel_pctpt`、`quarterly_op_growth_accel_pctpt`）を加え、`FEATURE_DEFAULTS` にも加える。必要な行がなければ `None`。
- [ ] `_fundamental_features` に渡る行は、呼び出し元（ライブでは J-Quants の全履歴、過去検証では `PointInTimeFinancials`）が判定日までに絞っているので、ここでは追加の絞り込みをしない（先読みしないことは、過去検証側のテストで既に保証されている。新しいテストでも、判定日より後の行を渡さないことを前提に、`PointInTimeFinancials` 経由の1ケースで確認する）。
**検証**: 受入条件 1〜5（REQ-053）。

#### Step 4: 取得率の測定（REQ-053 の受入条件 6）
- [ ] `.data/jquants/fins` の実データで、判定日を数日選び（例: 2026-07-03 と、その約3か月前・6か月前）、`PointInTimeFinancials`（disclosure）経由で、新しい4項目が `None` でない割合を測る。一回限りの確認用の呼び出しで、スクリプトは追加しない（scratchpad で実行）。
- [ ] 結果（日付ごとの取得率と、`None` の主な理由）を `memo/analysis/` に、銘柄を含まない集計だけで記録する。
- [ ] 取得率が低い場合（目安: 過半数が `None`）は、原因（必要な過去の行が足りない、など）を報告して、ユーザーに判断を仰ぐ。実装は変えない。
**検証**: memo に取得率が記録されている。

#### Step 5: 回帰と最終確認
- [ ] スコア・分類・`candidates`・`classification_counts` が変わらないことを確認する回帰テスト（新しい項目の追加前後の出力の比較。REQ-050 のテストと同じ方式。既存のテストがあれば拡張する）。
- [ ] `validate_report`、forward の loader、learning の loader が、新しい項目がある snapshot と、ない snapshot の両方を読めることを確認する（既存のテストを拡張）。
- [ ] ruff、mypy（CI の対象のファイル）、`pytest tests/ -q`（カバレッジ 80% 以上）。
**検証**: 完了条件の全項目。

### 例外・エラーハンドリング方針
- 足の除去で DataFrame の index が日付に変換できない場合は、その銘柄を除去の対象にせず、従来どおり扱う（除去は最新日付の判定を緩めるものではなく、期待日より後の足だけを捨てる）。
- 四半期・業種の特徴量は、計算できなければ `None` を返す。例外で scan を止めない（日次 scan を、診断用の特徴量の失敗で止めてはならない）。
- 日付と件数だけをログと通知に出す。銘柄名は出さない（公開リポジトリのログ）。

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/test_inflection_live.py tests/test_shadow_health.py -q`（対象）、最後に `.venv/bin/python -m pytest tests/ -q`（全体。メモリのため、他の重い処理を動かさない）。`ruff check src scripts tests`、CI と同じ対象の `mypy --ignore-missing-imports`。
- 受入条件を満たすテストが、実装の誤りを検出できることを、一時的にバグを入れて確認する（例: 除去を `<=` から `<` に変える、四半期の差分を累計のままにする、業種の中央値を平均にする）。
- 手動確認観点: Slack の失敗通知の本文の組み立て（workflow の1行）。ローカルでは `GITHUB_OUTPUT` に書かれるキーを確認する。

### リスクと対策
1. リスク: 期待日より後の足を捨てると、本来は有効な最新の足まで捨てる → 対策: 期待日は「確定しているはずの最新の営業日」で、`expected_tse_session_date` は祝日・場中・場外を処理済み。場中に起動した場合は、期待日が前営業日になり、当日の場中の足を捨てるのが正しい。テストで、期待日以前の足の値が変わらないことを確認する。
2. リスク: 10-05 の失敗の原因が仮説と違う（配信遅れなど）と、REQ-052 の除去では防げない → 対策: 最新日付の分布を失敗通知に出すので、次に失敗したときに原因が分かる。それを見て、再試行の待ち時間などを別の要件で見直す。
3. リスク: 四半期の単独の値の計算が、決算の訂正・会計年度の変更・連結と単体の混在で誤る → 対策: 同じ `CurFYEn`・`CurPerType` の行は新しい開示を使い、`DocType` の系統を揃え、期間の長さが合わない行を使わない。条件が揃わなければ `None`。実データで取得率を確認する。
4. リスク: 新しい項目が既存の snapshot の読み込み（forward、learning、`validate_report`）を壊す → 対策: 既存のテストの拡張で、項目がある場合とない場合の両方を確認する。
5. リスク: 業種の銘柄数が少ないとノイズになる → 対策: 5銘柄未満は `None`。閾値は記録のみの診断なので、変更しても過去の snapshot に影響しない。

### 完了条件
- [ ] REQ-052 の受入条件 1〜5 が、テストで確認されている
- [ ] REQ-053 の受入条件 1〜6 が、テスト（1〜5）と実データの測定（6）で確認されている
- [ ] REQ-054 の受入条件 1〜5 が、テストで確認されている
- [ ] スコア、分類、`candidates`、`classification_counts` が変わらない
- [ ] `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）が変わっていない
- [ ] ruff、mypy、`pytest tests/ -q` が PASS（カバレッジ 80% 以上）
- [ ] Slack の失敗通知の本文に、最新日付の分布が加わっている
