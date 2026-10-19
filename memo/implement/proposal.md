# 修正要件書: 比較不能・未評価の扱い（D1〜D3、Claude が設計・判断）

> 日時: 2026-10-19 / 出典: Codex 独立監査 #1・#2、Claude 再調査 2-1（[設計依頼](codex-design-request-2026-10-16.md)）。判断はユーザー委任（2026-10-19）。

## 判断

| 項目 | 採用 | 理由 |
|---|---|---|
| D1 ETF の日付ずれ | 銘柄の実 entry/exit 日と ETF の日付が**完全一致**しなければ比較不能（`excess=None`）。代用しない。 | 期間が違う値を確定するより「不明」が安全。拒否（実行停止）は全体を止めるので不採用。3 経路と市場別ベンチマークは共有関数なので同じ規則になる。 |
| D2 ETF 比較不能 | 成熟した独立取引で、銘柄は評価済みなのに超過収益が不明なものを `unresolved_matured` に加算。 | 銘柄側の未評価と同じ「落ちた結果」。別の数え方は不要。 |
| D3 kill criterion | 未解決があるときは原則 `incomplete`。`pass` だけは、各未解決を**証明できる下限**（銘柄側: 銘柄 −100%−コスト、ベンチマーク側: 窓内の ETF 最高終値）に置いても CI 下限>0 なら確定。未解決は**実際のシグナル日**の同日クラスタに入れる。`fail` は確定しない（上限が無いため）。ベンチマーク側の未解決は下限が無いので常に `incomplete`。`sensitivity.worst_ci95` を出す。 | 「−100%・観測最大」は超過収益の真の上下限ではなく、架空の別日は相関を落として誤合格する（review.md 2026-10-19 指摘1・2）。新しい閾値は無い。 |
| D3 learning | 変更しない（成熟した未評価があれば当該 horizon の昇格を保留）。 | 昇格は提案で、誤昇格を避ける方を優先。件数は coverage に既出。h60/h120 は保留が多い前提で運用する。 |

## 変更点
- [src/evaluation/inflection_forward.py](../../src/evaluation/inflection_forward.py) `paired_benchmark_returns`: 日付完全一致を要求。
- [src/evaluation/inflection_historical.py](../../src/evaluation/inflection_historical.py) `unresolved_matured_h60`・`kill_criterion`。キー `sensitivity` を追加（追加のみ）。
- テスト: `tests/test_inflection_historical.py`（ETF 日欠測、ETF 70 営業日で終了、判定が生き残る/覆る）。

## baseline への影響
ETF に欠測が無ければ数値は不変。欠測がある取引は超過収益が `None` になる（baseline-changing の可能性、実データ未測定）。

## 未確認
実データ（暗号化 snapshot・実 ETF 欠測の頻度）。ベンチマーク側の未解決と窓が揃わない銘柄側は下限が無く、保留が増える（安全側）。
