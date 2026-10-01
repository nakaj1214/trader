# snapshot schema 5 実装計画レビュー

レビュー日: 2026-10-01

対象: [plan.md](plan.md)（REQ-037 / REQ-038）。要件書と現在の scanner・loader・保存処理・関連テストを照合した。実装およびテスト実行は行っていない。

## 結論

VERDICT: PASS

更新された計画を再確認し、前回の指摘3件はすべて解消された。追加の指摘はない。これは実装計画のレビュー結果であり、実装・テストの合格判定ではない。

- Step 5 / Step 6: `pre_score` の検査条件が一致し、対照群にも candidate と同じ行検査を適用する計画になった。
- Step 3 / Step 7: 0件指定を許可し、既存の価格取得テストで対照群を無効化する更新が明記された。
- Step 1 / Step 7: 変更前の schema 4 signal 全体を期待値として固定し、変更後の単独・混在読み込みを検証する計画になった。

## 前回の指摘（今回の更新ですべて解消）

以下は前回レビュー時の記録。現在の計画に対する未解決の指摘ではない。

### 1. P2: 保存前の検査が読み込み時の検査・対照群の保存形式と一致していない

対象: [plan.md:61](plan.md#L61)、[plan.md:67–73](plan.md#L67-L73)（Step 5 / Step 6）。

Step 5 は `pre_score` に有限の数値を要求する一方、Step 6 は単に数値であることしか要求していない。例えば `float("nan")` は数値型の検査を通り、既存の `encrypt_json()` も Python の標準設定で NaN をシリアライズできるため、保存に成功してから learning loader が拒否する不整合が残る。`bool` も `int` の派生型なので、数値検査では明示的に除外する必要がある。

また、対照群は candidate と同じ形式で保存する要件だが、Step 6 の各行の検査は `features` の存在だけである。`features=None`、`score_details` / `pre_score` の欠落、空 ticker の行でも、件数・重複の条件を満たせば保存を許す計画になっている。対照群は今回 loader が読まないため、後段にも検出箇所がない。

**修正**: candidates と control_sample の両方で、行が dict、ticker が非空、`features` / `score_details` が dict、`pre_score` が bool を除く有限の数値であることを保存前に検査する。learning 側の `pre_score` の条件も同じにする。既存の `test_shadow_health.py` に非有限値・bool、および対照群の不正行の拒否テストを追加する。

### 2. P2: 既存の価格再試行テストが対照群の既定値によって失敗する

対象: [plan.md:45](plan.md#L45)、[plan.md:76](plan.md#L76)（Step 3 / Step 7）。

現在の `FakeJQuantsClient.financial_summary()` は `code == "11110"` のみを許す。一方、次の既存テストは複数銘柄を用意し、`deep_candidates=0` によって財務取得を避けている。

- `test_scan_retries_only_stale_tickers_and_recovers`
- `test_scan_retries_missing_tickers_when_price_coverage_is_low`
- `test_scan_recovers_on_second_retry`

既定の対照群25件を導入すると、これらのテストでも `22220` などの財務を取得し、fake client の assert で失敗する。Step 7 にある schema アサーションの更新と新規テストの追加だけでは既存テストを維持できない。

**修正**: 価格取得・coverage の既存テストには `control_sample_size=0` を指定する更新を明記する。対照群専用テストでは複数銘柄に対応した fake client を使う。0件指定を許容し、財務取得が増えないことも確認する。

### 3. P2: 受入条件3bのテストが「変更前後で同じ」を検証していない

対象: [plan.md:77](plan.md#L77)（Step 7、REQ-037 受入条件3b）。

提案されたテストは、変更後の loader を単独・混在の2通りで呼び出して比較するもの。schema 4 の読み込み内容が変更前から変わっていても、両方に同じ変更が適用されれば PASS するため、受入条件の「変更の前後で同じ内容」は保証できない。

既存の `test_load_inflection_signals_accepts_v3_schema4_snapshot` は strategy・schema・score の3項目だけを検査しており、schema 4 の signal 全体を固定するテストにもなっていない。

**修正**: schema 4 の固定入力に対して、現在の loader が返す signal 全体を期待値として既存テストに明記する。その期待値に、変更後の単独読み込みと混在読み込みの両方が一致することを確認する。
