# 実装要件書（REQ-037〜038: snapshot schema 5）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の A2・B2（propose-one で選択）。
> 以前の要件書（REQ-001〜036）は [proposal_req001-036.md](proposal_req001-036.md) に移した。

## 背景

日次の shadow scan は snapshot に分類・スコア・価格系の指標・`reasons` 文字列しか保存していない。そのため、自己学習と REQ-020/022 で必要な財務の数値特徴量、スコア内訳、開示日を後から分析できない。これらの値は point-in-time で再現できないため、保存しなかった日の分は失われる。

また、`WATCH` / `NONE` もモメンタム上位25銘柄の中での分類なので、「普通の銘柄と比べてどうか」を測る対照群がない。

両方とも snapshot schema の変更なので、**1回の schema 変更（4 → 5）にまとめる**。

## 共通の設計判断

- `REPORT_SCHEMA_VERSION`: 4 → **5**
- `STRATEGY_VERSION`: **`jp-inflection-shadow-v3` のまま据え置く**。スコア計算・分類・候補選定は一切変えず、保存する項目だけを増やす。保存先も `dashboard/data/inflection/v3/` のままとする。（2026-10-01 ユーザー確認済み: 条件は「v3 の蓄積データが無駄にならないこと」。v3 を据え置き、schema 4 と 5 を同じ評価系列として読むことでこれを満たす。v4 に上げると v3 の forward 評価系列が分断されるため採らない）
- 既存の schema 4 の snapshot は書き換えない。読み込み側が schema 4 と 5 の両方を受け付ける。

---

## 要件一覧

### REQ-037: 候補ごとの生特徴量・スコア内訳・開示日を snapshot に保存する（A2）

