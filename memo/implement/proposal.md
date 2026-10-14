# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-14
> 対象: ISSUE-07（learning の超過収益だけ、ベンチマークのコストが 0.2% で他は 0.05%）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）
> 前の要件書: ISSUE-01〜06（REQ-071〜076）は実装済み。ISSUE-04・06 と通知の警告は未コミット。

---

## 診断結果

### 確認した現象

- learning の超過収益は、ベンチマーク（1306.T）の往復コストを 0.2% で計算する。forward・historical は 0.05%（`BENCHMARK_ROUND_TRIP_COST_PCT`）で、文書（project-overview）にも 0.05% と記載されている。
- 同じ取引で結論が逆になる実測（synthetic。株が 1.00%/日、ベンチマークが 0.98%/日で 5 営業日保有）:
  - 取引の純損益: 3.8604%。
  - learning: ベンチマーク 3.778%、超過 **+0.0824**（勝ち）。
  - forward: ベンチマーク 3.928%、超過 **−0.0676**（負け）。

### 根本原因

[evaluate_learning_observations](../../src/evaluation/inflection_learning.py#L340-L344) が、取引用の `round_trip_cost_pct`（既定 0.2%）を、ベンチマークの比較（`paired_benchmark_returns`）にもそのまま渡している。forward は 9/10 の時点でベンチマーク専用の定数（0.05%）を持ち、レポートにも `"benchmark": 0.05` を出力していた。learning は 9/14 の最初のコミットから取引用のコストを流用しており、別にした理由の記録は履歴にも文書にも無い。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. 意図しない不一致 | 確認 | git 履歴（forward は専用定数が先、learning は流用で導入）。意図を示す記録なし。 |
| 2. 意図した差 | 棄却 | 同上。文書は 0.05% と明記。 |
| 3. 影響の大きさ | 確認 | 同じ取引で超過収益が 0.15pt ずれ、境界付近では勝ち/負けが逆になる。超過収益は外れ率（[inflection_learning.py:443](../../src/evaluation/inflection_learning.py#L443)）、`prediction_miss_reasons`（[同:288](../../src/evaluation/inflection_learning.py#L288)）、昇格判定の平均超過収益の符号に使われる。 |

---

## 修正要件

### REQ-077: learning のベンチマーク往復コストを、forward・historical と同じ定数にする（ISSUE-07）

- **画面**: 自己学習（`scripts/rebuild_inflection_learning.py`、`evaluate_learning_observations`）
- **対象ファイル**: [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py)（`evaluate_learning_observations`）、`tests/test_inflection_learning.py`
- **Before（現状）**: ベンチマーク側のコストに、取引用の `round_trip_cost_pct`（既定 0.2%）を使う。
- **After（期待）**:
  - ベンチマーク側の往復コストは、`BENCHMARK_ROUND_TRIP_COST_PCT`（0.05%）を常に使う。取引側のコスト（`round_trip_cost_pct`、既定 0.2%）は変えない。
  - forward のレポートと同様に、「ベンチマークのコストは取引のコスト設定によらず固定」とする。
  - 同じ取引は、learning と forward で超過収益の定義が一致する。
- **修正方針**:
  - `inflection_learning.py` で `BENCHMARK_ROUND_TRIP_COST_PCT` を `src.evaluation.inflection_report` から import する（循環なし。report は learning を import しない）。
  - `paired_benchmark_returns(..., round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT)` に変更する。
  - 取引側の計算、`ROUND_TRIP_COST_PCT`（0.2%）、爆発判定、昇格の閾値・統計は変更しない。
  - 学習レポートの `limitations` に、ベンチマークのコスト（0.05%）を 1 行で明記する。
- **受入条件**:
  1. 上記 synthetic で、learning の超過収益が forward と一致する（ベンチマーク 3.928%、超過 −0.0676）。修正前に失敗する回帰テストとして追加する。
  2. 取引側のコスト（引数 `round_trip_cost_pct`）を変えても、ベンチマーク側は 0.05% のまま。
  3. 取引の純損益、爆発判定、`explosive` は不変。
  4. 既存テストが無変更で PASS（超過収益を固定していたテストが無い想定。ある場合は意図を確認して報告する）。
  5. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: baseline-changing。learning の超過収益が一律に 0.15pt 下がる（ベンチマーク側が 0.15pt 増える）。外れ率（超過 ≤ 0）、`prediction_miss_reasons`、昇格判定の平均超過収益が変わり得る。実 snapshot は暗号化されており検証できない（鍵なし）ため、影響は synthetic で示す。

---

## 次の手順

- 修正は Phase 5 で実施する。原因は確定済み。
- 続けて ISSUE-08（失敗通知ジョブの依存前提）に進む。
