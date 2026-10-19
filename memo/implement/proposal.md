# 修正要件書: 比較不能・未評価の扱い（D1〜D3、Claude が設計・判断）

> 日時: 2026-10-19 / 出典: Codex 独立監査 #1・#2、Claude 再調査 2-1（[設計依頼](codex-design-request-2026-10-16.md)）。判断はユーザー委任（2026-10-19）。

## 判断

| 項目 | 採用 | 理由 |
|---|---|---|
| D1 ETF の日付ずれ | 銘柄の実 entry/exit 日と ETF の日付が**完全一致**しなければ比較不能（`excess=None`）。代用しない。 | 期間が違う値を確定するより「不明」が安全。拒否（実行停止）は全体を止めるので不採用。3 経路と市場別ベンチマークは共有関数なので同じ規則になる。 |
| D2 ETF 比較不能 | 成熟した独立取引で、銘柄は評価済みなのに超過収益が不明なものを `unresolved_matured` に加算。 | 銘柄側の未評価と同じ「落ちた結果」。別の数え方は不要。 |
| D3 kill criterion | 未解決があるときは、`pass` は各未解決を**証明できる下限**に置いても CI 下限>0 のとき、`fail` は各未解決を**無限大の利得**に置いても CI 下限≤0 のときだけ確定（bootstrap の下限は未知値について単調なので、両端で決まる）。それ以外は `incomplete`。未解決は実シグナル日のクラスタに入れ、**1 銘柄 1 ポジション**（有効組と同じ独立取引）で数える。下限は ETF の entry 日 Open と必要な全営業日（独立した市場カレンダー）の有効 Close が揃うときだけ。`sensitivity` に `worst_ci95`・`ceiling_ci95`。 | review.md と Codex 検証（P2 指摘 1・3）への対応。新しい閾値は無い。 |
| D3 learning | 成熟した未評価に加え、評価済みだが ETF と比較できない結果（`benchmark_unpaired`）も当該 horizon の昇格を保留（Codex 指摘 2）。 | 昇格は提案で、誤昇格を避ける方を優先。件数は coverage に既出。h60/h120 は保留が多い前提で運用する。 |

## 変更点
- [src/evaluation/inflection_forward.py](../../src/evaluation/inflection_forward.py) `paired_benchmark_returns`: 日付完全一致を要求。
- [src/evaluation/inflection_historical.py](../../src/evaluation/inflection_historical.py) `unresolved_matured_h60`・`kill_criterion`。キー `sensitivity` を追加（追加のみ）。
- テスト: `tests/test_inflection_historical.py`（ETF 日欠測、ETF 70 営業日で終了、判定が生き残る/覆る）。

## baseline への影響
ETF に欠測が無ければ数値は不変。欠測がある取引は超過収益が `None` になる（baseline-changing の可能性、実データ未測定）。

## 未確認
実データ（暗号化 snapshot・実 ETF 欠測の頻度）。ベンチマーク側の未解決と窓が揃わない銘柄側は下限が無く、保留が増える（安全側）。