- **画面**: なし（日次 scan の出力 snapshot）
- **対象ファイル**:
  - [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`LiveCandidate`、`scan_japan_inflection`、`REPORT_SCHEMA_VERSION`）
  - [src/evaluation/inflection_forward.py](../../src/evaluation/inflection_forward.py)（`load_inflection_signals` の schema 一致検査）
  - [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py)（`SUPPORTED_SCHEMA_VERSIONS`、observation の構築）
  - [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`validate_report`）
  - テスト: `tests/test_inflection_live.py`、`tests/test_inflection_forward.py`、`tests/test_inflection_learning.py`、`tests/test_shadow_health.py`
- **Before（現状）**:
  - `LiveCandidate` が保存するのは、`ticker`、`company_name`、`market`、`classification`、`live_normalized_score`、`raw_inflection_score`、`current_price`、`return_5d/20d/60d_pct`、`volume_ratio_20d`、`near_52w_high`、`near_listing_high`、`avg_turnover_20d_jpy`、`reasons`、`limitations` だけである。
  - `_fundamental_features()` が計算した数値（売上成長率など）と開示日、`score_inflection()` の `details` と小計、一次選別の `_pre_score()` は、計算後に捨てられている。
  - forward loader は、同じディレクトリ内で schema version が混在すると `SnapshotLoadError` で停止する。learning loader は schema 3 と 4 だけを受け付ける。
- **After（期待）**: schema 5 の各 candidate に次のキーを追加する（既存のキーは変更しない）。
  - `features`（dict）: `revenue_growth_yoy_pct`、`operating_profit_growth_yoy_pct`、`operating_margin_change_pctpt`、`turned_profitable`、`upward_revision_pct`、`negative_operating_cashflow`、`latest_actual_disclosure_date`、`latest_disclosure_date`。財務データがない銘柄は数値を `null`、真偽値を `false` とする（`_fundamental_features` が `{}` を返す場合も、キーはすべて出力する）。
  - `score_details`（dict）: `InflectionScore.details` の全キーに加え、`fundamental`、`momentum`、`risk_penalty` の小計。
  - `pre_score`（float）: 一次選別で使った `_pre_score()` の値。
  - `sector33_code` と `sector33_name`（str または null）: J-Quants master の `S33` と `S33Nm`（V2 の公式仕様 https://jpx-jquants.com/ja/spec/eq-master で確認済み）。値が欠損・空文字の場合は null とする。
  - `REPORT_SCHEMA_VERSION = 5`。
  - forward loader: **同じ `strategy_version` の中では schema 4 と 5 の混在を許可する**。strategy の不一致は従来どおり fail closed とする。forward が使う candidate のフィールドは変わらないため、集計結果も変わらない。
  - learning loader: `SUPPORTED_SCHEMA_VERSIONS` に 5 を加える。schema 5 の行は、schema 4 と同じ検査（`near_*` が bool であること）に加えて、`features` と `score_details` が dict であることを検査し、observation に `features`、`score_details`、`pre_score`、`sector33_code` を載せる。schema 3/4 の行ではこれらを `None` とする。
  - `validate_report`: schema 5 のとき、全 candidate が `features`、`score_details`、`pre_score` を持つことを検査する（欠けていれば `DATA_HEALTH` エラー）。
- **受入条件**:
  1. `scan_japan_inflection()` の出力（テスト用の fake client を使う）で、全 candidate に上記キーがあり、`features` の値が `_fundamental_features()` の戻り値と一致する。
  2. 財務データのない銘柄でも `features` の全キーが出力される（数値は null）。
  3. schema 4 と schema 5 の snapshot が同じディレクトリにあっても、`load_inflection_signals` が成功する。strategy_version の不一致は引き続き拒否される。
  3b. 既存の schema 4 snapshot から読み込んだ signal は、変更の前後で同じ内容である（v3 の蓄積データが評価から外れない、または評価内容が変わらないことの回帰テスト）。
  4. learning loader が schema 3、4、5 を読める。schema 5 で `features` が dict でない場合は `SnapshotLoadError` になる。
  5. `validate_report` が、schema 5 で `features` が欠けた candidate を拒否する。
  6. `pytest tests/`、`ruff check src scripts tests`、CI の mypy 対象がすべて PASS する。
- **備考**: snapshot は暗号化されたまま保存し、公開用の集計（`public_learning_summary`、forward の summary）には銘柄単位の新しいフィールドを出さない。

### REQ-038: 流動性フィルタ通過銘柄から無作為抽出した対照群を snapshot に保存する（B2）

- **画面**: なし（日次 scan の出力 snapshot）
- **対象ファイル**:
  - [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`scan_japan_inflection`）
  - [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`validate_report`）
  - テスト: `tests/test_inflection_live.py`、`tests/test_shadow_health.py`
- **Before（現状）**: 財務の評価と分類の対象は、一次選別（`_pre_score` の上位 `deep_candidates=25` 銘柄）だけである。`WATCH` / `NONE` もこの上位プールの中での分類で、プール外の銘柄の特徴量と分類は記録されない。
- **After（期待）**:
  - 流動性フィルタ（`min_turnover_jpy`）を通過した全銘柄から、`control_sample_size`（既定 25）銘柄を無作為に抽出する。deep_candidates との重複も許す（独立抽出）。
  - 乱数 seed は `latest_price_date` から決定的に作る（例: 日付文字列の SHA-256 の先頭8バイト）。同じ日のデータなら、再実行しても同じ銘柄が選ばれる。
  - 抽出した銘柄に、deep_candidates と**同じ処理**（`financial_summary` → `_fundamental_features` → `score_inflection` → `_classify`、REQ-037 の追加フィールドを含む）を行う。deep_candidates と重複する銘柄は、J-Quants を再度呼ばずに計算結果を再利用する。
  - 結果は report の**新しいキー `control_sample`**（candidate と同じ形式の list）に保存する。既存の `candidates` には混ぜない。forward と learning の既存集計には影響させない。
  - report に `control_sample_size`（要求数）と `control_sample_seed` を記録し、`scan_parameters` に `control_sample_size` を加える。
  - 流動性通過銘柄数が `control_sample_size` 未満の場合は、全件を対照群とする。
  - `validate_report`: schema 5 のとき、`control_sample` が list で、件数が `min(control_sample_size, liquid_candidate_count)` と一致し、ticker の重複がないことを検査する。
- **受入条件**:
  1. 同じ価格データと同じ `latest_price_date` で2回 scan すると、`control_sample` の ticker 集合が一致する。日付を変えると（通常は）異なる集合になる。
  2. `control_sample` の全銘柄が流動性フィルタを通過している。
  3. deep_candidates と重複する銘柄について、`financial_summary` が1日に1回しか呼ばれない（fake client の呼び出し回数で検証）。
  4. `candidates`、`deep_candidate_count`、`classification_counts` は REQ-038 の導入前後で変わらない。
  5. `validate_report` が、件数の不一致と ticker の重複を拒否する。
  6. `pytest tests/` などが PASS する。
- **備考**:
  - J-Quants の呼び出しは最大25回増える。`min_interval=12.2` 秒なので約5分である。直近15回の `inflection_shadow.yml` の実行時間は 11.5〜15.3 分（2026-09-10〜09-30、GitHub API で確認）。最悪ケースは「15.3分 + 再試行の待機10分 + 対照群5分 ≒ 31分」で、`timeout-minutes: 45` に収まるため変更しない。
  - 対照群を学習・評価に使う処理（ベースラインの爆発率、lift の再計算）は本要件に含めない（下記「保留中」）。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- （本書の対象外）A3、A8-c、A8-e は 2026-10-01 に直接修正済み。

### 保留中（今回のスコープ外）
- 対照群を使った学習・評価（learning のベースラインを control_sample に置き換える、forward に control グループを追加する）。schema 5 のデータが数週間たまってから別の要件にする。
- 新しい特徴量の追加（20日の最大日次リターン、上昇日比率など。レポート §4.1）。保存項目の追加ではなく、特徴量の新設にあたるため別の要件とする。
- スコア計算の変更（A7 の上方修正の減衰、A8-a、A8-b）。STRATEGY_VERSION の更新を伴う。
- 業種コードを使った業種相対モメンタム（REQ-022）、セクター上限（REQ-014b）。
