# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-14
> 対象: ISSUE-02（成熟した未評価取引が kill criterion の判定から落ちる、C04 の残存）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）、[Codex 最終監査](../../.harness/reports/reliability-final-audit-2026-10-13.md)
> 前の要件書: ISSUE-01（REQ-071、historical の市場カレンダー）は実装済み。

---

## 診断結果

### 確認した現象

- historical の kill criterion が、成熟した未評価の取引が残っているのに `pass` になる。
- synthetic（140 営業日、信号3件）での再現:
  - 1111.T・2222.T は完了してベンチマークを上回る。3333.T は価格系列が25営業日で途切れ、h60 は成熟しているが評価できない。
  - h60 summary: signals 3 / completed 2 / unevaluated 1（`price_unavailable`）。
  - kill_criterion: `verdict=pass`、`independent_trades=2`、`valid_pairs=2`、`ci95=[54.75, 55.32]`。未評価の1件は件数にも理由にも現れない。

### 根本原因

`h60_excess_pairs` は、h60 の取引を `select_non_overlapping_trades` に通してから超過収益を組にする。この関数は `exit_date` の無い取引（未評価）を落とす（[inflection_backtest.py:416-435](../../src/evaluation/inflection_backtest.py#L416-L435)）。そのため `kill_criterion` に渡る組は完了分だけで、成熟した未評価が何件あっても件数が分からず、完了分だけで `pass` / `fail` を決める。

learning は同じ状況（`horizon_matured` が True で未完了）を `unresolved_matured` として数え、昇格を保留する（[inflection_learning.py:734-738](../../src/evaluation/inflection_learning.py#L734-L738)）。historical だけ判定が甘く、評価を楽観方向へ歪め得る。

該当箇所: [h60_excess_pairs](../../src/evaluation/inflection_historical.py#L470-L490)、[kill_criterion](../../src/evaluation/inflection_historical.py#L495-L521)、[_lag_report の呼出し](../../src/evaluation/inflection_historical.py#L645)。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. kill criterion に成熟未評価の件数が渡っていない | 確認 | 上記 synthetic で `pass`・`independent_trades=2`。未評価1件は判定に現れない。 |
| 2. 「保留すべき条件」の定義が曖昧 | 棄却 | 条件は `horizon_matured is True` かつ純損益なし（learning の `unresolved_matured` と同一）。信号が新しい未成熟（`right_censored`、`matured=False`）は含まれない。価格が全く無い取引（`entry_price_unavailable`、`matured=True`）は含まれ、learning と一致する。 |
| 3. 新しい verdict を足すと他の機能が壊れる | 棄却 | verdict を読むのはログ出力（[inflection_historical.py:692](../../src/evaluation/inflection_historical.py#L692)）と実行スクリプトの出力（[run_inflection_historical_backtest.py:160](../../scripts/run_inflection_historical_backtest.py#L160)）だけ。値は文字列のまま扱われる。 |

補足: `lag_comparison` も同じ組を使うが、verdict を出さず差の統計だけを出すため、本要件の対象外とする。

---

## 修正要件

### REQ-072: 成熟した未評価取引がある間は kill criterion の判定を保留する（ISSUE-02 / C04）

- **画面**: historical backtest（`scripts/run_inflection_historical_backtest.py`、`build_backtest_report` の `kill_criterion`）
- **対象ファイル**: [src/evaluation/inflection_historical.py](../../src/evaluation/inflection_historical.py)（`h60_excess_pairs`、`kill_criterion`、`_lag_report`、`build_backtest_report`）、`tests/test_inflection_historical.py`
- **Before（現状）**: kill criterion は完了した取引の組だけで `pass` / `fail` / `insufficient_sample` を決める。成熟した未評価の取引は件数にも判定にも現れない。
- **After（期待）**:
  - h60 の成熟した未評価取引（`horizon_matured is True` かつ純損益なし）を数え、1件以上あれば verdict を `incomplete`（reason `matured_unresolved_outcomes`）にする。`pass` / `fail` のどちらも出さない。
  - kill_criterion の結果に `unresolved_matured`（件数）を常に含める（0件でも）。
  - 成熟した未評価が0件のとき、判定・数値は修正前と完全に一致する。
  - 未成熟（`right_censored`）の未評価は件数に含めず、保留しない。
- **修正方針**:
  - `h60_excess_pairs` を、組のリストに加えて成熟した未評価の件数も返す形にするか、件数だけを返す小さな関数を追加する（既存の呼出し・テストの互換を保つ）。集計の対象は、重複除去前の h60 取引（`simulate_signals` の結果）。
  - `kill_criterion` に `unresolved_matured: int = 0` を追加する。検査の順序は、(1) 未評価が1件以上なら `incomplete`、(2) 有効な組が `min_independent` 未満なら `insufficient_sample`、(3) CI が作れなければ `insufficient_sample`、(4) それ以外は `pass` / `fail`。
  - `_lag_report` が件数を `kill_criterion` に渡す。`lag_comparison` と `pairs_by_lag` の形は変えない。
  - 保留の定義は learning の `_outcome_coverage` と同じ（`horizon_matured is True` かつ未完了）。
  - 本番既定の `DEFAULT_MIN_INDEPENDENT`（100）や、スコア・閾値は変更しない。
- **受入条件**:
  1. 上記 synthetic（完了2件＋成熟した未評価1件、`min_independent=2`）で verdict が `incomplete`、`unresolved_matured=1`。修正前に失敗する回帰テストとして追加する。
  2. 未成熟の未評価（信号が新しい）では保留せず、従来どおり `pass` / `fail` / `insufficient_sample` になる。
  3. 未評価0件の既存ケース（既存の kill criterion テスト）が無変更で PASS し、結果が完全一致する。
  4. 実キャッシュ（読み取りのみ）の比較で、`unresolved_matured` の実数を記録する。0件なら修正前後のレポートが完全一致し、1件以上なら `incomplete` になることを baseline-changing として記録する。
  5. 全テスト・ruff・mypy（既知 31 件のみ）が通る。

---

## 次の手順

- 修正は Phase 5 で実施する。原因は確定済み。
- 続けて ISSUE-05（エントリー日のずれ）に進む。同じ historical・共通評価の経路に関わる。
